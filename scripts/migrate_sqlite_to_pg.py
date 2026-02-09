#!/usr/bin/env python3
"""One-time migration: copy all data from SQLite to PostgreSQL.

Reads from data/heartbeat.db (SQLite) and inserts into PostgreSQL.
Respects foreign key order: prompts -> runs -> actions -> security tables.
Resets SERIAL sequences to match max IDs after import.

Usage:
    python3 scripts/migrate_sqlite_to_pg.py
    python3 scripts/migrate_sqlite_to_pg.py --sqlite data/heartbeat.db --pg-url postgresql://...
"""

import argparse
import os
import sqlite3
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dashboard.api.database import DATABASE_URL, init_db

DEFAULT_SQLITE_PATH = str(PROJECT_ROOT / "data" / "heartbeat.db")


def migrate(sqlite_path: str, pg_url: str) -> None:
    """Migrate all data from SQLite to PostgreSQL.

    Parameters
    ----------
    sqlite_path : str
        Path to the SQLite database file.
    pg_url : str
        PostgreSQL connection URL.
    """
    if not Path(sqlite_path).exists():
        print(f"SQLite database not found: {sqlite_path} — skipping migration.")
        print("Initializing PostgreSQL schema...")
        init_db(pg_url)
        print("Schema initialized (no data to migrate).")
        return

    # Initialize PostgreSQL schema
    print("Initializing PostgreSQL schema...")
    init_db(pg_url)

    # Connect to both databases
    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row

    pg_conn = psycopg2.connect(pg_url, cursor_factory=psycopg2.extras.RealDictCursor)
    pg_cur = pg_conn.cursor()

    try:
        # Migration order respects foreign keys
        tables = [
            ("heartbeat_prompts", [
                "id", "version", "prompt_text", "change_summary", "author",
                "is_active", "created_at",
            ]),
            ("heartbeat_runs", [
                "id", "run_id", "started_at", "finished_at", "duration_seconds",
                "exit_code", "status", "agent_name", "script_variant",
                "run_number", "raw_output", "summary", "error_message",
                "prompt_version_id", "created_at",
            ]),
            ("heartbeat_actions", [
                "id", "run_id", "action_type", "target_id", "target_title",
                "target_author", "detail", "succeeded", "created_at",
            ]),
            ("security_events", [
                "id", "event_type", "timestamp", "source_ip", "post_id",
                "author_name", "submolt_name", "risk_score", "flags",
                "fields_affected", "target_path", "raw_log_line", "created_at",
            ]),
            ("tool_calls", [
                "id", "timestamp", "tool_name", "target_id", "target_type",
                "direction", "http_method", "http_url", "http_status",
                "raw_log_line", "created_at",
            ]),
            ("behavior_oddities", [
                "id", "oddity_type", "description", "severity",
                "related_tool_call_ids", "detected_at", "created_at",
            ]),
        ]

        total_rows = 0

        for table_name, columns in tables:
            # Check if table exists in SQLite
            sqlite_cur = sqlite_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,),
            )
            if not sqlite_cur.fetchone():
                print(f"  {table_name}: skipped (not in SQLite)")
                continue

            # Get available columns (schema may differ slightly)
            sqlite_cur = sqlite_conn.execute(f"PRAGMA table_info({table_name})")
            sqlite_columns = {row["name"] for row in sqlite_cur.fetchall()}
            available_cols = [c for c in columns if c in sqlite_columns]

            if not available_cols:
                print(f"  {table_name}: skipped (no matching columns)")
                continue

            # Read all rows from SQLite
            col_list = ", ".join(available_cols)
            rows = sqlite_conn.execute(f"SELECT {col_list} FROM {table_name}").fetchall()

            if not rows:
                print(f"  {table_name}: 0 rows (empty)")
                continue

            # Convert SQLite boolean integers to Python booleans
            bool_columns = {"is_active", "succeeded"}

            # Insert into PostgreSQL
            placeholders = ", ".join(["%s"] * len(available_cols))
            insert_sql = (
                f"INSERT INTO {table_name} ({col_list}) "
                f"VALUES ({placeholders}) "
                f"ON CONFLICT DO NOTHING"
            )

            count = 0
            for row in rows:
                values = []
                for col in available_cols:
                    val = row[col]
                    if col in bool_columns and val is not None:
                        val = bool(val)
                    values.append(val)
                try:
                    pg_cur.execute(insert_sql, values)
                    count += pg_cur.rowcount
                except psycopg2.Error as e:
                    print(f"    Warning: {table_name} row skipped: {e}")
                    pg_conn.rollback()
                    pg_cur = pg_conn.cursor()

            pg_conn.commit()
            total_rows += count
            print(f"  {table_name}: {count}/{len(rows)} rows migrated")

            # Reset SERIAL sequence to max ID
            if "id" in available_cols:
                pg_cur.execute(
                    f"SELECT COALESCE(MAX(id), 0) as max_id FROM {table_name}"
                )
                max_id = pg_cur.fetchone()["max_id"]
                if max_id > 0:
                    pg_cur.execute(
                        f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), %s)",
                        (max_id,),
                    )
                    pg_conn.commit()
                    print(f"    Sequence reset to {max_id}")

        print(f"\nMigration complete: {total_rows} total rows migrated.")

    finally:
        sqlite_conn.close()
        pg_conn.close()


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Migrate data from SQLite to PostgreSQL"
    )
    parser.add_argument(
        "--sqlite", default=DEFAULT_SQLITE_PATH,
        help=f"SQLite database path (default: {DEFAULT_SQLITE_PATH})",
    )
    parser.add_argument(
        "--pg-url", default=DATABASE_URL,
        help="PostgreSQL URL (default: from DATABASE_URL env var)",
    )
    args = parser.parse_args()

    print(f"Migrating from {args.sqlite} to PostgreSQL...")
    migrate(args.sqlite, args.pg_url)


if __name__ == "__main__":
    main()
