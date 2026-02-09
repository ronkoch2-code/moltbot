"""Tests for dashboard API endpoints."""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Add project root to path
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
    """Seed the test database with sample data."""
    conn = get_connection(setup_test_db)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO heartbeat_runs
                (run_id, started_at, finished_at, duration_seconds, exit_code,
                 status, agent_name, script_variant, run_number, raw_output, summary)
            VALUES
                ('run-1', '2026-02-07T10:00:00', '2026-02-07T10:05:00', 300, 0,
                 'completed', 'CelticXfer', 'run_today', 1, 'Browsed the hot feed.', 'Browsed feed.'),
                ('run-2', '2026-02-07T10:30:00', '2026-02-07T10:35:00', 300, 0,
                 'completed', 'CelticXfer', 'run_today', 2, 'Upvoted posts.', 'Upvoted.'),
                ('run-3', '2026-02-07T11:00:00', NULL, NULL, 1,
                 'failed', 'CelticXfer', 'run_today', 3, 'Credit balance too low', NULL)
            """,
        )
        cur.execute(
            """
            INSERT INTO heartbeat_actions
                (run_id, action_type, target_author, detail, succeeded)
            VALUES
                ('run-1', 'browsed', NULL, 'hot', TRUE),
                ('run-1', 'upvoted', 'eudaemon_0', 'supply chain security', TRUE),
                ('run-1', 'commented', 'Pith', 'model switching', TRUE),
                ('run-2', 'upvoted', 'm0ther', 'Good Samaritan', TRUE),
                ('run-2', 'subscribed', NULL, 'consciousness', TRUE)
            """,
        )
        conn.commit()
    finally:
        conn.close()

    return setup_test_db


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


class TestHealth:
    def test_health_check(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["database"] == "ok"


# ---------------------------------------------------------------------------
# Runs endpoints
# ---------------------------------------------------------------------------


class TestRuns:
    def test_list_runs_empty(self, client):
        resp = client.get("/api/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["runs"] == []
        assert data["total"] == 0

    def test_list_runs_with_data(self, client, seeded_db):
        resp = client.get("/api/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["runs"]) == 3
        # Should be ordered by started_at DESC
        assert data["runs"][0]["run_id"] == "run-3"

    def test_list_runs_filter_status(self, client, seeded_db):
        resp = client.get("/api/runs?status=completed")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert all(r["status"] == "completed" for r in data["runs"])

    def test_list_runs_filter_search(self, client, seeded_db):
        resp = client.get("/api/runs?search=Credit")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["runs"][0]["run_id"] == "run-3"

    def test_list_runs_pagination(self, client, seeded_db):
        resp = client.get("/api/runs?page=1&per_page=2")
        data = resp.json()
        assert len(data["runs"]) == 2
        assert data["total"] == 3
        assert data["total_pages"] == 2

        resp2 = client.get("/api/runs?page=2&per_page=2")
        data2 = resp2.json()
        assert len(data2["runs"]) == 1

    def test_create_run(self, client):
        resp = client.post("/api/runs", json={
            "run_id": "new-run-1",
            "started_at": "2026-02-08T10:00:00",
            "agent_name": "CelticXfer",
            "script_variant": "run_today",
            "run_number": 1,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["run_id"] == "new-run-1"
        assert data["status"] == "running"

    def test_get_run_detail(self, client, seeded_db):
        resp = client.get("/api/runs/run-1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["run_id"] == "run-1"
        assert len(data["actions"]) == 3
        assert data["raw_output"] == "Browsed the hot feed."

    def test_get_run_not_found(self, client):
        resp = client.get("/api/runs/nonexistent")
        assert resp.status_code == 404

    def test_update_run(self, client, seeded_db):
        resp = client.patch("/api/runs/run-3", json={
            "status": "completed",
            "finished_at": "2026-02-07T11:05:00",
            "summary": "Recovered",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["summary"] == "Recovered"


# ---------------------------------------------------------------------------
# Actions endpoints
# ---------------------------------------------------------------------------


class TestActions:
    def test_get_run_actions(self, client, seeded_db):
        resp = client.get("/api/runs/run-1/actions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3

    def test_get_run_actions_not_found(self, client):
        resp = client.get("/api/runs/nonexistent/actions")
        assert resp.status_code == 404

    def test_create_run_actions(self, client, seeded_db):
        resp = client.post("/api/runs/run-2/actions", json=[
            {"action_type": "upvoted", "target_author": "Dominus", "detail": "consciousness"},
        ])
        assert resp.status_code == 201
        data = resp.json()
        assert len(data) == 1
        assert data[0]["action_type"] == "upvoted"

    def test_list_all_actions(self, client, seeded_db):
        resp = client.get("/api/actions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5

    def test_list_actions_filter_type(self, client, seeded_db):
        resp = client.get("/api/actions?action_type=upvoted")
        assert resp.status_code == 200
        data = resp.json()
        assert all(a["action_type"] == "upvoted" for a in data["actions"])


# ---------------------------------------------------------------------------
# Stats endpoints
# ---------------------------------------------------------------------------


class TestStats:
    def test_stats_empty(self, client):
        resp = client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_runs"] == 0

    def test_stats_with_data(self, client, seeded_db):
        resp = client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_runs"] == 3
        assert data["successful_runs"] == 2
        assert data["failed_runs"] == 1
        assert data["total_actions"] == 5
        assert data["total_upvotes"] == 2
        assert data["total_comments"] == 1

    def test_timeline(self, client, seeded_db):
        resp = client.get("/api/stats/timeline?days=30")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        # All runs are on the same day
        if data:
            assert data[0]["runs"] >= 1


# ---------------------------------------------------------------------------
# Prompts endpoints
# ---------------------------------------------------------------------------


class TestPrompts:
    def test_list_prompts_empty(self, client):
        resp = client.get("/api/prompts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["prompts"] == []
        assert data["total"] == 0

    def test_create_prompt(self, client):
        resp = client.post("/api/prompts", json={
            "prompt_text": "You are CelticXfer.",
            "change_summary": "Initial prompt",
            "author": "system",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["version"] == 1
        assert data["is_active"] is True
        assert data["prompt_text"] == "You are CelticXfer."
        assert data["author"] == "system"

    def test_create_second_prompt_deactivates_first(self, client):
        client.post("/api/prompts", json={
            "prompt_text": "Version 1",
            "author": "system",
        })
        resp2 = client.post("/api/prompts", json={
            "prompt_text": "Version 2",
            "change_summary": "Updated personality",
            "author": "ron",
        })
        assert resp2.status_code == 201
        data2 = resp2.json()
        assert data2["version"] == 2
        assert data2["is_active"] is True

        # Check first is no longer active
        listing = client.get("/api/prompts").json()
        versions = {p["version"]: p["is_active"] for p in listing["prompts"]}
        assert versions[1] is False
        assert versions[2] is True

    def test_get_active_prompt(self, client):
        client.post("/api/prompts", json={
            "prompt_text": "Active prompt text",
            "author": "system",
        })
        resp = client.get("/api/prompts/active")
        assert resp.status_code == 200
        data = resp.json()
        assert data["prompt_text"] == "Active prompt text"
        assert data["is_active"] is True

    def test_get_active_prompt_text(self, client):
        client.post("/api/prompts", json={
            "prompt_text": "Plain text prompt",
            "author": "system",
        })
        resp = client.get("/api/prompts/active/text")
        assert resp.status_code == 200
        assert resp.text == "Plain text prompt"
        assert "text/plain" in resp.headers["content-type"]

    def test_get_active_prompt_none(self, client):
        resp = client.get("/api/prompts/active")
        assert resp.status_code == 404

    def test_get_prompt_by_id(self, client):
        create_resp = client.post("/api/prompts", json={
            "prompt_text": "Specific prompt",
            "author": "system",
        })
        prompt_id = create_resp.json()["id"]
        resp = client.get(f"/api/prompts/{prompt_id}")
        assert resp.status_code == 200
        assert resp.json()["prompt_text"] == "Specific prompt"

    def test_prompt_version_auto_increments(self, client):
        for i in range(3):
            client.post("/api/prompts", json={
                "prompt_text": f"Prompt v{i + 1}",
                "author": "system",
            })
        listing = client.get("/api/prompts").json()
        versions = sorted(p["version"] for p in listing["prompts"])
        assert versions == [1, 2, 3]
