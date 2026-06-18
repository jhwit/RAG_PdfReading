"""PDF parsing utilities with support for complex documents."""
import fitz  # PyMuPDF
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class TextChunk:
    content: str
    page: int
    bbox: Optional[tuple] = None


class PDFParser:
    """Parse PDF documents including scanned and standard PDFs."""

    def __init__(self, dpi: int = 200):
        self.dpi = dpi

    def parse(self, file_path: Path) -> List[TextChunk]:
        """Extract text from PDF with page-level tracking."""
        chunks = []
        doc = fitz.open(str(file_path))

        try:
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                text = page.get_text()

                if text.strip():
                    chunks.append(TextChunk(
                        content=text,
                        page=page_num + 1
                    ))
                else:
                    # Scanned page - would use OCR here
                    logger.warning(f"Page {page_num + 1} appears scanned, OCR not implemented")

        finally:
            doc.close()

        return chunks

    def parse_with_tables(self, file_path: Path) -> List[TextChunk]:
        """Extract text and tables from PDF."""
        chunks = []
        doc = fitz.open(str(file_path))

        try:
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)

                # Extract text blocks with coordinates
                blocks = page.get_text("blocks")
                for block in blocks:
                    x0, y0, x1, y1, text, block_no, block_type = block
                    if text.strip():
                        chunks.append(TextChunk(
                            content=text.strip(),
                            page=page_num + 1,
                            bbox=(x0, y0, x1, y1)
                        ))

                # Extract tables
                tables = page.find_tables()
                if tables.tables:
                    for idx, table in enumerate(tables.tables):
                        df = table.to_pandas()
                        chunks.append(TextChunk(
                            content=f"[Table {idx + 1}]\n{df.to_string()}",
                            page=page_num + 1
                        ))

        finally:
            doc.close()

        return chunks

    def get_metadata(self, file_path: Path) -> dict:
        """Get PDF metadata."""
        doc = fitz.open(str(file_path))
        try:
            return {
                "title": doc.metadata.get("title", ""),
                "author": doc.metadata.get("author", ""),
                "subject": doc.metadata.get("subject", ""),
                "creator": doc.metadata.get("creator", ""),
                "total_pages": len(doc),
            }
        finally:
            doc.close()
