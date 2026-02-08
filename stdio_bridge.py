#!/usr/bin/env python3
"""Bridge Claude Desktop (stdio) to remote MCP HTTP server.

Handles the MCP streamable-http protocol which uses SSE for responses
with chunked transfer encoding and session management.

Uses httpx for proper HTTP handling instead of raw sockets.
"""
import os
import sys
import json

import httpx

MCP_SERVER_HOST = os.environ.get("MCP_SERVER_HOST", "192.168.153.8")
MCP_SERVER_PORT = int(os.environ.get("MCP_SERVER_PORT", "8080"))
MCP_BASE_URL = f"http://{MCP_SERVER_HOST}:{MCP_SERVER_PORT}"
MCP_ENDPOINT = "/mcp"
MCP_AUTH_TOKEN = os.environ.get("MCP_AUTH_TOKEN", "")

# Session state - maintained across requests
session_id = None


def log(msg):
    """Log to stderr so it appears in Claude Desktop logs."""
    print(f"[bridge] {msg}", file=sys.stderr, flush=True)


def make_request(data: str, request_id) -> None:
    """Make HTTP request and handle SSE response."""
    global session_id

    try:
        log(f"Sending request to {MCP_BASE_URL}{MCP_ENDPOINT}")

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }

        if MCP_AUTH_TOKEN:
            headers["Authorization"] = f"Bearer {MCP_AUTH_TOKEN}"

        if session_id:
            headers["Mcp-Session-Id"] = session_id
            log(f"Using session ID: {session_id}")

        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{MCP_BASE_URL}{MCP_ENDPOINT}",
                content=data.encode("utf-8"),
                headers=headers,
            )

        log(f"Status code: {response.status_code}")

        # Capture session ID from response
        new_session_id = response.headers.get("mcp-session-id")
        if new_session_id and new_session_id != session_id:
            session_id = new_session_id
            log(f"Captured session ID: {session_id}")

        if response.status_code >= 400:
            err = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32000,
                    "message": f"HTTP {response.status_code}: {response.text[:200]}",
                },
            }
            print(json.dumps(err), flush=True)
            return

        body_text = response.text
        log(f"Response body length: {len(body_text)}")

        if body_text:
            # Handle SSE format
            for line in body_text.strip().split("\n"):
                if line.startswith("data: "):
                    json_data = line[6:]
                    if json_data:
                        log(f"SSE data: {json_data}")
                        print(json_data, flush=True)
                elif line and not line.startswith(":") and not line.startswith("event:"):
                    # Might be plain JSON
                    log(f"Plain line: {line}")
                    print(line, flush=True)
        else:
            log("Empty response body!")
            err = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32000, "message": "Empty response from server"},
            }
            print(json.dumps(err), flush=True)

    except Exception as e:
        log(f"Exception: {type(e).__name__}: {e}")
        err = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32000, "message": f"Bridge connection error: {type(e).__name__}"},
        }
        print(json.dumps(err), flush=True)


log("Bridge starting")

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue

    log(f"Received from client: {line[:200]}")

    # Extract request ID for error responses
    request_id = 0
    try:
        parsed = json.loads(line)
        request_id = parsed.get("id", 0)
    except json.JSONDecodeError:
        pass

    make_request(line, request_id)

log("Bridge exiting")
