"""PostgreSQL database management for heartbeat activity dashboard."""

import logging
import os
from contextlib import contextmanager

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "")

SCHEMA = """
CREATE TABLE IF NOT EXISTS heartbeat_prompts (
    id              SERIAL PRIMARY KEY,
    version         INTEGER NOT NULL,
    prompt_text     TEXT NOT NULL,
    change_summary  TEXT,
    author          TEXT NOT NULL DEFAULT 'system',
    is_active       BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_prompts_active ON heartbeat_prompts(is_active);
CREATE INDEX IF NOT EXISTS idx_prompts_version ON heartbeat_prompts(version);

CREATE TABLE IF NOT EXISTS heartbeat_runs (
    id               SERIAL PRIMARY KEY,
    run_id           TEXT UNIQUE NOT NULL,
    started_at       TEXT NOT NULL,
    finished_at      TEXT,
    duration_seconds DOUBLE PRECISION,
    exit_code        INTEGER,
    status           TEXT NOT NULL DEFAULT 'running',
    agent_name       TEXT NOT NULL,
    script_variant   TEXT,
    run_number       INTEGER,
    raw_output       TEXT,
    summary          TEXT,
    error_message    TEXT,
    prompt_version_id INTEGER REFERENCES heartbeat_prompts(id),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_runs_started_at ON heartbeat_runs(started_at);
CREATE INDEX IF NOT EXISTS idx_runs_status ON heartbeat_runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_agent_name ON heartbeat_runs(agent_name);

CREATE TABLE IF NOT EXISTS heartbeat_actions (
    id             SERIAL PRIMARY KEY,
    run_id         TEXT NOT NULL REFERENCES heartbeat_runs(run_id),
    action_type    TEXT NOT NULL,
    target_id      TEXT,
    target_title   TEXT,
    target_author  TEXT,
    detail         TEXT,
    succeeded      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_actions_run_id ON heartbeat_actions(run_id);
CREATE INDEX IF NOT EXISTS idx_actions_action_type ON heartbeat_actions(action_type);

CREATE TABLE IF NOT EXISTS security_events (
    id               SERIAL PRIMARY KEY,
    event_type       TEXT NOT NULL,
    timestamp        TEXT NOT NULL,
    source_ip        TEXT,
    post_id          TEXT,
    author_name      TEXT,
    submolt_name     TEXT,
    risk_score       DOUBLE PRECISION,
    flags            TEXT,
    fields_affected  TEXT,
    target_path      TEXT,
    raw_log_line     TEXT UNIQUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_security_events_event_type ON security_events(event_type);
CREATE INDEX IF NOT EXISTS idx_security_events_timestamp ON security_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_security_events_risk_score ON security_events(risk_score);

CREATE TABLE IF NOT EXISTS tool_calls (
    id               SERIAL PRIMARY KEY,
    timestamp        TEXT NOT NULL,
    tool_name        TEXT,
    target_id        TEXT,
    target_type      TEXT,
    direction        TEXT,
    http_method      TEXT,
    http_url         TEXT,
    http_status      INTEGER,
    raw_log_line     TEXT UNIQUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tool_calls_timestamp ON tool_calls(timestamp);
CREATE INDEX IF NOT EXISTS idx_tool_calls_tool_name ON tool_calls(tool_name);
CREATE INDEX IF NOT EXISTS idx_tool_calls_target_id ON tool_calls(target_id);

CREATE TABLE IF NOT EXISTS behavior_oddities (
    id                    SERIAL PRIMARY KEY,
    oddity_type           TEXT NOT NULL,
    description           TEXT NOT NULL,
    severity              TEXT NOT NULL DEFAULT 'info',
    related_tool_call_ids TEXT,
    detected_at           TEXT NOT NULL,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_oddities_oddity_type ON behavior_oddities(oddity_type);
CREATE INDEX IF NOT EXISTS idx_oddities_severity ON behavior_oddities(severity);
CREATE INDEX IF NOT EXISTS idx_oddities_detected_at ON behavior_oddities(detected_at);
"""


def get_connection(database_url: str | None = None):
    """Create a new PostgreSQL connection with RealDictCursor.

    Parameters
    ----------
    database_url : str | None
        Override the default database URL.

    Returns
    -------
    psycopg2.extensions.connection
    """
    url = database_url or DATABASE_URL
    conn = psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)
    conn.autocommit = False
    return conn


def init_db(database_url: str | None = None) -> None:
    """Initialize the database schema.

    Parameters
    ----------
    database_url : str | None
        Override the default database URL.
    """
    conn = get_connection(database_url)
    try:
        cur = conn.cursor()
        cur.execute(SCHEMA)
        conn.commit()
        logger.info("Database initialized at %s", database_url or DATABASE_URL)
    finally:
        conn.close()


@contextmanager
def get_db(database_url: str | None = None):
    """Context manager yielding a database connection.

    Parameters
    ----------
    database_url : str | None
        Override the default database URL.

    Yields
    ------
    psycopg2.extensions.connection
    """
    conn = get_connection(database_url)
    try:
        yield conn
    finally:
        conn.close()
