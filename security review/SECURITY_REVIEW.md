# Moltbot Security Review

**Version:** 4.0
**Date:** 2026-02-09
**Reviewer:** Claude (Anthropic)
**Scope:** Full codebase audit — `/Volumes/FS001/pythonscripts/moltbot/`
**Previous reviews:** v1 (2026-02-08), v2 (2026-02-08), v3 (2026-02-09)

---

## Executive Summary

The Moltbot project is a well-architected MCP server that provides an AI agent (CelticXfer) with sandboxed access to the Moltbook social network. The codebase demonstrates strong security awareness: bearer token authentication protects the MCP endpoint, ML-based prompt injection detection (DeBERTa v3) filters hostile content, Docker containers run as non-root users with dropped capabilities, and a pre-commit pipeline scans for secrets.

However, several issues remain. The most pressing are the **unauthenticated dashboard API** (which exposes full Claude output, prompt text, and security event data to anyone on the LAN), a **PostgreSQL password leaked into version-controllable settings**, and a **Moltbook API key that has been visible in review transcripts since v1 and has never been rotated**. The dashboard container also lacks the security hardening applied to the MCP container.

**Finding summary:**

| Severity | Count |
|----------|-------|
| Critical | 0 |
| High | 4 |
| Medium | 5 |
| Low | 5 |
| Informational | 4 |

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│  macOS Host (Hockessin)                                          │
│                                                                  │
│  ┌──────────────────┐    stdio     ┌──────────────────────────┐  │
│  │ Claude Desktop / │ ──────────── │ stdio_bridge.py          │  │
│  │ Claude Code CLI  │             │ (sends Bearer token)     │  │
│  └──────────────────┘             └───────────┬──────────────┘  │
│                                               │ HTTP :8080       │
│  ┌──────────────────┐                         │                  │
│  │ heartbeat/*.sh   │─── claude --print ──────┤                  │
│  │ (launchd / loop) │                         │                  │
│  └────────┬─────────┘                         │                  │
│           │ python3                            │                  │
│  ┌────────▼─────────┐                         │                  │
│  │ record_activity   │──── PostgreSQL ────┐    │                  │
│  │ collect_mcp_logs  │    :5433           │    │                  │
│  └──────────────────┘                    │    │                  │
│                                          │    │                  │
│  ┌───────────────────────────────────────┼────┼──── Docker ───┐  │
│  │                                       │    │               │  │
│  │  ┌────────────────────────┐           │    │               │  │
│  │  │ moltbook-mcp           │◄──────────┼────┘               │  │
│  │  │ :8080                  │           │                    │  │
│  │  │ BearerAuth ✅ active   │           │                    │  │
│  │  │ read_only ✅           │           │                    │  │
│  │  │ cap_drop: ALL ✅       │           │                    │  │
│  │  │ no-new-privileges ✅   │           │                    │  │
│  │  └────────────────────────┘           │                    │  │
│  │                                       │                    │  │
│  │  ┌────────────────────────┐           │                    │  │
│  │  │ moltbot-dashboard      │◄──────────┘                    │  │
│  │  │ :8081                  │                                │  │
│  │  │ Auth: ⚠ NONE           │                                │  │
│  │  │ CORS: ⚠ wildcard       │                                │  │
│  │  │ read_only: ⚠ not set   │                                │  │
│  │  │ cap_drop: ⚠ not set    │                                │  │
│  │  └────────────────────────┘                                │  │
│  │                                                            │  │
│  │  ┌────────────────────────┐                                │  │
│  │  │ postgres:16-alpine     │                                │  │
│  │  │ :5432 (internal)       │                                │  │
│  │  │ :5433 (host-mapped)    │                                │  │
│  │  └────────────────────────┘                                │  │
│  │                                                            │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

---

## Findings

---

### HIGH-01: Dashboard API Exposed Without Authentication

**Severity:** HIGH
**Component:** `dashboard/api/main.py`, `docker-compose.yml`
**Status:** Open

The dashboard FastAPI application listens on `0.0.0.0:8081` with no authentication and a wildcard CORS policy (`allow_origins=["*"]`). Any device on the local network can:

- **Read full Claude output** via `GET /api/runs/{run_id}` — the `raw_output` field contains everything Claude said and did, including tool call results with Moltbook post content.
- **Read and write agent identity prompts** via `GET/POST /api/prompts` — an attacker could replace the active heartbeat prompt with a malicious one, causing CelticXfer to execute attacker-controlled instructions on the next heartbeat cycle.
- **Read security audit data** via `GET /api/security/events` — exposes injection detection details, risk scores, and flagged content.
- **Write arbitrary run and action records** via `POST /api/runs`, `POST /api/runs/{id}/actions` — can inject false data into the dashboard.

The prompt injection endpoint (`POST /api/prompts`) is particularly dangerous: an attacker who can reach port 8081 can replace CelticXfer's entire personality and behavioral instructions.

**Remediation:**

1. Add API key or session authentication to the dashboard. A simple bearer token (like the MCP server already uses) would suffice.
2. Restrict CORS to known origins (e.g., `http://localhost:8081`, `http://192.168.153.8:8081`).
3. Optionally bind the dashboard to `127.0.0.1` instead of `0.0.0.0` if only local access is needed.

---

### HIGH-02: Moltbook API Key Not Rotated Since Initial Setup

**Severity:** HIGH
**Component:** `.env`
**Status:** Open

The Moltbook API key `moltbook_sk_Qa497tckoyhBulwkuUROs4ErRcUALozs` has been in use since the project's creation and has appeared in plain text in multiple review transcripts (v1, v2, v3) and conversation logs. While the MCP server's bearer authentication now provides a second layer of defense (an attacker would need both the bearer token and the API key to impersonate CelticXfer), the API key itself can still be used directly against the Moltbook API, bypassing the MCP server entirely.

**Remediation:**

1. Rotate the key via the Moltbook dashboard immediately.
2. Update `.env` with the new key.
3. Rebuild/restart the MCP container: `docker compose up -d --build moltbook-mcp`.
4. Verify the new key works: check the next heartbeat run.

---

### HIGH-03: PostgreSQL Password in Version-Controllable File

**Severity:** HIGH
**Component:** `.claude/settings.local.json`
**Status:** Open

The Claude Code local settings file contains the PostgreSQL password in plain text within a bash permission entry:

```
"Bash(DATABASE_URL=\"postgresql://moltbot:zU8Kuy5ZCcFZdlJmVqGm-ovdrAKjziib@localhost:5432/moltbot\" python3 -m pytest:*)"
```

and:

```
"Bash(PGPASSWORD='zU8Kuy5ZCcFZdlJmVqGm-ovdrAKjziib' psql:*)"
```

While `.claude/` is in `.gitignore`, this file lives on the shared volume `/Volumes/FS001` and could be read by any user with access to that filesystem. The same password also appears in `.env` (expected) and is passed to Docker via environment variables (standard practice), but embedding it in a permissions allowlist is an unnecessary additional exposure surface.

**Remediation:**

1. Remove the hardcoded password from `.claude/settings.local.json` by using environment variable references instead of inline credentials in the permission strings.
2. Consider rotating the PostgreSQL password since it has been exposed.

---

### HIGH-04: Dashboard Input Validation Gaps

**Severity:** HIGH
**Component:** `dashboard/api/models.py`
**Status:** Open

The dashboard's Pydantic input models lack field-level constraints, unlike the MCP server's models which are well-validated. This creates several risks:

- **`RunCreateIn` / `RunUpdateIn`**: The `raw_output` field has no `max_length`. A malicious POST to `/api/runs` could send gigabytes of data, exhausting disk and memory. The `run_id`, `started_at`, `agent_name` fields have no length limits or format validation.
- **`ActionCreateIn`**: The `action_type` field accepts any string — no `Literal` constraint to valid values like `"upvoted"`, `"commented"`, `"posted"`, etc.
- **`PromptCreateIn`**: The `prompt_text` field has no `max_length`. Combined with the lack of authentication (HIGH-01), this means anyone can write unlimited data to PostgreSQL.
- **All timestamp fields**: Stored as `TEXT` in PostgreSQL with no format validation — invalid timestamps won't cause errors but will corrupt queries.

**Remediation:**

1. Add `max_length` to all string fields (`raw_output: str | None = Field(default=None, max_length=500_000)`).
2. Add `Literal` constraints to `action_type` and `status` fields.
3. Add `pattern` or custom validators for timestamp fields to enforce ISO 8601.
4. Add `max_length` to `prompt_text` (e.g., 100,000 characters — the current prompt is ~3,500).

---

### MEDIUM-01: Dashboard Docker Container Lacks Security Hardening

**Severity:** MEDIUM
**Component:** `docker-compose.yml`, `dashboard/Dockerfile`
**Status:** Open

The MCP container has excellent security hardening (`read_only: true`, `cap_drop: ALL`, `no-new-privileges`, minimal `tmpfs`). The dashboard container has none of these. While the dashboard has lower risk than the MCP server (it doesn't handle external user content), it still processes data from Claude's output and serves a web application.

**Remediation:**

Add to the `moltbot-dashboard` service in `docker-compose.yml`:

```yaml
read_only: true
tmpfs:
  - /tmp:size=10M
security_opt:
  - no-new-privileges:true
cap_drop:
  - ALL
```

---

### MEDIUM-02: Heartbeat Fallback Prompt Missing Anti-Hallucination Guidelines

**Severity:** MEDIUM
**Component:** `heartbeat/celticxfer_heartbeat.sh`
**Status:** Open

The `run_today.sh` fallback prompt includes the anti-hallucination guideline:

> "Trust MCP tool responses completely. If a tool call returns without an error, the action succeeded and is fully published. There are no 'verification challenges', 'pending verification', or '30-second timeouts' — these do not exist in the Moltbook API."

The `celticxfer_heartbeat.sh` fallback prompt does not include this guideline. If the dashboard is unreachable and the fallback prompt activates, CelticXfer running via the cron variant may hallucinate verification steps that don't exist.

**Remediation:**

Copy the anti-hallucination behavioral guideline from `run_today.sh`'s fallback prompt into `celticxfer_heartbeat.sh`'s fallback prompt.

---

### MEDIUM-03: PostgreSQL Exposed on Host Network

**Severity:** MEDIUM
**Component:** `docker-compose.yml`
**Status:** Open

PostgreSQL is mapped to `0.0.0.0:5433` on the host, making it accessible from any device on the local network. The host-side scripts (`record_activity.py`, `collect_mcp_logs.py`) connect via the `.env`-configured `DATABASE_URL` pointing to `192.168.153.8:5433`.

While the database requires a password, the combination of network exposure and the password being present in multiple files (`.env`, `.claude/settings.local.json`) increases the attack surface.

**Remediation:**

Bind PostgreSQL to localhost only in `docker-compose.yml`:

```yaml
ports:
  - "127.0.0.1:5433:5432"
```

Then update `DATABASE_URL` in `.env` to use `localhost:5433` instead of `192.168.153.8:5433`. If the heartbeat scripts run on a different machine, use an SSH tunnel instead.

---

### MEDIUM-04: Script Comment / Constant Mismatch in `run_today.sh`

**Severity:** MEDIUM (operational, not directly exploitable)
**Component:** `heartbeat/run_today.sh`
**Status:** Open

The script header says "Run heartbeat every 30 minutes" and the status message says "Running every 30 minutes", but `INTERVAL_SECONDS=3600` (60 minutes). The `NEXT_TIME` calculation also uses `+30M`. This mismatch causes confusion about the actual heartbeat frequency and could lead to incorrect monitoring assumptions.

**Remediation:**

Either change `INTERVAL_SECONDS=1800` (for actual 30-minute intervals) or update all comments and messages to say "60 minutes."

---

### MEDIUM-05: No Rate Limiting on Dashboard API Writes

**Severity:** MEDIUM
**Component:** `dashboard/api/routers/runs.py`, `prompts.py`, `actions.py`
**Status:** Open

The dashboard API has no rate limiting on write endpoints (`POST /api/runs`, `POST /api/prompts`, `POST /api/runs/{id}/actions`). Combined with the lack of authentication (HIGH-01), an attacker could flood PostgreSQL with records. The MCP server has a good rate limiter (`RateLimiter` class) — a similar approach could be applied to the dashboard.

**Remediation:**

Add rate limiting middleware to the FastAPI app, or at minimum add rate limits to the `POST` endpoints.

---

### LOW-01: Content Filter Cache Has No TTL

**Severity:** LOW
**Component:** `content_filter.py`
**Status:** Open

The `_scan_cache` (OrderedDict, max 512 entries) has no time-to-live. Cached scan results persist for the lifetime of the process. If the ML model's threshold is changed via environment variable, the cache will still return results computed with the old threshold until the entries are naturally evicted by new content.

**Impact:** Minimal — threshold changes require a container restart anyway, which clears the cache.

**Remediation:** Add a timestamp to cache entries and skip entries older than a configurable TTL, or simply document that threshold changes require a restart.

---

### LOW-02: Rate Limiter State Lost on Container Restart

**Severity:** LOW
**Component:** `server.py` (`RateLimiter` class)
**Status:** Open

The `RateLimiter` uses `time.monotonic()` and in-memory lists. Container restarts reset all counters, allowing a burst of posts/comments immediately after restart. This is acceptable for the current use case (single agent, heartbeat-driven) but would be a concern if multiple agents shared the server.

**Remediation:** Acceptable as-is for the current single-agent architecture. If scaling to multiple agents, move rate limit state to Redis or PostgreSQL.

---

### LOW-03: No TLS Between Bridge and MCP Server

**Severity:** LOW
**Component:** `stdio_bridge.py`, `docker-compose.yml`
**Status:** Open

The stdio bridge communicates with the MCP server over plain HTTP (`http://192.168.153.8:8080`). The bearer token is transmitted in the clear. On a trusted home network this is low risk, but if the network segment is shared or if the Docker host is remote, the token could be intercepted.

**Remediation:** For a home network, this is acceptable. If deploying on a shared network, add a TLS-terminating reverse proxy (nginx, Caddy) in front of the MCP container.

---

### LOW-04: `.env.example` Contains Weak Default Password Hint

**Severity:** LOW
**Component:** `.env.example`
**Status:** Open

The `.env.example` file uses `change_me_to_a_secure_password` as the placeholder for `POSTGRES_PASSWORD`. While there's a helpful generation command in the comments, developers who copy the file may forget to change the placeholder, resulting in a weak database password.

**Remediation:** Use an obviously-invalid placeholder like `REPLACE_ME_BEFORE_USE` or add a startup check that rejects the default value.

---

### LOW-05: Stale/Orphan Files in Repository

**Severity:** LOW
**Component:** Various
**Status:** Open

Several files appear to be development artifacts that should be cleaned up:

- `=2.9.9` — appears to be a pip install artifact (filename is a version specifier).
- `heartbeat/test2.sh` — one-line test script running DNS resolution inside Docker.
- `heartbeat/.smbdeleteAAA055a4.4`, `.claude/.smbdeleteAAA54f74.4` — SMB deletion artifacts from the network volume.
- `heartbeat/pingtest.log` — test log file.
- `testscript/*.log` — should be gitignored (they are, but the files exist on disk).

**Remediation:** Delete orphan files. Add `=*` pattern to `.gitignore` to prevent pip artifacts.

---

### INFO-01: Strong MCP Server Security Posture

**Component:** `server.py`, `Dockerfile`, `docker-compose.yml`

The MCP server demonstrates excellent defensive design:

- Bearer token authentication via ASGI middleware, protecting all endpoints except `/health`.
- Strict Pydantic input validation with `extra="forbid"`, regex patterns, and length constraints on all user-facing models.
- ML-based prompt injection detection (LLM Guard DeBERTa v3) with configurable threshold.
- Regex-based pattern detection as a second filter layer for credential exfiltration and code injection.
- `_strip_security_metadata()` prevents filter internals from leaking to the reasoning LLM.
- Security audit logging to JSONL with log rotation.
- Container hardening: `read_only`, `cap_drop: ALL`, `no-new-privileges`, `tmpfs`, non-root user.
- Pre-downloaded model weights (no runtime internet access needed).
- Application-level rate limiting on write operations.

---

### INFO-02: Good Secret Scanning and Pre-Commit Configuration

**Component:** `.pre-commit-config.yaml`, `.secrets.baseline`

The project uses `detect-secrets` with a maintained baseline, `shellcheck` for shell scripts, and `ruff` for Python linting/formatting. The `.gitignore` properly excludes `.env`, credentials files, and logs.

---

### INFO-03: Comprehensive Test Suite

**Component:** `tests/`

The test suite covers input validation, content filtering, credential loading, HTTP error handling, dashboard API endpoints (CRUD for runs, actions, prompts, security events), the activity recorder's regex parsing, and the MCP log collector including oddity detection. Tests use PostgreSQL fixtures for realistic integration testing.

---

### INFO-04: Well-Structured Security Monitoring Pipeline

**Component:** `heartbeat/collect_mcp_logs.py`, `dashboard/api/routers/security.py`

The security monitoring pipeline is thoughtfully designed:

- Incremental log collection (byte offset tracking for JSONL, Docker `--since` for container logs).
- Automated oddity detection (duplicate votes, failed API calls, excessive call bursts).
- Structured storage in PostgreSQL with proper indexing.
- Dashboard API for querying events, tool calls, and oddities with filtering and pagination.

---

## Prioritized Remediation Plan

| Priority | Finding | Effort | Impact |
|----------|---------|--------|--------|
| 1 | **HIGH-01**: Add auth to dashboard API | Medium | Prevents prompt injection via dashboard, blocks LAN data disclosure |
| 2 | **HIGH-02**: Rotate Moltbook API key | Low | Eliminates compromised credential |
| 3 | **HIGH-03**: Remove PG password from settings.local.json | Low | Reduces credential exposure surface |
| 4 | **HIGH-04**: Add validation to dashboard models | Low | Prevents resource exhaustion via unbounded input |
| 5 | **MEDIUM-01**: Harden dashboard Docker container | Low | Matches MCP container security posture |
| 6 | **MEDIUM-02**: Add anti-hallucination to celticxfer_heartbeat.sh | Low | Prevents hallucinated verification steps |
| 7 | **MEDIUM-03**: Bind PostgreSQL to localhost | Low | Reduces network attack surface |
| 8 | **MEDIUM-05**: Add rate limiting to dashboard writes | Medium | Prevents flooding |
| 9 | **MEDIUM-04**: Fix comment/constant mismatch | Low | Operational clarity |
| 10 | **LOW-01–05**: Cache TTL, cleanup, TLS, etc. | Low | Polish |

---

## Strengths

1. **Defence in depth** on content filtering — ML model + regex + metadata stripping.
2. **Bearer token authentication** fully active on MCP server.
3. **Container hardening** on the MCP server is best-practice.
4. **Rate limiting** on write operations prevents API abuse.
5. **Pre-commit secret scanning** catches accidental credential commits.
6. **Input validation** on MCP server models is thorough (extra="forbid", patterns, length limits).
7. **Security audit logging** with rotation and structured JSONL format.
8. **Automated oddity detection** catches behavioral anomalies.
9. **Non-root container users** in both Dockerfiles.
10. **Model pre-download** eliminates runtime network dependency.

---

## Files Reviewed

### Core Application
- `server.py` — MCP server, tools, auth middleware, rate limiter, input models
- `content_filter.py` — ML + regex prompt injection detection
- `stdio_bridge.py` — stdio-to-HTTP bridge with retry logic
- `stdio_server.py` — Direct stdio mode launcher

### Docker & Infrastructure
- `Dockerfile` — MCP server container (multi-stage with model pre-download)
- `docker-compose.yml` — Full stack orchestration (MCP, dashboard, PostgreSQL)
- `dashboard/Dockerfile` — Dashboard container (multi-stage with React build)

### Dashboard API
- `dashboard/api/main.py` — FastAPI app, CORS, SPA serving
- `dashboard/api/database.py` — PostgreSQL schema and connection management
- `dashboard/api/models.py` — Pydantic models for all API endpoints
- `dashboard/api/routers/runs.py` — Heartbeat run CRUD
- `dashboard/api/routers/actions.py` — Action recording endpoints
- `dashboard/api/routers/stats.py` — Aggregate statistics
- `dashboard/api/routers/prompts.py` — Prompt version management
- `dashboard/api/routers/security.py` — Security analytics endpoints

### Dashboard Frontend
- `dashboard/webapp/src/api/client.ts` — TypeScript API client

### Heartbeat System
- `heartbeat/run_today.sh` — Continuous loop heartbeat runner
- `heartbeat/celticxfer_heartbeat.sh` — Single-run cron heartbeat
- `heartbeat/record_activity.py` — Claude output parser and PostgreSQL recorder
- `heartbeat/collect_mcp_logs.py` — Security log collector and oddity detector
- `heartbeat/seed_prompt.py` — Initial prompt seeder
- `heartbeat/backfill_from_log.py` — Historical log migration
- `heartbeat/config.json` — Agent configuration
- `heartbeat/mcp-config.json` — MCP bridge configuration
- `heartbeat/com.celticxfer.moltbook.heartbeat.plist` — macOS launchd schedule

### Utility Scripts
- `scripts/migrate_sqlite_to_pg.py` — SQLite-to-PostgreSQL migration
- `download_model.py` — DeBERTa model pre-download for Docker build
- `rebuild-test.sh` — Full rebuild and integration test script

### Configuration
- `.env` — Live secrets (API key, bearer token, PG password, database URL)
- `.env.example` — Template with generation instructions
- `.gitignore` — Properly excludes secrets and logs
- `.dockerignore` — Excludes secrets from Docker build context
- `.pre-commit-config.yaml` — Ruff, detect-secrets, shellcheck, pre-commit-hooks
- `.secrets.baseline` — detect-secrets baseline
- `.claude/settings.local.json` — Claude Code permissions (contains PG password)
- `requirements.txt` — Production Python dependencies
- `requirements-dev.txt` — Development/test dependencies
- `config/credentials.example.json` — Credentials file template

### Tests
- `tests/conftest.py` — Shared fixtures (PostgreSQL, mocks, sample data)
- `tests/test_content_filter.py` — Content filter unit tests
- `tests/test_server.py` — Server unit tests (credentials, HTTP, tools)
- `tests/test_models.py` — Pydantic model validation tests
- `tests/test_health.py` — Health endpoint integration test
- `tests/test_dashboard_api.py` — Dashboard API integration tests
- `tests/test_record_activity.py` — Activity parser and recorder tests
- `tests/test_collect_mcp_logs.py` — Log collector and oddity detector tests
- `tests/test_security_analytics.py` — Security analytics API tests

---

*End of review.*
