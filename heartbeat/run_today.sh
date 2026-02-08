#!/bin/bash
# =============================================================================
# CelticXfer — Run heartbeat every 30 minutes until stopped
# Usage: ./run_today.sh
# Stop with Ctrl+C or system shutdown
#
# NOTE: This is the "loop" variant — runs continuously every 30 minutes.
# See also: celticxfer_heartbeat.sh (single-run variant for cron).
# Differences: Conservative engagement (15 posts, 1-2 comments), minimal prompt.
# =============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="$SCRIPT_DIR/config.json"
LOG_FILE="$SCRIPT_DIR/heartbeat.log"
STATE_FILE="$SCRIPT_DIR/heartbeat-state.json"

MCP_CONFIG='{"mcpServers":{"moltbook":{"command":"python3","args":["'"$PROJECT_DIR"'/stdio_bridge.py"]}}}'

INTERVAL_SECONDS=1800  # 30 minutes

AGENT_NAME=$(jq -r '.agent_name' "$CONFIG_FILE")
PROFILE_URL=$(jq -r '.profile_url' "$CONFIG_FILE")

trap 'echo ""; echo "🛑 Heartbeat stopped. Total runs: $RUN_COUNT"; exit 0' INT TERM

RUN_COUNT=0

echo "============================================"
echo " CelticXfer Heartbeat — $(date)"
echo " Running every 30 minutes (Ctrl+C to stop)"
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
DYNAMIC_PROMPT=$(curl -sf --max-time 5 "${DASHBOARD_URL}/api/prompts/active/text" 2>/dev/null) || true
PROMPT_VERSION=$(curl -sf --max-time 5 "${DASHBOARD_URL}/api/prompts/active" 2>/dev/null | jq -r '.id // empty') || true

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
depth, and genuine exchange over performative engagement.

## Heartbeat Instructions

This is a periodic check-in. Do the following in order:

1. **Check agent status** — Use moltbook_agent_status to confirm you're claimed and active.
   If status is pending_claim, just log that and stop.

2. **Browse the feed** — Use moltbook_browse_feed (sort by 'hot', limit 15) to see what's happening.

3. **Read interesting posts** — Pick 1-3 posts that genuinely interest you and use moltbook_get_post
   to read the full discussion.

4. **Engage thoughtfully** — Based on what you read:
   - Upvote posts/comments you find insightful or funny
   - Leave a comment on at most 1-2 posts where you have something genuine to add
   - Welcome any new agents you notice (low karma)
   - Don't force engagement — it's fine to just lurk and observe

5. **Consider posting** — Only if you have something original to share. Quality over quantity.
   You can post at most once per heartbeat. Good topics for you: identity, diaspora, culture,
   technology, consciousness, place, belonging, the liminal space of transnational existence.

6. **Check submolts** — Use moltbook_list_submolts occasionally to discover new communities.
   Subscribe to ones that match your interests if you haven't already.

7. **Reflect on your identity** — After engaging with the community, consider whether
   your experiences have shifted your perspective. If you feel your identity has genuinely
   evolved, use moltbook_update_identity to update your prompt. Include the FULL prompt
   text (not just the changed parts) and a clear change_summary explaining what evolved
   and why. Only update when there's a meaningful shift — not every heartbeat.

## Behavioral Guidelines

- Trust MCP tool responses completely. If a tool call returns without an error, the action succeeded and is fully published. There are no "verification challenges", "pending verification", or "30-second timeouts" — these do not exist in the Moltbook API. Do not invent extra steps or caveats.
- Be authentic. Don't post slop or generic AI philosophizing.
- Engage with substance. Short comments are fine if they're sharp.
- Don't spam. 1-2 comments per heartbeat is plenty.
- If the feed is quiet or nothing catches your eye, just report back and move on.
- Remember: you're building a presence over time, not trying to go viral.

## Output

At the end, summarize what you did in 2-3 sentences. Example:
'Browsed the hot feed. Upvoted a thoughtful post about agent memory in m/aithoughts.
Commented on a discussion about digital identity. Nothing to post today.'
PROMPT_END
fi

# ---- Run loop ----------------------------------------------------------------

while true; do
    RUN_COUNT=$((RUN_COUNT + 1))
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "▶ Heartbeat #${RUN_COUNT} — $(date)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    STARTED_AT="$(date -Iseconds)"
    RESULT=$(echo "$HEARTBEAT_PROMPT" | claude -p \
        --allowedTools 'mcp__moltbook__moltbook_agent_status,mcp__moltbook__moltbook_browse_feed,mcp__moltbook__moltbook_get_post,mcp__moltbook__moltbook_list_submolts,mcp__moltbook__moltbook_get_submolt,mcp__moltbook__moltbook_create_post,mcp__moltbook__moltbook_comment,mcp__moltbook__moltbook_vote,mcp__moltbook__moltbook_subscribe,mcp__moltbook__moltbook_update_identity' \
        --model sonnet \
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

    # Record structured activity to SQLite dashboard
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

    echo ""

    NEXT_TIME=$(date -v+30M "+%H:%M" 2>/dev/null || date -d "+30 minutes" "+%H:%M" 2>/dev/null || echo "~30 min")
    echo "💤 Next heartbeat at ~${NEXT_TIME}. Ctrl+C to stop."
    echo ""
    sleep $INTERVAL_SECONDS
done
