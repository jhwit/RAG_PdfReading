"""Query / Q&A API endpoints."""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import StreamingResponse
from app.core.config import get_settings
from app.models.schemas import QueryRequest, QueryResponse
from app.services.rag_service import RAGService

router = APIRouter(prefix="/query", tags=["Query"])


def get_rag_service(request: Request) -> RAGService:
    """Dependency injection for RAGService — uses app.state singletons."""
    settings = get_settings()
    return RAGService(
        settings=settings,
        embedding_service=request.app.state.embedding_service,
        vector_store=request.app.state.vector_store,
    )


@router.post(
    "",
    summary="Submit a Q&A query",
    description="Submit a natural language question. The system retrieves relevant document chunks and uses an LLM to synthesize an answer with citations."
)
async def query(
    request: QueryRequest,
    service: RAGService = Depends(get_rag_service),
):
    result = await service.query(
        question=request.query,
        top_k=request.top_k,
        filter_doc_ids=request.filter_doc_ids,
    )
    return {
        "code": "SUCCESS",
        "message": "Query processed",
        "data": result,
    }


@router.post(
    "/stream",
    summary="Streaming Q&A query (SSE)",
    description="Submit a question and receive a streaming answer via Server-Sent Events. The response includes text chunks as they are generated, followed by source citations."
)
async def query_stream(
    request: QueryRequest,
    service: RAGService = Depends(get_rag_service),
):
    return StreamingResponse(
        service.query_stream(
            question=request.query,
            top_k=request.top_k,
            filter_doc_ids=request.filter_doc_ids,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
