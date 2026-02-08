# Development State — Moltbot

## Current Task
Security Review Remediation (HIGH-02, HIGH-03)

## Plan — 2026-02-08

### Block 4: Heartbeat Activity Dashboard
- [x] **4.1** Create directory structure and data/.gitkeep
- [x] **4.2** Write database.py (SQLite, WAL mode, schema) and models.py (Pydantic)
- [x] **4.3** Write record_activity.py (parse Claude output, extract actions)
- [x] **4.4** Write backfill_from_log.py (migrate heartbeat.log to SQLite)
- [x] **4.5** Write FastAPI dashboard API (main.py, runs/actions/stats routers)
- [x] **4.6** Modify run_today.sh and celticxfer_heartbeat.sh for record_activity.py
- [x] **4.7** Write React webapp (Vite + React 19 + TypeScript + Tailwind 4)
- [x] **4.8** Write dashboard/Dockerfile (multi-stage Node + Python)
- [x] **4.9** Update docker-compose.yml with dashboard service
- [x] **4.10** Write tests (test_record_activity.py, test_dashboard_api.py)
- [x] **4.11** Update .gitignore, CLAUDE.md, DEVELOPMENT_STATE.md

### Block 5: Pre-commit Hooks (Lint, Format, Secret Scanning)
- [x] **5.1** Create .pre-commit-config.yaml (ruff, detect-secrets, shellcheck, pre-commit-hooks)
- [x] **5.2** Add ruff configuration to pyproject.toml
- [x] **5.3** Create .secrets.baseline for detect-secrets
- [x] **5.4** Update requirements-dev.txt with ruff, pre-commit, detect-secrets
- [x] **5.5** Document hooks in CLAUDE.md

### Block 6: Security Review Remediation
- [x] **HIGH-02**: Replace raw sockets in stdio_bridge.py with httpx
- [x] **HIGH-03**: Expand content filter to scan all user-controllable fields

---

## Completed Work

### 2026-02-08 — Security Issue Remediation (Batch 1)
Fixed critical, high, and medium security findings from the security review:

**Critical:**
- CRITICAL-01: Removed API key from config.json, created config.example.json template
- CRITICAL-02: Added bearer token auth middleware (MCP_AUTH_TOKEN env var)
- CRITICAL-03: Replaced bypassPermissions with explicit --allowedTools in heartbeat scripts

**High:**
- HIGH-01: Added SAFE_ID_PATTERN validation to all Pydantic ID fields
- HIGH-02: Replaced raw sockets in stdio_bridge.py with httpx
- HIGH-03: Expanded content filter to scan all user-controllable fields
- HIGH-04: Added _strip_security_metadata() to remove _security from tool output
- HIGH-05: Sanitized error messages (log detail, return generic errors)

**Medium:**
- MEDIUM-02: Made security logging configurable (defaults to stderr)
- MEDIUM-04: Removed hardcoded test paths, use pythonpath in pyproject.toml
- MEDIUM-05: Added setup validation in run_today.sh

**Tests updated:** Fixed test_server.py for new error handling, fixed context helpers

Files changed: server.py, content_filter.py, stdio_bridge.py, heartbeat/run_today.sh,
heartbeat/celticxfer_heartbeat.sh, tests/test_server.py, tests/test_health.py,
docker-compose.yml, .env.example, pyproject.toml, heartbeat/config.example.json

### 2026-02-08 — Security Review Remediation (HIGH-02, HIGH-03)

**What**: Fixed high-priority security vulnerabilities identified in security review.

**Changes Made**:

**HIGH-02: Replace raw sockets with httpx in stdio_bridge.py**
- Removed all raw socket handling code (180+ lines of manual HTTP parsing)
- Replaced with httpx.Client for proper HTTP/TLS handling
- Benefits:
  - TLS support out of the box (can switch to HTTPS easily)
  - Automatic HTTP parsing (status codes, headers, chunked encoding)
  - Better error handling and timeouts
  - More maintainable code (reduced from 215 to 125 lines)
- Error messages now use `type(e).__name__` to avoid leaking internal details (consistent with HIGH-05)

**HIGH-03: Expand content filter coverage**
- Extended `filter_post()` to scan 6 fields instead of 2:
  - Before: `title`, `content`
  - After: `title`, `content`, `name`, `description`, `author_name`, `submolt_name`
- Updated `fields_affected` in audit log to match expanded coverage
- Updated docstring to reflect broader scanning scope
- No performance impact (same scan_text() logic, just more fields)

**Files Modified**:
- `stdio_bridge.py` — Complete rewrite using httpx (215 → 125 lines)
- `content_filter.py` — Expanded field scanning in filter_post() and audit logging

**Verification**:
- All 26 content filter tests pass
- Python syntax validation passed for both files
- httpx already available as project dependency (version 0.28.1)

### 2026-02-08 — Heartbeat Activity Dashboard

**What**: Built a complete monitoring dashboard for CelticXfer's heartbeat activity on Moltbook.

**Architecture**:
- SQLite database (data/heartbeat.db) stores structured run + action data
- Python CLI (record_activity.py) parses Claude output with regex, extracts actions
- FastAPI API (port 8081) serves paginated runs, actions, stats, timeline
- React 19 webapp with TypeScript + Tailwind CSS 4 dark theme dashboard
- Multi-stage Docker build (Node + Python)
- Backfill script migrates existing heartbeat.log data

**Files Created**:
- `data/.gitkeep`
- `dashboard/api/__init__.py`, `routers/__init__.py`
- `dashboard/api/database.py` — SQLite with WAL mode, schema management
- `dashboard/api/models.py` — Pydantic response models
- `dashboard/api/main.py` — FastAPI app with CORS, static serving
- `dashboard/api/routers/runs.py` — Run CRUD with pagination/filtering
- `dashboard/api/routers/actions.py` — Action endpoints
- `dashboard/api/routers/stats.py` — Aggregate stats and timeline
- `dashboard/api/requirements.txt`
- `dashboard/Dockerfile` — Multi-stage Node 22 + Python 3.12-slim
- `dashboard/webapp/` — Full React app (19 files)
- `heartbeat/record_activity.py` — Activity parser with 8 action types
- `heartbeat/backfill_from_log.py` — Log migration script
- `tests/test_record_activity.py` — 20 parser/recording tests
- `tests/test_dashboard_api.py` — 16 API endpoint tests

**Files Modified**:
- `heartbeat/run_today.sh` — Added record_activity.py call after each run
- `heartbeat/celticxfer_heartbeat.sh` — Same addition
- `docker-compose.yml` — Added moltbot-dashboard service
- `.gitignore` — Added dashboard/data exclusions
- `CLAUDE.md` — Added Dashboard and Pre-commit Hooks documentation
- `DEVELOPMENT_STATE.md` — Updated with current plan

### 2026-02-08 — Pre-commit Hooks

**What**: Configured pre-commit hooks for linting, formatting, and secret scanning at check-in.

**Files Created**:
- `.pre-commit-config.yaml` — ruff, detect-secrets, shellcheck, pre-commit-hooks
- `.secrets.baseline` — detect-secrets baseline

**Files Modified**:
- `pyproject.toml` — Added ruff lint/format configuration
- `requirements-dev.txt` — Added ruff, pre-commit, detect-secrets
- `CLAUDE.md` — Documented hooks

### 2026-02-07 — Bridge/Server Debugging
- Fixed `app_lifespan()` signature — MCP framework passes `app` argument
- Rewrote `stdio_bridge.py` to use raw sockets for proper chunked/SSE handling

### 2026-02-06 — Initial Development Session
- Added `/health` endpoint to `server.py` using Starlette wrapper
- Created comprehensive pytest suite with 58 tests
- Added `CONTENT_FILTER_THRESHOLD` and `LOG_LEVEL` env vars

## Known Issues
_(none)_

## Not In Scope (Future Sessions)
- CI/CD pipeline (GitHub Actions)
- Docker resource limits (`mem_limit`, `cpus`)
- Pagination/cursor support for feed browsing
- Post/comment editing & deletion tools
- Search functionality
- Retry logic on transient 5xx errors
- Security review remediation (see security-review/)
