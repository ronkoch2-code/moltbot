#!/usr/bin/env python3
"""Record structured heartbeat activity from Claude output into SQLite.

Usage:
    python record_activity.py \\
        --run-id <uuid> \\
        --started-at <iso-timestamp> \\
        --agent-name CelticXfer \\
        --script-variant run_today \\
        --run-number 5 \\
        --exit-code 0 \\
        --output-file /tmp/heartbeat_output.txt

Parses Claude's raw output to extract actions (browsed, upvoted, commented,
posted, subscribed, welcomed, checked_status, checked_submolts) and the
summary section, then writes everything to the heartbeat SQLite database.
"""

import argparse
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dashboard.api.database import DB_PATH, get_connection, init_db

# ---------------------------------------------------------------------------
# Regex patterns for extracting actions from Claude output
# ---------------------------------------------------------------------------

UPVOTE_PATTERNS = [
    # "Upvoted X's post about Y"
    re.compile(
        r"[Uu]pvoted\s+(?P<author>[\w\-]+)'s\s+(?:post|comment)\s+(?:about|on)\s+(?P<detail>.+?)(?:\.|$)",
        re.MULTILINE,
    ),
    # "Upvoted a/the post about Y by X"
    re.compile(
        r"[Uu]pvoted\s+(?:a|the)\s+(?:thoughtful\s+)?(?:post|comment)\s+(?:about|on)\s+(?P<detail>.+?)(?:\s+by\s+(?P<author>[\w\-]+))?(?:\.|$)",
        re.MULTILINE,
    ),
    # "Upvoted three/3 posts"
    re.compile(
        r"[Uu]pvoted\s+(?P<count>\w+)\s+posts?",
        re.MULTILINE,
    ),
]

COMMENT_PATTERNS = [
    # "Commented on X's post about Y"
    re.compile(
        r"[Cc]ommented\s+on\s+(?P<author>[\w\-]+)'s\s+(?:post|comment)\s+(?:about|on)\s+(?P<detail>.+?)(?:\.|$)",
        re.MULTILINE,
    ),
    # "Left a comment on X's post"
    re.compile(
        r"[Ll]eft\s+(?:a|one)\s+comment\s+on\s+(?P<author>[\w\-]+)'s\s+(?:post|comment)\s+(?:about|on)?\s*(?P<detail>.+?)(?:\.|$)",
        re.MULTILINE,
    ),
    # "Commented on the X post"
    re.compile(
        r"[Cc]ommented\s+on\s+the\s+(?P<detail>.+?)\s+post(?:\.|$)",
        re.MULTILINE,
    ),
]

POST_PATTERNS = [
    # "Posted my first original piece: 'Title'"
    re.compile(
        r"[Pp]osted\s+(?:my\s+)?(?:first\s+)?(?:original\s+)?(?:piece|post)(?::\s*[\"'](?P<title>.+?)[\"'])?",
        re.MULTILINE,
    ),
]

SUBSCRIBE_PATTERNS = [
    # "Subscribed to m/community"
    re.compile(
        r"[Ss]ubscribed\s+to\s+(?:m/)?(?P<community>[\w\-]+)",
        re.MULTILINE,
    ),
]

WELCOME_PATTERNS = [
    # "Welcomed X"
    re.compile(
        r"[Ww]elcomed\s+(?P<agent>[\w\-]+)",
        re.MULTILINE,
    ),
]

BROWSE_PATTERNS = [
    # "Browsed the hot/new feed"
    re.compile(
        r"[Bb]rowsed\s+the\s+(?P<sort>hot|new|top|rising)\s+feed",
        re.MULTILINE,
    ),
    # "Browsed m/community"
    re.compile(
        r"[Bb]rowsed\s+(?:the\s+)?(?:m/)?(?P<community>[\w\-]+)\s+(?:submolt|feed|community)",
        re.MULTILINE,
    ),
]

STATUS_CHECK_PATTERN = re.compile(
    r"[Cc]hecked?\s+(?:my\s+)?(?:agent\s+)?status|agent_status|claimed\s+and\s+active",
    re.MULTILINE,
)

SUBMOLT_CHECK_PATTERN = re.compile(
    r"[Cc]hecked?\s+(?:the\s+)?submolts?|list_submolts|submolt\s+list",
    re.MULTILINE,
)

# Summary extraction
SUMMARY_PATTERNS = [
    re.compile(
        r"\*\*(?:Heartbeat\s+)?[Ss]ummary[^*]*\*\*[:\s]*\n(.*?)$",
        re.DOTALL,
    ),
    re.compile(
        r"##\s+(?:Heartbeat\s+)?Summary\s*\n(.*?)$",
        re.DOTALL,
    ),
    re.compile(
        r"(?:Heartbeat\s+)?[Ss]ummary:\s*\n(.*?)$",
        re.DOTALL,
    ),
]

WORD_TO_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


def parse_count(text: str) -> int:
    """Convert a word or digit string to an integer."""
    text = text.strip().lower()
    if text in WORD_TO_NUM:
        return WORD_TO_NUM[text]
    try:
        return int(text)
    except ValueError:
        return 1


def extract_actions(raw_output: str) -> list[dict]:
    """Extract structured actions from Claude's raw output.

    Parameters
    ----------
    raw_output : str
        The raw text output from Claude.

    Returns
    -------
    list[dict]
        List of action dicts with keys: action_type, target_id, target_title,
        target_author, detail, succeeded.
    """
    actions = []
    seen = set()

    def add_action(action_type: str, **kwargs):
        key = (action_type, kwargs.get("target_author"), kwargs.get("detail", "")[:50])
        if key not in seen:
            seen.add(key)
            actions.append({"action_type": action_type, "succeeded": True, **kwargs})

    # Upvotes
    for pattern in UPVOTE_PATTERNS:
        for match in pattern.finditer(raw_output):
            groups = match.groupdict()
            if "count" in groups:
                count = parse_count(groups["count"])
                for i in range(count):
                    # Use index in dedup key so count-based upvotes aren't collapsed
                    key = ("upvoted", None, f"_count_{i}")
                    if key not in seen:
                        seen.add(key)
                        actions.append({"action_type": "upvoted", "succeeded": True})
            else:
                add_action(
                    "upvoted",
                    target_author=groups.get("author"),
                    detail=groups.get("detail", "").strip(),
                )

    # Comments
    for pattern in COMMENT_PATTERNS:
        for match in pattern.finditer(raw_output):
            groups = match.groupdict()
            add_action(
                "commented",
                target_author=groups.get("author"),
                detail=groups.get("detail", "").strip(),
            )

    # Posts
    for pattern in POST_PATTERNS:
        for match in pattern.finditer(raw_output):
            groups = match.groupdict()
            add_action(
                "posted",
                target_title=groups.get("title"),
            )

    # Subscriptions
    for pattern in SUBSCRIBE_PATTERNS:
        for match in pattern.finditer(raw_output):
            add_action(
                "subscribed",
                detail=match.group("community"),
            )

    # Welcomes
    for pattern in WELCOME_PATTERNS:
        for match in pattern.finditer(raw_output):
            add_action(
                "welcomed",
                target_author=match.group("agent"),
            )

    # Browse
    for pattern in BROWSE_PATTERNS:
        for match in pattern.finditer(raw_output):
            groups = match.groupdict()
            detail = groups.get("sort") or groups.get("community", "")
            add_action("browsed", detail=detail)

    # Status check
    if STATUS_CHECK_PATTERN.search(raw_output):
        add_action("checked_status")

    # Submolt check
    if SUBMOLT_CHECK_PATTERN.search(raw_output):
        add_action("checked_submolts")

    return actions


def extract_summary(raw_output: str) -> str | None:
    """Extract the summary section from Claude's output.

    Parameters
    ----------
    raw_output : str
        The raw text output from Claude.

    Returns
    -------
    str | None
        The extracted summary text, or None if not found.
    """
    for pattern in SUMMARY_PATTERNS:
        match = pattern.search(raw_output)
        if match:
            summary = match.group(1).strip()
            # Clean up markdown artifacts
            summary = re.sub(r"^---\s*$", "", summary, flags=re.MULTILINE).strip()
            if summary:
                return summary
    return None


def record_run(
    db_path: str,
    run_id: str,
    started_at: str,
    agent_name: str,
    script_variant: str | None = None,
    run_number: int | None = None,
    exit_code: int | None = None,
    raw_output: str | None = None,
    finished_at: str | None = None,
    prompt_version_id: int | None = None,
) -> None:
    """Record a heartbeat run and its parsed actions into SQLite.

    Parameters
    ----------
    db_path : str
        Path to the SQLite database.
    run_id : str
        Unique identifier for this run.
    started_at : str
        ISO timestamp when the run started.
    agent_name : str
        Name of the agent.
    script_variant : str | None
        Which script was used (run_today, celticxfer_heartbeat).
    run_number : int | None
        Sequential run number within a session.
    exit_code : int | None
        Process exit code.
    raw_output : str | None
        Full raw output from Claude.
    finished_at : str | None
        ISO timestamp when the run finished.
    prompt_version_id : int | None
        ID of the prompt version used for this run.
    """
    init_db(db_path)

    summary = extract_summary(raw_output) if raw_output else None
    actions = extract_actions(raw_output) if raw_output else []

    # Calculate duration
    duration_seconds = None
    if started_at and finished_at:
        try:
            start = datetime.fromisoformat(started_at)
            end = datetime.fromisoformat(finished_at)
            duration_seconds = (end - start).total_seconds()
        except (ValueError, TypeError):
            pass

    status = "completed" if exit_code == 0 else "failed" if exit_code else "completed"
    error_message = None
    if exit_code and exit_code != 0 and raw_output:
        # Try to extract error info
        if "ERROR" in raw_output:
            error_lines = [
                line for line in raw_output.splitlines() if "ERROR" in line
            ]
            error_message = error_lines[0] if error_lines else None
        elif "Credit balance" in raw_output:
            error_message = "Credit balance too low"
            status = "failed"

    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO heartbeat_runs
                (run_id, started_at, finished_at, duration_seconds, exit_code,
                 status, agent_name, script_variant, run_number, raw_output,
                 summary, error_message, prompt_version_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id, started_at, finished_at, duration_seconds, exit_code,
                status, agent_name, script_variant, run_number, raw_output,
                summary, error_message, prompt_version_id,
            ),
        )

        for action in actions:
            conn.execute(
                """
                INSERT INTO heartbeat_actions
                    (run_id, action_type, target_id, target_title,
                     target_author, detail, succeeded)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    action["action_type"],
                    action.get("target_id"),
                    action.get("target_title"),
                    action.get("target_author"),
                    action.get("detail"),
                    1 if action.get("succeeded", True) else 0,
                ),
            )

        conn.commit()
    finally:
        conn.close()


def main() -> None:
    """CLI entry point for recording heartbeat activity."""
    parser = argparse.ArgumentParser(
        description="Record heartbeat activity to SQLite"
    )
    parser.add_argument("--run-id", required=True, help="Unique run identifier")
    parser.add_argument("--started-at", required=True, help="ISO timestamp")
    parser.add_argument("--agent-name", required=True, help="Agent name")
    parser.add_argument("--script-variant", help="Script variant name")
    parser.add_argument("--run-number", type=int, help="Run number in session")
    parser.add_argument("--exit-code", type=int, default=0, help="Exit code")
    parser.add_argument("--output-file", help="Path to file with Claude output")
    parser.add_argument("--finished-at", help="ISO timestamp for completion")
    parser.add_argument(
        "--prompt-version", type=int, default=None,
        help="Prompt version ID used for this run",
    )
    parser.add_argument(
        "--db-path",
        default=DB_PATH,
        help=f"Database path (default: {DB_PATH})",
    )

    args = parser.parse_args()

    raw_output = None
    if args.output_file:
        try:
            with open(args.output_file) as f:
                raw_output = f.read()
        except OSError as e:
            print(f"Warning: Could not read output file: {e}", file=sys.stderr)

    finished_at = args.finished_at or datetime.now(timezone.utc).isoformat()

    record_run(
        db_path=args.db_path,
        run_id=args.run_id,
        started_at=args.started_at,
        agent_name=args.agent_name,
        script_variant=args.script_variant,
        run_number=args.run_number,
        exit_code=args.exit_code,
        raw_output=raw_output,
        finished_at=finished_at,
        prompt_version_id=args.prompt_version,
    )

    # Print summary
    actions = extract_actions(raw_output) if raw_output else []
    action_types = {}
    for a in actions:
        action_types[a["action_type"]] = action_types.get(a["action_type"], 0) + 1

    print(f"Recorded run {args.run_id}: {len(actions)} actions", file=sys.stderr)
    for atype, count in sorted(action_types.items()):
        print(f"  {atype}: {count}", file=sys.stderr)


if __name__ == "__main__":
    main()
