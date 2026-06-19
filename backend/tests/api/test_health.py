"""Tests for health check endpoint."""
import pytest
from unittest.mock import MagicMock, AsyncMock
from httpx import AsyncClient, ASGITransport


@pytest.fixture
def _setup_app():
    """Import the app and set required state mocks (lifespan does not run with ASGITransport)."""
    from app.main import app

    mock_vs = MagicMock()
    mock_vs.connect = AsyncMock()
    mock_vs.close = AsyncMock()
    app.state.vector_store = mock_vs
    app.state.embedding_service = MagicMock()

    yield app


@pytest.mark.asyncio
async def test_health_check(_setup_app):
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "SUCCESS"
        assert data["data"]["status"] == "healthy"
        assert "version" in data["data"]
