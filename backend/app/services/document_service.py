"""Document processing and management service."""
import uuid
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from fastapi import UploadFile
from fastapi.concurrency import run_in_threadpool

from app.core.config import Settings
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

    async def save_upload(self, file: UploadFile) -> Tuple[Path, str]:
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
