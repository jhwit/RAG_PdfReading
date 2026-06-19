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
