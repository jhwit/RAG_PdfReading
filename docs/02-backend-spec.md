# 后端开发规范（FastAPI）

## 1. 项目结构

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI 应用入口与生命周期管理
│   ├── core/
│   │   ├── config.py           # Pydantic Settings 配置中心
│   │   ├── logger.py           # 结构化日志配置
│   │   ├── exceptions.py       # 全局异常处理器
│   │   └── middleware.py       # 自定义中间件（CORS、请求日志、超时）
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py          # 所有 Pydantic 请求/响应模型
│   ├── api/
│   │   ├── __init__.py
│   │   ├── documents.py        # 文档管理路由
│   │   ├── query.py            # 问答检索路由
│   │   └── health.py           # 健康检查路由
│   ├── services/
│   │   ├── __init__.py
│   │   ├── rag_service.py      # RAG 核心管道编排
│   │   ├── vector_store.py     # Qdrant 向量库操作封装
│   │   └── document_service.py # 文档解析与索引服务
│   └── utils/
│       ├── __init__.py
│       ├── pdf_parser.py       # PDF 解析器（PyMuPDF + Marker）
│       ├── embedding.py        # Embedding 模型封装
│       └── text_splitter.py    # 文本分块策略
├── tests/
│   ├── unit/                   # 单元测试
│   ├── integration/            # 集成测试
│   └── conftest.py             # pytest fixtures
├── requirements.txt
├── Dockerfile
├── .env.example                # 环境变量模板
└── pytest.ini
```

## 2. 核心文件规范

### 2.1 main.py — 应用入口

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.exceptions import setup_exception_handlers
from app.api import documents, query, health

settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理：启动时初始化，关闭时清理。"""
    # Startup
    await vector_store.connect()
    await embedding_model.load()
    yield
    # Shutdown
    await vector_store.close()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 异常处理
setup_exception_handlers(app)

# 路由注册
app.include_router(health.router)
app.include_router(documents.router)
app.include_router(query.router)
```

### 2.2 config.py — 配置管理

```python
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # 应用
    app_name: str = "RAG Knowledge Base"
    app_version: str = "0.1.0"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000

    # CORS
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000"
    ]

    # LLM / Embedding
    embedding_model: str = "BAAI/bge-m3"
    embedding_device: str = "auto"  # auto, cuda, cpu
    llm_model: str = "gpt-4o"
    llm_temperature: float = 0.1
    openai_api_key: str | None = None
    openai_base_url: str | None = None

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "documents"
    qdrant_api_key: str | None = None

    # 路径
    data_dir: str = "./data"
    doc_dir: str = "./data/documents"
    vector_dir: str = "./data/vectors"

    # 分块策略
    chunk_size: int = 512
    chunk_overlap: int = 50
    chunk_separator: str = "\n\n"

    # 检索
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

**规范要点**：
- 所有配置项必须有默认值，保证本地开发可直接运行
- 敏感字段（api_key、password）类型为 `str | None`
- 使用 `@lru_cache()` 避免重复解析

### 2.3 exceptions.py — 全局异常处理

```python
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

class RAGBaseException(Exception):
    """业务异常基类"""
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

def setup_exception_handlers(app):
    @app.exception_handler(RAGBaseException)
    async def handle_rag_exception(request: Request, exc: RAGBaseException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message}
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
            content={"code": "INTERNAL_ERROR", "message": str(exc)}
        )
```

### 2.4 logger.py — 结构化日志

```python
import logging
import sys
import json
from datetime import datetime

class JSONFormatter(logging.Formatter):
    """生产环境 JSON 格式日志"""
    def format(self, record):
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
        }
        if hasattr(record, "extra"):
            log_data.update(record.extra)
        return json.dumps(log_data, ensure_ascii=False)

def get_logger(name: str = "rag_kb") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
```

## 3. API 路由规范

### 3.1 路由注册模式

```python
# app/api/documents.py
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from app.models.schemas import DocumentUploadResponse, DocumentListItem
from app.core.config import get_settings
from app.services.document_service import DocumentService

router = APIRouter(prefix="/documents", tags=["Documents"])

@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    summary="上传 PDF 文档",
    description="上传国家标准 PDF 文件，后端自动解析、分块、向量化并入库"
)
async def upload_document(
    file: UploadFile = File(..., description="PDF 文件，最大 50MB"),
    service: DocumentService = Depends()
):
    """..."""
    ...

@router.get(
    "",
    response_model=list[DocumentListItem],
    summary="获取文档列表"
)
async def list_documents(service: DocumentService = Depends()):
    ...

@router.delete(
    "/{doc_id}",
    summary="删除文档",
    status_code=204
)
async def delete_document(doc_id: str, service: DocumentService = Depends()):
    ...
```

**规范要点**：
- `prefix` 不加版本号，版本在 `main.py` include_router 时统一控制
- 每个端点必须写 `summary` 和 `description`
- `response_model` 必须显式声明
- 使用依赖注入获取 Service 实例

### 3.2 依赖注入模式

```python
# app/services/document_service.py
from fastapi import Depends
from app.core.config import Settings, get_settings
from app.services.vector_store import VectorStore

class DocumentService:
    def __init__(
        self,
        settings: Settings = Depends(get_settings),
        vector_store: VectorStore = Depends()
    ):
        self.settings = settings
        self.vector_store = vector_store

    async def process_document(self, file_path: Path) -> str:
        ...
```

## 4. 服务层规范

### 4.1 RAG 服务（rag_service.py）

```python
from llama_index.core import VectorStoreIndex, Settings
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.postprocessor import SimilarityPostprocessor

class RAGService:
    def __init__(self, vector_store, embedding_model, llm):
        self.vector_store = vector_store
        self.embedding_model = embedding_model
        self.llm = llm

        # LlamaIndex 全局设置
        Settings.embed_model = embedding_model
        Settings.llm = llm

    async def query(self, question: str, top_k: int = 5) -> dict:
        """执行 RAG 查询"""
        index = VectorStoreIndex.from_vector_store(
            vector_store=self.vector_store
        )

        retriever = VectorIndexRetriever(
            index=index,
            similarity_top_k=top_k
        )

        # 重排序与过滤
        postprocessor = SimilarityPostprocessor(similarity_cutoff=0.7)

        query_engine = RetrieverQueryEngine.from_args(
            retriever=retriever,
            node_postprocessors=[postprocessor]
        )

        response = await query_engine.aquery(question)

        return {
            "answer": response.response,
            "sources": [
                {
                    "doc_id": node.node.metadata.get("doc_id"),
                    "doc_name": node.node.metadata.get("doc_name"),
                    "page": node.node.metadata.get("page"),
                    "score": node.score
                }
                for node in response.source_nodes
            ]
        }
```

### 4.2 向量存储封装（vector_store.py）

```python
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams

class VectorStore:
    def __init__(self, host: str, port: int, collection: str, vector_size: int = 1024):
        self.client = AsyncQdrantClient(host=host, port=port)
        self.collection = collection
        self.vector_size = vector_size

    async def ensure_collection(self):
        """确保 Collection 存在"""
        exists = await self.client.collection_exists(self.collection)
        if not exists:
            await self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(
                    size=self.vector_size,
                    distance=Distance.COSINE
                )
            )

    async def upsert(self, points: list):
        """批量写入向量"""
        await self.client.upsert(
            collection_name=self.collection,
            points=points
        )

    async def search(self, vector: list, top_k: int = 5, filter_doc_ids: list = None):
        """向量检索"""
        from qdrant_client.models import Filter, FieldCondition, MatchAny

        query_filter = None
        if filter_doc_ids:
            query_filter = Filter(
                must=[
                    FieldCondition(
                        key="doc_id",
                        match=MatchAny(any=filter_doc_ids)
                    )
                ]
            )

        return await self.client.search(
            collection_name=self.collection,
            query_vector=vector,
            limit=top_k,
            query_filter=query_filter,
            with_payload=True
        )

    async def delete_by_doc_id(self, doc_id: str):
        """按文档 ID 删除"""
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        await self.client.delete(
            collection_name=self.collection,
            points_selector=Filter(
                must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
            )
        )
```

## 5. 工具层规范

### 5.1 PDF 解析器（pdf_parser.py）

```python
import fitz
from pathlib import Path
from dataclasses import dataclass
from typing import List

@dataclass
class ParsedPage:
    text: str
    page_number: int
    tables: List[str]
    images: List[bytes]

class PDFParser:
    def __init__(self, dpi: int = 200):
        self.dpi = dpi

    def parse(self, file_path: Path) -> List[ParsedPage]:
        doc = fitz.open(str(file_path))
        pages = []

        try:
            for i in range(len(doc)):
                page = doc.load_page(i)
                text = page.get_text()
                tables = self._extract_tables(page)

                pages.append(ParsedPage(
                    text=text,
                    page_number=i + 1,
                    tables=tables,
                    images=[]
                ))
        finally:
            doc.close()

        return pages

    def _extract_tables(self, page) -> List[str]:
        tables = page.find_tables()
        if not tables.tables:
            return []
        return [t.to_pandas().to_string() for t in tables.tables]
```

### 5.2 嵌入模型封装（embedding.py）

```python
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from app.core.config import Settings

class EmbeddingService:
    def __init__(self, settings: Settings):
        self.model = HuggingFaceEmbedding(
            model_name=settings.embedding_model,
            device=settings.embedding_device
        )

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        return self.model.get_text_embedding_batch(texts)

    async def embed_query(self, text: str) -> List[float]:
        return self.model.get_text_embedding(text)
```

## 6. 测试规范

### 6.1 pytest 配置

```ini
# pytest.ini
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
```

### 6.2 测试示例

```python
# tests/unit/test_pdf_parser.py
import pytest
from pathlib import Path
from app.utils.pdf_parser import PDFParser

@pytest.fixture
def parser():
    return PDFParser()

@pytest.fixture
def sample_pdf():
    return Path("tests/fixtures/sample.pdf")

def test_parse_returns_pages(parser, sample_pdf):
    pages = parser.parse(sample_pdf)
    assert len(pages) > 0
    assert all(p.text for p in pages)
    assert all(p.page_number > 0 for p in pages)

# tests/api/test_documents.py
import pytest
from httpx import AsyncClient
from app.main import app

@pytest.fixture
async def client():
    async with AsyncClient(app=app, base_url="http://test") as c:
        yield c

@pytest.mark.asyncio
async def test_upload_pdf(client):
    response = await client.post(
        "/api/v1/documents/upload",
        files={"file": ("test.pdf", b"%PDF-1.4 fake", "application/pdf")}
    )
    assert response.status_code == 200
    assert "doc_id" in response.json()
```

## 7. 性能与安全规范

### 7.1 性能优化

- **Embedding 批处理**：单次最多 32 条文本，避免内存溢出
- **PDF 解析异步化**：使用 `run_in_threadpool` 将 CPU 密集型解析放入线程池
- **向量检索缓存**：热点查询结果缓存 5 分钟（Redis 可选）
- **流式响应**：LLM 生成答案使用 SSE 流式输出

### 7.2 安全规范

- **文件类型校验**：只允许 `application/pdf`，通过 magic number 二次校验
- **文件大小限制**：单文件最大 50MB，总存储配额可配置
- **路径遍历防护**：保存文件时使用 UUID 命名，禁止用户控制路径
- **输入过滤**：查询文本长度限制 2000 字符，防止提示注入
- **CORS 白名单**：生产环境只允许特定域名

```python
# 文件上传安全校验
ALLOWED_MIME = {"application/pdf"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

def validate_file(file: UploadFile) -> None:
    if file.content_type not in ALLOWED_MIME:
        raise PDFParseError("Only PDF files are allowed")
    # 读取前 8 字节校验 magic number
    header = file.file.read(8)
    file.file.seek(0)
    if not header.startswith(b"%PDF-"):
        raise PDFParseError("Invalid PDF file")
```
