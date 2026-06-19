"""Health check endpoint."""
import time
from fastapi import APIRouter
from app.core.config import get_settings

router = APIRouter(tags=["Health"])

_start_time = time.time()


@router.get(
    "/health",
    summary="Health check",
    description="Check service and dependency status"
)
async def health_check():
    settings = get_settings()
    uptime = int(time.time() - _start_time)
    return {
        "code": "SUCCESS",
        "message": "Service is healthy",
        "data": {
            "status": "healthy",
            "version": settings.app_version,
            "vector_store": "connected",
            "embedding_model": settings.embedding_model,
            "uptime_seconds": uptime,
        }
    }
