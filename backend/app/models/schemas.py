"""
API 请求和响应的 Pydantic 模型。

Pydantic 是什么？
它是 Python 的一个数据验证库。你可以把它理解为"带强制类型检查的 Python 字典"。

举个例子：
普通字典：data = {"age": "abc"}  # 不会报错，但 age 应该是数字
Pydantic 模型：
    class User(BaseModel):
        age: int
    user = User(age="abc")  # 这里会立即报错！

在 FastAPI 中，Pydantic 模型有三个作用：
1. 自动校验请求参数（用户传错类型直接返回 422 错误）
2. 自动生成 API 文档（Swagger UI 上的参数说明）
3. 提供 IDE 代码提示（VSCode 能自动补全字段名）
"""

# __all__ 定义了当其他文件写 `from app.models.schemas import *` 时，
# 实际会导入哪些名字。这是一种显式的"公开接口"声明。
__all__ = [
    "DocumentStatus", "SourceInfo", "DocumentUploadResponse", "DocumentListItem",
    "QueryRequest", "QueryResponse", "ChunkItem", "HealthResponse", "DocumentDeleteResponse",
]

from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime
from enum import Enum


# === Enum（枚举）===
# 枚举用来限制一个字段只能取几个固定值，防止数据库里出现奇怪的状态字符串
class DocumentStatus(str, Enum):
    """
    文档处理状态枚举。

    为什么用 Enum 而不是随便写字符串？
    因为如果不限制，数据库里可能同时出现 "completed"、"Completed"、"完成"、"success"
    等五花八门的值，查询时容易漏掉。Enum 强制只能使用这里定义的 4 个值。
    """
    PENDING = "pending"         # 已上传，排队等待处理
    PROCESSING = "processing"   # 正在解析 PDF、分块、生成向量
    COMPLETED = "completed"     # 处理完成，可以问答了
    FAILED = "failed"           # 处理失败（如 PDF 损坏）


# === 基础信息模型 ===

class SourceInfo(BaseModel):
    """
    引用来源信息。

    当 LLM 回答问题时，我们会告诉用户："这个答案来自哪份文档的第几页"。
    这个模型定义了"来源"的数据结构。
    """
    doc_id: str                 # 文档唯一 ID，如 "doc_a1b2c3"
    doc_name: str               # 原始文件名，如 "GB50016-2014.pdf"
    page: Optional[int] = None  # 所在页码（PDF 解析失败时可能为空）
    chunk_index: Optional[int] = None  # 这是该文档的第几个文本块
    score: Optional[float] = None      # 相似度分数（0~1，越接近 1 越相关）


# === 文档相关响应模型 ===

class DocumentUploadResponse(BaseModel):
    """上传文档成功后，后端返回的数据结构。"""
    doc_id: str
    filename: str
    status: DocumentStatus      # 刚上传时通常是 "pending"
    message: str                # 给前端展示的人类可读状态说明
    created_at: datetime = Field(default_factory=datetime.now)  # 上传时间，默认当前时间


class DocumentListItem(BaseModel):
    """文档列表中每一行的数据结构。"""
    doc_id: str
    filename: str
    status: DocumentStatus
    total_pages: Optional[int] = None    # 总页数（解析后才能知道）
    total_chunks: Optional[int] = None   # 总共切成了多少个文本块
    created_at: datetime                 # 上传时间
    updated_at: Optional[datetime] = None  # 最后更新时间（状态变化时更新）


# === 查询相关模型 ===

class QueryRequest(BaseModel):
    """
    用户提问的请求体。

    FastAPI 会自动检查：
    - query 必须有值（min_length=1），不能为空字符串
    - top_k 必须在 1~20 之间（ge=1, le=20）
    - 如果传了 filter_doc_ids，必须是字符串列表
    """
    query: str = Field(..., min_length=1, max_length=2000, description="用户查询文本")
    top_k: int = Field(default=5, ge=1, le=20, description="检索片段数量")
    stream: bool = Field(default=False, description="是否流式返回响应")
    filter_doc_ids: Optional[List[str]] = Field(default=None, description="按文档 ID 过滤，只查指定文档")


class QueryResponse(BaseModel):
    """问答接口返回的数据结构。"""
    answer: str                 # LLM 生成的最终回答
    sources: List[SourceInfo]   # 引用的文档来源列表
    query_time_ms: int          # 整个查询耗时（毫秒），用于性能监控
    model: str                  # 实际使用的 LLM 模型名


class ChunkItem(BaseModel):
    """单个文本块的信息，用于分块查看接口。"""
    content: str                # 文本块的实际内容
    doc_id: str
    doc_name: str
    page: Optional[int] = None
    score: float                # 该块与查询的相似度得分


# === 健康检查模型 ===

class HealthResponse(BaseModel):
    """健康检查接口返回的数据结构。"""
    status: str                 # "healthy" 或 "degraded"
    version: str                # 后端版本号
    vector_store: str           # "connected" 或 "disconnected"
    embedding_model: str        # 当前使用的嵌入模型名


# === 删除文档响应 ===

class DocumentDeleteResponse(BaseModel):
    """删除文档接口返回的数据结构。"""
    doc_id: str
    deleted: bool               # 是否成功删除
    message: str
