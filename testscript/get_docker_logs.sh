#!/bin/bash
# Get Docker logs to see what's causing the 500 error

OUTPUT_DIR="/mnt/moltbot/testscript"

docker logs moltbook-mcp-server --tail 100 > "$OUTPUT_DIR/docker_logs.log" 2>&1

echo "Docker logs saved to $OUTPUT_DIR/docker_logs.log"
