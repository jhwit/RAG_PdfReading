# API 接口文档（OpenAPI 规范）

> **基础URL**: `http://localhost:8000/api/v1`  
> **协议**: HTTP/REST + SSE（流式响应）  
> **内容类型**: `application/json` / `multipart/form-data`  
> **文档自动生成**: FastAPI 原生支持 Swagger UI (`/docs`) 与 ReDoc (`/redoc`)

---

## 通用约定

### 响应格式

所有接口统一返回以下结构：

```json
{
  "code": "SUCCESS",
  "message": "操作成功",
  "data": { ... }
}
```

**错误响应结构：**

```json
{
  "code": "PDF_PARSE_ERROR",
  "message": "Failed to parse sample.pdf",
  "details": null
}
```

### HTTP 状态码

| 状态码 | 含义 | 场景 |
|---|---|---|
| 200 | 成功 | GET / POST 正常返回 |
| 201 | 已创建 | 文档上传成功 |
| 204 | 无内容 | 删除成功 |
| 400 | 请求错误 | 参数校验失败 |
| 404 | 不存在 | 文档/资源未找到 |
| 422 | 无法处理 | PDF 解析失败等 |
| 500 | 服务器错误 | 内部异常 |

---

## 接口清单

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/health` | 健康检查 |
| `POST` | `/documents/upload` | 上传 PDF 文档 |
| `GET` | `/documents` | 获取文档列表 |
| `GET` | `/documents/{doc_id}` | 获取文档详情 |
| `GET` | `/documents/{doc_id}/status` | 查询文档处理状态 |
| `DELETE` | `/documents/{doc_id}` | 删除文档 |
| `POST` | `/query` | 提交问答查询 |
| `POST` | `/query/stream` | 流式问答（SSE） |

---

## 1. 健康检查

### `GET /health`

检查服务与依赖组件状态。

**请求参数**：无

**响应示例（200）：**

```json
{
  "code": "SUCCESS",
  "message": "Service is healthy",
  "data": {
    "status": "healthy",
    "version": "0.1.0",
    "vector_store": "connected",
    "embedding_model": "BAAI/bge-m3",
    "uptime_seconds": 3600
  }
}
```

**响应字段：**

| 字段 | 类型 | 说明 |
|---|---|---|
| `status` | string | `healthy` / `degraded` / `unhealthy` |
| `version` | string | 服务版本号 |
| `vector_store` | string | 向量库连接状态 |
| `embedding_model` | string | 当前加载的嵌入模型 |
| `uptime_seconds` | integer | 服务运行时长（秒） |

---

## 2. 文档管理接口

### `POST /documents/upload`

上传 PDF 文档，后端异步完成解析、分块、向量化与入库。

**请求类型**: `multipart/form-data`

**请求参数：**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `file` | File | 是 | PDF 文件，最大 50MB |

**响应示例（201）：**

```json
{
  "code": "SUCCESS",
  "message": "Document uploaded successfully",
  "data": {
    "doc_id": "doc_2v8x9k3m",
    "filename": "GB-50016-2014.pdf",
    "status": "pending",
    "message": "Document queued for processing",
    "created_at": "2026-06-18T09:30:00Z"
  }
}
```

**响应字段：**

| 字段 | 类型 | 说明 |
|---|---|---|
| `doc_id` | string | 文档唯一标识（UUID） |
| `filename` | string | 原始文件名 |
| `status` | string | `pending` / `processing` / `completed` / `failed` |
| `message` | string | 状态说明 |
| `created_at` | string (ISO8601) | 创建时间 |

**错误响应：**

| 状态码 | Code | 说明 |
|---|---|---|
| 400 | `INVALID_FILE_TYPE` | 非 PDF 文件 |
| 413 | `FILE_TOO_LARGE` | 超过 50MB |
| 422 | `PDF_PARSE_ERROR` | PDF 解析失败 |

---

### `GET /documents`

获取所有已上传文档的列表。

**请求参数**：无

**响应示例（200）：**

```json
{
  "code": "SUCCESS",
  "message": "OK",
  "data": {
    "items": [
      {
        "doc_id": "doc_2v8x9k3m",
        "filename": "GB-50016-2014.pdf",
        "status": "completed",
        "total_pages": 156,
        "total_chunks": 312,
        "created_at": "2026-06-18T09:30:00Z",
        "updated_at": "2026-06-18T09:32:15Z"
      }
    ],
    "total": 1
  }
}
```

**响应字段：**

| 字段 | 类型 | 说明 |
|---|---|---|
| `items` | array | 文档列表 |
| `items[].doc_id` | string | 文档 ID |
| `items[].filename` | string | 文件名 |
| `items[].status` | string | 处理状态 |
| `items[].total_pages` | integer | 总页数 |
| `items[].total_chunks` | integer | 分块数量 |
| `items[].created_at` | string | 创建时间 |
| `items[].updated_at` | string | 最后更新时间 |
| `total` | integer | 文档总数 |

---

### `GET /documents/{doc_id}`

获取单个文档的详细信息。

**路径参数：**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `doc_id` | string | 是 | 文档唯一标识 |

**响应示例（200）：**

```json
{
  "code": "SUCCESS",
  "message": "OK",
  "data": {
    "doc_id": "doc_2v8x9k3m",
    "filename": "GB-50016-2014.pdf",
    "status": "completed",
    "total_pages": 156,
    "total_chunks": 312,
    "metadata": {
      "title": "建筑设计防火规范",
      "author": "",
      "total_pages": 156
    },
    "created_at": "2026-06-18T09:30:00Z",
    "updated_at": "2026-06-18T09:32:15Z"
  }
}
```

**错误响应：**

| 状态码 | Code | 说明 |
|---|---|---|
| 404 | `DOC_NOT_FOUND` | 文档不存在 |

---

### `GET /documents/{doc_id}/status`

查询文档的当前处理状态，前端可用此接口轮询进度。

**路径参数：**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `doc_id` | string | 是 | 文档唯一标识 |

**响应示例（200）：**

```json
{
  "code": "SUCCESS",
  "message": "OK",
  "data": {
    "doc_id": "doc_2v8x9k3m",
    "status": "processing",
    "progress": 45,
    "message": "Embedding chunks: 140/312",
    "updated_at": "2026-06-18T09:31:30Z"
  }
}
```

**响应字段：**

| 字段 | 类型 | 说明 |
|---|---|---|
| `status` | string | 当前状态 |
| `progress` | integer | 处理进度百分比（0-100） |
| `message` | string | 进度描述 |
| `updated_at` | string | 最后更新时间 |

---

### `DELETE /documents/{doc_id}`

删除指定文档及其所有向量数据。

**路径参数：**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `doc_id` | string | 是 | 文档唯一标识 |

**响应示例（204）：**

```json
{
  "code": "SUCCESS",
  "message": "Document deleted",
  "data": {
    "doc_id": "doc_2v8x9k3m",
    "deleted": true
  }
}
```

**错误响应：**

| 状态码 | Code | 说明 |
|---|---|---|
| 404 | `DOC_NOT_FOUND` | 文档不存在 |

---

## 3. 问答检索接口

### `POST /query`

提交问题，系统执行 RAG 检索并返回答案。

**请求类型**: `application/json`

**请求体：**

```json
{
  "query": "建筑设计防火规范中关于疏散楼梯的要求是什么？",
  "top_k": 5,
  "stream": false,
  "filter_doc_ids": ["doc_2v8x9k3m"]
}
```

**请求字段：**

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `query` | string | 是 | - | 用户问题（1-2000 字符） |
| `top_k` | integer | 否 | 5 | 检索文本块数量（1-20） |
| `stream` | boolean | 否 | false | 是否流式返回 |
| `filter_doc_ids` | array[string] | 否 | null | 限定检索的文档范围 |

**响应示例（200）：**

```json
{
  "code": "SUCCESS",
  "message": "Query processed",
  "data": {
    "answer": "根据《建筑设计防火规范》GB 50016-2014 第6.4节规定，疏散楼梯应符合以下要求：\n\n1. 楼梯间应能天然采光和自然通风...",
    "sources": [
      {
        "doc_id": "doc_2v8x9k3m",
        "doc_name": "GB-50016-2014.pdf",
        "page": 89,
        "chunk_index": 178,
        "score": 0.92
      },
      {
        "doc_id": "doc_2v8x9k3m",
        "doc_name": "GB-50016-2014.pdf",
        "page": 90,
        "chunk_index": 180,
        "score": 0.87
      }
    ],
    "query_time_ms": 1250,
    "model": "gpt-4o"
  }
}
```

**响应字段：**

| 字段 | 类型 | 说明 |
|---|---|---|
| `answer` | string | AI 生成的答案 |
| `sources` | array | 引用来源列表 |
| `sources[].doc_id` | string | 来源文档 ID |
| `sources[].doc_name` | string | 来源文档名称 |
| `sources[].page` | integer | 页码 |
| `sources[].chunk_index` | integer | 块序号 |
| `sources[].score` | float | 相似度分数（0-1） |
| `query_time_ms` | integer | 总耗时（毫秒） |
| `model` | string | 使用的 LLM 模型 |

**错误响应：**

| 状态码 | Code | 说明 |
|---|---|---|
| 400 | `EMPTY_QUERY` | 查询为空 |
| 400 | `QUERY_TOO_LONG` | 超过 2000 字符 |
| 404 | `NO_RELEVANT_DOCS` | 未检索到相关文档 |
| 503 | `LLM_UNAVAILABLE` | LLM 服务不可用 |

---

### `POST /query/stream`

流式问答接口，使用 Server-Sent Events (SSE) 逐字返回答案。

**请求类型**: `application/json`

**请求体：** 与 `/query` 相同（`stream` 字段固定为 `true`）

**响应格式**: `text/event-stream`

**SSE 事件流示例：**

```
data: {"type": "start", "query_time_ms": 0}

data: {"type": "chunk", "content": "根据", "query_time_ms": 320}

data: {"type": "chunk", "content": "《建筑设计防火规范》", "query_time_ms": 340}

data: {"type": "chunk", "content": "的规定，", "query_time_ms": 360}

...（持续输出直到答案完成）...

data: {"type": "sources", "sources": [{"doc_id": "doc_2v8x9k3m", "doc_name": "GB-50016-2014.pdf", "page": 89, "score": 0.92}]}

data: {"type": "end", "query_time_ms": 1250}

data: [DONE]
```

**事件类型说明：**

| type | 说明 | 附带字段 |
|---|---|---|
| `start` | 开始生成 | `query_time_ms` |
| `chunk` | 答案片段 | `content` |
| `sources` | 引用来源 | `sources` |
| `end` | 生成结束 | `query_time_ms` |
| `error` | 发生错误 | `message` |

**前端接收示例（JavaScript）：**

```javascript
const response = await fetch('/api/v1/query/stream', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ query: '...', top_k: 5 })
})

const reader = response.body.getReader()
const decoder = new TextDecoder()

while (true) {
  const { done, value } = await reader.read()
  if (done) break

  const lines = decoder.decode(value).split('\n')
  for (const line of lines) {
    if (line.startsWith('data: ')) {
      const data = line.slice(6)
      if (data === '[DONE]') continue
      const event = JSON.parse(data)
      handleEvent(event)
    }
  }
}
```

---

## 4. 数据模型定义

### DocumentStatus（枚举）

| 值 | 说明 |
|---|---|
| `pending` | 待处理 |
| `processing` | 处理中 |
| `completed` | 已完成 |
| `failed` | 失败 |

### DocumentUploadRequest

```yaml
schema:
  type: object
  required: [file]
  properties:
    file:
      type: string
      format: binary
      description: PDF 文件
```

### QueryRequest

```yaml
schema:
  type: object
  required: [query]
  properties:
    query:
      type: string
      minLength: 1
      maxLength: 2000
      description: 用户查询文本
    top_k:
      type: integer
      minimum: 1
      maximum: 20
      default: 5
      description: 检索文本块数量
    stream:
      type: boolean
      default: false
      description: 是否流式返回
    filter_doc_ids:
      type: array
      items:
        type: string
      description: 限定检索文档范围
```

### SourceInfo

```yaml
schema:
  type: object
  properties:
    doc_id:
      type: string
    doc_name:
      type: string
    page:
      type: integer
    chunk_index:
      type: integer
    score:
      type: number
      format: float
      minimum: 0
      maximum: 1
```

---

## 5. 认证与安全

当前版本为内部系统，暂不做认证。后续如需扩展：

**方案一：API Key**

```
Authorization: Bearer sk-rag-xxxxxx
```

**方案二：JWT Token**

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

---

## 6. 分页与限流

### 分页

列表接口支持以下参数：

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `page` | integer | 1 | 页码 |
| `page_size` | integer | 20 | 每页数量（最大 100） |

响应中包含：

```json
{
  "items": [...],
  "total": 100,
  "page": 1,
  "page_size": 20,
  "total_pages": 5
}
```

### 限流

| 接口 | 限流策略 |
|---|---|
| `/documents/upload` | 每 IP 每分钟 10 次 |
| `/query` | 每 IP 每分钟 60 次 |
| `/query/stream` | 每 IP 每分钟 30 次 |

超限返回 `429 Too Many Requests`：

```json
{
  "code": "RATE_LIMITED",
  "message": "Too many requests, please try again later"
}
```

---

## 7. 附录：OpenAPI 自动生成

FastAPI 项目启动后，可通过以下地址访问自动生成的交互式文档：

| 地址 | 说明 |
|---|---|
| `http://localhost:8000/docs` | Swagger UI（可在线测试） |
| `http://localhost:8000/redoc` | ReDoc（只读文档） |
| `http://localhost:8000/openapi.json` | OpenAPI JSON 规范 |

**FastAPI 路由中定义的 Pydantic 模型会自动映射为 OpenAPI Schema**，无需手写 YAML。

```python
@router.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    ...
```

上述代码会自动生成：
- 请求体 Schema（来自 `QueryRequest`）
- 响应 Schema（来自 `QueryResponse`）
- 参数校验规则（`min_length`, `max_length`, `ge`, `le` 等）
- 示例值与类型说明
