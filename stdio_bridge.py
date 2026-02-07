#!/usr/bin/env python3
"""Bridge Claude Desktop (stdio) to remote MCP HTTP server.

Handles the MCP streamable-http protocol which uses SSE for responses
with chunked transfer encoding and session management.
"""
import sys
import json
import socket

MCP_SERVER_HOST = "192.168.153.8"
MCP_SERVER_PORT = 8080
MCP_ENDPOINT = "/mcp"

# Session state - maintained across requests
session_id = None


def log(msg):
    """Log to stderr so it appears in Claude Desktop logs."""
    print(f"[bridge] {msg}", file=sys.stderr, flush=True)


def read_chunked_response(sock):
    """Read a chunked HTTP response body."""
    body = b""
    while True:
        # Read chunk size line
        size_line = b""
        while not size_line.endswith(b"\r\n"):
            char = sock.recv(1)
            if not char:
                break
            size_line += char

        if not size_line:
            break

        # Parse chunk size (hex)
        try:
            chunk_size = int(size_line.strip(), 16)
        except ValueError:
            log(f"Invalid chunk size: {size_line!r}")
            break

        if chunk_size == 0:
            # Read final CRLF after 0-size chunk
            sock.recv(2)
            break

        # Read chunk data
        chunk = b""
        remaining = chunk_size
        while remaining > 0:
            data = sock.recv(min(remaining, 4096))
            if not data:
                break
            chunk += data
            remaining -= len(data)

        # Read trailing CRLF
        sock.recv(2)
        body += chunk

    return body


def make_request(data: str, request_id) -> None:
    """Make HTTP request and handle SSE response with chunked encoding."""
    global session_id

    try:
        log(f"Connecting to {MCP_SERVER_HOST}:{MCP_SERVER_PORT}")
        sock = socket.create_connection((MCP_SERVER_HOST, MCP_SERVER_PORT), timeout=30)

        # Build headers
        headers = [
            f"POST {MCP_ENDPOINT} HTTP/1.1",
            f"Host: {MCP_SERVER_HOST}:{MCP_SERVER_PORT}",
            "Content-Type: application/json",
            "Accept: application/json, text/event-stream",
            f"Content-Length: {len(data.encode('utf-8'))}",
            "Connection: close",
        ]

        # Include session ID if we have one
        if session_id:
            headers.append(f"Mcp-Session-Id: {session_id}")
            log(f"Using session ID: {session_id}")

        # Build HTTP request
        request = "\r\n".join(headers) + "\r\n\r\n" + data

        log(f"Sending request to {MCP_ENDPOINT}")
        sock.sendall(request.encode("utf-8"))

        # Read response headers
        headers_raw = b""
        while b"\r\n\r\n" not in headers_raw:
            chunk = sock.recv(1)
            if not chunk:
                break
            headers_raw += chunk

        headers_text = headers_raw.decode("utf-8")
        log(f"Response headers:\n{headers_text}")

        # Parse status line
        lines = headers_text.split("\r\n")
        status_line = lines[0]
        status_code = int(status_line.split()[1])
        log(f"Status code: {status_code}")

        # Parse headers
        resp_headers = {}
        for line in lines[1:]:
            if ": " in line:
                key, value = line.split(": ", 1)
                resp_headers[key.lower()] = value

        # Capture session ID from response
        if "mcp-session-id" in resp_headers:
            new_session_id = resp_headers["mcp-session-id"]
            if new_session_id != session_id:
                session_id = new_session_id
                log(f"Captured session ID: {session_id}")

        # Read body
        if resp_headers.get("transfer-encoding", "").lower() == "chunked":
            log("Reading chunked response...")
            body = read_chunked_response(sock)
        elif "content-length" in resp_headers:
            length = int(resp_headers["content-length"])
            body = b""
            while len(body) < length:
                chunk = sock.recv(min(length - len(body), 4096))
                if not chunk:
                    break
                body += chunk
        else:
            # Read until connection closes
            body = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                body += chunk

        sock.close()

        body_text = body.decode("utf-8")
        log(f"Response body length: {len(body_text)}")
        log(f"Response body: {body_text[:500]}")

        if status_code >= 400:
            err = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32000, "message": f"HTTP {status_code}: {body_text}"}
            }
            print(json.dumps(err), flush=True)
            return

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
                "error": {"code": -32000, "message": "Empty response from server"}
            }
            print(json.dumps(err), flush=True)

    except Exception as e:
        log(f"Exception: {type(e).__name__}: {e}")
        err = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32000, "message": str(e)}
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
    except:
        pass

    make_request(line, request_id)

log("Bridge exiting")
