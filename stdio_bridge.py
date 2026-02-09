#!/usr/bin/env python3
"""Bridge Claude Desktop (stdio) to remote MCP HTTP server.

Handles the MCP streamable-http protocol which uses SSE for responses
with chunked transfer encoding and session management.

Uses httpx for proper HTTP handling instead of raw sockets.
"""
import os
import sys
import json
import time

import httpx

MCP_SERVER_HOST = os.environ.get("MCP_SERVER_HOST", "192.168.153.8")
MCP_SERVER_PORT = int(os.environ.get("MCP_SERVER_PORT", "8080"))
MCP_BASE_URL = f"http://{MCP_SERVER_HOST}:{MCP_SERVER_PORT}"
MCP_ENDPOINT = "/mcp"
MCP_AUTH_TOKEN = os.environ.get("MCP_AUTH_TOKEN", "")

# Retry configuration
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 1  # seconds
RETRYABLE_EXCEPTIONS = (httpx.ConnectTimeout, httpx.ConnectError, httpx.ReadTimeout)

# Session state - maintained across requests
session_id = None


def log(msg):
    """Log to stderr so it appears in Claude Desktop logs."""
    print(f"[bridge] {msg}", file=sys.stderr, flush=True)


def check_server_health():
    """Verify the MCP server is reachable before processing requests.

    Retries with backoff. Exits the bridge if the server is unreachable
    after all attempts, so Claude Code gets a clear startup failure.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(f"{MCP_BASE_URL}/health")
            if resp.status_code == 200:
                log(f"Server health OK (attempt {attempt})")
                return
            log(f"Health check returned {resp.status_code} (attempt {attempt})")
        except Exception as e:
            log(f"Health check failed (attempt {attempt}/{MAX_RETRIES}): {type(e).__name__}: {e}")
        if attempt < MAX_RETRIES:
            wait = RETRY_BACKOFF_BASE * attempt
            log(f"Retrying health check in {wait}s...")
            time.sleep(wait)

    log("ERROR: MCP server unreachable after all retries — bridge exiting")
    sys.exit(1)


def make_request(data: str, request_id) -> None:
    """Make HTTP request and handle SSE response.

    Retries on transient connection errors (ConnectTimeout, ConnectError,
    ReadTimeout) with exponential backoff.
    """
    global session_id

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }

    if MCP_AUTH_TOKEN:
        headers["Authorization"] = f"Bearer {MCP_AUTH_TOKEN}"

    if session_id:
        headers["Mcp-Session-Id"] = session_id
        log(f"Using session ID: {session_id}")

    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            log(f"Sending request to {MCP_BASE_URL}{MCP_ENDPOINT} (attempt {attempt})")

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

            return  # Success — exit retry loop

        except RETRYABLE_EXCEPTIONS as e:
            last_exc = e
            log(f"Retryable error (attempt {attempt}/{MAX_RETRIES}): {type(e).__name__}: {e}")
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF_BASE * attempt
                log(f"Retrying in {wait}s...")
                time.sleep(wait)

        except Exception as e:
            # Non-retryable error — fail immediately
            log(f"Exception: {type(e).__name__}: {e}")
            err = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32000, "message": f"Bridge connection error: {type(e).__name__}"},
            }
            print(json.dumps(err), flush=True)
            return

    # All retries exhausted
    log(f"All {MAX_RETRIES} retries failed: {type(last_exc).__name__}: {last_exc}")
    err = {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32000, "message": f"Bridge connection error after {MAX_RETRIES} retries: {type(last_exc).__name__}"},
    }
    print(json.dumps(err), flush=True)


log("Bridge starting")

# Verify server is reachable before accepting requests
check_server_health()

if MCP_AUTH_TOKEN:
    log("Auth token configured")
else:
    log("WARNING: No MCP_AUTH_TOKEN set — requests will be unauthenticated")

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
