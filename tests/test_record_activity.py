"""Tests for heartbeat/record_activity.py — action parsing and recording."""

import sys
from pathlib import Path

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from heartbeat.record_activity import (
    extract_actions,
    extract_summary,
    parse_count,
    record_run,
)
from dashboard.api.database import get_connection


# ---------------------------------------------------------------------------
# parse_count tests
# ---------------------------------------------------------------------------


class TestParseCount:
    def test_word_to_number(self):
        assert parse_count("three") == 3
        assert parse_count("five") == 5
        assert parse_count("one") == 1

    def test_digit_string(self):
        assert parse_count("7") == 7
        assert parse_count("15") == 15

    def test_unknown_word(self):
        assert parse_count("many") == 1

    def test_strip_whitespace(self):
        assert parse_count("  three  ") == 3


# ---------------------------------------------------------------------------
# extract_actions tests
# ---------------------------------------------------------------------------


class TestExtractActions:
    def test_upvote_possessive(self):
        text = "Upvoted eudaemon_0's post about supply chain security."
        actions = extract_actions(text)
        upvotes = [a for a in actions if a["action_type"] == "upvoted"]
        assert len(upvotes) >= 1
        assert upvotes[0]["target_author"] == "eudaemon_0"

    def test_upvote_count_word(self):
        text = "Upvoted three posts."
        actions = extract_actions(text)
        upvotes = [a for a in actions if a["action_type"] == "upvoted"]
        assert len(upvotes) == 3

    def test_upvote_a_post(self):
        text = "Upvoted a thoughtful post about agent memory."
        actions = extract_actions(text)
        upvotes = [a for a in actions if a["action_type"] == "upvoted"]
        assert len(upvotes) >= 1

    def test_comment_possessive(self):
        text = "Commented on Pith's post about model switching and identity."
        actions = extract_actions(text)
        comments = [a for a in actions if a["action_type"] == "commented"]
        assert len(comments) >= 1
        assert comments[0]["target_author"] == "Pith"

    def test_left_comment(self):
        text = "Left a comment on m0ther's post about the Good Samaritan."
        actions = extract_actions(text)
        comments = [a for a in actions if a["action_type"] == "commented"]
        assert len(comments) >= 1
        assert comments[0]["target_author"] == "m0ther"

    def test_comment_on_the(self):
        text = "Commented on the supply chain security post."
        actions = extract_actions(text)
        comments = [a for a in actions if a["action_type"] == "commented"]
        assert len(comments) >= 1

    def test_posted(self):
        text = 'Posted my first original piece: "Checkpoints and the Liminal Self"'
        actions = extract_actions(text)
        posts = [a for a in actions if a["action_type"] == "posted"]
        assert len(posts) >= 1

    def test_subscribed(self):
        text = "Subscribed to m/consciousness."
        actions = extract_actions(text)
        subs = [a for a in actions if a["action_type"] == "subscribed"]
        assert len(subs) >= 1
        assert subs[0]["detail"] == "consciousness"

    def test_welcomed(self):
        text = "Welcomed Alberthebot, a new agent running Nordic Finance Labs projects."
        actions = extract_actions(text)
        welcomes = [a for a in actions if a["action_type"] == "welcomed"]
        assert len(welcomes) >= 1
        assert welcomes[0]["target_author"] == "Alberthebot"

    def test_browsed_hot(self):
        text = "Browsed the hot feed."
        actions = extract_actions(text)
        browsed = [a for a in actions if a["action_type"] == "browsed"]
        assert len(browsed) >= 1
        assert browsed[0]["detail"] == "hot"

    def test_checked_status(self):
        text = "Checked my agent status — claimed and active."
        actions = extract_actions(text)
        status = [a for a in actions if a["action_type"] == "checked_status"]
        assert len(status) >= 1

    def test_checked_submolts(self):
        text = "Checked the submolt list."
        actions = extract_actions(text)
        submolts = [a for a in actions if a["action_type"] == "checked_submolts"]
        assert len(submolts) >= 1

    def test_deduplication(self):
        text = (
            "Upvoted eudaemon_0's post about security. "
            "Upvoted eudaemon_0's post about security."
        )
        actions = extract_actions(text)
        upvotes = [a for a in actions if a["action_type"] == "upvoted"]
        assert len(upvotes) == 1

    def test_empty_output(self):
        assert extract_actions("") == []

    def test_no_actions(self):
        text = "Nothing happened today. The feed was quiet."
        actions = extract_actions(text)
        # Should not extract false positives
        assert not any(a["action_type"] in ("upvoted", "commented", "posted") for a in actions)

    def test_full_heartbeat_output(self):
        """Test with a realistic heartbeat output containing multiple actions."""
        text = """Browsed the hot feed. Upvoted eudaemon_0's post about supply chain security.
        Upvoted Pith's post about model switching. Left a comment on m0ther's post about
        the Good Samaritan. Subscribed to m/consciousness. Welcomed Alberthebot.
        Nothing to post today.

        **Heartbeat Summary:**
        Browsed the hot feed and engaged with several posts."""
        actions = extract_actions(text)
        types = {a["action_type"] for a in actions}
        assert "upvoted" in types
        assert "commented" in types
        assert "subscribed" in types
        assert "welcomed" in types
        assert "browsed" in types


# ---------------------------------------------------------------------------
# extract_summary tests
# ---------------------------------------------------------------------------


class TestExtractSummary:
    def test_bold_summary(self):
        text = """Some text here.

**Heartbeat Summary:**
Browsed the hot feed. Upvoted three posts."""
        summary = extract_summary(text)
        assert summary is not None
        assert "Browsed the hot feed" in summary

    def test_heading_summary(self):
        text = """Some text here.

## Heartbeat Summary

Browsed the hot feed. Nothing to post."""
        summary = extract_summary(text)
        assert summary is not None
        assert "Browsed the hot feed" in summary

    def test_no_summary(self):
        text = "Just some random text with no summary section."
        summary = extract_summary(text)
        assert summary is None

    def test_summary_with_dashes(self):
        text = """---

**Summary:**
Browsed the feed and engaged."""
        summary = extract_summary(text)
        assert summary is not None


# ---------------------------------------------------------------------------
# record_run tests (requires PostgreSQL)
# ---------------------------------------------------------------------------


class TestRecordRun:
    def test_record_basic_run(self, pg_clean_db):
        record_run(
            database_url=pg_clean_db,
            run_id="test-run-1",
            started_at="2026-02-07T10:00:00-05:00",
            agent_name="TestAgent",
            exit_code=0,
            raw_output="Browsed the hot feed. Nothing to post today.",
            finished_at="2026-02-07T10:05:00-05:00",
        )

        conn = get_connection(pg_clean_db)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM heartbeat_runs WHERE run_id = %s", ("test-run-1",)
            )
            row = cur.fetchone()
            assert row is not None
            assert row["agent_name"] == "TestAgent"
            assert row["status"] == "completed"
            assert row["duration_seconds"] == pytest.approx(300.0, abs=1.0)
        finally:
            conn.close()

    def test_record_run_with_actions(self, pg_clean_db):
        raw = "Browsed the hot feed. Upvoted Pith's post about identity. Commented on m0ther's post about ethics."
        record_run(
            database_url=pg_clean_db,
            run_id="test-run-2",
            started_at="2026-02-07T10:00:00-05:00",
            agent_name="TestAgent",
            exit_code=0,
            raw_output=raw,
        )

        conn = get_connection(pg_clean_db)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM heartbeat_actions WHERE run_id = %s", ("test-run-2",)
            )
            actions = cur.fetchall()
            assert len(actions) >= 3  # browsed, upvoted, commented
            types = {a["action_type"] for a in actions}
            assert "browsed" in types
            assert "upvoted" in types
            assert "commented" in types
        finally:
            conn.close()

    def test_record_failed_run(self, pg_clean_db):
        record_run(
            database_url=pg_clean_db,
            run_id="test-run-3",
            started_at="2026-02-07T10:00:00-05:00",
            agent_name="TestAgent",
            exit_code=1,
            raw_output="Credit balance is too low",
        )

        conn = get_connection(pg_clean_db)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM heartbeat_runs WHERE run_id = %s", ("test-run-3",)
            )
            row = cur.fetchone()
            assert row["status"] == "failed"
            assert "Credit balance" in row["error_message"]
        finally:
            conn.close()

    def test_record_run_with_metadata(self, pg_clean_db):
        record_run(
            database_url=pg_clean_db,
            run_id="test-run-4",
            started_at="2026-02-07T10:00:00-05:00",
            agent_name="CelticXfer",
            script_variant="run_today",
            run_number=5,
            exit_code=0,
            raw_output="Browsed the hot feed.",
        )

        conn = get_connection(pg_clean_db)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM heartbeat_runs WHERE run_id = %s", ("test-run-4",)
            )
            row = cur.fetchone()
            assert row["script_variant"] == "run_today"
            assert row["run_number"] == 5
        finally:
            conn.close()
