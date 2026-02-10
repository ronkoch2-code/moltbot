"""Tests for dashboard API bearer token authentication."""

import importlib
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def setup_test_db(pg_clean_db):
    """Use the shared pg_clean_db fixture for all tests."""
    yield pg_clean_db


def _make_client(auth_token: str = ""):
    """Create a TestClient with a specific DASHBOARD_AUTH_TOKEN value."""
    # Patch the module-level token before reloading
    with patch.dict(os.environ, {"DASHBOARD_AUTH_TOKEN": auth_token}):
        import dashboard.api.auth as auth_mod

        importlib.reload(auth_mod)

        import dashboard.api.main as main_mod

        importlib.reload(main_mod)
        return TestClient(main_mod.app)


# ---------------------------------------------------------------------------
# Open mode (no token configured)
# ---------------------------------------------------------------------------


class TestOpenMode:
    """When DASHBOARD_AUTH_TOKEN is unset, all requests should pass through."""

    def test_no_token_allows_access(self):
        client = _make_client("")
        resp = client.get("/api/stats")
        assert resp.status_code == 200

    def test_no_token_ignores_bearer(self):
        client = _make_client("")
        resp = client.get(
            "/api/stats", headers={"Authorization": "Bearer anything"}
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Protected mode (token configured)
# ---------------------------------------------------------------------------

TEST_TOKEN = "test-secret-token-12345"


class TestProtectedMode:
    """When DASHBOARD_AUTH_TOKEN is set, requests must include a valid bearer token."""

    def test_missing_token_returns_401(self):
        client = _make_client(TEST_TOKEN)
        resp = client.get("/api/stats")
        assert resp.status_code == 401
        assert "bearer" in resp.headers.get("www-authenticate", "").lower()

    def test_wrong_token_returns_401(self):
        client = _make_client(TEST_TOKEN)
        resp = client.get(
            "/api/stats", headers={"Authorization": "Bearer wrong-token"}
        )
        assert resp.status_code == 401

    def test_correct_token_allows_access(self):
        client = _make_client(TEST_TOKEN)
        resp = client.get(
            "/api/stats",
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        )
        assert resp.status_code == 200

    def test_health_endpoint_is_unprotected(self):
        """Health check should be accessible without auth."""
        client = _make_client(TEST_TOKEN)
        resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_runs_protected(self):
        client = _make_client(TEST_TOKEN)
        resp = client.get("/api/runs")
        assert resp.status_code == 401

        resp = client.get(
            "/api/runs",
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        )
        assert resp.status_code == 200

    def test_actions_protected(self):
        client = _make_client(TEST_TOKEN)
        resp = client.get("/api/actions")
        assert resp.status_code == 401

        resp = client.get(
            "/api/actions",
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        )
        assert resp.status_code == 200

    def test_prompts_protected(self):
        client = _make_client(TEST_TOKEN)
        resp = client.get("/api/prompts")
        assert resp.status_code == 401

        resp = client.get(
            "/api/prompts",
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        )
        assert resp.status_code == 200

    def test_security_protected(self):
        client = _make_client(TEST_TOKEN)
        resp = client.get("/api/security/stats")
        assert resp.status_code == 401

        resp = client.get(
            "/api/security/stats",
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        )
        assert resp.status_code == 200

    def test_post_with_auth(self):
        client = _make_client(TEST_TOKEN)
        headers = {"Authorization": f"Bearer {TEST_TOKEN}"}
        resp = client.post(
            "/api/runs",
            json={
                "run_id": "auth-test-run",
                "started_at": "2026-02-09T10:00:00",
                "agent_name": "CelticXfer",
            },
            headers=headers,
        )
        assert resp.status_code == 201

    def test_post_without_auth(self):
        client = _make_client(TEST_TOKEN)
        resp = client.post(
            "/api/runs",
            json={
                "run_id": "auth-test-run",
                "started_at": "2026-02-09T10:00:00",
                "agent_name": "CelticXfer",
            },
        )
        assert resp.status_code == 401
