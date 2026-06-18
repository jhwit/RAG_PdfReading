"""Pydantic schemas for API requests and responses."""
from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime
from enum import Enum


class DocumentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class SourceInfo(BaseModel):
    doc_id: str
    doc_name: str
    page: Optional[int] = None
    chunk_index: Optional[int] = None
    score: Optional[float] = None


class DocumentUploadResponse(BaseModel):
    doc_id: str
    filename: str
    status: DocumentStatus
    message: str
    created_at: datetime = Field(default_factory=datetime.now)


class DocumentListItem(BaseModel):
    doc_id: str
    filename: str
    status: DocumentStatus
    total_pages: Optional[int] = None
    total_chunks: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="User query text")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of retrieved chunks")
    stream: bool = Field(default=False, description="Whether to stream the response")
    filter_doc_ids: Optional[List[str]] = Field(default=None, description="Filter by document IDs")


class QueryResponse(BaseModel):
    answer: str
    sources: List[SourceInfo]
    query_time_ms: int
    model: str


class ChunkItem(BaseModel):
    content: str
    doc_id: str
    doc_name: str
    page: Optional[int] = None
    score: float


class HealthResponse(BaseModel):
    status: str
    version: str
    vector_store: str
    embedding_model: str


class DocumentDeleteResponse(BaseModel):
    doc_id: str
    deleted: bool
    message: str
