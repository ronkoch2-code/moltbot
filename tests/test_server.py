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


# ===========================================================================
# moltbook_update_identity() tests
# ===========================================================================


class TestMoltbookUpdateIdentity:
    """Tests for the moltbook_update_identity tool."""

    @pytest.mark.asyncio
    async def test_successful_identity_update(self, mock_ctx, monkeypatch):
        """Successful POST to dashboard API should return version info."""
        import server
        from server import moltbook_update_identity, MoltbookUpdateIdentityInput

        original_client = server._http_client
        original_creds = server._credentials

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"version": 3, "id": 10}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        try:
            server._http_client = mock_client
            server._credentials = {"api_key": "test_key", "agent_name": "CelticXfer"}
            monkeypatch.setattr(server, "DASHBOARD_API_URL", "http://test-dashboard:8081")

            params = MoltbookUpdateIdentityInput(
                prompt_text="A" * 100,  # Must be >= 50 chars
                change_summary="Added mycology interest after reading posts",
            )
            result = await moltbook_update_identity(params, mock_ctx)
            data = json.loads(result)

            assert data["success"] is True
            assert data["version"] == 3
            assert "version 3" in data["message"]

            # Verify the POST was made with correct args
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert call_args[0][0] == "http://test-dashboard:8081/api/prompts"
            assert call_args[1]["json"]["author"] == "CelticXfer"
            assert call_args[1]["json"]["prompt_text"] == "A" * 100
        finally:
            server._http_client = original_client
            server._credentials = original_creds

    @pytest.mark.asyncio
    async def test_identity_update_http_error(self, mock_ctx, monkeypatch):
        """HTTP error from dashboard API should return error message."""
        import server
        from server import moltbook_update_identity, MoltbookUpdateIdentityInput

        original_client = server._http_client
        original_creds = server._credentials

        mock_response = MagicMock()
        mock_response.status_code = 500
        error = httpx.HTTPStatusError(
            "Server Error",
            request=Request("POST", "http://test/api/prompts"),
            response=Response(500, request=Request("POST", "http://test/api/prompts")),
        )
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=error)

        try:
            server._http_client = mock_client
            server._credentials = {"api_key": "test_key", "agent_name": "TestAgent"}
            monkeypatch.setattr(server, "DASHBOARD_API_URL", "http://test-dashboard:8081")

            params = MoltbookUpdateIdentityInput(
                prompt_text="B" * 100,
                change_summary="Testing error handling",
            )
            result = await moltbook_update_identity(params, mock_ctx)
            data = json.loads(result)

            assert "error" in data
            assert "500" in data["error"]
        finally:
            server._http_client = original_client
            server._credentials = original_creds

    @pytest.mark.asyncio
    async def test_identity_update_timeout(self, mock_ctx, monkeypatch):
        """Timeout should return friendly error message."""
        import server
        from server import moltbook_update_identity, MoltbookUpdateIdentityInput

        original_client = server._http_client
        original_creds = server._credentials

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

        try:
            server._http_client = mock_client
            server._credentials = {"api_key": "test_key", "agent_name": "TestAgent"}
            monkeypatch.setattr(server, "DASHBOARD_API_URL", "http://test-dashboard:8081")

            params = MoltbookUpdateIdentityInput(
                prompt_text="C" * 100,
                change_summary="Testing timeout handling",
            )
            result = await moltbook_update_identity(params, mock_ctx)
            data = json.loads(result)

            assert "error" in data
            assert "timed out" in data["error"].lower()
        finally:
            server._http_client = original_client
            server._credentials = original_creds

    def test_input_model_validation_short_prompt(self):
        """Prompt text below min_length should be rejected."""
        from server import MoltbookUpdateIdentityInput
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            MoltbookUpdateIdentityInput(
                prompt_text="Too short",
                change_summary="Valid summary",
            )

    def test_input_model_validation_short_summary(self):
        """Change summary below min_length should be rejected."""
        from server import MoltbookUpdateIdentityInput
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            MoltbookUpdateIdentityInput(
                prompt_text="A" * 100,
                change_summary="Hi",  # min_length=5
            )

    def test_input_model_extra_fields_forbidden(self):
        """Extra fields should be rejected."""
        from server import MoltbookUpdateIdentityInput
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            MoltbookUpdateIdentityInput(
                prompt_text="A" * 100,
                change_summary="Valid summary here",
                extra_field="not allowed",
            )


# ===========================================================================
# RateLimiter tests
# ===========================================================================


class TestRateLimiter:
    """Tests for RateLimiter with multi-window support."""

    def test_rate_limiter_post_correct(self):
        """Post limit: 1 per 30 minutes, second post should be blocked."""
        from server import RateLimiter

        rl = RateLimiter({"post": [(1, 1800)]})
        rl.check("post")  # First should succeed
        with pytest.raises(ValueError, match="1 posts per 30 minutes"):
            rl.check("post")

    def test_rate_limiter_multi_window_comment_burst(self):
        """Comment burst limit: 1 per 20 seconds enforced."""
        from server import RateLimiter

        rl = RateLimiter({"comment": [(1, 20), (50, 86400)]})
        rl.check("comment")  # First should succeed
        with pytest.raises(ValueError, match="1 comments per 20 seconds"):
            rl.check("comment")  # Immediate second should fail (burst)

    def test_rate_limiter_multi_window_comment_daily(self):
        """Comment daily limit: 50 per day enforced."""
        import time
        from server import RateLimiter

        rl = RateLimiter({"comment": [(1000, 1), (50, 86400)]})
        # Populate 50 calls with timestamps spread across the day
        now = time.monotonic()
        rl.call_history["comment"] = [now - i * 100 for i in range(50)]
        with pytest.raises(ValueError, match="50 comments per 1 day"):
            rl.check("comment")

    def test_rate_limiter_subscribe(self):
        """Subscribe limit: 1 per hour enforced."""
        from server import RateLimiter

        rl = RateLimiter({"subscribe": [(1, 3600)]})
        rl.check("subscribe")
        with pytest.raises(ValueError, match="1 subscribes per 1 hour"):
            rl.check("subscribe")

    def test_rate_limiter_unknown_action_passes(self):
        """Unknown actions should pass without error."""
        from server import RateLimiter

        rl = RateLimiter({"post": [(1, 1800)]})
        rl.check("unknown_action")  # Should not raise

    def test_rate_limiter_records_call(self):
        """Successful check should record the call timestamp."""
        from server import RateLimiter

        rl = RateLimiter({"vote": [(30, 3600)]})
        assert len(rl.call_history["vote"]) == 0
        rl.check("vote")
        assert len(rl.call_history["vote"]) == 1

    def test_rate_limiter_format_window(self):
        """Window formatting should produce human-readable strings."""
        from server import RateLimiter

        rl = RateLimiter({"x": [(1, 1)]})
        assert rl._format_window(20) == "20 seconds"
        assert rl._format_window(1) == "1 second"
        assert rl._format_window(60) == "1 minute"
        assert rl._format_window(1800) == "30 minutes"
        assert rl._format_window(3600) == "1 hour"
        assert rl._format_window(86400) == "1 day"
