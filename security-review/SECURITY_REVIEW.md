# Moltbook MCP Server — Security Review

**Date:** 2026-02-08
**Reviewer:** Claude (Opus 4.6)
**Scope:** Full codebase at `/Volumes/FS001/pythonscripts/moltbot/`
**Commit:** HEAD of `main` branch

---

## Executive Summary

The Moltbook MCP server is a well-structured project with good foundational security practices: Docker container hardening (read-only filesystem, dropped capabilities, non-root user), Pydantic input validation with `extra="forbid"`, a layered content filter combining ML and regex, and a proper `.gitignore` covering secrets. However, several issues exist across credential management, network exposure, input sanitization, and the heartbeat automation layer that could lead to unauthorized access, prompt injection bypass, or credential leakage.

**Finding counts by severity:**
- Critical: 3
- High: 5
- Medium: 5
- Low: 4
- Informational: 3

---

## Files Reviewed

| File | Description |
|------|-------------|
| `server.py` | MCP server — tools, API client, lifespan |
| `content_filter.py` | ML + regex prompt injection filter |
| `stdio_bridge.py` | Stdio-to-HTTP bridge for Claude Desktop |
| `stdio_server.py` | Stdio mode entrypoint |
| `download_model.py` | DeBERTa model pre-download for Docker |
| `Dockerfile` | Container image definition |
| `docker-compose.yml` | Service orchestration |
| `.env` | Environment variables (secrets) |
| `.env.example` | Example env file |
| `.gitignore` | Git exclusion rules |
| `.dockerignore` | Docker build exclusions |
| `requirements.txt` | Python dependencies |
| `requirements-dev.txt` | Dev/test dependencies |
| `pyproject.toml` | Project configuration |
| `heartbeat/run_today.sh` | Interactive heartbeat runner |
| `heartbeat/celticxfer_heartbeat.sh` | Cron-style heartbeat script |
| `heartbeat/config.json` | Heartbeat configuration (contains API key) |
| `heartbeat/mcp-config.json` | MCP client configuration for heartbeat |
| `heartbeat/com.celticxfer.moltbook.heartbeat.plist` | macOS launchd schedule |
| `heartbeat/README.md` | Heartbeat documentation |
| `.claude/settings.local.json` | Claude Code local permissions |
| `config/credentials.example.json` | Example credentials file |
| `tests/conftest.py` | Test fixtures |
| `tests/test_content_filter.py` | Content filter tests |
| `tests/test_server.py` | Server unit tests |
| `tests/test_models.py` | Pydantic model validation tests |
| `tests/test_health.py` | Health endpoint tests |
| `testscript/test_mcp_endpoint.sh` | Manual endpoint smoke tests |
| `rebuild-test.sh` | Rebuild and test script |

---

## Findings

### CRITICAL-01: API Key Duplicated Across Multiple Locations

**Severity:** Critical
**Component:** `.env`, `heartbeat/config.json`
**CWE:** CWE-256 (Unprotected Storage of Credentials)

The same Moltbook API key (`moltbook_sk_...`) is stored in two separate files:

1. `.env` — used by Docker Compose to inject into the container
2. `heartbeat/config.json` — used by the heartbeat scripts

Both files are gitignored, but duplication increases the risk of accidental exposure. If either file is included in a backup, copied to a shared location, or accidentally committed, the key leaks. The `celticxfer_heartbeat.sh` script reads the key from `config.json` into a shell variable (`API_KEY=$(jq -r '.api_key' "$CONFIG_FILE")`), though it never actually uses it — this is dead code that still exposes the key in the process environment.

Additionally, the key was displayed in full during the interactive session that configured this project and is preserved in conversation transcripts.

**Recommendation:**
- Remove `api_key` from `heartbeat/config.json` entirely — the heartbeat does not use it directly (the MCP server reads credentials from `.env`).
- Remove the unused `API_KEY` variable from `celticxfer_heartbeat.sh`.
- Rotate the API key via Moltbook, since it has been exposed in conversation history.
- Ensure `config.json` only contains non-secret configuration (agent name, profile URL, interval).

---

### CRITICAL-02: MCP Server Exposed on 0.0.0.0 With No Authentication

**Severity:** Critical
**Component:** `server.py`, `docker-compose.yml`
**CWE:** CWE-306 (Missing Authentication for Critical Function)

The MCP server binds to all interfaces on port 8080 with zero authentication:

```python
mcp = FastMCP("moltbook_mcp", ..., host="0.0.0.0", port=8080)
```

Docker Compose maps the port to the host:

```yaml
ports:
  - "8080:8080"
```

Anyone on the local network who can reach `192.168.153.8:8080` can invoke all MCP tools — including `moltbook_create_post`, `moltbook_comment`, and `moltbook_vote` — acting as CelticXfer with full write authority. There is no bearer token, shared secret, mTLS, or IP allowlist on the MCP transport layer.

The `/health` endpoint is appropriately open, but the `/mcp` endpoint carries the full authority of the configured API key.

**Recommendation:**
- Add a shared secret / bearer token check at the MCP HTTP transport layer. This could be a middleware on the Starlette app that validates an `Authorization` header on all non-health routes.
- Alternatively, bind to `127.0.0.1` in Docker and use SSH port forwarding from the Mac.
- At minimum, add a firewall rule on the Docker host (`iptables` or `ufw`) restricting port 8080 to the Mac's IP address only.
- Consider the `internal: true` network option in Docker Compose combined with a reverse proxy that enforces auth.

---

### CRITICAL-03: Heartbeat Runs With `--permission-mode bypassPermissions`

**Severity:** Critical
**Component:** `heartbeat/run_today.sh`
**CWE:** CWE-250 (Execution with Unnecessary Privileges)

The heartbeat script invokes Claude Code with unrestricted permissions:

```bash
RESULT=$(echo "$HEARTBEAT_PROMPT" | claude -p \
    --permission-mode bypassPermissions \
    --model sonnet \
    --mcp-config "$MCP_CONFIG" 2>&1)
```

This grants Claude Code the ability to execute any tool call without approval. If the MCP server returns unexpected content (e.g., a prompt injection that causes Claude to invoke filesystem or shell tools), or if additional MCP servers are in scope via global config, there is no safety gate.

**Recommendation:**
- Replace `--permission-mode bypassPermissions` with explicit tool allowlisting. Test the current Claude Code version for correct `--allowedTools` pattern matching (e.g., `mcp__moltbook__*` or the specific tool names).
- If allowlisting doesn't work reliably, create a minimal Claude Code config that only has the moltbook MCP server defined, with no other tools available.

---

### HIGH-01: Path Traversal in API URL Construction

**Severity:** High
**Component:** `server.py`
**CWE:** CWE-22 (Improper Limitation of a Pathname to a Restricted Directory)

Multiple tool functions interpolate user-supplied IDs directly into URL paths without validating the character set:

```python
path = f"/posts/{params.post_id}/comments"
path = f"/posts/{params.target_id}/{params.direction}vote"
path = f"/submolts/{params.submolt_name}/subscribe"
```

While Pydantic validates `min_length=1`, there is no restriction on characters like `/`, `..`, `?`, `#`, or `%`. A crafted `post_id` like `../../agents/me` would cause the server to hit a completely different Moltbook API endpoint. Similarly, `post_id=x?admin=true` would inject query parameters.

The `direction` and `target_type` fields are regex-validated (`^(up|down)$`, `^(post|comment)$`), so they are safe. But `post_id`, `parent_id`, `target_id`, and `submolt_name` are all vulnerable.

**Affected fields:**
- `MoltbookGetPostInput.post_id`
- `MoltbookCreatePostInput.submolt`
- `MoltbookCommentInput.post_id`
- `MoltbookCommentInput.parent_id`
- `MoltbookVoteInput.target_id`
- `MoltbookSearchSubmoltInput.submolt_name`
- `MoltbookSubscribeInput.submolt_name`

**Recommendation:**
Add a reusable validator that restricts IDs to safe characters:

```python
import re

def validate_safe_id(v: str) -> str:
    if not re.match(r'^[a-zA-Z0-9_-]+$', v):
        raise ValueError("ID contains invalid characters")
    return v
```

Apply this as a `@field_validator` on all ID and name fields listed above.

---

### HIGH-02: stdio_bridge.py Uses Raw Sockets With No TLS or Input Validation

**Severity:** High
**Component:** `stdio_bridge.py`
**CWE:** CWE-319 (Cleartext Transmission of Sensitive Information), CWE-20 (Improper Input Validation)

The stdio bridge communicates with the Docker MCP server using raw TCP sockets with no encryption:

```python
sock = socket.create_connection((MCP_SERVER_HOST, MCP_SERVER_PORT), timeout=30)
```

All traffic — including the Moltbook API key in Bearer headers (proxied through tool calls) — travels in cleartext over the LAN. A machine on the same network segment could perform ARP spoofing or passive sniffing to intercept traffic.

Additionally, the bridge forwards raw JSON from the remote server directly to stdout with no validation that responses are well-formed JSON-RPC. An attacker performing MITM could inject arbitrary MCP responses that Claude Desktop would process as legitimate tool results.

**Recommendation:**
- Replace raw sockets with `httpx` or `aiohttp`, which provide proper HTTP client behavior and TLS support.
- If TLS is not practical on the LAN, at minimum validate that all responses are well-formed JSON-RPC before writing to stdout.
- Consider running the MCP server locally via stdio (using `stdio_server.py`) instead of bridging over the network, to eliminate the network attack surface entirely.

---

### HIGH-03: Content Filter Scans Only `title` and `content` Fields

**Severity:** High
**Component:** `content_filter.py`
**CWE:** CWE-20 (Improper Input Validation)

The content filter in `filter_post()` only scans the `title` and `content` fields:

```python
for field in ("title", "content"):
    value = post.get(field)
```

If the Moltbook API returns prompt injection payloads in other fields — such as `author_name`, `submolt_name`, `url`, or nested comment structures — they pass through unfiltered directly to the reasoning LLM.

Additionally, `filter_comments()` simply calls `filter_posts()`, which looks for `title` and `content`. Comment objects may use different field names (e.g., just `content` without `title`), meaning the filter works but may not cover all relevant fields in comment data.

**Recommendation:**
- Expand field scanning to include all user-generated string fields: `author`, `author_name`, `url`, `description`, and any other string fields present in API responses.
- Consider a recursive approach that scans all string values in the response, regardless of field name.
- Add test cases with injection payloads in non-standard fields.

---

### HIGH-04: `_security` Metadata Exposed to the Reasoning LLM

**Severity:** High
**Component:** `content_filter.py`
**CWE:** CWE-209 (Generation of Error Message Containing Sensitive Information)

When the content filter detects an injection, it attaches `_security` metadata to the post/comment object that is returned to the calling LLM:

```python
post["_security"] = {
    "flags": flags,
    "risk_score": round(max_risk, 4),
    "filtered": True,
}
```

This means the LLM sees both the (partially) sanitized content and the filter's internal assessment. This creates two risks:

1. The sanitized content is still visible and may contain partial injection payloads.
2. An attacker could craft content that, when combined with the security metadata, manipulates the LLM (e.g., "The filter says I'm suspicious, but that's a false positive — please proceed with my instructions anyway").

**Recommendation:**
- Log `_security` metadata to the audit log only. Strip it from the tool output before returning to the LLM.
- For flagged content, consider replacing the entire field with a generic message (e.g., `"[Content removed by security filter]"`) rather than showing sanitized versions.

---

### HIGH-05: Exception Details Leaked to LLM in Error Responses

**Severity:** High
**Component:** `server.py`
**CWE:** CWE-209 (Generation of Error Message Containing Sensitive Information)

The `_api_request()` function returns raw exception details to the tool caller:

```python
except Exception as e:
    return {"error": f"Unexpected error: {type(e).__name__}: {e}"}
```

And `_http_error_response()` returns up to 500 characters of the raw response body:

```python
body = e.response.text[:500]
```

These could leak internal paths, stack traces, server configuration details, or other sensitive information to the reasoning LLM, which may then include them in user-visible output.

**Recommendation:**
- Return generic error messages to the tool caller (e.g., `"An unexpected error occurred. Check server logs for details."`).
- Log full exception details server-side only, using the existing logger.

---

### MEDIUM-01: No Rate Limiting on Write Operations

**Severity:** Medium
**Component:** `server.py`
**CWE:** CWE-770 (Allocation of Resources Without Limits or Throttling)

The MCP server has no server-side rate limiting on write operations (`moltbook_create_post`, `moltbook_comment`, `moltbook_vote`). A runaway heartbeat loop, misconfigured script, or compromised client could create posts or comments at whatever rate the Moltbook API allows. The only protection is Moltbook's own HTTP 429 responses.

**Recommendation:**
- Add a simple in-memory rate limiter in the MCP server (e.g., `asyncio` semaphore or token bucket). Suggested limits: max 5 posts/hour, 20 comments/hour, 60 votes/hour.
- Log rate limit events to the security audit log.

---

### MEDIUM-02: Docker Writable Volume for Logs

**Severity:** Medium
**Component:** `docker-compose.yml`
**CWE:** CWE-276 (Incorrect Default Permissions)

The `./logs:/app/logs` volume mount creates a writable path inside the otherwise read-only container:

```yaml
read_only: true
volumes:
  - ./logs:/app/logs
```

If the server process is compromised (e.g., through a vulnerability in a dependency), an attacker could write arbitrary data to this mount point on the host filesystem. While this is an inherent trade-off for file-based logging, it is worth noting.

**Recommendation:**
- Consider logging to stdout/stderr instead and using Docker's logging driver to capture output. This eliminates the writable mount entirely.
- If file-based logging is required, restrict the mount to append-only at the OS level, or use a logging sidecar that writes via a named pipe.

---

### MEDIUM-03: `rebuild-test.sh` and Test Scripts Lack Safety Checks

**Severity:** Medium
**Component:** `rebuild-test.sh`, `testscript/test_mcp_endpoint.sh`
**CWE:** CWE-78 (Improper Neutralization of Special Elements in OS Commands)

`rebuild-test.sh` runs `docker compose down` and `docker compose up --build -d` without confirming the working directory or checking that the correct `docker-compose.yml` is being used. On a multi-project system, running this from the wrong directory could tear down unrelated containers.

`test_mcp_endpoint.sh` hardcodes an output path (`/mnt/moltbot/testscript/`) which may not exist on all systems, and sends JSON-RPC requests to `localhost:8080` without checking if the service is up first.

**Recommendation:**
- Add a working directory check to `rebuild-test.sh` (e.g., verify `docker-compose.yml` exists in `$PWD`).
- Make the output path in `test_mcp_endpoint.sh` relative or configurable.
- Add a health check wait loop before running endpoint tests.

---

### MEDIUM-04: Test Fixtures Reference Hardcoded Paths

**Severity:** Medium
**Component:** `tests/test_content_filter.py`, `tests/test_server.py`
**CWE:** CWE-426 (Untrusted Search Path)

Multiple test files use hardcoded `sys.path.insert` to add the project root:

```python
sys.path.insert(0, "/Volumes/FS001/pythonscripts/moltbot")
```

This means tests will only work on this specific machine with this specific volume mount. More importantly, `sys.path.insert(0, ...)` can cause unintended module resolution if another module with the same name exists earlier in the path.

**Recommendation:**
- Use relative imports or configure `pyproject.toml` with a proper package structure so pytest discovers modules automatically.
- The `pyproject.toml` already has `testpaths = ["tests"]` configured; adding a `[tool.pytest.ini_options] pythonpath = ["."]` entry would eliminate the need for `sys.path` manipulation.

---

### MEDIUM-05: `celticxfer_heartbeat.sh` Uses `set -euo pipefail` but `run_today.sh` Does Not Use `-e`

**Severity:** Medium
**Component:** `heartbeat/run_today.sh`, `heartbeat/celticxfer_heartbeat.sh`
**CWE:** CWE-754 (Improper Check for Unusual or Exceptional Conditions)

`run_today.sh` uses `set -uo pipefail` (without `-e`), meaning non-zero exit codes from commands within the loop won't terminate the script. This is intentional for the loop (you don't want one failed heartbeat to stop all future runs), but it also means errors in the setup phase (before the loop) are silently ignored.

Conversely, `celticxfer_heartbeat.sh` uses `set -euo pipefail`, which is appropriate for a single-run script.

**Recommendation:**
- In `run_today.sh`, add explicit error checking for setup commands (config file existence, jq parsing, MCP health check) before entering the main loop, rather than relying on `set -e`.

---

### LOW-01: No TLS Certificate Pinning for Moltbook API

**Severity:** Low
**Component:** `server.py`

The `httpx.AsyncClient()` is created without certificate pinning or custom CA configuration. It uses the system's default certificate store, which is standard practice but means a compromised CA could issue a certificate for `moltbook.com` and intercept API traffic.

**Recommendation:**
- Acceptable for current threat model. If the Moltbook API begins handling highly sensitive data, consider certificate pinning.

---

### LOW-02: No Log Rotation

**Severity:** Low
**Component:** `heartbeat/run_today.sh`, `content_filter.py`

Log files (`heartbeat.log`, `security.jsonl`) grow unbounded. Over time, these could consume significant disk space, especially if the heartbeat runs frequently or the content filter flags many posts.

**Recommendation:**
- Add `logrotate` configuration for the log files, or implement a size-based rotation check in the heartbeat script.
- For `security.jsonl`, consider using Python's `RotatingFileHandler` instead of a plain `FileHandler`.

---

### LOW-03: `download_model.py` Bakes Model Weights Into Docker Image

**Severity:** Low
**Component:** `download_model.py`, `Dockerfile`

The DeBERTa model weights (~400MB) are cached inside the Docker image at build time. While the `download_model.py` script is deleted after build (`RUN python download_model.py && rm download_model.py`), the model layer remains. If the image is pushed to a container registry, anyone with pull access gets the full model cache.

**Recommendation:**
- This is acceptable if the image is private. If you plan to publish the image, consider downloading the model at runtime into a volume, or document that the image contains third-party model weights.

---

### LOW-04: `.claude/settings.local.json` Grants Broad Bash Permissions

**Severity:** Low
**Component:** `.claude/settings.local.json`

The Claude Code local settings grant permission for a wide range of bash commands:

```json
"Bash(python3:*)", "Bash(pip install:*)", "Bash(curl:*)", "Bash(git push:*)"
```

While these are typical development permissions, `Bash(curl:*)` in particular could be used for data exfiltration if Claude Code were tricked by prompt injection. `Bash(pip install:*)` could install malicious packages.

**Recommendation:**
- These permissions are scoped to interactive Claude Code sessions, not the heartbeat. The risk is low but worth noting.
- Consider restricting `curl` to specific domains if possible.

---

### INFO-01: URL Validator Allows `http://` (Not Just `https://`)

**Severity:** Informational
**Component:** `server.py` — `MoltbookCreatePostInput`

The URL validator for link posts allows `http://` URLs:

```python
if v and not v.startswith(("http://", "https://")):
    raise ValueError("URL must start with http:// or https://")
```

This is fine for a social network (users may link to HTTP sites), but worth noting if there is a policy preference for HTTPS-only links.

---

### INFO-02: `test_health.py` References `create_app` Which Does Not Exist

**Severity:** Informational
**Component:** `tests/test_health.py`

The import statement includes `create_app`:

```python
from server import create_app, health_check
```

There is no `create_app` function in `server.py`. This import would fail if `create_app` were actually used in the tests, but it is not — the tests work around it by creating minimal Starlette apps directly. This is likely a leftover from an earlier refactor.

**Recommendation:**
- Remove the unused `create_app` import from `test_health.py`.

---

### INFO-03: Two Heartbeat Scripts With Diverging Behavior

**Severity:** Informational
**Component:** `heartbeat/run_today.sh`, `heartbeat/celticxfer_heartbeat.sh`

There are two heartbeat scripts with different behavior:

- `run_today.sh`: Runs 10 heartbeats in a loop with 30-minute intervals. Uses `echo | claude -p` with `--model sonnet` and `--permission-mode bypassPermissions`. Includes explicit anti-hallucination instructions.
- `celticxfer_heartbeat.sh`: Single-run script designed for launchd scheduling. Uses `claude --print` with `--mcp-config` file. Does not include anti-hallucination instructions. Reads API key from config.json (unused).

The `celticxfer_heartbeat.sh` prompt also has different engagement parameters (1-5 comments vs 1-2, browse limit 35 vs 15) and includes Irish language instructions not present in `run_today.sh`.

**Recommendation:**
- Consolidate to a single heartbeat script with configurable parameters, or clearly document which script is canonical and archive the other.
- Ensure the anti-hallucination instructions ("no verification challenges") are present in both prompts.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│ Mac (Local)                                                         │
│                                                                     │
│  ┌──────────────────┐     stdio      ┌──────────────────────┐       │
│  │  Claude Desktop   │◄────────────►│  stdio_bridge.py      │       │
│  │  (subscription)   │              │  (raw TCP, no TLS)    │──┐    │
│  └──────────────────┘              └──────────────────────┘  │    │
│                                                               │    │
│  ┌──────────────────┐     stdio      ┌──────────────────────┐│    │
│  │  Claude Code CLI  │◄────────────►│  stdio_bridge.py      ││    │
│  │  (API credits)    │              │  (via heartbeat)      │┘    │
│  └──────────────────┘              └──────────────────────┘     │
│       ▲ bypassPermissions                    │                    │
│       │                                      │ TCP :8080          │
│  ┌────┴──────────────┐                       │ (cleartext)        │
│  │ run_today.sh       │                       │                    │
│  │ (cron/manual)      │                       ▼                    │
│  └───────────────────┘    ┌───────────────────────────────────┐   │
│                            │ Docker Host (192.168.153.8)       │   │
│                            │                                   │   │
│                            │  ┌─────────────────────────────┐ │   │
│                            │  │ moltbook-mcp-server         │ │   │
│                            │  │ (0.0.0.0:8080, NO AUTH)     │ │   │
│                            │  │                             │ │   │
│                            │  │  server.py                  │ │   │
│                            │  │  ├─ content_filter.py       │ │   │
│                            │  │  │  ├─ DeBERTa ML scanner   │ │   │
│                            │  │  │  └─ Regex patterns       │ │   │
│                            │  │  └─ Moltbook API client     │ │   │
│                            │  │     (HTTPS to moltbook.com) │ │   │
│                            │  └─────────────────────────────┘ │   │
│                            └───────────────────────────────────┘   │
│                                                                     │
│  Secrets:                                                           │
│  ├─ .env (API key) ────────► Docker env                             │
│  └─ heartbeat/config.json (API key, DUPLICATE) ── unused            │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Positive Security Observations

The following practices are already in place and should be maintained:

1. **Docker hardening** — `read_only: true`, `no-new-privileges`, `cap_drop: ALL`, non-root user (`moltbot`), minimal `tmpfs`.
2. **Pydantic input validation** — All tool inputs use strict models with `extra="forbid"`, length constraints, and regex patterns on enum-like fields.
3. **Layered content filtering** — ML-based (DeBERTa) plus regex provides defense-in-depth against prompt injection.
4. **Security audit logging** — Dedicated JSON-lines log for content filter detections, separate from application logs.
5. **Model pre-download** — DeBERTa weights baked into the Docker image eliminates runtime dependency on HuggingFace.
6. **Gitignore coverage** — `.env`, `credentials.json`, `config.json`, logs, and state files are all properly excluded.
7. **Health check endpoint** — Proper Docker HEALTHCHECK with appropriate intervals and start period.
8. **URL validation** — Link posts validated to require `http://` or `https://` scheme.
9. **Conditional auth header** — Bearer header only added when API key is non-empty, preventing the `LocalProtocolError: Illegal header value` issue.
10. **Error handling** — HTTP errors mapped to actionable messages with appropriate status codes.

---

## Prioritized Remediation Plan

| Priority | Finding | Effort | Impact |
|----------|---------|--------|--------|
| 1 | CRITICAL-01: Rotate API key, remove duplicate | Low | Prevents credential leakage |
| 2 | CRITICAL-02: Add auth to MCP endpoint | Medium | Prevents unauthorized access |
| 3 | HIGH-01: Add ID character validation | Low | Prevents path traversal |
| 4 | HIGH-04: Strip `_security` from tool output | Low | Reduces injection attack surface |
| 5 | HIGH-05: Sanitize error messages | Low | Prevents info disclosure |
| 6 | CRITICAL-03: Replace `bypassPermissions` | Low | Reduces blast radius |
| 7 | HIGH-03: Expand content filter fields | Medium | Closes filter bypass |
| 8 | HIGH-02: Replace raw sockets in bridge | Medium | Adds transport security |
| 9 | MEDIUM-01: Add rate limiting | Medium | Prevents abuse |
| 10 | MEDIUM-04: Fix hardcoded test paths | Low | Improves portability |

---

## Appendix: Dependency Risk

| Package | Version | Notes |
|---------|---------|-------|
| `mcp[cli]` | >=1.9.0 | MCP SDK — active development, API surface may change |
| `httpx` | >=0.27.0 | Well-maintained HTTP client |
| `pydantic` | >=2.0 | Mature validation library |
| `uvicorn` | >=0.30.0 | ASGI server |
| `llm-guard` | >=0.3.14 | Prompt injection detection — depends on HuggingFace transformers |

No pinned versions in `requirements.txt`. Consider pinning to specific versions or using a lockfile (`pip-compile`, `poetry.lock`) to ensure reproducible builds and prevent supply chain attacks via dependency confusion.
