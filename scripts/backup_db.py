#!/usr/bin/env python3
"""Backup PostgreSQL database to a SQL dump file.

Connects via DATABASE_URL and exports all tables as INSERT statements,
producing a self-contained .sql file that can restore the full database.

Usage:
    source .env && export DATABASE_URL
    python3 scripts/backup_db.py
    python3 scripts/backup_db.py --output backups/my_backup.sql
"""

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKUP_DIR = PROJECT_ROOT / "backups"

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Tables in foreign-key-safe order (parents before children)
TABLES = [
    "heartbeat_prompts",
    "heartbeat_runs",
    "heartbeat_actions",
    "security_events",
    "tool_calls",
    "behavior_oddities",
    "blocked_authors",
]


def escape_value(val) -> str:
    """Escape a Python value for SQL INSERT."""
    if val is None:
        return "NULL"
    if isinstance(val, bool):
        return "TRUE" if val else "FALSE"
    if isinstance(val, (int, float)):
        return str(val)
    # String: escape single quotes
    s = str(val).replace("'", "''")
    return f"'{s}'"


def backup(database_url: str, output_path: str) -> None:
    """Export all tables to a SQL file."""
    conn = psycopg2.connect(database_url, cursor_factory=psycopg2.extras.RealDictCursor)
    conn.set_session(readonly=True)

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    total_rows = 0
    timestamp = datetime.now(timezone.utc).isoformat()

    with open(output, "w") as f:
        f.write(f"-- Moltbot PostgreSQL backup\n")
        f.write(f"-- Generated: {timestamp}\n")
        f.write(f"-- Source: {database_url.split('@')[-1] if '@' in database_url else 'local'}\n")
        f.write(f"--\n")
        f.write(f"-- Restore with: psql $DATABASE_URL < {output.name}\n")
        f.write(f"-- Or: python3 scripts/restore_db.py --input {output}\n\n")

        f.write("BEGIN;\n\n")

        for table in TABLES:
            cur = conn.cursor()

            # Check if table exists
            cur.execute(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = %s)",
                (table,),
            )
            if not cur.fetchone()["exists"]:
                f.write(f"-- {table}: table not found, skipped\n\n")
                continue

            # Get column names
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = %s ORDER BY ordinal_position",
                (table,),
            )
            columns = [row["column_name"] for row in cur.fetchall()]

            # Get all rows
            cur.execute(f"SELECT * FROM {table} ORDER BY id")
            rows = cur.fetchall()

            f.write(f"-- {table}: {len(rows)} rows\n")

            if rows:
                col_list = ", ".join(columns)
                for row in rows:
                    values = ", ".join(escape_value(row[col]) for col in columns)
                    f.write(
                        f"INSERT INTO {table} ({col_list}) VALUES ({values}) "
                        f"ON CONFLICT DO NOTHING;\n"
                    )

                # Reset sequence
                f.write(
                    f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {table}), 1));\n"
                )

            f.write("\n")
            total_rows += len(rows)
            print(f"  {table}: {len(rows)} rows")

        f.write("COMMIT;\n")

    conn.close()
    size_kb = output.stat().st_size / 1024
    print(f"\nBackup complete: {total_rows} rows → {output} ({size_kb:.1f} KB)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backup Moltbot PostgreSQL database")
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Output SQL file path (default: backups/moltbot_YYYYMMDD_HHMMSS.sql)",
    )
    parser.add_argument(
        "--database-url",
        default=DATABASE_URL,
        help="PostgreSQL URL (default: from DATABASE_URL env var)",
    )
    args = parser.parse_args()

    if not args.database_url:
        print("Error: DATABASE_URL not set. Run: source .env && export DATABASE_URL")
        sys.exit(1)

    if args.output is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        BACKUP_DIR.mkdir(exist_ok=True)
        args.output = str(BACKUP_DIR / f"moltbot_{ts}.sql")

    print(f"Backing up to {args.output}...")
    backup(args.database_url, args.output)


if __name__ == "__main__":
    main()
