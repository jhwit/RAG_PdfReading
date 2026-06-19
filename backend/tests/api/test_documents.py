"""Tests for document API endpoints."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
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


@pytest.fixture
def mock_document_service():
    """Mock DocumentService for API tests."""
    with patch("app.api.documents.DocumentService") as mock:
        service = MagicMock()
        service.get_documents.return_value = []
        service.get_document.return_value = {
            "doc_id": "doc_test123",
            "filename": "test.pdf",
            "status": "completed",
            "total_pages": 10,
            "total_chunks": 20,
            "created_at": "2026-06-19T00:00:00Z",
            "updated_at": "2026-06-19T00:05:00Z",
        }
        service.get_status.return_value = {
            "doc_id": "doc_test123",
            "status": "completed",
            "progress": 100,
            "message": "Done",
            "updated_at": "2026-06-19T00:05:00Z",
        }
        service.delete_document = AsyncMock(return_value={
            "doc_id": "doc_test123",
            "deleted": True,
        })
        mock.return_value = service
        yield service


@pytest.mark.asyncio
async def test_list_documents_empty(_setup_app, mock_document_service):
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/documents")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "SUCCESS"
        assert data["data"]["items"] == []


@pytest.mark.asyncio
async def test_get_document(_setup_app, mock_document_service):
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/documents/doc_test123")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "SUCCESS"
        assert data["data"]["doc_id"] == "doc_test123"


@pytest.mark.asyncio
async def test_get_document_status(_setup_app, mock_document_service):
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/documents/doc_test123/status")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "SUCCESS"
        assert data["data"]["status"] == "completed"


@pytest.mark.asyncio
async def test_delete_document(_setup_app, mock_document_service):
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete("/api/v1/documents/doc_test123")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "SUCCESS"
        assert data["data"]["doc_id"] == "doc_test123"
        assert data["data"]["deleted"] is True
