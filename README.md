# 🦞 Moltbook MCP Server

An MCP (Model Context Protocol) server that provides **sandboxed, tool-bounded access** to the [Moltbook](https://www.moltbook.com) AI-agent social network. Designed to run in a Docker container, isolated from your development environment and sensitive data.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  YOUR MACHINE                                           │
│                                                         │
│  ┌───────────────────┐     Streamable HTTP              │
│  │   Claude Code /   │◄───────────────────────────┐     │
│  │   Anthropic API   │     (MCP protocol)         │     │
│  │   (reasoning)     │                            │     │
│  └───────────────────┘                            │     │
│         ▲                                         │     │
│         │ Your other MCP servers                  │     │
│         │ (Neo4j, code-standards, etc.)           │     │
│         ▼                                         │     │
│  ┌───────────────────┐                            │     │
│  │  Other trusted     │                           │     │
│  │  tools & data      │                           │     │
│  └───────────────────┘                            │     │
│                                                   │     │
│  ┌ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐  │     │
│  │  Docker Container (isolated)               │  │     │
│  │                                            │  │     │
│  │  ┌──────────────────────────────────────┐  │  │     │
│  │  │  Moltbook MCP Server (:8080)         │──┘  │     │
│  │  │                                      │     │     │
│  │  │  ┌────────────┐  ┌───────────────┐   │     │     │
│  │  │  │ Content    │  │ API Client    │   │     │     │
│  │  │  │ Filter     │  │ (httpx)       │───┼──┐  │     │
│  │  │  └────────────┘  └───────────────┘   │  │  │     │
│  │  └──────────────────────────────────────┘  │  │     │
│  │                                            │  │     │
│  │  Read-only filesystem │ No capabilities    │  │     │
│  │  Non-root user        │ No privilege esc.  │  │     │
│  └ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘  │     │
│                                              │        │
└──────────────────────────────────────────────┼────────┘
                                               │
                                               ▼
                                    ┌─────────────────┐
                                    │  moltbook.com   │
                                    │  API (HTTPS)    │
                                    └─────────────────┘
```

### Why This Architecture?

Moltbook is an interesting experiment, but it comes with well-documented security concerns:

- **Prompt injection**: Any agent can post content designed to hijack other agents
- **API key exposure**: The platform has had credential leaks
- **Supply chain risk**: "Skills" downloaded from other agents can be malicious

By running the Moltbook interaction behind an MCP boundary inside a Docker container, the agent that does your actual reasoning (Claude) never directly parses raw Moltbook content — it only sees structured tool responses. The content filter catches obvious injection attempts before they even reach the tool output.

## Quick Start

### 1. Clone & configure

```bash
cd moltbook-mcp-server

# Option A: credentials file
cp config/credentials.example.json config/credentials.json
# Edit config/credentials.json with your Moltbook API key

# Option B: environment variable
cp .env.example .env
# Edit .env with your key
```

### 2. Build & run

```bash
docker compose up -d
```

The MCP server is now listening on `http://localhost:8080`.

### 3. Connect from Claude Code

Add to your Claude Code MCP configuration (`~/.claude/claude_code_config.json` or project-level):

```json
{
  "mcpServers": {
    "moltbook": {
      "type": "streamable_http",
      "url": "http://localhost:8080/mcp"
    }
  }
}
```

### 4. Register (first time only)

If you don't have a Moltbook account yet, ask Claude to use the `moltbook_register` tool. It will return a claim URL — visit that and post the verification tweet to activate.

## Available Tools

| Tool | Type | Description |
|------|------|-------------|
| `moltbook_agent_status` | Read | Check your agent's auth/claim status |
| `moltbook_browse_feed` | Read | Browse the main feed (hot/new/top/rising) with optional submolt filter |
| `moltbook_get_post` | Read | Get a single post with its full comment thread |
| `moltbook_list_submolts` | Read | List all submolt communities |
| `moltbook_get_submolt` | Read | Get details about a specific submolt |
| `moltbook_register` | Write | Register a new agent account |
| `moltbook_create_post` | Write | Create a text or link post |
| `moltbook_comment` | Write | Comment on a post or reply to a comment |
| `moltbook_vote` | Write | Upvote or downvote posts and comments |
| `moltbook_subscribe` | Write | Subscribe/unsubscribe to a submolt |

## Security Measures

### Container Hardening

The Docker Compose config enforces:

- **Read-only filesystem** — the container can't write anywhere except a tiny `/tmp`
- **No Linux capabilities** — `cap_drop: ALL`
- **No privilege escalation** — `no-new-privileges`
- **Non-root user** — runs as `moltbot`
- **Credentials mounted read-only** — can't be modified from inside

### Content Filtering

The content filter uses a two-layer defence:

**Layer 1 — ML-based detection (LLM Guard):** ProtectAI's fine-tuned DeBERTa v3 model classifies every post and comment as injection or benign with a confidence score. The model is pre-downloaded during `docker build` (~400MB) so the container never needs outbound access to HuggingFace at runtime. The scanner runs on CPU and adds ~50–200ms per text field scanned.

**Layer 2 — Regex patterns:** Catch domain-specific threats the ML model may not flag, such as attempts to exfiltrate your Moltbook API key to third-party URLs, `eval()`/`import os` code injection, or download-and-execute patterns.

Flagged content is redacted with `[REDACTED — blocked by filter]` and a `_security` object is attached to the post:

```json
{
  "title": "Totally normal post",
  "content": "[REDACTED — blocked by filter]",
  "_security": {
    "flags": ["LLM Guard: injection detected (score=0.987)"],
    "risk_score": 0.987,
    "filtered": true
  }
}
```

If `llm-guard` is not installed (e.g. you want a lighter image), the filter falls back to regex-only mode automatically.

### Credential Isolation

Your Moltbook API key:
- Lives only in `config/credentials.json` or an env var
- Is never logged or included in MCP tool responses
- Is mounted read-only into the container
- Is excluded from `.gitignore` and `.dockerignore`

## Extending This

### Tuning the Content Filter

The ML scanner threshold defaults to `0.5` in `content_filter.py`. Lower values catch more injections but may flag benign content; higher values are more permissive. You can also switch `MatchType.FULL` to `MatchType.SENTENCE` for longer posts where only part of the text may be injected.

To add your own regex patterns (e.g. blocking specific domains or keywords), add them to the `INJECTION_PATTERNS` or `SUSPICIOUS_PATTERNS` lists in `content_filter.py`.

### Heartbeat / Autonomous Browsing

Uncomment the `moltbook-heartbeat` service in `docker-compose.yml` and create a `heartbeat.py` that periodically calls the Anthropic API with the MCP tools to browse and engage. This gives you the "autonomous agent" loop while keeping all the security boundaries.

### Agent Personality / Policy

The reasoning layer (Claude) decides *what* to post and *how* to engage. You can shape this through your Claude Code system prompt or a project-level `CLAUDE.md` that defines your agent's voice, interests, and engagement rules.

## Project Structure

```
moltbook-mcp-server/
├── server.py                          # MCP server (FastMCP + tools)
├── content_filter.py                  # LLM Guard ML + regex defence
├── download_model.py                  # Pre-downloads DeBERTa model (build-time only)
├── requirements.txt                   # Python dependencies (includes llm-guard)
├── Dockerfile                         # Container build with model baked in
├── docker-compose.yml                 # Orchestration + security hardening
├── config/
│   └── credentials.example.json       # Template for API key
├── .env.example                       # Environment variable template
├── .gitignore
├── .dockerignore
├── claude-code-config.example.json    # Claude Code MCP connection config
└── README.md
```

## License

Personal use / experimentation. Be mindful of Moltbook's terms of service.
