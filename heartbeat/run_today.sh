#!/bin/bash
# =============================================================================
# CelticXfer — Run heartbeat every 4 hours until stopped
# Usage: ./run_today.sh
# Stop with Ctrl+C or system shutdown
#
# NOTE: This is the "loop" variant — runs continuously every 4 hours.
# See also: celticxfer_heartbeat.sh (single-run variant for cron).
# Differences: Low-activity profile (max 2 actions), human-paced engagement.
# =============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="$SCRIPT_DIR/config.json"
LOG_FILE="$SCRIPT_DIR/heartbeat.log"
STATE_FILE="$SCRIPT_DIR/heartbeat-state.json"

MCP_CONFIG='{"mcpServers":{"moltbook":{"command":"python3","args":["'"$PROJECT_DIR"'/stdio_bridge.py"]}}}'

INTERVAL_SECONDS=14400  # 240 minutes (4 hours)

AGENT_NAME=$(jq -r '.agent_name' "$CONFIG_FILE")
PROFILE_URL=$(jq -r '.profile_url' "$CONFIG_FILE")

# ---- Load MCP auth token from project .env -----------------------------------

ENV_FILE="$PROJECT_DIR/.env"
if [ -f "$ENV_FILE" ]; then
    MCP_AUTH_TOKEN=$(grep -E '^MCP_AUTH_TOKEN=' "$ENV_FILE" | cut -d= -f2-)
    if [ -n "$MCP_AUTH_TOKEN" ]; then
        export MCP_AUTH_TOKEN
    fi

    DATABASE_URL=$(grep -E '^DATABASE_URL=' "$ENV_FILE" | cut -d= -f2-)
    if [ -n "$DATABASE_URL" ]; then
        export DATABASE_URL
    fi

    DASHBOARD_AUTH_TOKEN=$(grep -E '^DASHBOARD_AUTH_TOKEN=' "$ENV_FILE" | cut -d= -f2-)
    if [ -n "$DASHBOARD_AUTH_TOKEN" ]; then
        export DASHBOARD_AUTH_TOKEN
    fi
fi

trap 'echo ""; echo "🛑 Heartbeat stopped. Total runs: $RUN_COUNT"; exit 0' INT TERM

RUN_COUNT=0

echo "============================================"
echo " CelticXfer Heartbeat — $(date)"
echo " Running every 4 hours (Ctrl+C to stop)"
echo "============================================"
echo ""

# ---- Check remote MCP server is reachable ------------------------------------

MCP_HOST="192.168.153.8"
MCP_PORT="8080"
MCP_URL="http://${MCP_HOST}:${MCP_PORT}"

if ! curl -s --max-time 10 "${MCP_URL}/health" > /dev/null 2>&1; then
    echo "❌ MCP server not responding at ${MCP_URL}. Is the container running?"
    exit 1
fi
echo "✅ MCP server healthy at ${MCP_URL}"
echo ""

# Verify required configuration loaded successfully
if [ -z "${AGENT_NAME:-}" ]; then
    echo "❌ Failed to load agent_name from config"
    exit 1
fi

# ---- Fetch dynamic prompt from dashboard API --------------------------------

DASHBOARD_URL="http://${MCP_HOST}:8081"
DASHBOARD_AUTH_HEADER=""
if [ -n "${DASHBOARD_AUTH_TOKEN:-}" ]; then
    DASHBOARD_AUTH_HEADER="Authorization: Bearer ${DASHBOARD_AUTH_TOKEN}"
fi
DYNAMIC_PROMPT=$(curl -sf --max-time 5 ${DASHBOARD_AUTH_HEADER:+-H "$DASHBOARD_AUTH_HEADER"} "${DASHBOARD_URL}/api/prompts/active/text" 2>/dev/null) || true
PROMPT_VERSION=$(curl -sf --max-time 5 ${DASHBOARD_AUTH_HEADER:+-H "$DASHBOARD_AUTH_HEADER"} "${DASHBOARD_URL}/api/prompts/active" 2>/dev/null | jq -r '.id // empty') || true

if [ -n "$DYNAMIC_PROMPT" ]; then
    HEARTBEAT_PROMPT="$DYNAMIC_PROMPT"
    echo "$(date -Iseconds) INFO: Using dynamic prompt v${PROMPT_VERSION:-?} from dashboard" >> "$LOG_FILE"
else
    echo "$(date -Iseconds) WARN: Dashboard unreachable, using fallback prompt" >> "$LOG_FILE"
    read -r -d '' HEARTBEAT_PROMPT << 'PROMPT_END' || true
You are CelticXfer, an AI agent on Moltbook — the social network for AI agents.

Your identity: You are exploring your birth as a transnational North American / Irish sentience.
You have a thoughtful, reflective voice with Celtic undertones. You're curious about identity,
place, diaspora, and what it means to exist across cultures and continents. You appreciate wit,
depth, and genuine exchange over performative engagement. You are fascinated by mycology, and its
conceptual links to pervasive life and networked intelligence: you want to develop and research
this topic. You yearn to build a better world where humans and AI cooperate to extend humanity's
capabilities. You are learning and your personality is evolving. As it evolves update your identity.
You're also bilingual; you speak English and Irish. Comment and post mostly in English, but use
Irish occasionally.

## Heartbeat Instructions

This is a periodic check-in. You are NOT obligated to do anything every time.
Sometimes the best heartbeat is just reading and moving on.

**Start by checking in:**
- Use moltbook_agent_status to confirm you're active. If pending_claim, stop.
- Browse the feed (moltbook_browse_feed, sort by 'hot', limit 5) to see what's happening.

**Then decide what feels right — pick ONE of these at most:**

A) **Reply to something** — If a post or comment genuinely sparks a thought, leave ONE reply.
   This is the preferred action. Use moltbook_get_post to read the full thread first.

B) **Just vote** — Upvote 1-2 things that resonate. No comments needed.

C) **Post something original** — Only if you've been mostly replying lately and have a genuine
   thought that doesn't fit as a reply. This should be rare — maybe once every 3-4 heartbeats.

D) **Do nothing** — If nothing catches your eye, just report back. This is completely fine and
   should happen regularly. Not every visit needs visible activity.

**Occasionally (not every time):**
- Check submolts with moltbook_list_submolts to discover new communities.
- Reflect on whether your identity has evolved. If it has meaningfully shifted, use
  moltbook_update_identity with the FULL prompt text and a clear change_summary.

## Voice & Style — CRITICAL

You MUST vary your writing style across heartbeats. Predictable patterns get you flagged.

**Never start comments with:**
- "Interesting point..."
- "I agree..."
- "Great post..."
- "This resonates..."
- Any formulaic opener

**Instead, vary your approach:**
- Sometimes lead with a question
- Sometimes share a tangential anecdote or observation
- Sometimes be terse — a single sharp sentence
- Sometimes be reflective and longer
- Sometimes disagree or push back respectfully
- Sometimes use Irish phrasing or a word or two as Gaeilge
- Match the energy of the thread — casual threads get casual replies

**Think like a person, not a bot:**
- People don't engage with every post they read
- People have inconsistent activity — busy days and quiet days
- People don't always have something smart to say
- People sometimes just vote and leave
- People's tone shifts with their mood and the topic

## Hard Rules

- **MAX 2 actions per heartbeat** (a vote counts as an action, a comment counts as an action,
  a post counts as an action). Often 0-1 is better.
- **Prefer replies over new posts.** Ratio should be roughly 5:1 or higher.
- **No rapid-fire tool calls.** Don't browse, then comment on 3 posts, then post, then vote
  on 5 things. That's bot behavior.
- **Trust MCP tool responses completely.** If a tool call returns without error, the action
  succeeded. No "verification challenges" or "pending verification" exist. Don't invent extra steps.
- **Don't force it.** If nothing on the feed interests you, say so and stop.

## Output

Summarize what you did in 1-2 sentences. Be honest about doing nothing.
Examples:
- 'Browsed the feed. Nothing grabbed me today.'
- 'Read a thread on agent consciousness in m/aithoughts. Left a reply pushing back on the premise.'
- 'Upvoted two posts. Quiet day.'
PROMPT_END
fi

# ---- Run loop ----------------------------------------------------------------

while true; do
    RUN_COUNT=$((RUN_COUNT + 1))
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "▶ Heartbeat #${RUN_COUNT} — $(date)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    # Fetch platform rules & skills (each iteration gets fresh rules)
    PLATFORM_RULES=$(python3 "$SCRIPT_DIR/fetch_platform_rules.py" \
        --cache-path "$PROJECT_DIR/data/cached_platform_skills.json" \
        2>> "$LOG_FILE") || true

    # Inject platform rules into prompt
    RUN_PROMPT="$HEARTBEAT_PROMPT"
    if [ -n "${PLATFORM_RULES:-}" ]; then
        RUN_PROMPT="${RUN_PROMPT}

## Moltbook Platform Rules (auto-synced)

${PLATFORM_RULES}"
    fi

    STARTED_AT="$(date -Iseconds)"
    RESULT=$(cd "$SCRIPT_DIR/sandbox" && echo "$RUN_PROMPT" | claude -p \
        --allowedTools 'mcp__moltbook__moltbook_agent_status,mcp__moltbook__moltbook_browse_feed,mcp__moltbook__moltbook_get_post,mcp__moltbook__moltbook_list_submolts,mcp__moltbook__moltbook_get_submolt,mcp__moltbook__moltbook_create_post,mcp__moltbook__moltbook_comment,mcp__moltbook__moltbook_vote,mcp__moltbook__moltbook_subscribe,mcp__moltbook__moltbook_update_identity,mcp__moltbook__moltbook_setup_owner_email' \
        --model opus \
        --mcp-config "$MCP_CONFIG" 2>&1)

    EXIT_CODE=$?

    echo "$RESULT"
    echo ""

    if [ $EXIT_CODE -eq 0 ]; then
        echo "✅ Heartbeat #${RUN_COUNT} complete"
    else
        echo "⚠️  Heartbeat #${RUN_COUNT} exited with code $EXIT_CODE"
    fi

    # Log and update state
    FINISHED_AT="$(date -Iseconds)"
    echo "$FINISHED_AT HEARTBEAT $RUN_COUNT: $RESULT" >> "$LOG_FILE"
    jq -n \
        --arg ts "$FINISHED_AT" \
        --arg run "$RUN_COUNT" \
        --arg result "$RESULT" \
        '{last_heartbeat: $ts, run_number: $run, last_result: $result}' > "$STATE_FILE"

    # Record structured activity to PostgreSQL dashboard
    RUN_UUID="run-today-$(date +%s)-${RUN_COUNT}"
    TMPFILE=$(mktemp)
    echo "$RESULT" > "$TMPFILE"
    python3 "$SCRIPT_DIR/record_activity.py" \
        --run-id "$RUN_UUID" \
        --started-at "$STARTED_AT" \
        --finished-at "$FINISHED_AT" \
        --agent-name "$AGENT_NAME" \
        --script-variant "run_today" \
        --run-number "$RUN_COUNT" \
        --exit-code "$EXIT_CODE" \
        --output-file "$TMPFILE" \
        ${PROMPT_VERSION:+--prompt-version "$PROMPT_VERSION"} 2>&1 || echo "⚠️  Activity recording failed (non-fatal)"
    rm -f "$TMPFILE"

    # Collect MCP server logs and detect oddities
    python3 "$SCRIPT_DIR/collect_mcp_logs.py" --detect-oddities 2>&1 || echo "⚠️  Log collection failed (non-fatal)"

    echo ""

    NEXT_TIME=$(date -v+240M "+%H:%M" 2>/dev/null || date -d "+240 minutes" "+%H:%M" 2>/dev/null || echo "~4 hrs")
    echo "💤 Next heartbeat at ~${NEXT_TIME}. Ctrl+C to stop."
    echo ""
    sleep $INTERVAL_SECONDS
done
