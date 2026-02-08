#!/bin/bash
# Rebuild, restart, and test the MCP server
# Run from project root on the Docker host

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

echo "=== Stopping containers ==="
docker compose down

echo "=== Rebuilding ==="
docker compose up --build -d

echo "=== Waiting for container to start ==="
MAX_WAIT=30
WAITED=0
until curl -sf http://localhost:8080/health > /dev/null 2>&1; do
    if [ $WAITED -ge $MAX_WAIT ]; then
        echo "Error: Container did not become healthy within ${MAX_WAIT}s"
        docker compose logs --tail 20
        exit 1
    fi
    sleep 2
    WAITED=$((WAITED + 2))
done
echo "Container healthy after ${WAITED}s"

echo "=== Running endpoint tests ==="
# Verify test script exists
if [ ! -f "$SCRIPT_DIR/testscript/test_mcp_endpoint.sh" ]; then
    echo "Error: test_mcp_endpoint.sh not found in $SCRIPT_DIR/testscript/"
    exit 1
fi
"$SCRIPT_DIR/testscript/test_mcp_endpoint.sh"

echo "=== Container status ==="
docker compose ps

echo "=== Recent logs ==="
docker logs moltbook-mcp-server --tail 20

echo "=== Done ==="
