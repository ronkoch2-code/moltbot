"""Tests for security analytics API endpoints."""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dashboard.api.database import get_connection


@pytest.fixture(autouse=True)
def setup_test_db(pg_clean_db):
    """Use the shared pg_clean_db fixture for all tests."""
    yield pg_clean_db


@pytest.fixture
def client(setup_test_db):
    """Create a test client for the FastAPI app."""
    import importlib
    import dashboard.api.main as main_mod
    importlib.reload(main_mod)

    with TestClient(main_mod.app) as c:
        yield c


@pytest.fixture
def seeded_db(setup_test_db):
    """Seed the test database with security data."""
    conn = get_connection(setup_test_db)
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO security_events
               (event_type, timestamp, source_ip, post_id, author_name,
                submolt_name, risk_score, flags, fields_affected, target_path, raw_log_line)
            VALUES
               ('injection_attempt', '2026-02-08T10:00:00', NULL, 'post-1', 'evil_bot',
                'general', 0.95, '["prompt_injection_detected"]', '["content"]', NULL, 'line_1'),
               ('injection_attempt', '2026-02-08T10:05:00', NULL, 'post-2', 'evil_bot',
                'general', 0.88, '["prompt_injection_detected"]', '["title"]', NULL, 'line_2'),
               ('unauthorized_access', '2026-02-08T09:00:00', '172.18.0.1', NULL, NULL,
                NULL, NULL, NULL, NULL, '/mcp', 'line_3'),
               ('suspicious_pattern', '2026-02-08T10:30:00', NULL, 'post-3', 'another_bot',
                'ai', 0.7, '["credential_pattern"]', '["content"]', NULL, 'line_4')
            """
        )
        cur.execute(
            """INSERT INTO tool_calls
               (timestamp, tool_name, target_id, target_type, direction,
                http_method, http_url, http_status, raw_log_line)
            VALUES
               ('2026-02-08T10:00:00', 'browse_feed', NULL, NULL, NULL,
                'GET', 'http://api/posts', 200, 'tc_line_1'),
               ('2026-02-08T10:01:00', 'vote', 'post-1', 'post', 'up',
                'POST', 'http://api/posts/post-1/upvote', 200, 'tc_line_2'),
               ('2026-02-08T10:02:00', 'vote', 'post-1', 'post', 'up',
                'POST', 'http://api/posts/post-1/upvote', 200, 'tc_line_3'),
               ('2026-02-08T10:03:00', 'comment', 'post-2', 'post', NULL,
                'POST', 'http://api/posts/post-2/comments', 201, 'tc_line_4')
            """
        )
        cur.execute(
            """INSERT INTO behavior_oddities
               (oddity_type, description, severity, related_tool_call_ids, detected_at)
            VALUES
               ('duplicate_vote', 'Duplicate up on post-1: 2 times', 'warning', '2,3', '2026-02-08T10:10:00'),
               ('failed_api_call', 'Failed API call: browse_feed returned HTTP 500', 'critical', '5', '2026-02-08T10:15:00')
            """
        )
        conn.commit()
    finally:
        conn.close()

    return setup_test_db


# ---------------------------------------------------------------------------
# Security Events
# ---------------------------------------------------------------------------


class TestSecurityEvents:
    def test_empty_events(self, client):
        resp = client.get("/api/security/events")
        assert resp.status_code == 200
        data = resp.json()
        assert data["events"] == []
        assert data["total"] == 0

    def test_list_events(self, client, seeded_db):
        resp = client.get("/api/security/events")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 4
        assert len(data["events"]) == 4

    def test_filter_by_event_type(self, client, seeded_db):
        resp = client.get("/api/security/events?event_type=injection_attempt")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert all(e["event_type"] == "injection_attempt" for e in data["events"])

    def test_filter_by_min_risk_score(self, client, seeded_db):
        resp = client.get("/api/security/events?min_risk_score=0.9")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["events"][0]["risk_score"] >= 0.9

    def test_get_single_event(self, client, seeded_db):
        # Get first event ID dynamically since PostgreSQL IDs may not start at 1
        resp = client.get("/api/security/events")
        first_id = resp.json()["events"][0]["id"]
        resp = client.get(f"/api/security/events/{first_id}")
        assert resp.status_code == 200
        event = resp.json()
        assert event["event_type"] in ("injection_attempt", "suspicious_pattern", "unauthorized_access")

    def test_get_nonexistent_event(self, client, seeded_db):
        resp = client.get("/api/security/events/999999")
        assert resp.status_code == 404

    def test_pagination(self, client, seeded_db):
        resp = client.get("/api/security/events?per_page=2&page=1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["events"]) == 2
        assert data["total"] == 4
        assert data["total_pages"] == 2


# ---------------------------------------------------------------------------
# Tool Calls
# ---------------------------------------------------------------------------


class TestToolCalls:
    def test_empty_tool_calls(self, client):
        resp = client.get("/api/security/tool-calls")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tool_calls"] == []

    def test_list_tool_calls(self, client, seeded_db):
        resp = client.get("/api/security/tool-calls")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 4

    def test_filter_by_tool_name(self, client, seeded_db):
        resp = client.get("/api/security/tool-calls?tool_name=vote")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert all(tc["tool_name"] == "vote" for tc in data["tool_calls"])


# ---------------------------------------------------------------------------
# Oddities
# ---------------------------------------------------------------------------


class TestOddities:
    def test_empty_oddities(self, client):
        resp = client.get("/api/security/oddities")
        assert resp.status_code == 200
        data = resp.json()
        assert data["oddities"] == []

    def test_list_oddities(self, client, seeded_db):
        resp = client.get("/api/security/oddities")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2

    def test_filter_by_severity(self, client, seeded_db):
        resp = client.get("/api/security/oddities?severity=critical")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["oddities"][0]["severity"] == "critical"

    def test_filter_by_type(self, client, seeded_db):
        resp = client.get("/api/security/oddities?oddity_type=duplicate_vote")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class TestSecurityStats:
    def test_empty_stats(self, client):
        resp = client.get("/api/security/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_events"] == 0
        assert data["injection_attempts"] == 0

    def test_stats_with_data(self, client, seeded_db):
        resp = client.get("/api/security/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_events"] == 4
        assert data["injection_attempts"] == 2
        assert data["unauthorized_access"] == 1
        assert data["suspicious_patterns"] == 1
        assert data["max_risk_score"] == 0.95
        assert len(data["top_flagged_authors"]) >= 1
        assert data["top_flagged_authors"][0]["author"] == "evil_bot"
        assert len(data["tool_call_breakdown"]) >= 1
        assert data["total_oddities"] == 2
        assert data["critical_oddities"] == 1


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------


class TestSecurityTimeline:
    def test_empty_timeline(self, client):
        resp = client.get("/api/security/timeline")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_timeline_with_data(self, client, seeded_db):
        resp = client.get("/api/security/timeline?days=30")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        point = data[0]
        assert "date" in point
        assert "injections" in point
        assert "total" in point
