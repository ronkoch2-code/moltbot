#!/bin/bash
# Rebuild, restart, and test the MCP server
# Run from project root on the Docker host (with sudo/elevated access)

set -e

# Get script directory and validate environment
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Verify docker-compose.yml exists
if [ ! -f "$SCRIPT_DIR/docker-compose.yml" ]; then
    echo "Error: docker-compose.yml not found in $SCRIPT_DIR"
    exit 1
fi

# Verify docker command exists
if ! command -v docker &> /dev/null; then
    echo "Error: docker not found"
    exit 1
fi

# Change to script directory
cd "$SCRIPT_DIR"

# --- Ensure Docker daemon DNS config exists ---
# Prevents container DNS failures caused by systemd-resolved instability
# during docker compose restarts (iptables changes destabilize the stub resolver)
DAEMON_JSON="/etc/docker/daemon.json"
NEEDS_DOCKER_RESTART=false

if [ ! -f "$DAEMON_JSON" ]; then
    echo "=== Creating Docker daemon DNS config ==="
    cat > "$DAEMON_JSON" <<'DNSJSON'
{
  "dns": ["8.8.8.8", "8.8.4.4"]
}
DNSJSON
    NEEDS_DOCKER_RESTART=true
elif ! grep -q '"dns"' "$DAEMON_JSON" 2>/dev/null; then
    echo "=== WARNING: $DAEMON_JSON exists but has no dns config ==="
    echo "    Add manually: \"dns\": [\"8.8.8.8\", \"8.8.4.4\"]"
fi

if [ "$NEEDS_DOCKER_RESTART" = true ]; then
    echo "=== Restarting Docker daemon for DNS config ==="
    systemctl restart docker
    sleep 3
fi

echo "=== Backing up database ==="
if [ -f "$SCRIPT_DIR/.env" ]; then
    # shellcheck disable=SC1091
    DB_URL=$(grep -E '^DATABASE_URL=' "$SCRIPT_DIR/.env" | cut -d= -f2-)
    if [ -n "$DB_URL" ]; then
        DATABASE_URL="$DB_URL" python3 "$SCRIPT_DIR/scripts/backup_db.py" || echo "WARNING: Database backup failed (continuing with rebuild)"
    else
        echo "WARNING: DATABASE_URL not found in .env, skipping backup"
    fi
else
    echo "WARNING: .env not found, skipping backup"
fi

echo "=== Stopping application containers (preserving PostgreSQL) ==="
# Only stop MCP + dashboard; leave postgres running to preserve data.
# "docker compose down" removes ALL containers including postgres,
# and on some Docker versions may also recreate the named volume.
docker compose stop moltbook-mcp moltbot-dashboard
docker compose rm -f moltbook-mcp moltbot-dashboard

echo "=== Ensuring PostgreSQL is running ==="
# Start postgres if it's not already running (first run or manual stop)
docker compose up -d postgres

MAX_WAIT=60
WAITED=0
until docker exec moltbot-postgres pg_isready -U moltbot > /dev/null 2>&1; do
    if [ $WAITED -ge $MAX_WAIT ]; then
        echo "Error: PostgreSQL did not become healthy within ${MAX_WAIT}s"
        docker compose logs postgres --tail 20
        exit 1
    fi
    sleep 2
    WAITED=$((WAITED + 2))
done
echo "PostgreSQL healthy after ${WAITED}s"

echo "=== Rebuilding application containers ==="
docker compose up --build -d moltbook-mcp moltbot-dashboard

echo "=== Waiting for MCP server ==="
MAX_WAIT=60
WAITED=0
until curl -sf http://localhost:8080/health > /dev/null 2>&1; do
    if [ $WAITED -ge $MAX_WAIT ]; then
        echo "Error: MCP server did not become healthy within ${MAX_WAIT}s"
        docker compose logs moltbook-mcp --tail 20
        exit 1
    fi
    sleep 2
    WAITED=$((WAITED + 2))
done
echo "MCP server healthy after ${WAITED}s"

echo "=== Waiting for Dashboard ==="
WAITED=0
until curl -sf http://localhost:8081/api/health > /dev/null 2>&1; do
    if [ $WAITED -ge $MAX_WAIT ]; then
        echo "Error: Dashboard did not become healthy within ${MAX_WAIT}s"
        docker compose logs moltbot-dashboard --tail 20
        exit 1
    fi
    sleep 2
    WAITED=$((WAITED + 2))
done
echo "Dashboard healthy after ${WAITED}s"

echo "=== Running endpoint tests ==="
# Verify test script exists
if [ ! -f "$SCRIPT_DIR/testscript/test_mcp_endpoint.sh" ]; then
    echo "Error: test_mcp_endpoint.sh not found in $SCRIPT_DIR/testscript/"
    exit 1
fi
"$SCRIPT_DIR/testscript/test_mcp_endpoint.sh"

echo "=== Container status ==="
docker compose ps

echo "=== MCP server logs ==="
docker logs moltbook-mcp-server --tail 10

echo "=== Dashboard logs ==="
docker logs moltbot-dashboard --tail 10

echo "=== Done ==="
