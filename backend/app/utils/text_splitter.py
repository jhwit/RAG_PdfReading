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
