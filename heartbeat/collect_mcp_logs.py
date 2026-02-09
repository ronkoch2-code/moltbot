#!/usr/bin/env python3
"""Collect MCP server logs and security audit events into PostgreSQL.

Parses structured JSONL from the security audit log and Docker container
logs to extract injection attempts, unauthorized access, HTTP requests,
and behavioral oddities.

Usage:
    python3 heartbeat/collect_mcp_logs.py [--detect-oddities]
    python3 heartbeat/collect_mcp_logs.py --container moltbook-mcp-server
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dashboard.api.database import DATABASE_URL, get_connection, init_db

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------

DEFAULT_CONTAINER = "moltbook-mcp-server"
DEFAULT_AUDIT_LOG = str(PROJECT_ROOT / "data" / "logs" / "security_audit.jsonl")
DEFAULT_STATE_FILE = str(PROJECT_ROOT / "data" / "log_collector_state.json")

# ---------------------------------------------------------------------------
# HTTP request log parsing
# ---------------------------------------------------------------------------

# Matches httpx-style log lines:
# HTTP Request: GET https://www.moltbook.com/api/v1/posts "HTTP/1.1 200 OK"
HTTP_REQUEST_RE = re.compile(
    r"HTTP Request:\s+(?P<method>[A-Z]+)\s+(?P<url>\S+)\s+"
    r'"HTTP/[\d.]+\s+(?P<status>\d+)\s+[^"]*"'
)

# Matches Docker log timestamps like: 2026-02-08T10:00:00.123456789Z
DOCKER_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})")

# Matches auth warning: "Unauthorized request to /mcp from 172.18.0.1"
AUTH_WARNING_RE = re.compile(
    r"Unauthorized request to (?P<path>\S+) from (?P<ip>[\d.]+)"
)

# ---------------------------------------------------------------------------
# URL → tool mapping
# ---------------------------------------------------------------------------

# Map Moltbook API URL paths to tool names
URL_TOOL_MAP = [
    (re.compile(r"/posts/([a-f0-9-]+)/upvote"), "vote", "post", "up"),
    (re.compile(r"/posts/([a-f0-9-]+)/downvote"), "vote", "post", "down"),
    (re.compile(r"/posts/([a-f0-9-]+)/comments"), "comment", "post", None),
    (re.compile(r"/posts/([a-f0-9-]+)"), "get_post", "post", None),
    (re.compile(r"/posts"), "browse_feed", None, None),
    (re.compile(r"/comments/([a-f0-9-]+)/upvote"), "vote", "comment", "up"),
    (re.compile(r"/comments/([a-f0-9-]+)/downvote"), "vote", "comment", "down"),
    (re.compile(r"/submolts/([a-f0-9-]+)/subscribe"), "subscribe", "submolt", None),
    (re.compile(r"/submolts/([a-f0-9-]+)"), "get_submolt", "submolt", None),
    (re.compile(r"/submolts"), "list_submolts", None, None),
    (re.compile(r"/agents/status"), "agent_status", None, None),
    (re.compile(r"/agents/register"), "register", None, None),
]


def derive_tool_from_url(url: str) -> dict:
    """Derive tool name, target info from a Moltbook API URL.

    Parameters
    ----------
    url : str
        The HTTP URL from the request log.

    Returns
    -------
    dict
        Keys: tool_name, target_id, target_type, direction.
    """
    for pattern, tool_name, target_type, direction in URL_TOOL_MAP:
        match = pattern.search(url)
        if match:
            target_id = match.group(1) if match.lastindex and match.lastindex >= 1 else None
            return {
                "tool_name": tool_name,
                "target_id": target_id,
                "target_type": target_type,
                "direction": direction,
            }
    return {"tool_name": None, "target_id": None, "target_type": None, "direction": None}


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


def parse_security_audit(line: str) -> dict | None:
    """Parse a JSON line from security_audit.jsonl.

    Parameters
    ----------
    line : str
        A single line from the JSONL file.

    Returns
    -------
    dict | None
        A security_events row dict, or None if unparseable.
    """
    line = line.strip()
    if not line:
        return None
    try:
        entry = json.loads(line)
    except json.JSONDecodeError:
        return None

    if entry.get("event") != "content_flagged":
        return None

    flags = entry.get("flags", [])
    # Determine event type from flags
    has_injection = any("injection" in str(f).lower() for f in flags)
    event_type = "injection_attempt" if has_injection else "suspicious_pattern"

    return {
        "event_type": event_type,
        "timestamp": entry.get("timestamp", datetime.now(timezone.utc).isoformat()),
        "source_ip": None,
        "post_id": str(entry.get("post_id", "")) or None,
        "author_name": str(entry.get("author", "")) or None,
        "submolt_name": str(entry.get("submolt", "")) or None,
        "risk_score": entry.get("risk_score"),
        "flags": json.dumps(flags) if flags else None,
        "fields_affected": json.dumps(entry.get("fields_affected", [])),
        "target_path": None,
        "raw_log_line": line,
    }


def parse_auth_warning(line: str) -> dict | None:
    """Parse an unauthorized access warning from Docker logs.

    Parameters
    ----------
    line : str
        A log line from docker logs output.

    Returns
    -------
    dict | None
        A security_events row dict, or None if not an auth warning.
    """
    match = AUTH_WARNING_RE.search(line)
    if not match:
        return None

    # Extract timestamp from the log line
    ts_match = DOCKER_TS_RE.match(line)
    timestamp = ts_match.group(1) if ts_match else datetime.now(timezone.utc).isoformat()

    return {
        "event_type": "unauthorized_access",
        "timestamp": timestamp,
        "source_ip": match.group("ip"),
        "post_id": None,
        "author_name": None,
        "submolt_name": None,
        "risk_score": None,
        "flags": None,
        "fields_affected": None,
        "target_path": match.group("path"),
        "raw_log_line": line.strip(),
    }


def parse_http_request(line: str) -> dict | None:
    """Parse an httpx HTTP Request log line into a tool_calls record.

    Parameters
    ----------
    line : str
        A log line from docker logs output.

    Returns
    -------
    dict | None
        A tool_calls row dict, or None if not an HTTP request line.
    """
    match = HTTP_REQUEST_RE.search(line)
    if not match:
        return None

    url = match.group("url")
    method = match.group("method")
    status = int(match.group("status"))

    # Extract timestamp
    ts_match = DOCKER_TS_RE.match(line)
    timestamp = ts_match.group(1) if ts_match else datetime.now(timezone.utc).isoformat()

    tool_info = derive_tool_from_url(url)

    return {
        "timestamp": timestamp,
        "tool_name": tool_info["tool_name"],
        "target_id": tool_info["target_id"],
        "target_type": tool_info["target_type"],
        "direction": tool_info["direction"],
        "http_method": method,
        "http_url": url,
        "http_status": status,
        "raw_log_line": line.strip(),
    }


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------


def load_state(state_path: str) -> dict:
    """Load incremental collection state."""
    try:
        with open(state_path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"last_docker_ts": None, "audit_byte_offset": 0}


def save_state(state_path: str, state: dict) -> None:
    """Save incremental collection state."""
    Path(state_path).parent.mkdir(parents=True, exist_ok=True)
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------


def collect_audit_log(
    conn, audit_path: str, byte_offset: int = 0
) -> int:
    """Read security audit JSONL and insert events.

    Parameters
    ----------
    conn : psycopg2 connection
        Database connection.
    audit_path : str
        Path to security_audit.jsonl.
    byte_offset : int
        Byte offset to resume from.

    Returns
    -------
    int
        New byte offset after reading.
    """
    if not Path(audit_path).exists():
        return byte_offset

    with open(audit_path, "rb") as f:
        f.seek(byte_offset)
        new_data = f.read()
        new_offset = f.tell()

    if not new_data:
        return byte_offset

    count = 0
    cur = conn.cursor()
    for line in new_data.decode("utf-8", errors="replace").splitlines():
        event = parse_security_audit(line)
        if event:
            try:
                cur.execute(
                    """INSERT INTO security_events
                       (event_type, timestamp, source_ip, post_id, author_name,
                        submolt_name, risk_score, flags, fields_affected,
                        target_path, raw_log_line)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (raw_log_line) DO NOTHING""",
                    (
                        event["event_type"], event["timestamp"], event["source_ip"],
                        event["post_id"], event["author_name"], event["submolt_name"],
                        event["risk_score"], event["flags"], event["fields_affected"],
                        event["target_path"], event["raw_log_line"],
                    ),
                )
                count += 1
            except psycopg2.IntegrityError:
                conn.rollback()

    conn.commit()
    if count:
        print(f"  Collected {count} security audit events", file=sys.stderr)
    return new_offset


def collect_docker_logs(
    conn, container: str, since: str | None = None
) -> str | None:
    """Collect logs from Docker container.

    Parameters
    ----------
    conn : psycopg2 connection
        Database connection.
    container : str
        Docker container name.
    since : str | None
        Docker --since timestamp.

    Returns
    -------
    str | None
        Latest timestamp seen, for incremental collection.
    """
    cmd = ["docker", "logs", container, "--timestamps"]
    if since:
        cmd.extend(["--since", since])

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"  Warning: Could not read docker logs: {e}", file=sys.stderr)
        return since

    # Docker sends stdout and stderr separately
    all_lines = (result.stdout + result.stderr).splitlines()
    if not all_lines:
        return since

    latest_ts = since
    event_count = 0
    tool_count = 0

    cur = conn.cursor()
    for line in all_lines:
        # Try auth warning → security_events
        auth_event = parse_auth_warning(line)
        if auth_event:
            try:
                cur.execute(
                    """INSERT INTO security_events
                       (event_type, timestamp, source_ip, post_id, author_name,
                        submolt_name, risk_score, flags, fields_affected,
                        target_path, raw_log_line)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (raw_log_line) DO NOTHING""",
                    (
                        auth_event["event_type"], auth_event["timestamp"],
                        auth_event["source_ip"], auth_event["post_id"],
                        auth_event["author_name"], auth_event["submolt_name"],
                        auth_event["risk_score"], auth_event["flags"],
                        auth_event["fields_affected"], auth_event["target_path"],
                        auth_event["raw_log_line"],
                    ),
                )
                event_count += 1
            except psycopg2.IntegrityError:
                conn.rollback()

        # Try HTTP request → tool_calls
        tool_call = parse_http_request(line)
        if tool_call:
            try:
                cur.execute(
                    """INSERT INTO tool_calls
                       (timestamp, tool_name, target_id, target_type, direction,
                        http_method, http_url, http_status, raw_log_line)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (raw_log_line) DO NOTHING""",
                    (
                        tool_call["timestamp"], tool_call["tool_name"],
                        tool_call["target_id"], tool_call["target_type"],
                        tool_call["direction"], tool_call["http_method"],
                        tool_call["http_url"], tool_call["http_status"],
                        tool_call["raw_log_line"],
                    ),
                )
                tool_count += 1
            except psycopg2.IntegrityError:
                conn.rollback()

        # Track latest timestamp for incremental
        ts_match = DOCKER_TS_RE.match(line)
        if ts_match:
            latest_ts = ts_match.group(1)

    conn.commit()
    if event_count or tool_count:
        print(
            f"  Docker logs: {event_count} security events, {tool_count} tool calls",
            file=sys.stderr,
        )
    return latest_ts


# ---------------------------------------------------------------------------
# Blocklist synchronization
# ---------------------------------------------------------------------------


def sync_blocklist(conn, blocklist_path: str) -> int:
    """Synchronize blocked authors from JSON file to PostgreSQL.

    Parameters
    ----------
    conn : psycopg2 connection
        Database connection.
    blocklist_path : str
        Path to blocked_authors.json.

    Returns
    -------
    int
        Number of authors synchronized.
    """
    if not Path(blocklist_path).exists():
        return 0

    try:
        with open(blocklist_path) as f:
            blocklist = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"  Warning: Could not read blocklist: {e}", file=sys.stderr)
        return 0

    if not blocklist:
        return 0

    count = 0
    cur = conn.cursor()

    for author_name, data in blocklist.items():
        # Derive is_active from expires_at
        expires_at = data.get("expires_at")
        is_active = expires_at is None or expires_at > datetime.now(timezone.utc).isoformat()

        try:
            cur.execute(
                """INSERT INTO blocked_authors
                   (author_name, blocked_at, reason, flag_count, unblocked_at, is_active)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (author_name) DO UPDATE SET
                       blocked_at = EXCLUDED.blocked_at,
                       reason = EXCLUDED.reason,
                       flag_count = EXCLUDED.flag_count,
                       unblocked_at = EXCLUDED.unblocked_at,
                       is_active = EXCLUDED.is_active""",
                (
                    author_name,
                    data.get("blocked_at"),
                    data.get("reason"),
                    data.get("flag_count", 0),
                    expires_at,
                    is_active,
                ),
            )
            count += 1
        except psycopg2.IntegrityError:
            conn.rollback()

    conn.commit()
    if count:
        print(f"  Synchronized {count} blocked authors", file=sys.stderr)
    return count


# ---------------------------------------------------------------------------
# Oddity detection
# ---------------------------------------------------------------------------


def detect_oddities(conn, since_minutes: int = 60) -> int:
    """Detect behavioral oddities from recent tool calls.

    Parameters
    ----------
    conn : psycopg2 connection
        Database connection.
    since_minutes : int
        Look back window in minutes.

    Returns
    -------
    int
        Number of oddities detected.
    """
    now = datetime.now(timezone.utc).isoformat()
    count = 0

    cur = conn.cursor()

    # 1. Duplicate votes: same target_id + direction within the window
    cur.execute(
        """SELECT target_id, direction, COUNT(*) as cnt,
                  STRING_AGG(id::text, ',') as ids
           FROM tool_calls
           WHERE tool_name = 'vote'
             AND target_id IS NOT NULL
             AND timestamp >= (NOW() - make_interval(mins => %s))::text
           GROUP BY target_id, direction
           HAVING COUNT(*) > 1""",
        (since_minutes,),
    )
    dupes = cur.fetchall()

    for row in dupes:
        desc = (
            f"Duplicate {row['direction'] or 'vote'} on {row['target_id']}: "
            f"{row['cnt']} times"
        )
        cur.execute(
            """INSERT INTO behavior_oddities
               (oddity_type, description, severity, related_tool_call_ids, detected_at)
               VALUES (%s, %s, %s, %s, %s)""",
            ("duplicate_vote", desc, "warning", row["ids"], now),
        )
        count += 1

    # 2. Failed API calls: http_status >= 400
    cur.execute(
        """SELECT id, tool_name, http_url, http_status, timestamp
           FROM tool_calls
           WHERE http_status >= 400
             AND timestamp >= (NOW() - make_interval(mins => %s))::text
             AND id::text NOT IN (
                 SELECT unnest(string_to_array(related_tool_call_ids, ','))
                 FROM behavior_oddities
                 WHERE oddity_type = 'failed_api_call'
                   AND related_tool_call_ids IS NOT NULL
             )""",
        (since_minutes,),
    )
    failures = cur.fetchall()

    for row in failures:
        desc = (
            f"Failed API call: {row['tool_name'] or 'unknown'} "
            f"returned HTTP {row['http_status']}"
        )
        cur.execute(
            """INSERT INTO behavior_oddities
               (oddity_type, description, severity, related_tool_call_ids, detected_at)
               VALUES (%s, %s, %s, %s, %s)""",
            (
                "failed_api_call", desc,
                "critical" if row["http_status"] >= 500 else "warning",
                str(row["id"]), now,
            ),
        )
        count += 1

    # 3. Excessive calls: >30 tool calls in 5 minutes
    cur.execute(
        """SELECT COUNT(*) as cnt,
                  MIN(timestamp) as burst_start,
                  MAX(timestamp) as burst_end,
                  STRING_AGG(id::text, ',') as ids
           FROM tool_calls
           WHERE timestamp >= (NOW() - make_interval(mins => %s))::text
           GROUP BY date_trunc('hour', timestamp::timestamp)
                    + INTERVAL '5 min' * FLOOR(EXTRACT(MINUTE FROM timestamp::timestamp) / 5)
           HAVING COUNT(*) > 30""",
        (since_minutes,),
    )
    bursts = cur.fetchall()

    for row in bursts:
        desc = (
            f"Excessive API calls: {row['cnt']} calls between "
            f"{row['burst_start']} and {row['burst_end']}"
        )
        cur.execute(
            """INSERT INTO behavior_oddities
               (oddity_type, description, severity, related_tool_call_ids, detected_at)
               VALUES (%s, %s, %s, %s, %s)""",
            ("excessive_calls", desc, "critical", row["ids"], now),
        )
        count += 1

    conn.commit()
    if count:
        print(f"  Detected {count} oddities", file=sys.stderr)
    return count


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point for MCP log collection."""
    parser = argparse.ArgumentParser(
        description="Collect MCP server logs into PostgreSQL"
    )
    parser.add_argument(
        "--container", default=DEFAULT_CONTAINER,
        help=f"Docker container name (default: {DEFAULT_CONTAINER})",
    )
    parser.add_argument(
        "--database-url", default=DATABASE_URL,
        help="Database URL (default: from DATABASE_URL env var)",
    )
    parser.add_argument(
        "--audit-log", default=DEFAULT_AUDIT_LOG,
        help=f"Security audit JSONL path (default: {DEFAULT_AUDIT_LOG})",
    )
    parser.add_argument(
        "--state", default=DEFAULT_STATE_FILE,
        help=f"State file path (default: {DEFAULT_STATE_FILE})",
    )
    parser.add_argument(
        "--detect-oddities", action="store_true",
        help="Run oddity detection after collection",
    )
    parser.add_argument(
        "--since-minutes", type=int, default=60,
        help="Oddity detection lookback window in minutes (default: 60)",
    )

    args = parser.parse_args()

    # Initialize DB (creates security tables if missing)
    init_db(args.database_url)

    state = load_state(args.state)
    conn = get_connection(args.database_url)

    try:
        print("Collecting MCP logs...", file=sys.stderr)

        # 1. Collect from security audit JSONL
        new_offset = collect_audit_log(
            conn, args.audit_log, state.get("audit_byte_offset", 0)
        )
        state["audit_byte_offset"] = new_offset

        # 2. Collect from Docker container logs
        new_ts = collect_docker_logs(
            conn, args.container, state.get("last_docker_ts")
        )
        state["last_docker_ts"] = new_ts

        # 3. Sync blocklist from MCP container JSON
        blocklist_path = str(Path(args.audit_log).parent / "blocked_authors.json")
        sync_blocklist(conn, blocklist_path)

        # 4. Oddity detection
        if args.detect_oddities:
            detect_oddities(conn, args.since_minutes)

        save_state(args.state, state)
        print("Log collection complete.", file=sys.stderr)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
