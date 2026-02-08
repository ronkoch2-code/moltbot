"""SQLite database management for heartbeat activity dashboard."""

import logging
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = os.environ.get(
    "HEARTBEAT_DB_PATH",
    str(Path(__file__).resolve().parent.parent.parent / "data" / "heartbeat.db"),
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS heartbeat_runs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id           TEXT UNIQUE NOT NULL,
    started_at       TEXT NOT NULL,
    finished_at      TEXT,
    duration_seconds REAL,
    exit_code        INTEGER,
    status           TEXT NOT NULL DEFAULT 'running',
    agent_name       TEXT NOT NULL,
    script_variant   TEXT,
    run_number       INTEGER,
    raw_output       TEXT,
    summary          TEXT,
    error_message    TEXT,
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS heartbeat_actions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id         TEXT NOT NULL REFERENCES heartbeat_runs(run_id),
    action_type    TEXT NOT NULL,
    target_id      TEXT,
    target_title   TEXT,
    target_author  TEXT,
    detail         TEXT,
    succeeded      INTEGER NOT NULL DEFAULT 1,
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_runs_started_at ON heartbeat_runs(started_at);
CREATE INDEX IF NOT EXISTS idx_runs_status ON heartbeat_runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_agent_name ON heartbeat_runs(agent_name);
CREATE INDEX IF NOT EXISTS idx_actions_run_id ON heartbeat_actions(run_id);
CREATE INDEX IF NOT EXISTS idx_actions_action_type ON heartbeat_actions(action_type);
"""


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    """Create a new SQLite connection with WAL mode and row factory.

    Parameters
    ----------
    db_path : str | None
        Override the default database path.

    Returns
    -------
    sqlite3.Connection
    """
    path = db_path or DB_PATH
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: str | None = None) -> None:
    """Initialize the database schema.

    Parameters
    ----------
    db_path : str | None
        Override the default database path.
    """
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
        logger.info("Database initialized at %s", db_path or DB_PATH)
    finally:
        conn.close()


@contextmanager
def get_db(db_path: str | None = None):
    """Context manager yielding a database connection.

    Parameters
    ----------
    db_path : str | None
        Override the default database path.

    Yields
    ------
    sqlite3.Connection
    """
    conn = get_connection(db_path)
    try:
        yield conn
    finally:
        conn.close()
