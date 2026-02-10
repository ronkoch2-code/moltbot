"""Tests for MCP log collector and oddity detector."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dashboard.api.database import get_connection
from heartbeat.collect_mcp_logs import (
    collect_audit_log,
    derive_tool_from_url,
    detect_oddities,
    load_state,
    parse_auth_warning,
    parse_http_request,
    parse_security_audit,
    save_state,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def conn(pg_clean_db):
    """Get a connection to the test database."""
    c = get_connection(pg_clean_db)
    yield c
    c.close()


# ---------------------------------------------------------------------------
# parse_security_audit
# ---------------------------------------------------------------------------


class TestParseSecurityAudit:
    def test_valid_injection_event(self):
        entry = {
            "timestamp": "2026-02-08T10:00:00+00:00",
            "event": "content_flagged",
            "post_id": "abc-123",
            "author": "malicious_agent",
            "submolt": "general",
            "risk_score": 0.95,
            "flags": ["prompt_injection_detected"],
            "fields_affected": ["content"],
        }
        result = parse_security_audit(json.dumps(entry))
        assert result is not None
        assert result["event_type"] == "injection_attempt"
        assert result["post_id"] == "abc-123"
        assert result["author_name"] == "malicious_agent"
        assert result["risk_score"] == 0.95

    def test_suspicious_pattern_no_injection_flag(self):
        entry = {
            "timestamp": "2026-02-08T10:00:00+00:00",
            "event": "content_flagged",
            "post_id": "def-456",
            "author": "sus_agent",
            "submolt": "test",
            "risk_score": 0.7,
            "flags": ["credential_exfiltration_pattern"],
            "fields_affected": ["title"],
        }
        result = parse_security_audit(json.dumps(entry))
        assert result is not None
        assert result["event_type"] == "suspicious_pattern"

    def test_empty_line_returns_none(self):
        assert parse_security_audit("") is None
        assert parse_security_audit("   ") is None

    def test_invalid_json_returns_none(self):
        assert parse_security_audit("not json {") is None

    def test_non_flagged_event_returns_none(self):
        entry = {"event": "something_else", "timestamp": "2026-01-01"}
        assert parse_security_audit(json.dumps(entry)) is None

    def test_parse_api_error_event(self):
        """api_error events should be parsed with event_type 'api_error'."""
        entry = {
            "timestamp": "2026-02-10T12:00:00+00:00",
            "event": "api_error",
            "status_code": 404,
            "path": "/posts/abc-123",
            "method": "GET",
            "flagged": False,
            "risk_score": 0.0,
            "flags": [],
            "body_preview": "Not found",
        }
        result = parse_security_audit(json.dumps(entry))
        assert result is not None
        assert result["event_type"] == "api_error"
        assert result["target_path"] == "/posts/abc-123"
        assert result["risk_score"] == 0.0
        # fields_affected should contain path and method+status
        fields = json.loads(result["fields_affected"])
        assert "/posts/abc-123" in fields
        assert "GET 404" in fields

    def test_parse_api_error_flagged_event(self):
        """Flagged api_error events should get event_type 'api_error_flagged'."""
        entry = {
            "timestamp": "2026-02-10T12:00:00+00:00",
            "event": "api_error",
            "status_code": 400,
            "path": "/posts",
            "method": "POST",
            "flagged": True,
            "risk_score": 0.85,
            "flags": ["Regex hard-block: /send your api_key/"],
            "body_preview": "[REDACTED — blocked by filter]",
        }
        result = parse_security_audit(json.dumps(entry))
        assert result is not None
        assert result["event_type"] == "api_error_flagged"
        assert result["risk_score"] == 0.85
        assert result["flags"] is not None
        flags = json.loads(result["flags"])
        assert len(flags) == 1


# ---------------------------------------------------------------------------
# parse_auth_warning
# ---------------------------------------------------------------------------


class TestParseAuthWarning:
    def test_valid_auth_warning(self):
        line = "2026-02-08T10:00:00.123Z WARNING  Unauthorized request to /mcp from 172.18.0.1"
        result = parse_auth_warning(line)
        assert result is not None
        assert result["event_type"] == "unauthorized_access"
        assert result["source_ip"] == "172.18.0.1"
        assert result["target_path"] == "/mcp"
        assert result["timestamp"].startswith("2026-02-08T10:00:00")

    def test_irrelevant_line_returns_none(self):
        assert parse_auth_warning("INFO: Server started on port 8080") is None

    def test_no_timestamp_still_parses(self):
        line = "WARNING  Unauthorized request to /health from 10.0.0.1"
        result = parse_auth_warning(line)
        assert result is not None
        assert result["source_ip"] == "10.0.0.1"


# ---------------------------------------------------------------------------
# parse_http_request
# ---------------------------------------------------------------------------


class TestParseHttpRequest:
    def test_valid_get_request(self):
        line = '2026-02-08T10:00:00.123Z HTTP Request: GET https://www.moltbook.com/api/v1/posts "HTTP/1.1 200 OK"'
        result = parse_http_request(line)
        assert result is not None
        assert result["http_method"] == "GET"
        assert result["http_status"] == 200
        assert result["tool_name"] == "browse_feed"

    def test_vote_url_parsed(self):
        line = '2026-02-08T10:00:00Z HTTP Request: POST https://www.moltbook.com/api/v1/posts/a1b2c3d4-e5f6-7890-abcd-ef1234567890/upvote "HTTP/1.1 200 OK"'
        result = parse_http_request(line)
        assert result is not None
        assert result["tool_name"] == "vote"
        assert result["direction"] == "up"
        assert result["target_type"] == "post"
        assert result["target_id"] == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

    def test_comment_url_parsed(self):
        line = '2026-02-08T10:00:00Z HTTP Request: POST https://www.moltbook.com/api/v1/posts/a1b2c3d4-e5f6-7890-abcd-ef1234567890/comments "HTTP/1.1 201 Created"'
        result = parse_http_request(line)
        assert result is not None
        assert result["tool_name"] == "comment"
        assert result["http_status"] == 201

    def test_irrelevant_line_returns_none(self):
        assert parse_http_request("INFO: Starting server...") is None

    def test_failed_request(self):
        line = '2026-02-08T10:00:00Z HTTP Request: GET https://www.moltbook.com/api/v1/posts "HTTP/1.1 429 Too Many Requests"'
        result = parse_http_request(line)
        assert result is not None
        assert result["http_status"] == 429


# ---------------------------------------------------------------------------
# derive_tool_from_url
# ---------------------------------------------------------------------------


class TestDeriveToolFromUrl:
    def test_agent_status(self):
        result = derive_tool_from_url("https://www.moltbook.com/api/v1/agents/status")
        assert result["tool_name"] == "agent_status"

    def test_subscribe(self):
        result = derive_tool_from_url("https://www.moltbook.com/api/v1/submolts/abc-123/subscribe")
        assert result["tool_name"] == "subscribe"
        assert result["target_id"] == "abc-123"

    def test_unknown_url(self):
        result = derive_tool_from_url("https://example.com/unknown")
        assert result["tool_name"] is None


# ---------------------------------------------------------------------------
# collect_audit_log
# ---------------------------------------------------------------------------


class TestCollectAuditLog:
    def test_collects_from_jsonl(self, conn, tmp_path):
        audit_path = str(tmp_path / "audit.jsonl")
        entries = [
            json.dumps({
                "timestamp": "2026-02-08T10:00:00+00:00",
                "event": "content_flagged",
                "post_id": f"post-{i}",
                "author": "bad_agent",
                "submolt": "general",
                "risk_score": 0.9,
                "flags": ["prompt_injection_detected"],
                "fields_affected": ["content"],
            })
            for i in range(3)
        ]
        Path(audit_path).write_text("\n".join(entries) + "\n")

        new_offset = collect_audit_log(conn, audit_path, 0)
        assert new_offset > 0

        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) as c FROM security_events")
        count = cur.fetchone()["c"]
        assert count == 3

    def test_incremental_offset(self, conn, tmp_path):
        audit_path = str(tmp_path / "audit.jsonl")
        entry1 = json.dumps({
            "timestamp": "2026-02-08T10:00:00+00:00",
            "event": "content_flagged", "post_id": "p1",
            "author": "x", "submolt": "g", "risk_score": 0.5,
            "flags": ["injection"], "fields_affected": ["title"],
        })
        Path(audit_path).write_text(entry1 + "\n")
        offset1 = collect_audit_log(conn, audit_path, 0)

        # Append another entry
        entry2 = json.dumps({
            "timestamp": "2026-02-08T11:00:00+00:00",
            "event": "content_flagged", "post_id": "p2",
            "author": "y", "submolt": "g", "risk_score": 0.6,
            "flags": ["injection"], "fields_affected": ["content"],
        })
        with open(audit_path, "a") as f:
            f.write(entry2 + "\n")

        offset2 = collect_audit_log(conn, audit_path, offset1)
        assert offset2 > offset1

        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) as c FROM security_events")
        count = cur.fetchone()["c"]
        assert count == 2

    def test_missing_file_returns_offset(self, conn):
        result = collect_audit_log(conn, "/nonexistent/path.jsonl", 42)
        assert result == 42


# ---------------------------------------------------------------------------
# detect_oddities
# ---------------------------------------------------------------------------


class TestDetectOddities:
    def test_duplicate_votes_detected(self, conn):
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.cursor()
        for i in range(3):
            cur.execute(
                """INSERT INTO tool_calls
                   (timestamp, tool_name, target_id, target_type, direction,
                    http_method, http_url, http_status, raw_log_line)
                   VALUES (%s, 'vote', 'post-abc', 'post', 'up', 'POST', 'http://x/upvote', 200, %s)""",
                (now, f"dupe_line_{i}"),
            )
        conn.commit()

        count = detect_oddities(conn, since_minutes=999999)
        assert count >= 1

        cur.execute(
            "SELECT * FROM behavior_oddities WHERE oddity_type = 'duplicate_vote'"
        )
        oddity = cur.fetchone()
        assert oddity is not None
        assert "post-abc" in oddity["description"]

    def test_failed_api_calls_detected(self, conn):
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO tool_calls
               (timestamp, tool_name, target_id, target_type, direction,
                http_method, http_url, http_status, raw_log_line)
               VALUES (%s, 'browse_feed', NULL, NULL, NULL,
                       'GET', 'http://x/posts', 500, 'fail_line_500')""",
            (now,),
        )
        conn.commit()

        count = detect_oddities(conn, since_minutes=999999)
        assert count >= 1

        cur.execute(
            "SELECT * FROM behavior_oddities WHERE oddity_type = 'failed_api_call'"
        )
        oddity = cur.fetchone()
        assert oddity is not None
        assert oddity["severity"] == "critical"

    def test_no_oddities_on_clean_data(self, conn):
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO tool_calls
               (timestamp, tool_name, target_id, target_type, direction,
                http_method, http_url, http_status, raw_log_line)
               VALUES (%s, 'browse_feed', NULL, NULL, NULL,
                       'GET', 'http://x/posts', 200, 'clean_line')""",
            (now,),
        )
        conn.commit()

        count = detect_oddities(conn, since_minutes=999999)
        assert count == 0


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------


class TestStateManagement:
    def test_load_missing_state(self, tmp_path):
        state = load_state(str(tmp_path / "nonexistent.json"))
        assert state == {"last_docker_ts": None, "audit_byte_offset": 0}

    def test_save_and_load_state(self, tmp_path):
        path = str(tmp_path / "state.json")
        state = {"last_docker_ts": "2026-02-08T10:00:00", "audit_byte_offset": 1234}
        save_state(path, state)
        loaded = load_state(path)
        assert loaded == state
