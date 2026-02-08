"""Tests for server.py — credentials, HTTP helpers, and tool functions."""

import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

import httpx
from httpx import Response, Request

# Import server module
from server import (
    _load_credentials,
    _http_error_response,
    _api_request,
    _get_client,
    _get_api_key,
    MOLTBOOK_API_BASE,
)


# ===========================================================================
# _load_credentials() tests
# ===========================================================================


class TestLoadCredentials:
    """Tests for credential loading."""

    def test_load_from_env_var(self, monkeypatch):
        """Credentials should be loaded from environment variables."""
        monkeypatch.setenv("MOLTBOOK_API_KEY", "env_api_key_123")
        monkeypatch.setenv("MOLTBOOK_AGENT_NAME", "EnvAgent")

        creds = _load_credentials()
        assert creds["api_key"] == "env_api_key_123"
        assert creds["agent_name"] == "EnvAgent"

    def test_load_from_env_var_default_agent_name(self, monkeypatch):
        """Missing agent name should default to 'unknown'."""
        monkeypatch.setenv("MOLTBOOK_API_KEY", "env_api_key_123")
        monkeypatch.delenv("MOLTBOOK_AGENT_NAME", raising=False)

        creds = _load_credentials()
        assert creds["api_key"] == "env_api_key_123"
        assert creds["agent_name"] == "unknown"

    def test_load_from_file(self, clean_env, credentials_file, monkeypatch):
        """Credentials should be loaded from JSON file when env vars missing."""
        # Patch the module-level constant since it's evaluated at import time
        import server
        monkeypatch.setattr(server, "CREDENTIALS_PATH", credentials_file)

        creds = _load_credentials()
        assert creds["api_key"] == "test_api_key_12345"
        assert creds["agent_name"] == "TestAgent"

    def test_missing_credentials(self, clean_env, monkeypatch, tmp_path):
        """Missing credentials should return empty dict."""
        monkeypatch.setenv("MOLTBOOK_CREDENTIALS_PATH", str(tmp_path / "nonexistent.json"))

        creds = _load_credentials()
        assert creds == {}


# ===========================================================================
# _http_error_response() tests
# ===========================================================================


class TestHttpErrorResponse:
    """Tests for HTTP error message mapping."""

    def _make_error(self, status_code: int, body: str = "{}") -> httpx.HTTPStatusError:
        """Helper to create HTTPStatusError."""
        request = Request("GET", "https://example.com")
        response = Response(status_code, text=body, request=request)
        return httpx.HTTPStatusError(
            message=f"HTTP {status_code}",
            request=request,
            response=response
        )

    def test_401_auth_failed(self):
        """401 should return auth failed message."""
        error = self._make_error(401)
        result = _http_error_response(error)
        assert "authentication failed" in result["error"].lower()
        assert result["status"] == 401

    def test_403_not_claimed(self):
        """403 should return not claimed message."""
        error = self._make_error(403)
        result = _http_error_response(error)
        assert "claimed" in result["error"].lower()
        assert result["status"] == 403

    def test_404_not_found(self):
        """404 should return not found message."""
        error = self._make_error(404)
        result = _http_error_response(error)
        assert "not found" in result["error"].lower()
        assert result["status"] == 404

    def test_429_rate_limited(self):
        """429 should return rate limited message."""
        error = self._make_error(429)
        result = _http_error_response(error)
        assert "rate limit" in result["error"].lower()
        assert result["status"] == 429

    def test_500_generic_error(self):
        """500 should return generic HTTP error message."""
        error = self._make_error(500)
        result = _http_error_response(error)
        assert "500" in result["error"]
        assert result["status"] == 500

    def test_json_body_not_leaked(self):
        """JSON body should NOT be returned to LLM (logged instead)."""
        error = self._make_error(400, '{"message": "Bad request details"}')
        result = _http_error_response(error)
        assert "detail" not in result
        assert result["status"] == 400

    def test_text_body_not_leaked(self):
        """Raw text body should NOT be returned to LLM (logged instead)."""
        long_body = "x" * 600
        error = self._make_error(400, long_body)
        result = _http_error_response(error)
        assert "detail" not in result
        assert result["status"] == 400


# ===========================================================================
# _api_request() tests
# ===========================================================================


class TestApiRequest:
    """Tests for _api_request() helper."""

    @pytest.mark.asyncio
    async def test_successful_request(self, httpx_mock):
        """Successful API request should return JSON response."""
        httpx_mock.add_response(
            url=f"{MOLTBOOK_API_BASE}/test",
            json={"success": True, "data": "test"}
        )

        async with httpx.AsyncClient() as client:
            result = await _api_request(client, "GET", "/test", "api_key_123")

        assert result["success"] is True
        assert result["data"] == "test"

    @pytest.mark.asyncio
    async def test_request_with_json_body(self, httpx_mock):
        """POST request with JSON body should work."""
        httpx_mock.add_response(
            url=f"{MOLTBOOK_API_BASE}/posts",
            json={"id": "post_123", "title": "New Post"}
        )

        async with httpx.AsyncClient() as client:
            result = await _api_request(
                client, "POST", "/posts", "api_key_123",
                json_body={"title": "New Post", "content": "Body"}
            )

        assert result["id"] == "post_123"

    @pytest.mark.asyncio
    async def test_request_with_params(self, httpx_mock):
        """GET request with query params should work."""
        httpx_mock.add_response(
            url=f"{MOLTBOOK_API_BASE}/posts?sort=hot&limit=10",
            json={"posts": []}
        )

        async with httpx.AsyncClient() as client:
            result = await _api_request(
                client, "GET", "/posts", "api_key_123",
                params={"sort": "hot", "limit": 10}
            )

        assert "posts" in result

    @pytest.mark.asyncio
    async def test_timeout_handling(self, httpx_mock):
        """Timeout should return friendly error message."""
        httpx_mock.add_exception(httpx.TimeoutException("Connection timed out"))

        async with httpx.AsyncClient() as client:
            result = await _api_request(client, "GET", "/test", "api_key_123")

        assert "error" in result
        assert "timed out" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_http_error_handling(self, httpx_mock):
        """HTTP errors should be converted to error responses."""
        httpx_mock.add_response(
            url=f"{MOLTBOOK_API_BASE}/test",
            status_code=401,
            json={"error": "Unauthorized"}
        )

        async with httpx.AsyncClient() as client:
            result = await _api_request(client, "GET", "/test", "api_key_123")

        assert "error" in result
        assert result["status"] == 401


# ===========================================================================
# Context helper tests
# ===========================================================================


class TestContextHelpers:
    """Tests for MCP context helpers."""

    def test_get_client(self, mock_ctx):
        """_get_client should return module-level HTTP client."""
        import server
        original = server._http_client
        try:
            server._http_client = httpx.AsyncClient()
            client = _get_client(mock_ctx)
            assert isinstance(client, httpx.AsyncClient)
        finally:
            server._http_client = original

    def test_get_api_key(self, mock_ctx):
        """_get_api_key should return API key from module-level credentials."""
        import server
        original = server._credentials
        try:
            server._credentials = {"api_key": "test_api_key_12345"}
            key = _get_api_key(mock_ctx)
            assert key == "test_api_key_12345"
        finally:
            server._credentials = original

    def test_get_api_key_missing(self, mock_ctx_no_key):
        """_get_api_key should raise ValueError when key missing."""
        import server
        original = server._credentials
        try:
            server._credentials = {}
            with pytest.raises(ValueError) as exc_info:
                _get_api_key(mock_ctx_no_key)
            assert "no moltbook api key" in str(exc_info.value).lower()
        finally:
            server._credentials = original
