# RAG 知识库系统 — 开发文档

> **项目定位**：基于国家标准 PDF 文档的 RAG（检索增强生成）知识库问答系统  
> **后端**：FastAPI + LlamaIndex + Qdrant  
> **前端**：Vue 3 + Element Plus  
> **目标**：支持 PDF 上传、向量化存储、语义检索、AI 问答，后期可扩展 Agentic RAG 与 GraphRAG

---

## 1. 系统架构

### 1.1 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                        前端层 (Vue 3)                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ 文档管理  │  │ 知识检索  │  │  AI 问答  │  │ 系统配置  │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP / REST API
┌────────────────────────▼────────────────────────────────────┐
│                     网关层 (Nginx / Traefik)                 │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                      后端层 (FastAPI)                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Document │  │   RAG    │  │  Vector  │  │  Health  │   │
│  │   API    │  │  Service │  │  Store   │  │  Check   │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              LlamaIndex (RAG Pipeline)                │  │
│  │   NodeParser → Embedding → Index → Retriever → LLM   │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────┬────────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┐
        │                │                │
┌───────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐
│   Qdrant     │ │  Embedding  │ │    LLM      │
│ Vector Store │ │   Model     │ │   Service   │
└──────────────┘ └─────────────┘ └─────────────┘
        │                │                │
   (持久化向量)      (BGE-M3等)      (OpenAI/本地)
```

### 1.2 模块职责

| 模块 | 职责 | 技术组件 |
|---|---|---|
| **前端** | 用户交互界面、文件上传、问答交互、结果展示 | Vue 3, Element Plus, Axios |
| **API 网关** | 路由转发、负载均衡、静态资源托管、CORS | Nginx / Traefik |
| **文档服务** | PDF 上传、解析、分块、向量化入库 | FastAPI, PyMuPDF, LlamaIndex |
| **RAG 服务** | 语义检索、上下文组装、LLM 生成答案 | LlamaIndex, Retriever, Synthesizer |
| **向量存储** | 嵌入向量持久化、近似最近邻检索 | Qdrant |
| **嵌入模型** | 文本向量化 | BGE-M3 / GTE / OpenAI Embedding |
| **LLM** | 答案生成、摘要、重排 | GPT-4o / Claude / Qwen / 本地模型 |

### 1.3 数据流

**PDF 上传与索引流程：**
```
用户上传 PDF → 后端接收保存 → PyMuPDF 解析文本 → 清洗与分块
    → SentenceTransformer 生成 Embedding → 写入 Qdrant 向量库
    → 返回文档 ID 与处理状态
```

**问答检索流程：**
```
用户提问 → 查询向量化 → Qdrant ANN 检索 Top-K 文本块
    → 重排序（可选）→ 上下文组装 → LLM 生成答案
    → 返回答案 + 引用来源
```

---

## 2. 技术选型与理由

### 2.1 核心框架

| 技术 | 版本建议 | 选型理由 |
|---|---|---|
| **FastAPI** | ^0.115 | 异步原生、自动 OpenAPI 文档、类型安全、Python 生态最成熟的 ASGI 框架 |
| **Vue 3** | ^3.4 | 组合式 API 更灵活、性能更好、TypeScript 支持完善、社区活跃 |
| **LlamaIndex** | ^0.12 | RAG 领域最专业的框架，文档解析、索引策略、检索优化原生支持 |
| **Qdrant** | ^1.13 | 开源、高性能、支持过滤与混合检索、Docker 一键部署、中文社区友好 |
| **BGE-M3** | latest | 北京智源开源，中文 embedding 效果顶尖，支持多语言、多粒度 |

### 2.2 辅助库

| 技术 | 用途 |
|---|---|
| **PyMuPDF (fitz)** | PDF 文本与表格提取，速度快、功能全 |
| **marker-pdf** | 复杂排版/扫描版 PDF 的高质量解析（备选） |
| **SentenceTransformers** | 本地 Embedding 模型加载与推理 |
| **Element Plus** | Vue 3 UI 组件库，企业级设计 |
| **Axios** | HTTP 客户端，支持拦截器与请求取消 |
| **Pydantic v2** | 数据校验、序列化、Settings 管理 |

### 2.3 为什么不选 LangChain 作为主框架？

- **LlamaIndex 在 RAG 场景更专业**：文档加载器、分块策略、索引类型（摘要索引、树形索引、知识图谱索引）设计更细致
- **国家标准 PDF 特点**：复杂表格、层级标题、公式、引用关系，LlamaIndex 的 `IngestionPipeline` 和 `NodeParser` 对这些场景支持更好
- **LangChain 可作为补充**：后期复杂 Agentic RAG 工作流（查询路由、多跳推理、结果验证）可引入 LangGraph 与 LlamaIndex 结合

---

## 3. 后端开发规范（FastAPI）

### 3.1 项目目录结构

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI 应用入口
│   ├── core/
│   │   ├── config.py           # Pydantic Settings 配置
│   │   ├── logger.py           # 日志配置
│   │   └── exceptions.py       # 全局异常处理
│   ├── models/
│   │   └── schemas.py          # Pydantic 请求/响应模型
│   ├── api/
│   │   ├── __init__.py
│   │   ├── documents.py        # 文档管理接口
│   │   ├── query.py            # 问答检索接口
│   │   └── health.py           # 健康检查接口
│   ├── services/
│   │   ├── rag_service.py      # RAG 核心业务逻辑
│   │   ├── vector_store.py     # Qdrant 向量库封装
│   │   └── document_service.py # 文档处理服务
│   └── utils/
│       ├── pdf_parser.py       # PDF 解析工具
│       └── embedding.py        # 嵌入模型封装
├── tests/                      # 单元测试与集成测试
├── requirements.txt
├── Dockerfile
└── .env                        # 环境变量（不提交 Git）
```

### 3.2 配置管理规范

使用 `pydantic-settings` 管理配置，支持 `.env` 文件与环境变量覆盖：

```python
# app/core/config.py
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    app_name: str = "RAG Knowledge Base"
    debug: bool = False
    cors_origins: list[str] = ["http://localhost:5173"]

    # LLM / Embedding
    embedding_model: str = "BAAI/bge-m3"
    llm_model: str = "gpt-4o"
    openai_api_key: str | None = None

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "documents"

    # Chunking
    chunk_size: int = 512
    chunk_overlap: int = 50

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings() -> Settings:
    return Settings()
```

**规范要求**：
- 所有可配置项必须放入 `Settings`，禁止代码中硬编码
- 敏感信息（API Key、密码）只通过环境变量注入
- `.env` 文件加入 `.gitignore`

### 3.3 API 路由规范

```python
# app/api/documents.py
from fastapi import APIRouter, UploadFile, File, Depends
from app.models.schemas import DocumentUploadResponse
from app.core.config import get_settings

router = APIRouter(prefix="/api/v1/documents", tags=["Documents"])

@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    settings = Depends(get_settings)
):
    """Upload a PDF document for indexing."""
    ...
```

**规范要求**：
- 所有路由统一前缀 `/api/v1`
- 使用 `tags` 分组，便于自动生成文档分类
- 响应模型必须显式声明 `response_model`
- 依赖注入使用 `Depends`

### 3.4 异常处理规范

```python
# app/core/exceptions.py
from fastapi import Request
from fastapi.responses import JSONResponse

async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"code": "INTERNAL_ERROR", "message": str(exc)}
    )

# main.py 中注册
app.add_exception_handler(Exception, global_exception_handler)
```

### 3.5 异步规范

- **IO 密集型操作必须异步**：文件上传、数据库操作、HTTP 请求
- **CPU 密集型操作放入线程池**：PDF 解析、Embedding 推理、LLM 调用

```python
from fastapi.concurrency import run_in_threadpool

@router.post("/upload")
async def upload(file: UploadFile):
    content = await file.read()
    # CPU 密集型：PDF 解析
    result = await run_in_threadpool(parse_pdf, content)
    return result
```

### 3.6 日志规范

```python
import logging
import sys

logger = logging.getLogger("rag_kb")
logger.setLevel(logging.INFO)

formatter = logging.Formatter(
    "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)

console = logging.StreamHandler(sys.stdout)
console.setFormatter(formatter)
logger.addHandler(console)
```

**规范要求**：
- 统一使用 `logging` 而非 `print`
- Logger 名称按模块命名：`rag_kb.documents`, `rag_kb.rag`
- 生产环境日志输出 JSON 格式，便于日志收集系统解析

---

## 4. 前端开发规范（Vue 3）

### 4.1 项目目录结构

```
frontend/
├── public/
├── src/
│   ├── api/
│   │   ├── client.js           # Axios 实例配置
│   │   ├── documents.js        # 文档 API 封装
│   │   └── query.js            # 问答 API 封装
│   ├── components/
│   │   ├── UploadPanel.vue     # 文件上传组件
│   │   ├── ChatPanel.vue       # 问答对话组件
│   │   ├── DocumentList.vue    # 文档列表组件
│   │   └── SourceCard.vue      # 引用来源展示组件
│   ├── views/
│   │   ├── HomeView.vue        # 首页
│   │   ├── DocumentsView.vue   # 文档管理页
│   │   └── ChatView.vue        # 问答页
│   ├── router/
│   │   └── index.js            # Vue Router 配置
│   ├── stores/
│   │   └── documents.js        # Pinia 状态管理
│   ├── App.vue
│   └── main.js
├── package.json
├── vite.config.js
└── index.html
```

### 4.2 技术栈

| 技术 | 版本建议 | 用途 |
|---|---|---|
| **Vue 3** | ^3.4 | 框架核心 |
| **Vue Router 4** | ^4.2 | 前端路由 |
| **Pinia** | ^2.1 | 状态管理 |
| **Element Plus** | ^2.5 | UI 组件库 |
| **Axios** | ^1.7 | HTTP 请求 |
| **Vite** | ^5.0 | 构建工具 |

### 4.3 Axios 封装规范

```javascript
// src/api/client.js
import axios from 'axios'

const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' }
})

// 请求拦截器：添加认证、日志
client.interceptors.request.use(config => {
  console.log(`[API] ${config.method.toUpperCase()} ${config.url}`)
  return config
})

// 响应拦截器：统一错误处理
client.interceptors.response.use(
  response => response.data,
  error => {
    const message = error.response?.data?.message || error.message
    console.error(`[API Error] ${message}`)
    return Promise.reject(error)
  }
)

export default client
```

### 4.4 API 模块封装

```javascript
// src/api/documents.js
import client from './client.js'

export const documentsApi = {
  upload: (file, onProgress) => {
    const formData = new FormData()
    formData.append('file', file)
    return client.post('/documents/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: onProgress
    })
  },

  list: () => client.get('/documents'),

  delete: (docId) => client.delete(`/documents/${docId}`),

  getStatus: (docId) => client.get(`/documents/${docId}/status`)
}
```

### 4.5 组件开发规范

```vue
<!-- src/components/UploadPanel.vue -->
<template>
  <div class="upload-panel">
    <el-upload
      drag
      action="/api/v1/documents/upload"
      accept=".pdf"
      :before-upload="beforeUpload"
      :on-success="onSuccess"
      :on-error="onError"
    >
      <el-icon class="el-icon--upload"><upload-filled /></el-icon>
      <div class="el-upload__text">
        拖拽文件到此处或 <em>点击上传</em>
      </div>
      <template #tip>
        <div class="el-upload__tip">
          仅支持 PDF 文件，单个文件不超过 50MB
        </div>
      </template>
    </el-upload>
  </div>
</template>

<script setup>
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'

const beforeUpload = (file) => {
  const isPdf = file.type === 'application/pdf'
  if (!isPdf) {
    ElMessage.error('仅支持 PDF 文件')
  }
  return isPdf
}

const onSuccess = (response) => {
  ElMessage.success(`上传成功: ${response.doc_id}`)
}

const onError = (error) => {
  ElMessage.error(error.message || '上传失败')
}
</script>
```

**规范要求**：
- 使用 `<script setup>` 语法
- 组件名使用 PascalCase
- Props 使用 `defineProps` 并声明类型
- 事件使用 `defineEmits`
- 样式使用 `scoped` 或 CSS Modules

### 4.6 状态管理规范

```javascript
// src/stores/documents.js
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { documentsApi } from '@/api/documents.js'

export const useDocumentStore = defineStore('documents', () => {
  // State
  const documents = ref([])
  const loading = ref(false)

  // Getters
  const completedDocs = computed(() =>
    documents.value.filter(d => d.status === 'completed')
  )

  // Actions
  const fetchDocuments = async () => {
    loading.value = true
    try {
      const res = await documentsApi.list()
      documents.value = res.items
    } finally {
      loading.value = false
    }
  }

  const addDocument = (doc) => {
    documents.value.unshift(doc)
  }

  return { documents, loading, completedDocs, fetchDocuments, addDocument }
})
```

### 4.7 环境变量

```
# .env.development
VITE_API_BASE_URL=http://localhost:8000/api/v1

# .env.production
VITE_API_BASE_URL=/api/v1
```

---

## 5. 向量数据库设计（Qdrant）

### 5.1 Collection 设计

```python
# Collection 名称: documents
{
    "vectors": {
        "size": 1024,           # BGE-M3 输出维度
        "distance": "Cosine"    # 余弦相似度
    },
    "hnsw_config": {
        "m": 16,                # 图连接数
        "ef_construct": 200     # 构建时搜索深度
    }
}
```

### 5.2 Payload 字段设计

| 字段 | 类型 | 说明 |
|---|---|---|
| `doc_id` | string | 文档唯一标识 |
| `doc_name` | string | 文件名 |
| `content` | string | 文本块内容 |
| `page` | integer | 页码 |
| `chunk_index` | integer | 块序号 |
| `status` | string | 文档处理状态 |
| `created_at` | timestamp | 创建时间 |

### 5.3 索引策略

```python
# 为常用过滤字段创建索引
client.create_payload_index(
    collection_name="documents",
    field_name="doc_id",
    field_schema="keyword"
)

client.create_payload_index(
    collection_name="documents",
    field_name="status",
    field_schema="keyword"
)
```

---

## 6. 部署架构

### 6.1 Docker Compose 部署

```yaml
# docker-compose.yml
version: "3.8"

services:
  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
    volumes:
      - qdrant_storage:/qdrant/storage

  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - QDRANT_HOST=qdrant
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    volumes:
      - ./data:/app/data
    depends_on:
      - qdrant

  frontend:
    build: ./frontend
    ports:
      - "80:80"
    depends_on:
      - backend

volumes:
  qdrant_storage:
```

### 6.2 生产环境建议

| 层面 | 建议 |
|---|---|
| **网关** | Nginx 做反向代理、SSL 终止、静态资源缓存 |
| **后端** | Gunicorn + Uvicorn Worker，4-8 进程 |
| **向量库** | Qdrant 集群模式，SSD 存储 |
| **监控** | Prometheus + Grafana 监控 API 与向量库 |
| **日志** | ELK Stack 或 Loki 集中收集 |

---

## 7. 开发流程

### 7.1 环境准备

```bash
# 1. 克隆项目
git clone <repo>
cd rag-knowledge-base

# 2. 启动向量库
docker-compose up -d qdrant

# 3. 后端环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r backend/requirements.txt
cd backend && uvicorn app.main:app --reload

# 4. 前端环境
cd frontend
npm install
npm run dev
```

### 7.2 代码提交规范

```
feat: 新增文档批量上传功能
fix: 修复 PDF 表格解析错位问题
docs: 更新 API 接口文档
refactor: 重构向量检索服务
perf: 优化 Embedding 批处理性能
test: 添加 RAG 端到端测试
```

### 7.3 测试策略

| 测试类型 | 工具 | 覆盖范围 |
|---|---|---|
| 单元测试 | pytest | Services, Utils |
| API 测试 | pytest + httpx | 所有接口 |
| 集成测试 | pytest | PDF 解析 → 向量化 → 检索全流程 |
| E2E 测试 | Playwright | 前端关键路径 |

---

## 8. 后期优化路线图

| 阶段 | 目标 | 技术方案 |
|---|---|---|
| **Phase 1** | 基础 RAG | LlamaIndex + Qdrant + BGE-M3 + GPT-4o |
| **Phase 2** | 检索优化 | Hybrid Search（向量 + 关键词）、重排序（Cross-Encoder）、查询重写 |
| **Phase 3** | Agentic RAG | LangGraph + LlamaIndex Agent（查询路由、多文档聚合、结果验证） |
| **Phase 4** | GraphRAG | 构建知识图谱，处理标准间的引用关系与层级结构 |
| **Phase 5** | 多模态 | 支持 PDF 中的图片、公式、图表理解与检索 |

---

*文档版本：v0.1.0*  
*最后更新：2026-06-18*
