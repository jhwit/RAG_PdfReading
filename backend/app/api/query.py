"""Query / Q&A API endpoints."""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import StreamingResponse
from app.core.config import get_settings
from app.models.schemas import QueryRequest
from app.services.rag_service import RAGService

router = APIRouter(prefix="/query", tags=["Query"])


def get_rag_service(request: Request) -> RAGService:
    """Get RAGService wired with the shared singletons from app.state."""
    return RAGService(
        settings=get_settings(),
        embedding_service=request.app.state.embedding_service,
        vector_store=request.app.state.vector_store,
    )


@router.post(
    "",
    summary="Submit a Q&A query",
    description="Submit a natural language question. The system retrieves relevant document chunks and uses an LLM to synthesize an answer with citations."
)
async def query(
    body: QueryRequest,
    service: RAGService = Depends(get_rag_service),
):
    result = await service.query(
        question=body.query,
        top_k=body.top_k,
        filter_doc_ids=body.filter_doc_ids,
    )
    return {
        "code": "SUCCESS",
        "message": "Query processed",
        "data": result,
    }


@router.post(
    "/stream",
    summary="Streaming Q&A query (SSE)",
    description="Submit a question and receive a streaming answer via Server-Sent Events."
)
async def query_stream(
    body: QueryRequest,
    service: RAGService = Depends(get_rag_service),
):
    return StreamingResponse(
        service.query_stream(
            question=body.query,
            top_k=body.top_k,
            filter_doc_ids=body.filter_doc_ids,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
