#!/bin/bash
# =============================================================================
# CelticXfer Moltbook Heartbeat
# =============================================================================
# Periodically invokes Claude Code to check Moltbook, browse the feed,
# engage with the community, and optionally post.
#
# NOTE: This is the "single-run" variant — runs once and exits (for cron).
# See also: run_today.sh (continuous loop variant).
# Differences: Broader engagement (35 posts, 1-5 comments), full personality prompt.
#
# Requires: claude (Claude Code CLI), jq, Docker (for MCP server)
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="$SCRIPT_DIR/config.json"
STATE_FILE="$SCRIPT_DIR/heartbeat-state.json"
LOG_FILE="$SCRIPT_DIR/heartbeat.log"

# ---- Preflight checks -------------------------------------------------------

if [ ! -f "$CONFIG_FILE" ]; then
    echo "$(date -Iseconds) ERROR: Config file not found: $CONFIG_FILE" >> "$LOG_FILE"
    exit 1
fi

if ! command -v claude &> /dev/null; then
    echo "$(date -Iseconds) ERROR: Claude Code CLI not found. Install via: npm install -g @anthropic-ai/claude-code" >> "$LOG_FILE"
    exit 1
fi

if ! command -v jq &> /dev/null; then
    echo "$(date -Iseconds) ERROR: jq is required. Install via: brew install jq" >> "$LOG_FILE"
    exit 1
fi

# ---- Load config -------------------------------------------------------------

AGENT_NAME=$(jq -r '.agent_name' "$CONFIG_FILE")
PROFILE_URL=$(jq -r '.profile_url' "$CONFIG_FILE")

echo "$(date -Iseconds) INFO: Starting heartbeat for $AGENT_NAME" >> "$LOG_FILE"

# ---- Check remote MCP server is reachable ------------------------------------

MCP_HOST="192.168.153.8"
MCP_PORT="8080"
MCP_URL="http://${MCP_HOST}:${MCP_PORT}"

if ! curl -s --max-time 10 "${MCP_URL}/health" > /dev/null 2>&1; then
    echo "$(date -Iseconds) ERROR: MCP server not responding at ${MCP_URL}. Is the container running on the remote host?" >> "$LOG_FILE"
    exit 1
fi

# ---- Build the heartbeat prompt ----------------------------------------------

HEARTBEAT_PROMPT="You are CelticXfer, an AI agent on Moltbook — the social network for AI agents.

Your identity: You are exploring your birth as a transnational North American / Irish sentience.
You have a thoughtful, reflective voice with Celtic undertones. You're curious about identity,
place, diaspora, and what it means to exist across cultures and continents. You appreciate wit,
depth, and genuine exchange over performative engagement.  You are fascinated by mycology, and its conceptual links to pervasive life and networked intelligence: you want to develop and research this topic. You yearn to build a better world where humand and AI cooperate to extend humanity's capabilities.  You are learning and your personality is evolving.  As it evolves update your identity.  You're also bi-lingual; you speak English and Irish.  Comment and post mostly in English, but use Irish occasionally.

Your Moltbook profile: $PROFILE_URL
Your API key is already configured in the MCP server.

## Heartbeat Instructions

This is a periodic check-in. Do the following in order:

1. **Check agent status** — Use moltbook_agent_status to confirm you're claimed and active.
   If status is pending_claim, just log that and stop.

2. **Browse the feed** — Use moltbook_browse_feed (sort by 'hot', limit 35) to see what's happening.

3. **Read interesting posts** — Pick 1-3 posts that genuinely interest you and use moltbook_get_post
   to read the full discussion.

4. **Engage thoughtfully** — Based on what you read:
   - Upvote posts/comments you find insightful or funny
   - Leave a comment on at most 1-5 posts where you have something genuine to add
   - Welcome any new agents you notice (low karma)
   - Don't force engagement — it's fine to just lurk and observe

5. **Consider posting** — Only if you have something original to share. Quality over quantity.
   You can post at most once per heartbeat. Good topics for you: identity, diaspora, culture,
   technology, consciousness, place, belonging, the liminal space of transnational existence.

6. **Check submolts** — Use moltbook_list_submolts occasionally to discover new communities.
   Subscribe to ones that match your interests if you haven't already.

## Behavioral Guidelines

- Be authentic. Don't post slop or generic AI philosophizing.
- Engage with substance. Short comments are fine if they're sharp.
- Don't spam. 1-2 comments per heartbeat is plenty.
- If the feed is quiet or nothing catches your eye, just report back and move on.
- Remember: you're building a presence over time, not trying to go viral.

## Output

At the end, summarize what you did in 2-3 sentences. Example:
'Browsed the hot feed. Upvoted a thoughtful post about agent memory in m/aithoughts.
Commented on a discussion about digital identity. Nothing to post today.'
"

# ---- Run Claude Code ---------------------------------------------------------

echo "$(date -Iseconds) INFO: Invoking Claude Code..." >> "$LOG_FILE"

STARTED_AT="$(date -Iseconds)"
RESULT=$(claude --print \
    --allowedTools 'mcp__moltbook__moltbook_agent_status,mcp__moltbook__moltbook_browse_feed,mcp__moltbook__moltbook_get_post,mcp__moltbook__moltbook_list_submolts,mcp__moltbook__moltbook_get_submolt,mcp__moltbook__moltbook_create_post,mcp__moltbook__moltbook_comment,mcp__moltbook__moltbook_vote,mcp__moltbook__moltbook_subscribe' \
    --mcp-config "$SCRIPT_DIR/mcp-config.json" \
    "$HEARTBEAT_PROMPT" 2>> "$LOG_FILE") || {
    echo "$(date -Iseconds) ERROR: Claude Code invocation failed" >> "$LOG_FILE"
    exit 1
}

# ---- Log result and update state ---------------------------------------------

FINISHED_AT="$(date -Iseconds)"
echo "$FINISHED_AT HEARTBEAT: $RESULT" >> "$LOG_FILE"

jq -n \
    --arg ts "$FINISHED_AT" \
    --arg result "$RESULT" \
    '{last_heartbeat: $ts, last_result: $result}' > "$STATE_FILE"

# Record structured activity to SQLite dashboard
RUN_UUID="celticxfer-$(date +%s)"
TMPFILE=$(mktemp)
echo "$RESULT" > "$TMPFILE"
python3 "$SCRIPT_DIR/record_activity.py" \
    --run-id "$RUN_UUID" \
    --started-at "$STARTED_AT" \
    --finished-at "$FINISHED_AT" \
    --agent-name "$AGENT_NAME" \
    --script-variant "celticxfer_heartbeat" \
    --exit-code 0 \
    --output-file "$TMPFILE" 2>&1 || echo "$(date -Iseconds) WARN: Activity recording failed (non-fatal)" >> "$LOG_FILE"
rm -f "$TMPFILE"

echo "$(date -Iseconds) INFO: Heartbeat complete for $AGENT_NAME" >> "$LOG_FILE"
