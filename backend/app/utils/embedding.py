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
