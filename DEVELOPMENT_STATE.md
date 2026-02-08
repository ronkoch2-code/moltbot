# Development State — Moltbot

## Current Task
Heartbeat Activity Dashboard + Pre-commit Hooks

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

---

## Completed Work

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
