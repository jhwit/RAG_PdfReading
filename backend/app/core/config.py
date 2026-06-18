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
    llm_model: str = "gpt-4o"
    openai_api_key: Optional[str] = None
    openai_base_url: Optional[str] = None

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "documents"

    # Paths
    data_dir: str = "./data"
    doc_dir: str = "./data/documents"
    vector_dir: str = "./data/vectors"

    # Chunking
    chunk_size: int = 512
    chunk_overlap: int = 50

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
