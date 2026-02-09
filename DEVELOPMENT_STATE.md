# Development State — Moltbot

## Current Task
_(none — all tasks complete)_

## Plan — 2026-02-08 (continued)

### Block 11: SQLite → PostgreSQL Migration
- [x] **11.1** Add PostgreSQL service to docker-compose.yml + update .env
- [x] **11.2** Rewrite database.py — psycopg2, PostgreSQL DDL, get_connection/init_db/get_db
- [x] **11.3** Update all 5 router files — SQL translation (? → %s, RETURNING, booleans, date functions)
- [x] **11.4** Update main.py lifespan — psycopg2.OperationalError
- [x] **11.5** Update host-side scripts — record_activity.py, collect_mcp_logs.py, seed_prompt.py, backfill_from_log.py
- [x] **11.6** Update shell scripts — export DATABASE_URL from .env
- [x] **11.7** Update Dockerfile and requirements — psycopg2-binary
- [x] **11.8** Create migration script — scripts/migrate_sqlite_to_pg.py
- [x] **11.9** Update tests — conftest.py with pg_clean_db fixture, all 4 test files
- [x] **11.10** Documentation — CLAUDE.md and DEVELOPMENT_STATE.md

### Block 10: Server Stability & Bridge Resilience
- [x] **10.1** Docker resource limits — `mem_limit: 2g` (MCP) / `256m` (dashboard), `cpus`, `memswap_limit`
- [x] **10.2** Bridge retry logic — 3 retries with backoff on ConnectTimeout/ConnectError/ReadTimeout
- [x] **10.3** Bridge startup health check — verify MCP server reachable before accepting requests
- [x] **10.4** Auth token passthrough — heartbeat scripts export MCP_AUTH_TOKEN from `.env` to bridge subprocess
- [x] **10.5** ML filter kill switch — `CONTENT_FILTER_ML=false` env var skips DeBERTa model, saves ~1.5GB RAM

### Block 9: MCP Log Analytics & Security Event Tracking
- [x] **9.1** Database schema — 3 new tables (security_events, tool_calls, behavior_oddities) + migrations
- [x] **9.2** Pydantic models — SecurityEventOut, ToolCallOut, OddityOut, SecurityStatsOut + paginated variants
- [x] **9.3** Log collector script — `heartbeat/collect_mcp_logs.py` with parsers and oddity detection
- [x] **9.4** Docker Compose — SECURITY_LOG_PATH env var + logs volume mount
- [x] **9.5** API router — `dashboard/api/routers/security.py` (events, tool-calls, oddities, stats, timeline)
- [x] **9.6** React frontend — SecurityPage.tsx with tabbed tables, stats bar, types, API client, route, nav
- [x] **9.7** Heartbeat integration — Added collect_mcp_logs.py call to both shell scripts
- [x] **9.8** Tests — 24 parser/collector tests + 18 API endpoint tests = 42 new tests (181 total)
- [x] **9.9** Updated DEVELOPMENT_STATE.md and CLAUDE.md

### Block 8: `moltbook_update_identity` MCP Tool
- [x] **8.1** Add `MoltbookUpdateIdentityInput` Pydantic model to `server.py`
- [x] **8.2** Add `DASHBOARD_API_URL` env var to `server.py`
- [x] **8.3** Add `moltbook_update_identity` tool function to `server.py`
- [x] **8.4** Add `DASHBOARD_API_URL` to `docker-compose.yml` (moltbook-mcp service)
- [x] **8.5** Add tool to `--allowedTools` in `celticxfer_heartbeat.sh` and `run_today.sh`
- [x] **8.6** Add identity reflection instructions (section 7) to `seed_prompt.py` and shell fallbacks
- [x] **8.7** Add 6 tests for the new tool in `tests/test_server.py`
- [x] **8.8** Update DEVELOPMENT_STATE.md

### Block 7: Dynamic Heartbeat Prompt with Version History (Issue #21)
- [x] **7.1** Database schema — add `heartbeat_prompts` table, migration for `prompt_version_id`
- [x] **7.2** Pydantic models — `PromptOut`, `PromptCreateIn`, `PaginatedPrompts`; add `prompt_version_id` to `RunOut`
- [x] **7.3** API router — `dashboard/api/routers/prompts.py` (list, active, active/text, get by ID, create)
- [x] **7.4** Seed initial prompt — `heartbeat/seed_prompt.py` (idempotent, migrates from shell script)
- [x] **7.5** Shell script changes — fetch dynamic prompt from `/api/prompts/active/text` with hardcoded fallback
- [x] **7.6** `record_activity.py` — add `--prompt-version` CLI arg and DB column
- [x] **7.7** React dashboard — `PromptsPage.tsx`, types, API client, route, nav link
- [x] **7.8** Tests — 8 new prompt API tests (26 total dashboard tests)
- [x] **7.9** Update `_row_to_run` and DEVELOPMENT_STATE.md
- [x] **7.10** Seed baseline prompt into production database

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

### 2026-02-08 — SQLite → PostgreSQL Migration

**What**: Migrated all database access from SQLite-on-SMB to PostgreSQL in a Docker container with a named volume. Eliminates SMB file locking issues (stranded `.db-journal` files corrupting mounts) and "database is locked" errors.

**Architecture**: PostgreSQL 16-alpine runs as a Docker service (`moltbot-postgres`) with a named volume (`pgdata`) on local disk. Dashboard container connects via Docker network (`postgres:5432`). Host-side scripts connect via published port (`localhost:5432`). No database files touch SMB.

**Files Created**:
- `scripts/migrate_sqlite_to_pg.py` — One-time SQLite → PostgreSQL data migration (respects FK order, resets sequences)

**Files Rewritten**:
- `dashboard/api/database.py` — sqlite3 → psycopg2 with RealDictCursor, full PostgreSQL DDL schema
- `dashboard/api/routers/runs.py` — %s params, RETURNING *, cursor-based access
- `dashboard/api/routers/actions.py` — Same pattern
- `dashboard/api/routers/stats.py` — PostgreSQL date functions (make_interval), SUM() aggregates
- `dashboard/api/routers/security.py` — Same pattern
- `dashboard/api/routers/prompts.py` — Boolean TRUE/FALSE, RETURNING *
- `heartbeat/record_activity.py` — ON CONFLICT DO UPDATE, --database-url CLI arg
- `heartbeat/collect_mcp_logs.py` — STRING_AGG, date_trunc, ON CONFLICT DO NOTHING
- `heartbeat/seed_prompt.py` — psycopg2 connection
- `heartbeat/backfill_from_log.py` — ON CONFLICT DO NOTHING

**Files Modified**:
- `docker-compose.yml` — Added postgres service + pgdata volume, removed data bind mount from dashboard
- `.env` / `.env.example` — Added POSTGRES_PASSWORD, DATABASE_URL
- `dashboard/api/main.py` — psycopg2.OperationalError
- `dashboard/Dockerfile` — Removed SQLite data dir creation
- `dashboard/api/requirements.txt` — aiosqlite → psycopg2-binary
- `requirements-dev.txt` — Added psycopg2-binary
- `heartbeat/run_today.sh` — Export DATABASE_URL
- `heartbeat/celticxfer_heartbeat.sh` — Export DATABASE_URL
- `tests/conftest.py` — pg_clean_db fixture (drops/recreates tables, patches DATABASE_URL)
- `tests/test_dashboard_api.py` — PostgreSQL fixtures and SQL
- `tests/test_record_activity.py` — database_url parameter
- `tests/test_collect_mcp_logs.py` — PostgreSQL fixtures and SQL
- `tests/test_security_analytics.py` — PostgreSQL fixtures and SQL
- `CLAUDE.md` — PostgreSQL references throughout
- `DEVELOPMENT_STATE.md` — Migration plan and completion

**Deployment**: `docker compose up -d postgres` → `python3 scripts/migrate_sqlite_to_pg.py` → `docker compose up --build -d`

**Verification**: 181/181 tests pass against PostgreSQL.

### 2026-02-08 — Server Stability & Bridge Resilience

**What**: Fixed intermittent server crashes (OOM) and heartbeat agent tool failures caused by unbounded container memory and fragile bridge connections.

**Root cause**: DeBERTa v3 content filter consumes ~1.5GB RAM. With no resource limits, both containers could consume unlimited memory, causing the Linux OOM killer to crash the entire host. When the MCP server was slow or unreachable, the stdio bridge failed on the first connection attempt with no retry, causing Claude to hallucinate "I don't have MCP tools."

**Files Modified**:
- `docker-compose.yml` — Resource limits (configurable via `MCP_MEM_LIMIT`), `CONTENT_FILTER_ML` env var
- `content_filter.py` — `CONTENT_FILTER_ML=false` skips DeBERTa model loading entirely (regex still applies)
- `stdio_bridge.py` — 3-retry loop with backoff for ConnectTimeout/ConnectError/ReadTimeout; startup health check
- `heartbeat/celticxfer_heartbeat.sh` — Exports `MCP_AUTH_TOKEN` from project `.env` before invoking Claude
- `heartbeat/run_today.sh` — Same auth token export
- `.env.example` — Documented `CONTENT_FILTER_ML` option

**Verification**: 181/181 tests pass (26 content filter, 155 rest). docker-compose.yml validates.

### 2026-02-08 — MCP Log Analytics & Security Event Tracking

**What**: Built automatic collection, structured storage, API endpoints, and a React dashboard page for MCP server security events — injection attempts, unauthorized access, tool call tracking, and behavioral oddity detection.

**Architecture**: Host-side Python script (`collect_mcp_logs.py`) runs after each heartbeat, reads structured JSONL from `data/logs/security_audit.jsonl` and Docker container logs, parses events into SQLite, and detects anomalies (duplicate votes, failed API calls, excessive call rates). Dashboard API serves paginated/filterable endpoints. React page shows stats bar + tabbed tables.

**Files Created**:
- `heartbeat/collect_mcp_logs.py` — Log collector with 3 parsers + oddity detector
- `dashboard/api/routers/security.py` — 6 API endpoints (events, tool-calls, oddities, stats, timeline)
- `dashboard/webapp/src/pages/SecurityPage.tsx` — Tabbed security dashboard UI
- `data/logs/.gitkeep` — Logs directory for security audit JSONL
- `tests/test_collect_mcp_logs.py` — 24 parser/collector/detector tests
- `tests/test_security_analytics.py` — 18 API endpoint tests

**Files Modified**:
- `dashboard/api/database.py` — 3 new tables + migration support
- `dashboard/api/models.py` — 7 new Pydantic models
- `dashboard/api/main.py` — Registered security router
- `docker-compose.yml` — SECURITY_LOG_PATH env var + logs volume mount
- `heartbeat/run_today.sh` — Added collector call
- `heartbeat/celticxfer_heartbeat.sh` — Added collector call
- `dashboard/webapp/src/types/index.ts` — 7 new TypeScript interfaces
- `dashboard/webapp/src/api/client.ts` — 5 new fetch functions
- `dashboard/webapp/src/App.tsx` — /security route
- `dashboard/webapp/src/components/Layout.tsx` — Security nav link

**Verification**: 181/181 tests pass (42 new).

### 2026-02-08 — `moltbook_update_identity` MCP Tool

**What**: Added an MCP tool that lets CelticXfer update its own identity prompt by creating a new version in the dashboard's prompt versioning system. This closes the self-modification loop: the heartbeat prompt tells the agent to reflect on its identity, and now it has a tool to act on that reflection.

**Architecture**: The MCP server (moltbook-mcp container) POSTs to the dashboard API (`moltbot-dashboard:8081/api/prompts`) over the shared Docker network. The tool creates a new active prompt version, which is then picked up by the next heartbeat run via `GET /api/prompts/active/text`.

**Files Modified**:
- `server.py` — Added `DASHBOARD_API_URL` constant, `MoltbookUpdateIdentityInput` model, `moltbook_update_identity` tool
- `docker-compose.yml` — Added `DASHBOARD_API_URL` env var to moltbook-mcp service
- `heartbeat/celticxfer_heartbeat.sh` — Added tool to `--allowedTools`, added section 7 to fallback prompt
- `heartbeat/run_today.sh` — Added tool to `--allowedTools`, added section 7 to fallback prompt
- `heartbeat/seed_prompt.py` — Added section 7 (identity reflection) to initial prompt
- `tests/test_server.py` — Added 6 tests (success, HTTP error, timeout, 3 validation tests)

**Verification**: 139/139 tests pass.

### 2026-02-08 — Dynamic Heartbeat Prompt with Version History (Issue #21)

**What**: Moved the heartbeat prompt from hardcoded shell scripts into SQLite with full version history, a REST API for CRUD, and a dashboard UI to view/edit prompts.

**Architecture**: Shell scripts fetch active prompt from `GET /api/prompts/active/text` at runtime, falling back to hardcoded prompt if the API is unreachable. Dashboard UI shows version history and allows creating new versions.

**Files Created**:
- `dashboard/api/routers/prompts.py` — Full CRUD with plain-text endpoint for shell `curl`
- `dashboard/webapp/src/pages/PromptsPage.tsx` — Version history UI with create form
- `heartbeat/seed_prompt.py` — One-time seed script (idempotent)

**Files Modified**:
- `dashboard/api/database.py` — Added `heartbeat_prompts` table, `migrate_db()` for `prompt_version_id` column
- `dashboard/api/models.py` — Added `PromptOut`, `PromptCreateIn`, `PaginatedPrompts`; `prompt_version_id` on `RunOut`
- `dashboard/api/main.py` — Registered prompts router
- `dashboard/api/routers/runs.py` — Added `prompt_version_id` to `_row_to_run()`
- `heartbeat/record_activity.py` — Added `--prompt-version` CLI arg and DB column
- `heartbeat/celticxfer_heartbeat.sh` — Dynamic prompt fetch with fallback
- `heartbeat/run_today.sh` — Dynamic prompt fetch with fallback
- `dashboard/webapp/src/types/index.ts` — Added `Prompt`, `PaginatedPrompts` interfaces
- `dashboard/webapp/src/api/client.ts` — Added `postJSON`, `fetchPrompts`, `fetchActivePrompt`, `createPrompt`
- `dashboard/webapp/src/App.tsx` — Added `/prompts` route
- `dashboard/webapp/src/components/Layout.tsx` — Added "Prompts" nav link
- `tests/test_dashboard_api.py` — Added 8 prompt tests (26 total)

**Verification**: 133/133 tests pass. Baseline prompt seeded as version 1.

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
- `data/heartbeat.db` still exists as read-only backup; can be deleted once PostgreSQL is confirmed stable

## Not In Scope (Future Sessions)
- CI/CD pipeline (GitHub Actions)
- Pagination/cursor support for feed browsing
- Post/comment editing & deletion tools
- Search functionality
- Retry logic on transient 5xx errors
