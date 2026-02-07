#!/bin/bash
# Rebuild, restart, and test the MCP server
# Run from project root on the Docker host

set -e

echo "=== Stopping containers ==="
docker compose down

echo "=== Rebuilding ==="
docker compose up --build -d

echo "=== Waiting for container to start ==="
sleep 5

echo "=== Running endpoint tests ==="
./testscript/test_mcp_endpoint.sh

echo "=== Container status ==="
docker compose ps

echo "=== Recent logs ==="
docker logs moltbook-mcp-server --tail 20

echo "=== Done ==="
