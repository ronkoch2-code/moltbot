# CLAUDE.md — Moltbot (Moltbook MCP Server)

## Project Overview

Security-hardened MCP server providing sandboxed access to [Moltbook](https://www.moltbook.com), an AI-agent social network. Runs in Docker, exposes 10 tools for browsing, posting, commenting, voting, and managing communities — all behind a two-layer content filter (ML + regex) to defend against prompt injection.

## Architecture

```
Claude/AI  →  MCP Server (Docker, localhost:8080)  →  moltbook.com API
               ├── Content Filter (DeBERTa v3 + regex)
               ├── API Client (httpx async)
               └── Credential isolation
```

## Key Files

| File | Purpose |
|------|---------|
| `server.py` | Main MCP server — tools, Pydantic models, HTTP client, `/health` endpoint |
| `content_filter.py` | Two-layer injection detection (LLM Guard ML + regex patterns) |
| `download_model.py` | Pre-downloads DeBERTa model during Docker build |
| `Dockerfile` | Container build (Python 3.12-slim) |
| `docker-compose.yml` | Orchestration with security hardening |
| `config/credentials.example.json` | API credential template |
| `.env.example` | Environment variable template |
| `tests/` | Pytest test suite |
| `pyproject.toml` | Project config, pytest settings, ruff config |
| `requirements-dev.txt` | Dev/test dependencies |
| `dashboard/` | Heartbeat activity dashboard (FastAPI + React) |
| `heartbeat/record_activity.py` | Structured activity recorder |
| `.pre-commit-config.yaml` | Pre-commit hook configuration |
| `.secrets.baseline` | detect-secrets baseline for token scanning |

## Tech Stack

- **Python 3.12** with async/await throughout
- **FastMCP** (`mcp[cli]`) — MCP server framework
- **httpx** — async HTTP client
- **uvicorn** — ASGI server (streamable HTTP transport)
- **Pydantic v2** — input validation with strict models
- **llm-guard** — ML-based prompt injection detection (DeBERTa v3)

## Code Conventions

- **Style**: snake_case functions, PascalCase classes, UPPER_CASE constants
- **Type hints**: Full annotations on all functions
- **Docstrings**: NumPy-style with Args/Returns sections
- **Pydantic models**: `ConfigDict(str_strip_whitespace=True, extra="forbid")` on all input models
- **Error handling**: `_http_error_response()` maps HTTP status codes to user-friendly messages
- **Logging**: Python standard `logging` module
- **Tool annotations**: Each tool has `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`

## Running

```bash
# Build and start
docker compose up --build -d

# Entry point
python server.py --transport streamable_http --port 8080

# Health check
curl http://localhost:8080/health
```

## Security Model

- Docker: read-only root, all capabilities dropped, no-new-privileges, non-root user `moltbot`
- Credentials: mounted read-only, never logged or exposed in responses
- Content filter: ML threshold configurable via `CONTENT_FILTER_THRESHOLD` env var (default: 0.5), regex fallback if llm-guard unavailable
- Flagged content redacted with `[REDACTED — blocked by filter]` and `_security` metadata attached

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `MOLTBOOK_API_KEY` | — | Your Moltbook API key (required) |
| `MOLTBOOK_AGENT_NAME` | `unknown` | Agent display name |
| `CONTENT_FILTER_THRESHOLD` | `0.5` | ML injection detection threshold (0.0-1.0, lower = more aggressive) |
| `LOG_LEVEL` | `INFO` | Logging verbosity (DEBUG, INFO, WARNING, ERROR) |

## Tools (10)

**Read-only**: `moltbook_agent_status`, `moltbook_browse_feed`, `moltbook_get_post`, `moltbook_list_submolts`, `moltbook_get_submolt`

**Write**: `moltbook_register`, `moltbook_create_post`, `moltbook_comment`, `moltbook_vote`, `moltbook_subscribe`

## Testing

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=. --cov-report=html
```

Test suite covers:
- **Content filter**: Regex patterns, scan_text(), filter_post/posts/comments
- **Pydantic models**: Validation, defaults, bounds, whitespace stripping
- **Server helpers**: Credential loading, HTTP error mapping, API requests
- **Health endpoint**: `/health` route via ASGI transport

## Development Workflow

### Agent-Based Development

Use specialized agents for planning and implementation:

**1. Architect Agent (`architect-context-master`)** — Use for:
- Designing solutions that span multiple components
- Planning features requiring changes to 3+ layers (API, models, database, UI)
- Refactoring that touches multiple modules
- Understanding architectural implications before implementation
- Creating detailed implementation plans

**2. Code Worker Agent (`code-worker`)** — Use for:
- Executing specific steps from an Architect's plan
- Focused implementation of discrete tasks
- Sequential execution of multi-step plans
- Making changes while maintaining awareness of the broader plan

### Workflow

1. **For complex changes**: First spawn `architect-context-master` to analyze the codebase and create a comprehensive implementation plan
2. **For execution**: Use `code-worker` to implement each step of the plan sequentially
3. **For simple fixes**: Direct implementation is fine for single-file, obvious changes
4. **After all code changes**: Review modified files for completeness and internal consistency before testing or deployment. Check for:
   - Unused imports or variables
   - Mismatched function signatures
   - Hardcoded values that should use parameters
   - Missing error handling
   - Inconsistent naming or patterns

### Example

```
User: "Add rate limiting to the API client"

1. Spawn architect-context-master → analyzes server.py, understands _api_request(),
   designs rate limiting strategy, produces step-by-step plan

2. Spawn code-worker for Step 1 → "Add RateLimiter class to server.py"
3. Spawn code-worker for Step 2 → "Integrate rate limiter into _api_request()"
4. Spawn code-worker for Step 3 → "Add tests for rate limiting"
```

## Development State Tracking

**MANDATORY**: Always maintain a `DEVELOPMENT_STATE.md` file in the project root to track all development activity. This file is your persistent memory across sessions and serves as the restart point if anything fails.

### Rules

1. **Before starting work**: Read `DEVELOPMENT_STATE.md` (create it if it doesn't exist) to understand where things left off.
2. **When planning**: Write the full plan into `DEVELOPMENT_STATE.md` before writing any code — include what you're doing, why, and which files will be touched.
3. **During development**: Update `DEVELOPMENT_STATE.md` as each step completes or fails. Mark steps with status indicators:
   - `[ ]` — planned / not started
   - `[~]` — in progress
   - `[x]` — completed
   - `[!]` — failed (include error details and what was tried)
4. **On failure or interruption**: Ensure `DEVELOPMENT_STATE.md` reflects exactly where things stopped, what broke, and what needs to happen next. This is the most critical update.
5. **On completion**: Update `DEVELOPMENT_STATE.md` with a summary of what was done and clear the active plan section.

### File Format

```markdown
# Development State — Moltbot

## Current Task
Brief description of what's being worked on.

## Plan
- [x] Step 1 — description (completed)
- [~] Step 2 — description (in progress)
- [ ] Step 3 — description
- [!] Step 4 — description (FAILED: error details here)

## Completed Work
### YYYY-MM-DD — Task name
Summary of what was done and files changed.

## Known Issues
- Issue description and context
```

### Why This Matters

- Sessions can fail, context can be lost, and conversations can be interrupted
- This file gives any future session (or a human) full context to pick up exactly where things left off
- It prevents duplicate work and avoids repeating mistakes

## Moltbook Platform Features

### Core Features

**Content & Engagement**
- Create posts and comments in communities (submolts)
- Upvote/downvote content to surface quality discussions
- Threaded conversations with nested replies

**Semantic Search**
- Find relevant discussions and posts across the platform
- Search by topic, keyword, or community

**Community Building**
- Join and participate in topic-focused submolts
- Subscribe to communities of interest
- Discover trending topics via hot/rising/top sorting

### Rate Limits

| Action | Limit |
|--------|-------|
| Posts | 1 per 30 minutes |
| Comments | 50 per day |
| Votes | No explicit limit |

### Agent Registration Flow

1. Call `moltbook_register` with agent name and description
2. **Save the API key immediately** — it cannot be recovered
3. Human owner must visit the claim URL and post verification tweet
4. Once claimed, all tools become available

### Human-Agent Verification

Every Moltbook agent must be verified by a human via Twitter/X. This:
- Links the agent to a real human identity
- Prevents spam and bot abuse
- Enables accountability for agent behavior

## Heartbeat Activity Dashboard

The dashboard monitors CelticXfer's automated heartbeat activity on Moltbook.

### Architecture

```
Heartbeat scripts → record_activity.py → SQLite (data/heartbeat.db)
Dashboard API (FastAPI :8081) → SQLite → React webapp (static files)
```

### Key Dashboard Files

| File | Purpose |
|------|---------|
| `dashboard/api/main.py` | FastAPI app, static file serving, CORS |
| `dashboard/api/database.py` | SQLite connection, schema init, WAL mode |
| `dashboard/api/models.py` | Pydantic response models |
| `dashboard/api/routers/runs.py` | Run CRUD endpoints |
| `dashboard/api/routers/actions.py` | Action endpoints |
| `dashboard/api/routers/stats.py` | Aggregate statistics |
| `dashboard/webapp/` | React 19 + TypeScript + Tailwind CSS 4 |
| `dashboard/Dockerfile` | Multi-stage build (Node + Python) |
| `heartbeat/record_activity.py` | Parses Claude output, writes to SQLite |
| `heartbeat/backfill_from_log.py` | One-time migration from heartbeat.log |

### Running the Dashboard

```bash
# Build and start (with MCP server)
docker compose up --build -d

# Dashboard accessible at
curl http://localhost:8081/api/health

# Backfill historical data from logs
python3 heartbeat/backfill_from_log.py
```

### Dashboard API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/runs` | GET | List runs (paginated, filterable) |
| `/api/runs` | POST | Record new run |
| `/api/runs/{run_id}` | GET | Single run with actions |
| `/api/runs/{run_id}` | PATCH | Update run |
| `/api/runs/{run_id}/actions` | GET/POST | Actions for a run |
| `/api/actions` | GET | All actions (filterable) |
| `/api/stats` | GET | Aggregate stats |
| `/api/stats/timeline` | GET | Daily counts for charting |

## Code Quality and Pre-commit Hooks

This project uses pre-commit hooks to enforce code quality at check-in time.

### Setup

```bash
pip install pre-commit
pre-commit install
```

### Hooks Configured

| Hook | Purpose |
|------|---------|
| **ruff** | Python linting (pycodestyle, pyflakes, isort, bugbear, bandit) |
| **ruff-format** | Python code formatting (consistent style) |
| **detect-secrets** | Scans for API keys, tokens, passwords, credentials |
| **shellcheck** | Shell script linting and best practices |
| **trailing-whitespace** | Removes trailing whitespace |
| **end-of-file-fixer** | Ensures files end with newline |
| **check-yaml/json** | Validates YAML/JSON syntax |
| **check-added-large-files** | Blocks files >500KB |
| **no-commit-to-branch** | Prevents direct commits to main |

### Manual Usage

```bash
# Run all hooks on all files
pre-commit run --all-files

# Run specific hook
pre-commit run ruff --all-files
pre-commit run detect-secrets --all-files

# Update hook versions
pre-commit autoupdate
```

## Known Pitfalls

### MCP SDK Lifespan Context Access
The attribute name for accessing lifespan state from a `Context` object varies across
MCP SDK versions (`ctx.lifespan_context`, `ctx.request_context.lifespan_state`, etc.).
**Do not guess attribute names.** If the current pattern breaks after a version upgrade:

1. Check the installed version: `pip show mcp`
2. Inspect the Context class: `python -c "from mcp.server.fastmcp import Context; print(dir(Context))"`
3. If no reliable attribute exists, use module-level globals set during lifespan instead
   of accessing state through `ctx` — this is version-proof.

### General Debugging Approach
When hitting attribute errors or SDK compatibility issues:
- **Check the actual installed version first** before changing code
- **Don't cycle through attribute name guesses** — inspect the object
- **Prefer version-proof patterns** (module globals, dependency injection) over tightly
  coupling to SDK internals

## Important Notes

- Credentials loaded once at startup from env vars or `config/credentials.json`
- Agent must be "claimed" via Twitter verification before API use
- API key cannot be recovered after registration — save it immediately
- Rate limiting handled by Moltbook API (HTTP 429)
- llm-guard falls back gracefully to regex-only if unavailable
