"""文档 API 端点测试。"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport


@pytest.fixture
def _setup_app():
    """导入应用并设置所需的 state 单例（ASGITransport 不会运行 lifespan）。"""
    from app.main import app

    # VectorStore 模拟
    mock_vs = MagicMock()
    mock_vs.connect = AsyncMock()
    mock_vs.close = AsyncMock()
    mock_vs.is_connected = MagicMock(return_value=True)
    app.state.vector_store = mock_vs

    # EmbeddingService 模拟
    app.state.embedding_service = MagicMock()

    # DocumentService 模拟（单例 — API 从 app.state 读取）
    mock_ds = MagicMock()
    mock_ds.get_documents.return_value = []
    mock_ds.get_document.return_value = {
        "doc_id": "doc_test123",
        "filename": "test.pdf",
        "status": "completed",
        "total_pages": 10,
        "total_chunks": 20,
        "created_at": "2026-06-19T00:00:00Z",
        "updated_at": "2026-06-19T00:05:00Z",
    }
    mock_ds.get_status.return_value = {
        "doc_id": "doc_test123",
        "status": "completed",
        "progress": 100,
        "message": "Done",
        "updated_at": "2026-06-19T00:05:00Z",
    }
    mock_ds.delete_document = AsyncMock(return_value={
        "doc_id": "doc_test123",
        "deleted": True,
    })
    app.state.document_service = mock_ds

    yield app


@pytest.mark.asyncio
async def test_list_documents_empty(_setup_app):
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/documents")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "SUCCESS"
        assert data["data"]["items"] == []


@pytest.mark.asyncio
async def test_get_document(_setup_app):
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/documents/doc_test123")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "SUCCESS"
        assert data["data"]["doc_id"] == "doc_test123"


@pytest.mark.asyncio
async def test_get_document_status(_setup_app):
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/documents/doc_test123/status")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "SUCCESS"
        assert data["data"]["status"] == "completed"


@pytest.mark.asyncio
async def test_delete_document(_setup_app):
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete("/api/v1/documents/doc_test123")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "SUCCESS"
        assert data["data"]["doc_id"] == "doc_test123"
        assert data["data"]["deleted"] is True
