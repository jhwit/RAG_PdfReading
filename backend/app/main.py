"""FastAPI application entry point."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.exceptions import setup_exception_handlers
from app.core.logger import setup_logger
from app.api import health, documents, query
from app.services.vector_store import VectorStore
from app.services.document_service import DocumentService
from app.utils.embedding import EmbeddingService
from app.utils.text_splitter import TextSplitter

settings = get_settings()
logger = setup_logger("rag_kb")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: startup / shutdown."""
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"Embedding model: {settings.embedding_model}")
    logger.info(f"LLM model: {settings.llm_model}")
    logger.info(f"Qdrant: {settings.qdrant_host}:{settings.qdrant_port}")

    # ── Initialize shared services ──

    # VectorStore — connect to Qdrant (non-fatal if unavailable)
    app.state.vector_store = VectorStore(settings)
    await app.state.vector_store.connect()

    # EmbeddingService — preload model at startup
    app.state.embedding_service = EmbeddingService(settings)
    logger.info("Preloading embedding model (this may take a moment)...")
    try:
        _ = app.state.embedding_service.model  # trigger lazy load
        logger.info(f"Embedding model loaded: {settings.embedding_model}")
    except Exception as e:
        logger.warning(f"Embedding model preload failed (will retry on first use): {e}")

    # DocumentService — singleton so _documents survives across requests
    app.state.document_service = DocumentService(
        settings=settings,
        text_splitter=TextSplitter(settings),
        embedding_service=app.state.embedding_service,
        vector_store=app.state.vector_store,
    )
    logger.info("Services initialized")

    yield

    # Shutdown
    await app.state.vector_store.close()
    logger.info("Shutting down")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="RAG Knowledge Base System — Document Q&A powered by LlamaIndex + Qdrant",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handlers
setup_exception_handlers(app)

# Routes — /api/v1 prefix applied here
app.include_router(health.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(query.router, prefix="/api/v1")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
