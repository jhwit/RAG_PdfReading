"""Document management API endpoints."""
from fastapi import APIRouter, Request, UploadFile, File, Depends, Path, status as http_status
from app.core.config import get_settings
from app.core.exceptions import DocumentNotFound
from app.services.document_service import DocumentService

router = APIRouter(prefix="/documents", tags=["Documents"])


def get_document_service(request: Request) -> DocumentService:
    """Get the singleton DocumentService from app.state."""
    return request.app.state.document_service


@router.post(
    "/upload",
    response_model=dict,
    status_code=http_status.HTTP_201_CREATED,
    summary="Upload PDF document",
    description="Upload a national standard PDF file. The backend returns immediately and processes the file in the background."
)
async def upload_document(
    file: UploadFile = File(..., description="PDF file, max 50MB"),
    service: DocumentService = Depends(get_document_service),
):
    doc = await service.process_document(file)
    return {
        "code": "SUCCESS",
        "message": "Document uploaded successfully",
        "data": {
            "doc_id": doc["doc_id"],
            "filename": doc["filename"],
            "status": doc["status"],
            "message": doc["message"],
            "created_at": doc["created_at"],
        }
    }


@router.get(
    "",
    summary="Get document list",
    description="Get all uploaded documents with their processing status"
)
async def list_documents(
    service: DocumentService = Depends(get_document_service),
):
    docs = service.get_documents()
    return {
        "code": "SUCCESS",
        "message": "OK",
        "data": {
            "items": [
                {
                    "doc_id": d["doc_id"],
                    "filename": d["filename"],
                    "status": d["status"],
                    "total_pages": d.get("total_pages"),
                    "total_chunks": d.get("total_chunks"),
                    "created_at": d.get("created_at"),
                    "updated_at": d.get("updated_at"),
                }
                for d in docs
            ],
            "total": len(docs),
        }
    }


@router.get(
    "/{doc_id}",
    summary="Get document detail",
    description="Get detailed information for a single document"
)
async def get_document(
    doc_id: str = Path(..., description="Document unique identifier"),
    service: DocumentService = Depends(get_document_service),
):
    doc = service.get_document(doc_id)
    return {
        "code": "SUCCESS",
        "message": "OK",
        "data": {
            "doc_id": doc["doc_id"],
            "filename": doc["filename"],
            "status": doc["status"],
            "total_pages": doc.get("total_pages"),
            "total_chunks": doc.get("total_chunks"),
            "metadata": doc.get("metadata", {
                "title": doc.get("filename", ""),
                "author": "",
                "subject": "",
                "total_pages": doc.get("total_pages", 0),
            }),
            "created_at": doc.get("created_at"),
            "updated_at": doc.get("updated_at"),
        }
    }


@router.get(
    "/{doc_id}/status",
    summary="Get document processing status",
    description="Query the current processing status of a document. The frontend can poll this for progress updates."
)
async def get_document_status(
    doc_id: str = Path(..., description="Document unique identifier"),
    service: DocumentService = Depends(get_document_service),
):
    status = service.get_status(doc_id)
    return {
        "code": "SUCCESS",
        "message": "OK",
        "data": status,
    }


@router.delete(
    "/{doc_id}",
    summary="Delete document",
    description="Delete a document and all its vector data"
)
async def delete_document(
    doc_id: str = Path(..., description="Document unique identifier"),
    service: DocumentService = Depends(get_document_service),
):
    result = await service.delete_document(doc_id)
    return {
        "code": "SUCCESS",
        "message": "Document deleted",
        "data": {
            "doc_id": result["doc_id"],
            "deleted": result["deleted"],
        }
    }
