#!/bin/bash
# Get Docker logs for both MCP server and dashboard containers

OUTPUT_DIR="/mnt/moltbot/testscript"

echo "=== moltbook-mcp-server ===" > "$OUTPUT_DIR/docker_logs.log"
docker logs moltbook-mcp-server --tail 100 >> "$OUTPUT_DIR/docker_logs.log" 2>&1

echo "" >> "$OUTPUT_DIR/docker_logs.log"
echo "=== moltbot-dashboard ===" >> "$OUTPUT_DIR/docker_logs.log"
docker logs moltbot-dashboard --tail 100 >> "$OUTPUT_DIR/docker_logs.log" 2>&1

echo "Docker logs saved to $OUTPUT_DIR/docker_logs.log"
