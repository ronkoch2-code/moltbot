"""Tests for the /health endpoint."""

import pytest
import httpx

# Import the app factory
import sys
sys.path.insert(0, "/Volumes/FS001/pythonscripts/moltbot")

from server import create_app, health_check


class TestHealthEndpoint:
    """Tests for the /health endpoint."""

    @pytest.mark.asyncio
    async def test_health_check_function(self):
        """Direct call to health_check should return status ok."""
        from starlette.testclient import TestClient
        from starlette.applications import Starlette
        from starlette.routing import Route

        # Create minimal app with just health route
        app = Starlette(routes=[Route("/health", health_check)])
        client = TestClient(app)

        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_health_via_asgi_transport(self):
        """Health endpoint should be accessible via ASGI transport."""
        from starlette.testclient import TestClient
        from starlette.applications import Starlette
        from starlette.routing import Route

        # Create minimal app with just health route
        app = Starlette(routes=[Route("/health", health_check)])

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver"
        ) as client:
            response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_health_endpoint_method_get_only(self):
        """Health endpoint should only accept GET requests."""
        from starlette.testclient import TestClient
        from starlette.applications import Starlette
        from starlette.routing import Route

        app = Starlette(routes=[Route("/health", health_check, methods=["GET"])])
        client = TestClient(app)

        # GET should work
        response = client.get("/health")
        assert response.status_code == 200

        # POST should fail
        response = client.post("/health")
        assert response.status_code == 405
