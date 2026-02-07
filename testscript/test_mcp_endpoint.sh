#!/bin/bash
# Run this on the server (192.168.153.8) where Docker is running
# This tests what endpoints the MCP server responds to

OUTPUT_DIR="/mnt/moltbot/testscript"

echo "Testing MCP server endpoints..." > "$OUTPUT_DIR/curl_test.log"
echo "================================" >> "$OUTPUT_DIR/curl_test.log"
echo "" >> "$OUTPUT_DIR/curl_test.log"

echo "Test 1: Health check" >> "$OUTPUT_DIR/curl_test.log"
echo "--------------------" >> "$OUTPUT_DIR/curl_test.log"
curl -s http://localhost:8080/health >> "$OUTPUT_DIR/curl_test.log" 2>&1
echo -e "\n" >> "$OUTPUT_DIR/curl_test.log"

echo "Test 2: POST to root /" >> "$OUTPUT_DIR/curl_test.log"
echo "----------------------" >> "$OUTPUT_DIR/curl_test.log"
curl -v -X POST http://localhost:8080/ \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}' \
  >> "$OUTPUT_DIR/curl_test.log" 2>&1
echo -e "\n" >> "$OUTPUT_DIR/curl_test.log"

echo "Test 3: POST to /mcp" >> "$OUTPUT_DIR/curl_test.log"
echo "--------------------" >> "$OUTPUT_DIR/curl_test.log"
curl -v -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}' \
  >> "$OUTPUT_DIR/curl_test.log" 2>&1
echo -e "\n" >> "$OUTPUT_DIR/curl_test.log"

echo "Test 4: POST to /sse" >> "$OUTPUT_DIR/curl_test.log"
echo "--------------------" >> "$OUTPUT_DIR/curl_test.log"
curl -v -X POST http://localhost:8080/sse \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}' \
  >> "$OUTPUT_DIR/curl_test.log" 2>&1
echo -e "\n" >> "$OUTPUT_DIR/curl_test.log"

echo "Done! Results in $OUTPUT_DIR/curl_test.log"
