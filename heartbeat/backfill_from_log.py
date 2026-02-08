#!/usr/bin/env python3
"""Backfill heartbeat.db from existing heartbeat.log.

One-time migration script that parses the flat log file and populates SQLite
with historical runs. Safe to re-run — uses INSERT OR IGNORE.

Usage:
    python heartbeat/backfill_from_log.py
    python heartbeat/backfill_from_log.py --log-file /path/to/heartbeat.log
"""

import argparse
import hashlib
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dashboard.api.database import DB_PATH, get_connection, init_db
from heartbeat.record_activity import extract_actions, extract_summary

LOG_FILE = Path(__file__).resolve().parent / "heartbeat.log"

# Matches lines like: 2026-02-07T11:41:55-05:00 HEARTBEAT 1: <content>
HEARTBEAT_LINE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}T[\d:]+[+-]\d{2}:\d{2})\s+"
    r"HEARTBEAT\s+(?P<run_number>\d+):\s+"
    r"(?P<content>.*)$",
    re.DOTALL,
)

# Matches INFO/ERROR/WARN lines
INFO_LINE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}T[\d:]+[+-]\d{2}:\d{2})\s+"
    r"(?P<level>INFO|ERROR|WARN):\s+"
    r"(?P<message>.*)$",
)


def parse_log_file(log_path: Path) -> list[dict]:
    """Parse heartbeat.log into a list of run records.

    Parameters
    ----------
    log_path : Path
        Path to the heartbeat.log file.

    Returns
    -------
    list[dict]
        List of run dicts ready for database insertion.
    """
    if not log_path.exists():
        print(f"Log file not found: {log_path}", file=sys.stderr)
        return []

    content = log_path.read_text()
    lines = content.split("\n")

    runs = []
    i = 0

    while i < len(lines):
        line = lines[i]
        match = HEARTBEAT_LINE.match(line)

        if match:
            timestamp = match.group("timestamp")
            run_number = int(match.group("run_number"))
            raw_content = match.group("content")

            # Collect continuation lines (not matching a new timestamped entry)
            i += 1
            while i < len(lines):
                next_line = lines[i]
                if not next_line:
                    raw_content += "\n"
                    i += 1
                    continue
                # Check if this is a new log entry
                if re.match(r"^\d{4}-\d{2}-\d{2}T", next_line):
                    break
                # Check if it's docker build output
                if re.match(r"^#\d+\s|^\s*(Image|Network|Container)\s", next_line):
                    break
                raw_content += "\n" + next_line
                i += 1

            raw_content = raw_content.strip()

            # Generate a deterministic run_id from timestamp + run_number
            run_id_hash = hashlib.sha256(
                f"{timestamp}-{run_number}".encode()
            ).hexdigest()[:12]
            run_id = f"backfill-{run_id_hash}"

            # Detect failures
            status = "completed"
            error_message = None
            exit_code = 0
            if "Credit balance" in raw_content:
                status = "failed"
                error_message = "Credit balance too low"
                exit_code = 1

            runs.append({
                "run_id": run_id,
                "started_at": timestamp,
                "finished_at": timestamp,
                "run_number": run_number,
                "raw_output": raw_content,
                "status": status,
                "error_message": error_message,
                "exit_code": exit_code,
                "agent_name": "CelticXfer",
                "script_variant": "backfill",
            })
        else:
            i += 1

    return runs


def backfill(log_path: Path, db_path: str) -> int:
    """Backfill the database from the log file.

    Parameters
    ----------
    log_path : Path
        Path to heartbeat.log.
    db_path : str
        Path to the SQLite database.

    Returns
    -------
    int
        Number of runs inserted.
    """
    init_db(db_path)
    runs = parse_log_file(log_path)

    if not runs:
        print("No heartbeat entries found in log.", file=sys.stderr)
        return 0

    conn = get_connection(db_path)
    inserted = 0

    try:
        for run in runs:
            summary = extract_summary(run["raw_output"])
            actions = extract_actions(run["raw_output"])

            try:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO heartbeat_runs
                        (run_id, started_at, finished_at, duration_seconds,
                         exit_code, status, agent_name, script_variant,
                         run_number, raw_output, summary, error_message)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run["run_id"],
                        run["started_at"],
                        run["finished_at"],
                        None,
                        run["exit_code"],
                        run["status"],
                        run["agent_name"],
                        run["script_variant"],
                        run["run_number"],
                        run["raw_output"],
                        summary,
                        run["error_message"],
                    ),
                )

                if conn.total_changes > 0:
                    for action in actions:
                        conn.execute(
                            """
                            INSERT INTO heartbeat_actions
                                (run_id, action_type, target_id, target_title,
                                 target_author, detail, succeeded)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                run["run_id"],
                                action["action_type"],
                                action.get("target_id"),
                                action.get("target_title"),
                                action.get("target_author"),
                                action.get("detail"),
                                1 if action.get("succeeded", True) else 0,
                            ),
                        )
                    inserted += 1

            except Exception as e:
                print(
                    f"Warning: Failed to insert run {run['run_id']}: {e}",
                    file=sys.stderr,
                )

        conn.commit()
    finally:
        conn.close()

    return inserted


def main() -> None:
    """CLI entry point for backfilling from heartbeat.log."""
    parser = argparse.ArgumentParser(
        description="Backfill heartbeat.db from heartbeat.log"
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=LOG_FILE,
        help=f"Path to heartbeat.log (default: {LOG_FILE})",
    )
    parser.add_argument(
        "--db-path",
        default=DB_PATH,
        help=f"Database path (default: {DB_PATH})",
    )
    args = parser.parse_args()

    print(f"Backfilling from {args.log_file} to {args.db_path}")
    count = backfill(args.log_file, args.db_path)
    print(f"Inserted {count} runs.")

    # Print quick summary
    conn = get_connection(args.db_path)
    try:
        row = conn.execute(
            "SELECT COUNT(*) as runs FROM heartbeat_runs"
        ).fetchone()
        actions_row = conn.execute(
            "SELECT COUNT(*) as actions FROM heartbeat_actions"
        ).fetchone()
        print(f"Database now has {row['runs']} runs and {actions_row['actions']} actions.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
