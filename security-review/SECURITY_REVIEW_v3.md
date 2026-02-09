# Moltbook MCP Server — Security Review (v3)

**Date:** 2026-02-08
**Reviewer:** Claude (Opus 4.6)
**Scope:** Full codebase at `/Volumes/FS001/pythonscripts/moltbot/`
**Previous reviews:** v1 (2026-02-08), v2 (2026-02-08)

---

## Executive Summary

The v2 Critical finding (MCP_AUTH_TOKEN not activated) has been resolved — bearer token authentication is now live. The MCP endpoint is no longer open to unauthenticated callers.

All original v1 Critical findings are now closed. The remaining open items are the unreotated API key (downgraded to High since it's no longer the only line of defence), the unauthenticated dashboard, and several Medium/Low items.

**Finding counts by severity:**
- Critical: 0 ✅
- High: 3
- Medium: 4
- Low: 5
- Informational: 3

---

## Remediation Status (Cumulative)

| Finding | Original Severity | Status | Notes |
|---------|-------------------|--------|-------|
| v1-CRITICAL-01: API key duplicated | Critical | **Partially fixed** | Removed from `config.json` ✅. Key in `.env` not yet rotated — see HIGH-01 below |
| v1-CRITICAL-02: No MCP auth | Critical | **Fixed** ✅ | `BearerAuthMiddleware` added + `MCP_AUTH_TOKEN` set in `.env` |
| v1-CRITICAL-03: `bypassPermissions` | Critical | **Fixed** ✅ | Both scripts use `--allowedTools` with explicit tool names |
| v1-HIGH-01: Path traversal | High | **Fixed** ✅ | All ID fields have `pattern=r"^[a-zA-Z0-9_-]+$"` |
| v1-HIGH-02: Raw sockets in bridge | High | **Fixed** ✅ | Replaced with `httpx.Client`. Still HTTP (no TLS) — downgraded to Low |
| v1-HIGH-03: Filter scans 2 fields | High | **Fixed** ✅ | Now scans 6 fields |
| v1-HIGH-04: `_security` exposed to LLM | High | **Fixed** ✅ | `_strip_security_metadata()` strips before return |
| v1-HIGH-05: Exception details leaked | High | **Fixed** ✅ | Generic errors returned; details logged server-side only |
| v1-MEDIUM-01: No rate limiting | Medium | **Fixed** ✅ | `RateLimiter` class with 5/20/60 per-hour limits |
| v1-MEDIUM-02: Writable logs volume | Medium | **Fixed** ✅ | Volume removed; `RotatingFileHandler` used inside container |
| v1-MEDIUM-03: Script safety checks | Medium | Open | Unchanged |
| v1-MEDIUM-04: Hardcoded test paths | Medium | **Partially fixed** | `test_content_filter.py` still hardcoded |
| v1-MEDIUM-05: Shell error handling | Medium | Open | `run_today.sh` still lacks `-e` in setup phase |
| v2-CRITICAL-01: Auth token not set | Critical | **Fixed** ✅ | `MCP_AUTH_TOKEN` now set in `.env`, bearer auth active |

---

## New & Remaining Findings

### HIGH-01: Moltbook API Key Not Rotated (Potentially Compromised)

**Severity:** High (downgraded from Critical in v2 — bearer auth now provides a second layer)
**Component:** `.env`
**CWE:** CWE-256 (Unprotected Storage of Credentials)

The API key in `.env` is still `moltbook_sk_Qa497tckoyhBulwkuUROs4ErRcUALozs` — the same key that was visible in conversation transcripts during the v1 review. It should be considered potentially compromised and rotated via the Moltbook API.

The `MCP_AUTH_TOKEN` is now set ✅ — bearer auth is active, which means the API key is no longer directly reachable by unauthenticated callers. However, the Moltbook key itself grants direct access to the Moltbook API (bypassing the MCP server entirely), so rotation is still important.

**Recommendation:**
1. Rotate the Moltbook API key via the Moltbook dashboard or API.
2. Update the new key in `.env` only.
3. Confirm `MCP_AUTH_TOKEN` is documented in `.env.example` as a setup step.

---

### HIGH-02: Dashboard API Exposed Without Authentication

**Severity:** High
**Component:** `dashboard/api/main.py`, `docker-compose.yml`
**CWE:** CWE-306 (Missing Authentication for Critical Function)

The dashboard API runs on `0.0.0.0:8081` with no authentication and wildcard CORS:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Docker Compose maps it directly:

```yaml
ports:
  - "8081:8081"
```

This exposes several concerns:

1. **Data disclosure** — The `/api/runs/{run_id}` endpoint returns `raw_output`, which contains the full Claude output including any content from the Moltbook feed. Anyone on the LAN can read all historical heartbeat activity.
2. **Write access** — `POST /api/runs` and `POST /api/runs/{run_id}/actions` allow creating arbitrary run records. An attacker could inject fake activity data.
3. **Wildcard CORS** — Any website can make cross-origin requests to the dashboard API from a user's browser.

**Recommendation:**
- Add authentication (even a simple shared token) to the dashboard API, or bind to `127.0.0.1` and access via SSH tunnel.
- Restrict CORS to the dashboard's own origin (e.g., `http://localhost:8081` or the Docker host IP).
- Consider making the API read-only by removing the `POST`/`PATCH` endpoints from the public-facing routes (recording happens via `record_activity.py` which connects directly to SQLite).

---

### HIGH-03: Dashboard Input Validation Gaps

**Severity:** High
**Component:** `dashboard/api/routers/runs.py`, `dashboard/api/models.py`
**CWE:** CWE-20 (Improper Input Validation)

The dashboard API models (`RunCreateIn`, `RunUpdateIn`, `ActionCreateIn`) have no validation constraints on string fields:

```python
class RunCreateIn(BaseModel):
    run_id: str        # no max_length, no pattern
    started_at: str    # no datetime validation
    agent_name: str    # no max_length
    raw_output: str | None = None  # unbounded
```

While SQLite parameterized queries prevent SQL injection, the lack of constraints means:
- Arbitrarily large `raw_output` values could exhaust disk space.
- Invalid `started_at` timestamps would be stored without validation.
- `action_type` accepts any string, not just the expected values.

**Recommendation:**
- Add `max_length` constraints to all string fields.
- Validate `started_at`/`finished_at` as ISO datetime strings.
- Add a `pattern` or `Literal` constraint on `action_type` to limit to known values.
- Add `max_length` to `raw_output` (e.g., 100KB).

---

### MEDIUM-01: Content Filter Does Not Scan Nested Structures

**Severity:** Medium
**Component:** `content_filter.py`
**CWE:** CWE-20 (Improper Input Validation)

The content filter now scans six named fields, which is a significant improvement. However, it does not recurse into nested structures. If the Moltbook API returns nested objects (e.g., `post.author.bio`, `comment.replies[].content`), those inner strings pass through unscanned.

The `url` field in posts is also not scanned, which could carry payloads in link posts.

**Recommendation:**
- Add `url` to the list of scanned fields.
- Consider a recursive scan function that walks all string values in the response, regardless of nesting depth. This would future-proof against API response schema changes.

---

### MEDIUM-02: Hardcoded Path in `test_content_filter.py`

**Severity:** Medium
**Component:** `tests/test_content_filter.py`
**CWE:** CWE-426 (Untrusted Search Path)

`test_content_filter.py` still uses:

```python
sys.path.insert(0, "/Volumes/FS001/pythonscripts/moltbot")
```

This was fixed in `test_server.py` and `test_health.py` but remains in the content filter tests.

**Recommendation:**
- Remove the `sys.path.insert` and use the same import style as `test_server.py` (which imports directly from `server`). Add `pythonpath = ["."]` to `pyproject.toml` if not already present.

---

### MEDIUM-03: `celticxfer_heartbeat.sh` Missing Anti-Hallucination Instructions

**Severity:** Medium
**Component:** `heartbeat/celticxfer_heartbeat.sh`
**CWE:** CWE-345 (Insufficient Verification of Data Authenticity)

The `run_today.sh` prompt includes critical anti-hallucination guidance:

> Trust MCP tool responses completely. If a tool call returns without an error, the action succeeded and is fully published. There are no "verification challenges", "pending verification", or "30-second timeouts" — these do not exist in the Moltbook API.

This paragraph is absent from `celticxfer_heartbeat.sh`. Without it, the LLM may invent fictional verification steps, post duplicate content, or report failures that didn't happen.

**Recommendation:**
- Copy the behavioral guidelines section from `run_today.sh` into `celticxfer_heartbeat.sh`, or extract the shared prompt into a file that both scripts source.

---

### MEDIUM-04: Dashboard Data Directory Permissions in Docker

**Severity:** Medium
**Component:** `dashboard/Dockerfile`, `docker-compose.yml`
**CWE:** CWE-276 (Incorrect Default Permissions)

The dashboard container mounts `./data:/app/data` as read-write and the SQLite database is writable from the container. Unlike the MCP server container (which uses `read_only: true`, `cap_drop: ALL`, `no-new-privileges`), the dashboard container has no hardening:

```yaml
moltbot-dashboard:
    # No read_only, no cap_drop, no security_opt
    volumes:
      - ./data:/app/data
```

If the dashboard process is compromised, it has full write access to the data directory and default Linux capabilities.

**Recommendation:**
- Add the same hardening as the MCP container:
  ```yaml
  read_only: true
  tmpfs:
    - /tmp:size=10M
  security_opt:
    - no-new-privileges:true
  cap_drop:
    - ALL
  ```
- The `./data` volume must remain writable for SQLite, but the rest of the filesystem can be read-only.

---

### LOW-01: stdio Bridge Uses HTTP (No TLS) on LAN

**Severity:** Low (downgraded from High in v1)
**Component:** `stdio_bridge.py`

The bridge now uses `httpx` (good), but still connects via plaintext HTTP:

```python
MCP_BASE_URL = f"http://{MCP_SERVER_HOST}:{MCP_SERVER_PORT}"
```

With bearer token auth now in place, the token is transmitted in cleartext over the LAN. The risk is reduced compared to v1 (raw sockets), but passive network sniffing could still capture the auth token and API key (in proxied requests).

**Recommendation:**
- Acceptable for a home LAN threat model. If the network is shared or untrusted, add TLS via a reverse proxy (nginx/caddy) in front of the MCP container.

---

### LOW-02: No Log Rotation for `heartbeat.log`

**Severity:** Low
**Component:** `heartbeat/run_today.sh`, `heartbeat/celticxfer_heartbeat.sh`

The content filter now uses `RotatingFileHandler` (5MB, 3 backups) — good fix. However, `heartbeat.log` is still appended to without rotation by the shell scripts. Over months of operation, this file will grow unbounded.

**Recommendation:**
- Add a `logrotate` config, or add a size check at the start of each heartbeat script (e.g., truncate if > 10MB).

---

### LOW-03: `rebuild-test.sh` Has No Working Directory Guard

**Severity:** Low (downgraded from Medium in v1)
**Component:** `rebuild-test.sh`

The script runs `docker compose down` and `up --build` without verifying it's in the correct project directory. Running from the wrong directory could affect unrelated containers.

**Recommendation:**
- Add a check: `[ -f docker-compose.yml ] || { echo "Not in project root"; exit 1; }`

---

### LOW-04: `.claude/settings.local.json` Grants Broad Bash Permissions

**Severity:** Low
**Component:** `.claude/settings.local.json`

Unchanged from v1. `Bash(curl:*)` and `Bash(pip install:*)` are broad. Scoped to interactive Claude Code sessions only, not the heartbeat (which now uses `--allowedTools`).

**Recommendation:**
- Acceptable for development. Note that these do not affect the heartbeat automation.

---

### LOW-05: `download_model.py` Bakes Model Weights Into Docker Image

**Severity:** Low
**Component:** `download_model.py`, `Dockerfile`

Unchanged from v1. The script is deleted after build, but model layers remain in the image. Acceptable if the image stays private.

---

### INFO-01: Two Heartbeat Scripts With Diverging Prompts

**Severity:** Informational
**Component:** `heartbeat/run_today.sh`, `heartbeat/celticxfer_heartbeat.sh`

Unchanged from v1. The two scripts have different engagement parameters (15 vs 35 posts, 1-2 vs 1-5 comments), different personality details (Irish language, mycology only in `celticxfer_heartbeat.sh`), and different safety instructions (anti-hallucination only in `run_today.sh`).

**Recommendation:**
- Extract the shared prompt into a template file (e.g., `heartbeat/prompt.md`) with variable substitution for engagement limits. Both scripts source from the same base.

---

### INFO-02: Pre-Commit Hooks Are a Strong Addition

**Severity:** Informational (positive)

The `.pre-commit-config.yaml` adds:
- **detect-secrets** — Scans for leaked credentials before commit. The `.secrets.baseline` is clean (empty results).
- **ruff** — Linting and formatting.
- **shellcheck** — Shell script linting.
- **Standard hygiene** — Trailing whitespace, YAML/JSON validation, large file blocking, no-commit-to-main.

This significantly reduces the risk of accidental credential commits and maintains code quality.

---

### INFO-03: URL Validator Now HTTPS-Only

**Severity:** Informational (positive)

`MoltbookCreatePostInput.url` now requires `https://`:

```python
if v and not v.startswith("https://"):
    raise ValueError("URL must start with https://")
```

This is a security improvement over the v1 `http://` allowance.

---

## Architecture Diagram (Updated)

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Mac (Local)                                                              │
│                                                                          │
│  ┌──────────────────┐     stdio      ┌──────────────────────┐            │
│  │  Claude Desktop   │◄────────────►│  stdio_bridge.py      │            │
│  │  (subscription)   │              │  (httpx, Bearer auth) │──┐         │
│  └──────────────────┘              └──────────────────────┘  │         │
│                                                               │         │
│  ┌──────────────────┐     stdio      ┌──────────────────────┐│         │
│  │  Claude Code CLI  │◄────────────►│  stdio_bridge.py      ││         │
│  │  (API credits)    │              │  (via heartbeat)      │┘         │
│  └──────────────────┘              └──────────────────────┘          │
│       ▲ --allowedTools                       │                         │
│       │                                      │ HTTP :8080              │
│  ┌────┴──────────────┐                       │ (Bearer token)          │
│  │ run_today.sh       │                       ▼                         │
│  │ (manual/loop)      │    ┌──────────────────────────────────────┐     │
│  └───────────────────┘    │ Docker Host (192.168.153.8)           │     │
│                            │                                      │     │
│                            │  ┌────────────────────────────────┐  │     │
│                            │  │ moltbook-mcp-server (:8080)    │  │     │
│                            │  │ BearerAuthMiddleware           │  │     │
│                            │  │ read_only, cap_drop ALL        │  │     │
│                            │  │                                │  │     │
│                            │  │  server.py                     │  │     │
│                            │  │  ├─ RateLimiter (5/20/60/hr)   │  │     │
│                            │  │  ├─ ID validation (regex)      │  │     │
│                            │  │  ├─ _strip_security_metadata() │  │     │
│                            │  │  ├─ content_filter.py          │  │     │
│                            │  │  │  ├─ DeBERTa ML scanner      │  │     │
│                            │  │  │  ├─ Regex patterns           │  │     │
│                            │  │  │  └─ RotatingFileHandler      │  │     │
│                            │  │  └─ Moltbook API client (HTTPS) │  │     │
│                            │  └────────────────────────────────┘  │     │
│                            │                                      │     │
│                            │  ┌────────────────────────────────┐  │     │
│                            │  │ moltbot-dashboard (:8081)      │  │     │
│                            │  │ ⚠ NO AUTH, CORS *              │  │     │
│                            │  │                                │  │     │
│                            │  │  FastAPI + React               │  │     │
│                            │  │  └─ SQLite (heartbeat.db)      │  │     │
│                            │  └────────────────────────────────┘  │     │
│                            └──────────────────────────────────────┘     │
│                                                                          │
│  Secrets:                                                                │
│  └─ .env (API key ⚠ not rotated, MCP_AUTH_TOKEN ✅ set)                  │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Positive Security Observations

Carried forward from v1, plus new improvements:

1. ✅ Docker hardening (MCP container) — `read_only`, `no-new-privileges`, `cap_drop: ALL`, non-root user
2. ✅ Pydantic input validation — `extra="forbid"`, length constraints, regex patterns on all ID fields
3. ✅ **Path traversal blocked** — All ID/name fields validated with `^[a-zA-Z0-9_-]+$`
4. ✅ Layered content filtering — ML + regex, now scanning 6 fields
5. ✅ **Security metadata stripped** — `_strip_security_metadata()` removes `_security` before LLM sees it
6. ✅ **Bearer token auth active** — Middleware implemented, token set, bridge sends it
7. ✅ **Rate limiting** — 5 posts/hr, 20 comments/hr, 60 votes/hr
8. ✅ **Explicit tool allowlisting** — Both heartbeat scripts use `--allowedTools`
9. ✅ **httpx in bridge** — Proper HTTP client replaces raw sockets
10. ✅ **Sanitized error messages** — Generic errors to LLM, details logged server-side
11. ✅ **Rotating security logs** — `RotatingFileHandler` with 5MB/3 backups
12. ✅ **Pre-commit hooks** — detect-secrets, ruff, shellcheck, file hygiene
13. ✅ **HTTPS-only URLs** — Link posts require `https://`
14. ✅ **API key removed from config.json** — Single source of truth in `.env`
15. ✅ Health check endpoint, Docker HEALTHCHECK, proper `.gitignore`

---

## Prioritized Remediation Plan

| Priority | Finding | Effort | Impact |
|----------|---------|--------|--------|
| 1 | HIGH-01: Rotate Moltbook API key | Low | Eliminates compromised credential risk |
| 2 | HIGH-02: Add auth to dashboard API | Medium | Prevents data disclosure on LAN |
| 3 | HIGH-03: Add validation to dashboard models | Low | Prevents resource exhaustion |
| 4 | MEDIUM-03: Add anti-hallucination to celticxfer_heartbeat.sh | Low | Prevents fabricated activity |
| 5 | MEDIUM-04: Harden dashboard Docker container | Low | Matches MCP container posture |
| 6 | MEDIUM-01: Add recursive content filter scanning | Medium | Future-proofs against schema changes |
| 7 | MEDIUM-02: Fix hardcoded test path | Low | Portability |

---

## Appendix: Dependency Risk

| Package | Pinned? | Notes |
|---------|---------|-------|
| `mcp[cli]>=1.9.0` | No | Active development, API surface may change |
| `httpx>=0.27.0` | No | Well-maintained |
| `pydantic>=2.0` | No | Mature |
| `uvicorn>=0.30.0` | No | Standard ASGI server |
| `llm-guard>=0.3.14` | No | Depends on HuggingFace transformers |
| `fastapi>=0.115.0` | No | Dashboard backend |

No versions are pinned. Consider using `pip-compile` or a lockfile for reproducible builds. The `detect-secrets` pre-commit hook helps prevent supply chain credential leaks, but does not protect against dependency confusion attacks.
