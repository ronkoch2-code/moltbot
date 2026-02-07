# Development State — Moltbot

## Current Task
Fixing Claude Desktop MCP bridge connectivity.

## Active Work — 2026-02-07

### Bridge/Server Debugging
- [x] Fixed `app_lifespan()` signature — MCP framework passes `app` argument
- [x] Rewrote `stdio_bridge.py` to use raw sockets for proper chunked/SSE handling
- [ ] User needs to rebuild containers and restart Claude Desktop to test

## Plan

### Block 1: Fix Broken Health Check
- [x] **1.1** Modify `server.py` entrypoint — wrap FastMCP's streamable HTTP app in a Starlette application that also mounts a `/health` route returning JSON status. Keep `stdio` transport branch unchanged.
- [x] **1.2** Simplify Dockerfile `HEALTHCHECK` command — switch from `httpx` import to stdlib `urllib.request` to avoid loading heavy dependencies for a simple GET.
- [x] **1.3** Update `CLAUDE.md` health check reference to stay consistent.

---

### Block 2: Create Test Suite
- [x] **2.1** Create test infrastructure — `tests/__init__.py`, `tests/conftest.py`, `pyproject.toml`, `requirements-dev.txt`.
- [x] **2.2** Create `tests/test_content_filter.py` — 17 tests covering regex scanning, scan_text(), filter_post/posts/comments.
- [x] **2.3** Create `tests/test_models.py` — 25 tests covering all Pydantic input models.
- [x] **2.4** Create `tests/test_server.py` — 13 tests covering credential loading, HTTP error mapping, API requests.
- [x] **2.5** Create `tests/test_health.py` — 3 tests for `/health` endpoint.
- [x] **2.6** Update `.gitignore` — add `.pytest_cache/`, `htmlcov/`, `.coverage`.

---

### Block 3: Configurable Threshold & Log Level
- [x] **3.1** Modify `content_filter.py` — read `CONTENT_FILTER_THRESHOLD` from env var, default to 0.5.
- [x] **3.2** Modify `server.py` — add `logging.basicConfig()` driven by `LOG_LEVEL` env var, default to INFO.
- [x] **3.3** Update `docker-compose.yml` — pass through `CONTENT_FILTER_THRESHOLD` and `LOG_LEVEL` env vars.
- [x] **3.4** Update `.env.example` — add both new env vars with comments.
- [x] **3.5** Add test `TestConfigurableThreshold` to `tests/test_content_filter.py`.
- [x] **3.6** Update `CLAUDE.md` — mention configurable threshold, log level, and testing section.

---

## Completed Work

### 2026-02-06 — Initial Development Session

**Block 1: Health Check Fix**
- Added `/health` endpoint to `server.py` using Starlette wrapper around FastMCP
- Simplified Dockerfile HEALTHCHECK to use stdlib `urllib.request` instead of httpx
- Container now properly reports HEALTHY status

**Block 2: Test Suite**
- Created comprehensive pytest suite with 58 tests
- Tests cover content filtering, Pydantic models, server helpers, health endpoint
- All tests run in regex-only mode (no ML model needed) for speed

**Block 3: Configuration**
- `CONTENT_FILTER_THRESHOLD` env var controls ML detection sensitivity (default: 0.5)
- `LOG_LEVEL` env var controls logging verbosity (default: INFO)
- Both vars documented in `.env.example` and passed through `docker-compose.yml`

**Files Created:**
- `tests/__init__.py`
- `tests/conftest.py`
- `tests/test_content_filter.py`
- `tests/test_models.py`
- `tests/test_server.py`
- `tests/test_health.py`
- `pyproject.toml`
- `requirements-dev.txt`

**Files Modified:**
- `server.py` — Starlette wrapper, health endpoint, logging config
- `content_filter.py` — Configurable threshold
- `Dockerfile` — Simplified HEALTHCHECK
- `docker-compose.yml` — New env vars
- `.env.example` — New env vars documented
- `.gitignore` — Pytest/coverage artifacts
- `CLAUDE.md` — Updated docs for testing, configuration, key files

## Known Issues
_(none — all previously known issues resolved)_

## Not In Scope (Future Sessions)
- CI/CD pipeline (GitHub Actions) — depends on test suite existing first
- `heartbeat.py` autonomous agent loop — needs design decisions on Anthropic API integration
- Docker resource limits (`mem_limit`, `cpus`) — quick fix for next session
- Pagination/cursor support for feed browsing
- Post/comment editing & deletion tools
- Search functionality
- Retry logic on transient 5xx errors
