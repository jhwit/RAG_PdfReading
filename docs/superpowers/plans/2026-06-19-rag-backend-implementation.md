# RAG 知识库后端 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete FastAPI backend for the RAG Knowledge Base system per the 4 spec documents in `docs/`.

**Architecture:** FastAPI + LlamaIndex + Qdrant. Document upload → PDF parsing → text chunking → embedding → Qdrant storage. Query → embedding → ANN search → LLM synthesis → answer with sources.

**Tech Stack:** FastAPI 0.115+, LlamaIndex 0.12+, Qdrant 1.13+, BGE-M3, GPT-4o, PyMuPDF

## Global Constraints

- All config from `Settings`, no hardcoded values
- Routes use `/api/v1` prefix via `include_router`
- All endpoints have `response_model`, `summary`, `description`
- CPU-intensive ops (PDF parsing, embedding) use `run_in_threadpool`
- File upload validated by MIME type + magic number
- All exceptions use custom hierarchy (`RAGBaseException`)
- Logger named per module: `rag_kb.<module>`

---

### Task 1: Update Config & Create missing `__init__.py` files

**Files:**
- Modify: `backend/app/core/config.py`
- Create: `backend/app/core/__init__.py`
- Create: `backend/app/api/__init__.py`
- Create: `backend/app/services/__init__.py`
- Create: `backend/app/utils/__init__.py`
- Create: `backend/app/models/__init__.py`

**Interfaces:**
- Produces: `Settings` with full fields: `embedding_device`, `llm_temperature`, `default_top_k`, `max_top_k`, `similarity_threshold`, `chunk_separator`, `qdrant_api_key`, `data_dir`, `doc_dir`, `vector_dir`; all `__init__.py` files present for import resolution.

- [ ] **Step 1: Update config.py**

Replace `backend/app/core/config.py`:

```python
"""Application configuration."""
from functools import lru_cache
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    app_name: str = "RAG Knowledge Base"
    app_version: str = "0.1.0"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # LLM / Embedding
    embedding_model: str = "BAAI/bge-m3"
    embedding_device: str = "auto"
    llm_model: str = "gpt-4o"
    llm_temperature: float = 0.1
    openai_api_key: Optional[str] = None
    openai_base_url: Optional[str] = None

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "documents"
    qdrant_api_key: Optional[str] = None

    # Paths
    data_dir: str = "./data"
    doc_dir: str = "./data/documents"
    vector_dir: str = "./data/vectors"

    # Chunking
    chunk_size: int = 512
    chunk_overlap: int = 50
    chunk_separator: str = "\n\n"

    # Retrieval
    default_top_k: int = 5
    max_top_k: int = 20
    similarity_threshold: float = 0.7

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 2: Create all `__init__.py` files**

```bash
touch "D:/AI_coding/Rag/backend/app/core/__init__.py"
touch "D:/AI_coding/Rag/backend/app/api/__init__.py"
touch "D:/AI_coding/Rag/backend/app/services/__init__.py"
touch "D:/AI_coding/Rag/backend/app/utils/__init__.py"
touch "D:/AI_coding/Rag/backend/app/models/__init__.py"
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/ && git commit -m "feat: update config with full settings, add __init__.py files"
```

---

### Task 2: Exceptions Module

**Files:**
- Create: `backend/app/core/exceptions.py`

**Interfaces:**
- Produces: `RAGBaseException(code, message, status_code)`, `DocumentNotFound(doc_id)`, `PDFParseError(filename)`, `VectorStoreError(message)`, `setup_exception_handlers(app)` — registers handlers for `RAGBaseException`, `RequestValidationError`, generic `Exception` on the FastAPI app.

- [ ] **Step 1: Create exceptions.py** (from `02-backend-spec.md` §2.3)

```python
"""Global exception handlers."""
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError


class RAGBaseException(Exception):
    """Base business exception."""
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class DocumentNotFound(RAGBaseException):
    def __init__(self, doc_id: str):
        super().__init__("DOC_NOT_FOUND", f"Document {doc_id} not found", 404)


class PDFParseError(RAGBaseException):
    def __init__(self, filename: str):
        super().__init__("PDF_PARSE_ERROR", f"Failed to parse {filename}", 422)


class VectorStoreError(RAGBaseException):
    def __init__(self, message: str):
        super().__init__("VECTOR_STORE_ERROR", message, 500)


class LLMUnavailableError(RAGBaseException):
    def __init__(self, message: str = "LLM service unavailable"):
        super().__init__("LLM_UNAVAILABLE", message, 503)


class NoRelevantDocsError(RAGBaseException):
    def __init__(self):
        super().__init__("NO_RELEVANT_DOCS", "No relevant documents found", 404)


class InvalidFileTypeError(RAGBaseException):
    def __init__(self):
        super().__init__("INVALID_FILE_TYPE", "Only PDF files are allowed", 400)


class FileTooLargeError(RAGBaseException):
    def __init__(self, max_mb: int = 50):
        super().__init__("FILE_TOO_LARGE", f"File exceeds {max_mb}MB limit", 413)


class EmptyQueryError(RAGBaseException):
    def __init__(self):
        super().__init__("EMPTY_QUERY", "Query cannot be empty", 400)


class QueryTooLongError(RAGBaseException):
    def __init__(self, max_chars: int = 2000):
        super().__init__("QUERY_TOO_LONG", f"Query exceeds {max_chars} characters", 400)


def setup_exception_handlers(app):
    @app.exception_handler(RAGBaseException)
    async def handle_rag_exception(request: Request, exc: RAGBaseException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message, "details": None}
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "details": exc.errors()
            }
        )

    @app.exception_handler(Exception)
    async def handle_generic(request: Request, exc: Exception):
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"code": "INTERNAL_ERROR", "message": str(exc), "details": None}
        )
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/core/exceptions.py && git commit -m "feat: add exception hierarchy and global handlers"
```

---

### Task 3: Utility Services — Text Splitter & Embedding

**Files:**
- Create: `backend/app/utils/text_splitter.py`
- Create: `backend/app/utils/embedding.py`

**Interfaces:**
- Consumes: `Settings` from Task 1
- Produces:
  - `TextSplitter(settings)` → `split(text, doc_id, doc_name, page)` → `List[dict]` (chunks with metadata)
  - `EmbeddingService(settings)` → `embed_texts(List[str])` → `List[List[float]]`, `embed_query(str)` → `List[float]`

- [ ] **Step 1: Create text_splitter.py**

```python
"""Text chunking utilities."""
from typing import List
from app.core.config import Settings


class TextSplitter:
    """Split text into overlapping chunks with metadata."""

    def __init__(self, settings: Settings):
        self.chunk_size = settings.chunk_size
        self.chunk_overlap = settings.chunk_overlap
        self.separator = settings.chunk_separator

    def split(self, text: str, doc_id: str, doc_name: str, page: int = 1) -> List[dict]:
        """Split text into chunks with metadata."""
        if not text.strip():
            return []

        # First split by separator for natural boundaries
        paragraphs = text.split(self.separator)
        chunks = []
        current_chunk = ""
        chunk_index = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(current_chunk) + len(para) + len(self.separator) <= self.chunk_size:
                current_chunk = (current_chunk + self.separator + para).strip(self.separator)
            else:
                if current_chunk:
                    chunks.append(self._make_chunk(current_chunk, doc_id, doc_name, page, chunk_index))
                    chunk_index += 1
                # Handle paragraphs longer than chunk_size
                if len(para) > self.chunk_size:
                    sub_chunks = self._split_long_paragraph(para)
                    for sc in sub_chunks:
                        chunks.append(self._make_chunk(sc, doc_id, doc_name, page, chunk_index))
                        chunk_index += 1
                    current_chunk = ""
                else:
                    current_chunk = para

        # Don't forget the last chunk
        if current_chunk:
            chunks.append(self._make_chunk(current_chunk, doc_id, doc_name, page, chunk_index))

        return chunks

    def _split_long_paragraph(self, text: str) -> List[str]:
        """Split a paragraph longer than chunk_size into sentence-aware segments."""
        if len(text) <= self.chunk_size:
            return [text]

        result = []
        start = 0
        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            # Try to break at a sentence boundary
            if end < len(text):
                for sep in ["。", ". ", "；", "; ", "\n"]:
                    last_sep = text.rfind(sep, start, end)
                    if last_sep > start + self.chunk_size // 2:
                        end = last_sep + 1
                        break
            result.append(text[start:end].strip())
            start = end - self.chunk_overlap if end < len(text) else end
        return result

    def _make_chunk(self, text: str, doc_id: str, doc_name: str, page: int, index: int) -> dict:
        return {
            "content": text.strip(),
            "doc_id": doc_id,
            "doc_name": doc_name,
            "page": page,
            "chunk_index": index,
        }
```

- [ ] **Step 2: Create embedding.py**

```python
"""Embedding model wrapper."""
from typing import List
from app.core.config import Settings
from app.core.logger import setup_logger

logger = setup_logger("rag_kb.embedding")


class EmbeddingService:
    """Wrapper around HuggingFace embedding models."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.model_name = settings.embedding_model
        self.device = settings.embedding_device
        self._model = None

    @property
    def model(self):
        """Lazy-load the embedding model."""
        if self._model is None:
            from llama_index.embeddings.huggingface import HuggingFaceEmbedding
            logger.info(f"Loading embedding model: {self.model_name} on {self.device}")
            self._model = HuggingFaceEmbedding(
                model_name=self.model_name,
                device=self.device,
            )
        return self._model

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a batch of texts."""
        if not texts:
            return []
        return self.model.get_text_embedding_batch(texts)

    def embed_query(self, text: str) -> List[float]:
        """Generate embedding for a single query."""
        return self.model.get_text_embedding(text)

    def get_dimension(self) -> int:
        """Get the embedding vector dimension."""
        return 1024  # BGE-M3 dimension
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/utils/text_splitter.py backend/app/utils/embedding.py && git commit -m "feat: add text splitter and embedding service"
```

---

### Task 4: Vector Store Service

**Files:**
- Create: `backend/app/services/vector_store.py`

**Interfaces:**
- Consumes: `Settings` from Task 1
- Produces: `VectorStore(settings)` — `connect()`, `close()`, `ensure_collection()`, `upsert(points)`, `search(vector, top_k, filter_doc_ids)`, `delete_by_doc_id(doc_id)`

- [ ] **Step 1: Create vector_store.py**

```python
"""Qdrant vector store wrapper."""
from typing import List, Optional
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue, MatchAny,
)
from app.core.config import Settings
from app.core.exceptions import VectorStoreError
from app.core.logger import setup_logger

logger = setup_logger("rag_kb.vector_store")


class VectorStore:
    """Async wrapper around Qdrant vector database."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.collection = settings.qdrant_collection
        self.vector_size = 1024  # BGE-M3 dimension
        self._client: Optional[AsyncQdrantClient] = None

    @property
    def client(self) -> AsyncQdrantClient:
        if self._client is None:
            raise VectorStoreError("Vector store not connected. Call connect() first.")
        return self._client

    async def connect(self):
        """Initialize Qdrant client connection."""
        logger.info(f"Connecting to Qdrant at {self.settings.qdrant_host}:{self.settings.qdrant_port}")
        self._client = AsyncQdrantClient(
            host=self.settings.qdrant_host,
            port=self.settings.qdrant_port,
            api_key=self.settings.qdrant_api_key,
        )
        await self.ensure_collection()
        logger.info("Qdrant connection established")

    async def close(self):
        """Close Qdrant client connection."""
        if self._client:
            await self._client.close()
            self._client = None
            logger.info("Qdrant connection closed")

    async def ensure_collection(self):
        """Ensure the collection exists, creating it if necessary."""
        exists = await self.client.collection_exists(self.collection)
        if not exists:
            logger.info(f"Creating collection '{self.collection}'")
            await self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(
                    size=self.vector_size,
                    distance=Distance.COSINE,
                ),
                hnsw_config={
                    "m": 16,
                    "ef_construct": 200,
                },
            )
            # Create payload indexes for filtering
            await self.client.create_payload_index(
                collection_name=self.collection,
                field_name="doc_id",
                field_schema="keyword",
            )
            await self.client.create_payload_index(
                collection_name=self.collection,
                field_name="status",
                field_schema="keyword",
            )
            logger.info(f"Collection '{self.collection}' created with indexes")

    async def upsert(self, points: List[dict]):
        """Batch upsert vector points with payloads."""
        qdrant_points = [
            PointStruct(
                id=p["id"],
                vector=p["vector"],
                payload=p["payload"],
            )
            for p in points
        ]
        try:
            await self.client.upsert(
                collection_name=self.collection,
                points=qdrant_points,
            )
            logger.debug(f"Upserted {len(points)} points")
        except Exception as e:
            raise VectorStoreError(f"Failed to upsert points: {str(e)}")

    async def search(
        self,
        vector: List[float],
        top_k: int = 5,
        filter_doc_ids: Optional[List[str]] = None,
        similarity_threshold: Optional[float] = None,
    ) -> List[dict]:
        """Search for similar vectors."""
        if similarity_threshold is None:
            similarity_threshold = self.settings.similarity_threshold

        query_filter = None
        if filter_doc_ids:
            query_filter = Filter(
                must=[
                    FieldCondition(
                        key="doc_id",
                        match=MatchAny(any=filter_doc_ids),
                    )
                ]
            )

        try:
            results = await self.client.search(
                collection_name=self.collection,
                query_vector=vector,
                limit=top_k,
                query_filter=query_filter,
                with_payload=True,
                score_threshold=similarity_threshold,
            )
            return [
                {
                    "id": hit.id,
                    "score": hit.score,
                    "payload": hit.payload,
                }
                for hit in results
            ]
        except Exception as e:
            raise VectorStoreError(f"Search failed: {str(e)}")

    async def delete_by_doc_id(self, doc_id: str):
        """Delete all points for a given document."""
        try:
            await self.client.delete(
                collection_name=self.collection,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="doc_id",
                            match=MatchValue(value=doc_id),
                        )
                    ]
                ),
            )
            logger.info(f"Deleted points for doc_id={doc_id}")
        except Exception as e:
            raise VectorStoreError(f"Failed to delete points: {str(e)}")

    async def count(self, doc_id: Optional[str] = None) -> int:
        """Count points, optionally filtered by doc_id."""
        if doc_id:
            filter_condition = Filter(
                must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
            )
        else:
            filter_condition = None
        result = await self.client.count(
            collection_name=self.collection,
            count_filter=filter_condition,
        )
        return result.count
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/vector_store.py && git commit -m "feat: add Qdrant vector store service"
```

---

### Task 5: Document Service

**Files:**
- Create: `backend/app/services/document_service.py`

**Interfaces:**
- Consumes: `Settings`, `TextSplitter`, `EmbeddingService`, `VectorStore`, `PDFParser`
- Produces: `DocumentService(settings, text_splitter, embedding_service, vector_store)` — `process_document(file_path, doc_id, filename)` → doc record dict, `get_document(doc_id)`, `get_documents()`, `get_status(doc_id)`, `delete_document(doc_id)`

- [ ] **Step 1: Create document_service.py**

```python
"""Document processing and management service."""
import uuid
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import UploadFile
from fastapi.concurrency import run_in_threadpool

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    DocumentNotFound, PDFParseError, InvalidFileTypeError, FileTooLargeError
)
from app.core.logger import setup_logger
from app.utils.pdf_parser import PDFParser
from app.utils.text_splitter import TextSplitter
from app.utils.embedding import EmbeddingService
from app.services.vector_store import VectorStore

logger = setup_logger("rag_kb.document")

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
ALLOWED_MIME = {"application/pdf"}


class DocumentService:
    """Manages document lifecycle: upload, parse, chunk, embed, index, query, delete."""

    def __init__(
        self,
        settings: Settings,
        text_splitter: TextSplitter,
        embedding_service: EmbeddingService,
        vector_store: VectorStore,
    ):
        self.settings = settings
        self.text_splitter = text_splitter
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.pdf_parser = PDFParser()
        # In-memory document metadata store (production would use a real DB)
        self._documents: Dict[str, Dict[str, Any]] = {}

    def validate_file(self, file: UploadFile) -> None:
        """Validate uploaded file type and size."""
        if file.content_type not in ALLOWED_MIME:
            raise InvalidFileTypeError()

        # Check magic number for PDF
        header = file.file.read(8)
        file.file.seek(0)
        if not header.startswith(b"%PDF-"):
            raise InvalidFileTypeError()

        # Check size by reading content length
        file.file.seek(0, os.SEEK_END)
        size = file.file.tell()
        file.file.seek(0)
        if size > MAX_FILE_SIZE:
            raise FileTooLargeError()

    async def save_upload(self, file: UploadFile) -> Path:
        """Save uploaded file to disk with UUID name."""
        os.makedirs(self.settings.doc_dir, exist_ok=True)

        doc_id = f"doc_{uuid.uuid4().hex[:10]}"
        safe_name = f"{doc_id}.pdf"
        file_path = Path(self.settings.doc_dir) / safe_name

        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)

        return file_path, doc_id

    async def process_document(self, file: UploadFile) -> dict:
        """Full document processing pipeline: validate → save → parse → chunk → embed → index."""
        # Validate
        self.validate_file(file)

        # Save
        file_path, doc_id = await self.save_upload(file)
        filename = file.filename or "unknown.pdf"

        # Record initial state
        doc_record = {
            "doc_id": doc_id,
            "filename": filename,
            "status": "pending",
            "total_pages": 0,
            "total_chunks": 0,
            "message": "Document queued for processing",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        self._documents[doc_id] = doc_record

        # Process asynchronously (in production: background task queue)
        try:
            doc_record["status"] = "processing"
            doc_record["message"] = "Parsing PDF"
            doc_record["updated_at"] = datetime.utcnow().isoformat()

            # Parse PDF (CPU-intensive, run in thread pool)
            chunks = await run_in_threadpool(
                self.pdf_parser.parse_with_tables, file_path
            )
            metadata = await run_in_threadpool(
                self.pdf_parser.get_metadata, file_path
            )
            doc_record["total_pages"] = metadata.get("total_pages", len(chunks))
            doc_record["message"] = f"Parsed {len(chunks)} pages"

            # Split into chunks
            all_chunks = []
            for chunk in chunks:
                text_chunks = self.text_splitter.split(
                    text=chunk.content,
                    doc_id=doc_id,
                    doc_name=filename,
                    page=chunk.page,
                )
                all_chunks.extend(text_chunks)

            doc_record["message"] = f"Chunked into {len(all_chunks)} segments"
            doc_record["total_chunks"] = len(all_chunks)

            # Generate embeddings in batches
            BATCH_SIZE = 32
            texts = [c["content"] for c in all_chunks]
            all_embeddings = []

            for i in range(0, len(texts), BATCH_SIZE):
                batch_texts = texts[i:i + BATCH_SIZE]
                batch_embeddings = await run_in_threadpool(
                    self.embedding_service.embed_texts, batch_texts
                )
                all_embeddings.extend(batch_embeddings)
                progress = min(100, int((i + len(batch_texts)) / len(texts) * 100))
                doc_record["message"] = f"Embedding chunks: {i + len(batch_texts)}/{len(texts)}"
                doc_record["updated_at"] = datetime.utcnow().isoformat()

            # Prepare Qdrant points
            points = []
            for i, chunk in enumerate(all_chunks):
                points.append({
                    "id": f"{doc_id}_{i}",
                    "vector": all_embeddings[i],
                    "payload": {
                        "doc_id": doc_id,
                        "doc_name": filename,
                        "content": chunk["content"],
                        "page": chunk["page"],
                        "chunk_index": chunk["chunk_index"],
                        "status": doc_record["status"],
                        "created_at": doc_record["created_at"],
                    },
                })

            # Upsert to Qdrant
            doc_record["message"] = f"Indexing {len(points)} vectors"
            await self.vector_store.upsert(points)

            doc_record["status"] = "completed"
            doc_record["message"] = "Processing complete"
            doc_record["updated_at"] = datetime.utcnow().isoformat()

        except Exception as e:
            logger.error(f"Failed to process document {doc_id}: {str(e)}")
            doc_record["status"] = "failed"
            doc_record["message"] = str(e)
            doc_record["updated_at"] = datetime.utcnow().isoformat()

        return doc_record

    def get_document(self, doc_id: str) -> dict:
        """Get a single document record."""
        if doc_id not in self._documents:
            raise DocumentNotFound(doc_id)
        return self._documents[doc_id]

    def get_documents(self) -> List[dict]:
        """Get all document records, newest first."""
        docs = list(self._documents.values())
        docs.sort(key=lambda d: d.get("created_at", ""), reverse=True)
        return docs

    def get_status(self, doc_id: str) -> dict:
        """Get processing status for a document."""
        doc = self.get_document(doc_id)
        return {
            "doc_id": doc["doc_id"],
            "status": doc["status"],
            "progress": self._compute_progress(doc),
            "message": doc.get("message", ""),
            "updated_at": doc.get("updated_at", ""),
        }

    async def delete_document(self, doc_id: str) -> dict:
        """Delete a document and its vectors."""
        if doc_id not in self._documents:
            raise DocumentNotFound(doc_id)

        # Delete vectors from Qdrant
        await self.vector_store.delete_by_doc_id(doc_id)

        # Delete file from disk
        file_path = Path(self.settings.doc_dir) / f"{doc_id}.pdf"
        if file_path.exists():
            os.remove(file_path)

        # Remove from in-memory store
        del self._documents[doc_id]

        return {"doc_id": doc_id, "deleted": True}

    def _compute_progress(self, doc: dict) -> int:
        """Estimate processing progress percentage."""
        status = doc.get("status", "pending")
        if status == "pending":
            return 0
        if status == "completed":
            return 100
        if status == "failed":
            return 0
        # processing — parse the message for progress
        msg = doc.get("message", "")
        if "/" in msg:
            try:
                parts = msg.split(":")[-1].strip()
                done, total = parts.split("/")
                return int(int(done) / int(total) * 100)
            except (ValueError, ZeroDivisionError):
                pass
        return 50  # default mid-processing
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/document_service.py && git commit -m "feat: add document processing service"
```

---

### Task 6: RAG Service

**Files:**
- Create: `backend/app/services/rag_service.py`

**Interfaces:**
- Consumes: `Settings`, `EmbeddingService`, `VectorStore`
- Produces: `RAGService(settings, embedding_service, vector_store)` — `query(question, top_k, filter_doc_ids)` → `{"answer", "sources", "query_time_ms", "model"}`, `query_stream(question, top_k, filter_doc_ids)` → async generator of SSE events

- [ ] **Step 1: Create rag_service.py**

```python
"""RAG query pipeline service."""
import time
from typing import List, Optional, AsyncGenerator, Dict, Any
from llama_index.core import VectorStoreIndex, Settings as LlamaSettings
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.postprocessor import SimilarityPostprocessor
from llama_index.core.schema import NodeWithScore
from llama_index.llms.openai import OpenAI

from app.core.config import Settings
from app.core.exceptions import EmptyQueryError, QueryTooLongError, NoRelevantDocsError, LLMUnavailableError
from app.core.logger import setup_logger

logger = setup_logger("rag_kb.rag")


class RAGService:
    """Orchestrates the RAG pipeline: retrieve → synthesize → answer."""

    def __init__(
        self,
        settings: Settings,
        embedding_service,
        vector_store,
    ):
        self.settings = settings
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self._llm = None

    @property
    def llm(self):
        """Lazy-load the LLM."""
        if self._llm is None:
            kwargs = {
                "model": self.settings.llm_model,
                "temperature": self.settings.llm_temperature,
            }
            if self.settings.openai_api_key:
                kwargs["api_key"] = self.settings.openai_api_key
            if self.settings.openai_base_url:
                kwargs["api_base"] = self.settings.openai_base_url
            self._llm = OpenAI(**kwargs)
        return self._llm

    async def query(
        self,
        question: str,
        top_k: int = 5,
        filter_doc_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Execute a RAG query and return answer with sources."""
        self._validate_query(question, top_k)

        start_time = time.time()

        try:
            # Generate query embedding
            query_vector = await self._embed_query(question)

            # Search Qdrant
            results = await self.vector_store.search(
                vector=query_vector,
                top_k=top_k,
                filter_doc_ids=filter_doc_ids,
            )

            if not results:
                raise NoRelevantDocsError()

            # Build context from retrieved chunks
            context_parts = []
            sources = []
            for hit in results:
                payload = hit["payload"]
                context_parts.append(f"[来源: {payload.get('doc_name', '')}, 第{payload.get('page', '?')}页]\n{payload.get('content', '')}")
                sources.append({
                    "doc_id": payload.get("doc_id", ""),
                    "doc_name": payload.get("doc_name", ""),
                    "page": payload.get("page"),
                    "chunk_index": payload.get("chunk_index"),
                    "score": round(hit["score"], 4),
                })

            context = "\n\n---\n\n".join(context_parts)

            # Generate answer with LLM
            prompt = self._build_prompt(question, context)
            answer = await self._generate(prompt)

            query_time_ms = int((time.time() - start_time) * 1000)

            return {
                "answer": answer,
                "sources": sources,
                "query_time_ms": query_time_ms,
                "model": self.settings.llm_model,
            }

        except (EmptyQueryError, QueryTooLongError, NoRelevantDocsError):
            raise
        except Exception as e:
            logger.error(f"RAG query failed: {str(e)}")
            raise LLMUnavailableError(str(e))

    async def query_stream(
        self,
        question: str,
        top_k: int = 5,
        filter_doc_ids: Optional[List[str]] = None,
    ) -> AsyncGenerator[str, None]:
        """Execute a RAG query with streaming SSE response."""
        self._validate_query(question, top_k)

        start_time = time.time()

        yield self._sse_event("start", {"query_time_ms": 0})

        try:
            # Generate query embedding
            query_vector = await self._embed_query(question)

            # Search Qdrant
            results = await self.vector_store.search(
                vector=query_vector,
                top_k=top_k,
                filter_doc_ids=filter_doc_ids,
            )

            if not results:
                yield self._sse_event("error", {"message": "No relevant documents found"})
                yield self._sse_event("end", {"query_time_ms": int((time.time() - start_time) * 1000)})
                return

            # Build context
            context_parts = []
            sources = []
            for hit in results:
                payload = hit["payload"]
                context_parts.append(f"[来源: {payload.get('doc_name', '')}, 第{payload.get('page', '?')}页]\n{payload.get('content', '')}")
                sources.append({
                    "doc_id": payload.get("doc_id", ""),
                    "doc_name": payload.get("doc_name", ""),
                    "page": payload.get("page"),
                    "chunk_index": payload.get("chunk_index"),
                    "score": round(hit["score"], 4),
                })

            context = "\n\n---\n\n".join(context_parts)
            prompt = self._build_prompt(question, context)

            # Streaming LLM response
            try:
                response = self.llm.stream_complete(prompt)
                for chunk in response:
                    content = chunk.delta if hasattr(chunk, 'delta') else str(chunk)
                    if content:
                        yield self._sse_event("chunk", {"content": content})
            except AttributeError:
                # Fallback: non-streaming LLM
                answer = self.llm.complete(prompt)
                text = answer.text if hasattr(answer, 'text') else str(answer)
                # Simulate streaming by chunking the output
                chunk_size = 10
                for i in range(0, len(text), chunk_size):
                    yield self._sse_event("chunk", {"content": text[i:i + chunk_size]})

            # Send sources
            yield self._sse_event("sources", {"sources": sources})

            query_time_ms = int((time.time() - start_time) * 1000)
            yield self._sse_event("end", {"query_time_ms": query_time_ms})

        except Exception as e:
            logger.error(f"Streaming query failed: {str(e)}")
            yield self._sse_event("error", {"message": str(e)})
            yield self._sse_event("end", {"query_time_ms": int((time.time() - start_time) * 1000)})

    def _validate_query(self, question: str, top_k: int):
        """Validate query parameters."""
        if not question or not question.strip():
            raise EmptyQueryError()
        if len(question) > 2000:
            raise QueryTooLongError()
        if top_k < 1 or top_k > self.settings.max_top_k:
            top_k = self.settings.default_top_k

    async def _embed_query(self, text: str) -> List[float]:
        """Generate embedding for a query."""
        from fastapi.concurrency import run_in_threadpool
        return await run_in_threadpool(self.embedding_service.embed_query, text)

    async def _generate(self, prompt: str) -> str:
        """Generate an answer from the LLM."""
        from fastapi.concurrency import run_in_threadpool

        def _sync_generate():
            response = self.llm.complete(prompt)
            return response.text if hasattr(response, 'text') else str(response)

        return await run_in_threadpool(_sync_generate)

    def _build_prompt(self, question: str, context: str) -> str:
        """Build the RAG prompt."""
        return f"""你是一个专业的知识库问答助手，基于提供的国家标准文档内容回答问题。

请遵循以下规则：
1. 仅根据以下文档内容回答问题，不要使用你的先验知识
2. 如果文档中没有相关信息，请明确说明"根据提供的文档，未找到相关信息"
3. 引用具体规范条文时，注明来源
4. 答案要准确、简洁、结构化

文档内容：
{context}

用户问题：{question}

请回答："""

    def _sse_event(self, event_type: str, data: dict) -> str:
        """Format a Server-Sent Event."""
        import json
        payload = json.dumps({"type": event_type, **data}, ensure_ascii=False)
        return f"data: {payload}\n\n"
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/rag_service.py && git commit -m "feat: add RAG query service with streaming support"
```

---

### Task 7: API Routes — Health & Documents

**Files:**
- Create: `backend/app/api/health.py`
- Create: `backend/app/api/documents.py`

**Interfaces:**
- Consumes: `DocumentService`
- Produces: `router` for health check + document CRUD endpoints matching `04-api-spec.md`

- [ ] **Step 1: Create health.py**

```python
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
```

- [ ] **Step 2: Create documents.py**

```python
"""Document management API endpoints."""
from fastapi import APIRouter, UploadFile, File, Depends, Path, status as http_status
from app.core.config import Settings, get_settings
from app.core.exceptions import DocumentNotFound
from app.models.schemas import DocumentUploadResponse, DocumentListItem
from app.services.document_service import DocumentService
from app.services.vector_store import VectorStore
from app.utils.text_splitter import TextSplitter
from app.utils.embedding import EmbeddingService

router = APIRouter(prefix="/documents", tags=["Documents"])


def get_document_service(
    settings: Settings = Depends(get_settings),
) -> DocumentService:
    """Dependency injection for DocumentService."""
    text_splitter = TextSplitter(settings)
    embedding_service = EmbeddingService(settings)
    vector_store = VectorStore(settings)
    return DocumentService(
        settings=settings,
        text_splitter=text_splitter,
        embedding_service=embedding_service,
        vector_store=vector_store,
    )


@router.post(
    "/upload",
    response_model=dict,
    status_code=http_status.HTTP_201_CREATED,
    summary="Upload PDF document",
    description="Upload a national standard PDF file. The backend will parse, chunk, embed, and index it asynchronously."
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
            "metadata": {
                "title": doc.get("filename", ""),
                "author": "",
                "total_pages": doc.get("total_pages", 0),
            },
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
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/health.py backend/app/api/documents.py && git commit -m "feat: add health check and document management API routes"
```

---

### Task 8: API Routes — Query

**Files:**
- Create: `backend/app/api/query.py`

**Interfaces:**
- Consumes: `RAGService`, `QueryRequest`, `QueryResponse`
- Produces: `router` — `POST /query` (sync), `POST /query/stream` (SSE streaming)

- [ ] **Step 1: Create query.py**

```python
"""Query / Q&A API endpoints."""
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from app.core.config import Settings, get_settings
from app.models.schemas import QueryRequest, QueryResponse
from app.services.rag_service import RAGService
from app.services.vector_store import VectorStore
from app.utils.embedding import EmbeddingService

router = APIRouter(prefix="/query", tags=["Query"])


def get_rag_service(
    settings: Settings = Depends(get_settings),
) -> RAGService:
    """Dependency injection for RAGService."""
    embedding_service = EmbeddingService(settings)
    vector_store = VectorStore(settings)
    return RAGService(
        settings=settings,
        embedding_service=embedding_service,
        vector_store=vector_store,
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
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/query.py && git commit -m "feat: add Q&A query API routes (sync + SSE streaming)"
```

---

### Task 9: FastAPI Application Entry Point

**Files:**
- Create: `backend/app/main.py`
- Modify: `backend/app/core/config.py`
- Create: `backend/.env.example`
- Create: `backend/Dockerfile`

**Interfaces:**
- Consumes: All API routers, exceptions, config
- Produces: Runnable FastAPI application with lifespan management, CORS, routes

- [ ] **Step 1: Update config.py** — add `host`, `port`, `cors_origins` updates (already done in Task 1, verify)

- [ ] **Step 2: Create main.py** (from `02-backend-spec.md` §2.1)

```python
"""FastAPI application entry point."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.exceptions import setup_exception_handlers
from app.core.logger import setup_logger
from app.api import health, documents, query

settings = get_settings()
logger = setup_logger("rag_kb")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: startup / shutdown."""
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"Embedding model: {settings.embedding_model}")
    logger.info(f"LLM model: {settings.llm_model}")
    logger.info(f"Qdrant: {settings.qdrant_host}:{settings.qdrant_port}")
    yield
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
```

- [ ] **Step 3: Create .env.example**

```
# Application
APP_NAME=RAG Knowledge Base
APP_VERSION=0.1.0
DEBUG=true
HOST=0.0.0.0
PORT=8000
CORS_ORIGINS=["http://localhost:5173","http://localhost:3000"]

# LLM / Embedding
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_DEVICE=cpu
LLM_MODEL=gpt-4o
LLM_TEMPERATURE=0.1
OPENAI_API_KEY=sk-your-api-key-here
OPENAI_BASE_URL=

# Qdrant
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_COLLECTION=documents
QDRANT_API_KEY=

# Paths
DATA_DIR=./data
DOC_DIR=./data/documents
VECTOR_DIR=./data/vectors

# Chunking
CHUNK_SIZE=512
CHUNK_OVERLAP=50
CHUNK_SEPARATOR=\n\n

# Retrieval
DEFAULT_TOP_K=5
MAX_TOP_K=20
SIMILARITY_THRESHOLD=0.7
```

- [ ] **Step 4: Create Dockerfile**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# System dependencies for PyMuPDF
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY .env.example .env

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/.env.example backend/Dockerfile && git commit -m "feat: add FastAPI entry point, .env.example, and Dockerfile"
```

---

### Task 10: Test Suite

**Files:**
- Create: `backend/pytest.ini`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/unit/__init__.py`
- Create: `backend/tests/integration/__init__.py`
- Create: `backend/tests/unit/test_pdf_parser.py`
- Create: `backend/tests/unit/test_text_splitter.py`
- Create: `backend/tests/api/test_health.py`
- Create: `backend/tests/api/test_documents.py`

**Interfaces:**
- Consumes: All backend modules
- Produces: pytest test suite with fixtures and test cases

- [ ] **Step 1: Create pytest.ini**

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -v --tb=short
```

- [ ] **Step 2: Create tests/conftest.py**

```python
"""Shared pytest fixtures."""
import pytest
from app.core.config import Settings, get_settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        qdrant_host="fake-host",
        openai_api_key="fake-key",
        debug=True,
    )


@pytest.fixture
def sample_pdf_path(tmp_path):
    """Create a minimal valid PDF file for testing."""
    pdf_path = tmp_path / "test.pdf"
    # Minimal PDF content
    pdf_content = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
        b"4 0 obj\n<< /Length 44 >>\nstream\n"
        b"BT /F1 12 Tf 100 700 Td (Hello World) Tj ET\n"
        b"endstream\nendobj\n"
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        b"xref\n0 6\n0000000000 65535 f \n0000000009 00000 n \n"
        b"0000000058 00000 n \n0000000115 00000 n \n0000000266 00000 n \n"
        b"0000000360 00000 n \ntrailer\n<< /Size 6 /Root 1 0 R >>\n"
        b"startxref\n414\n%%EOF"
    )
    pdf_path.write_bytes(pdf_content)
    return pdf_path
```

- [ ] **Step 3: Create tests/unit/test_pdf_parser.py**

```python
"""Tests for PDF parser."""
from app.utils.pdf_parser import PDFParser


def test_parse_extracts_text(sample_pdf_path):
    parser = PDFParser()
    chunks = parser.parse(sample_pdf_path)
    assert len(chunks) > 0, "Should extract at least one text chunk"


def test_get_metadata(sample_pdf_path):
    parser = PDFParser()
    meta = parser.get_metadata(sample_pdf_path)
    assert "total_pages" in meta
    assert meta["total_pages"] > 0


def test_parse_with_tables(sample_pdf_path):
    parser = PDFParser()
    chunks = parser.parse_with_tables(sample_pdf_path)
    assert len(chunks) > 0
    assert all(c.page > 0 for c in chunks)
```

- [ ] **Step 4: Create tests/unit/test_text_splitter.py**

```python
"""Tests for text splitter."""
from app.core.config import Settings
from app.utils.text_splitter import TextSplitter


def test_split_empty_text():
    splitter = TextSplitter(Settings(chunk_size=512, chunk_overlap=50))
    chunks = splitter.split("", "doc1", "test.pdf", 1)
    assert len(chunks) == 0


def test_split_short_text():
    splitter = TextSplitter(Settings(chunk_size=512, chunk_overlap=50))
    text = "This is a short text."
    chunks = splitter.split(text, "doc1", "test.pdf", 1)
    assert len(chunks) == 1
    assert chunks[0]["content"] == text
    assert chunks[0]["doc_id"] == "doc1"
    assert chunks[0]["doc_name"] == "test.pdf"
    assert chunks[0]["page"] == 1
    assert chunks[0]["chunk_index"] == 0


def test_split_long_text():
    splitter = TextSplitter(Settings(chunk_size=100, chunk_overlap=20))
    text = "A" * 300
    chunks = splitter.split(text, "doc1", "test.pdf", 2)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk["content"]) <= 100


def test_chunk_metadata():
    splitter = TextSplitter(Settings(chunk_size=512, chunk_overlap=50))
    text = "Paragraph one.\n\nParagraph two."
    chunks = splitter.split(text, "doc_x", "file.pdf", 5)
    assert len(chunks) > 0
    for chunk in chunks:
        assert "content" in chunk
        assert "doc_id" in chunk
        assert "doc_name" in chunk
        assert "page" in chunk
        assert "chunk_index" in chunk
```

- [ ] **Step 5: Create tests/api/test_health.py**

```python
"""Tests for health check endpoint."""
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_health_check():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "SUCCESS"
        assert data["data"]["status"] == "healthy"
        assert "version" in data["data"]
```

- [ ] **Step 6: Create tests/api/test_documents.py**

```python
"""Tests for document API endpoints."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport


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
async def test_list_documents_empty(mock_document_service):
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/documents")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "SUCCESS"
        assert data["data"]["items"] == []


@pytest.mark.asyncio
async def test_get_document(mock_document_service):
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/documents/doc_test123")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "SUCCESS"
        assert data["data"]["doc_id"] == "doc_test123"


@pytest.mark.asyncio
async def test_get_document_status(mock_document_service):
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/documents/doc_test123/status")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "SUCCESS"
        assert data["data"]["status"] == "completed"
```

- [ ] **Step 7: Run tests and commit**

```bash
cd backend && pip install httpx && python -m pytest tests/ -v
git add backend/pytest.ini backend/tests/ && git commit -m "test: add test suite for PDF parser, text splitter, health, and documents API"
```

---

### Task 11: Integration Verification

**Files:**
- None (verification only)

- [ ] **Step 1: Verify all files exist matching the spec structure**

```bash
ls -R backend/app/
```

Expected:
```
backend/app/
├── __init__.py
├── main.py
├── api/
│   ├── __init__.py
│   ├── health.py
│   ├── documents.py
│   └── query.py
├── core/
│   ├── __init__.py
│   ├── config.py
│   ├── logger.py
│   └── exceptions.py
├── models/
│   ├── __init__.py
│   └── schemas.py
├── services/
│   ├── __init__.py
│   ├── rag_service.py
│   ├── vector_store.py
│   └── document_service.py
└── utils/
    ├── __init__.py
    ├── pdf_parser.py
    ├── embedding.py
    └── text_splitter.py
```

- [ ] **Step 2: Verify Python imports resolve**

```bash
cd backend && python -c "
from app.core.config import get_settings
from app.core.exceptions import RAGBaseException
from app.models.schemas import QueryRequest, DocumentStatus
from app.utils.pdf_parser import PDFParser
from app.utils.text_splitter import TextSplitter
from app.utils.embedding import EmbeddingService
print('All imports OK')
"
```

- [ ] **Step 3: Run full test suite**

```bash
cd backend && python -m pytest tests/ -v
```

Expected: All tests pass.

---
