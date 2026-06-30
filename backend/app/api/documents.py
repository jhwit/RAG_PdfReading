"""
文档管理 API 端点。

这个文件处理所有与"文档"相关的 HTTP 请求：
- POST   /api/v1/documents/upload      → 上传 PDF
- GET    /api/v1/documents              → 获取文档列表
- GET    /api/v1/documents/{doc_id}     → 获取单个文档详情
- GET    /api/v1/documents/{doc_id}/status   → 查询处理进度
- GET    /api/v1/documents/{doc_id}/chunks   → 查看文档分块内容
- DELETE /api/v1/documents/{doc_id}     → 删除文档

路由前缀：所有接口会自动加上 /documents，因为下面创建了 APIRouter(prefix="/documents")
"""
from fastapi import APIRouter, Request, UploadFile, File, Depends, Path, status as http_status
from app.core.config import get_settings
from app.core.exceptions import DocumentNotFound
from app.core.logger import setup_logger
from app.services.document_service import DocumentService

# 创建模块级别的日志记录器，方便追踪这个文件里的操作
logger = setup_logger("rag_kb.api.documents")

# 创建路由实例。
# prefix="/documents" 表示这个路由器下所有路径前面都加 /documents
# tags=["Documents"]  表示在 Swagger API 文档里，这些接口归类到 "Documents" 组
router = APIRouter(prefix="/documents", tags=["Documents"])


def get_document_service(request: Request) -> DocumentService:
    """
    从 app.state 获取单例 DocumentService。

    为什么写成函数？
    FastAPI 的 Depends 依赖注入系统需要可调用的函数或类。
    每次有接口需要 DocumentService 时，FastAPI 会自动调用这个函数，
    把 request 传进来，我们从中取出预先初始化好的服务实例。

    参数:
        request: FastAPI 自动注入的当前 HTTP 请求对象

    返回:
        DocumentService: 处理文档业务逻辑的服务实例
    """
    return request.app.state.document_service


# ====== 1. 上传文档 ======
@router.post(
    "/upload",
    response_model=dict,              # 告诉 FastAPI 这个接口返回 dict 结构（用于生成文档）
    status_code=http_status.HTTP_201_CREATED,  # 上传成功返回 201（Created），这是 REST 惯例
    summary="上传 PDF 文档",
    description="上传国家标准 PDF 文件。后端立即返回并在后台异步处理（解析、分块、嵌入、索引）。"
)
async def upload_document(
    file: UploadFile = File(..., description="PDF 文件，最大 50MB"),
    service: DocumentService = Depends(get_document_service),
):
    """
    处理文件上传请求。

    流程：
    1. FastAPI 自动把用户上传的文件流包装成 UploadFile 对象
    2. 调用 service.process_document(file) 进行异步处理
    3. 立即返回 {doc_id, filename, status: "pending"}，不等待后台处理完成

    参数:
        file: 用户上传的文件对象，包含文件名、内容类型、文件流
        service: 通过 Depends 注入的 DocumentService 实例

    返回:
        dict: 包含 doc_id、filename、status、message、created_at 的 JSON
    """
    # process_document 内部会：验证 → 保存磁盘 → 记录元数据 → 启动后台任务
    doc = await service.process_document(file)
    return {
        "code": "SUCCESS",
        "message": "文档上传成功",
        "data": {
            "doc_id": doc["doc_id"],
            "filename": doc["filename"],
            "status": doc["status"],      # 刚上传时通常是 "pending"
            "message": doc["message"],    # 如 "Document queued for processing"
            "created_at": doc["created_at"],
        }
    }


# ====== 2. 获取文档列表 ======
@router.get(
    "",
    summary="获取文档列表",
    description="获取所有已上传文档及其处理状态，最新的排在最前面。"
)
async def list_documents(
    service: DocumentService = Depends(get_document_service),
):
    """
    返回所有文档的摘要列表。

    注意这里没做分页。如果文档很多（几千份），建议后期加上 page/size 参数，
    否则一次性返回太多数据会拖慢前端。
    """
    docs = service.get_documents()
    return {
        "code": "SUCCESS",
        "message": "OK",
        "data": {
            "items": [
                {
                    "doc_id": d["doc_id"],
                    "filename": d["filename"],
                    "status": d["status"],
                    "total_pages": d.get("total_pages"),   # .get() 表示字段不存在时返回 None 而不是报错
                    "total_chunks": d.get("total_chunks"),
                    "created_at": d.get("created_at"),
                    "updated_at": d.get("updated_at"),
                }
                for d in docs  # 列表推导式：把每个文档对象转换成前端需要的格式
            ],
            "total": len(docs),  # 文档总数，方便前端显示"共 X 条"
        }
    }


# ====== 3. 获取单个文档详情 ======
@router.get(
    "/{doc_id}",
    summary="获取文档详情",
    description="获取单个文档的详细信息，包括元数据（标题、作者、页数等）。"
)
async def get_document(
    doc_id: str = Path(..., description="文档唯一标识符，如 doc_a1b2c3"),
    service: DocumentService = Depends(get_document_service),
):
    """
    根据 doc_id 查询单个文档。

    如果文档不存在，service.get_document 会抛出 DocumentNotFound 异常，
    然后被全局异常处理器捕获，自动返回 HTTP 404。
    """
    doc = service.get_document(doc_id)
    return {
        "code": "SUCCESS",
        "message": "OK",
        "data": {
            "doc_id": doc["doc_id"],
            "filename": doc["filename"],
            "status": doc["status"],
            "total_pages": doc.get("total_pages"),
            "total_chunks": doc.get("total_chunks"),
            "metadata": doc.get("metadata", {  # 如果 metadata 不存在，返回一个默认空结构
                "title": doc.get("filename", ""),
                "author": "",
                "subject": "",
                "total_pages": doc.get("total_pages", 0),
            }),
            "created_at": doc.get("created_at"),
            "updated_at": doc.get("updated_at"),
        }
    }


# ====== 4. 查询文档处理状态 ======
@router.get(
    "/{doc_id}/status",
    summary="获取文档处理状态",
    description="查询文档当前处理状态。前端可以轮询（每隔几秒请求一次）此接口来实时显示进度条。"
)
async def get_document_status(
    doc_id: str = Path(..., description="文档唯一标识符"),
    service: DocumentService = Depends(get_document_service),
):
    """
    返回文档的实时处理状态。

    响应中的 progress 字段是 0~100 的整数，前端可以直接用来做进度条。
    """
    status = service.get_status(doc_id)
    return {
        "code": "SUCCESS",
        "message": "OK",
        "data": status,
    }


# ====== 5. 查看文档分块内容 ======
@router.get(
    "/{doc_id}/chunks",
    summary="获取文档分块内容",
    description="从 Qdrant 向量数据库中获取指定文档的所有文本分块，按页码和分块索引排序。"
)
async def get_document_chunks(
    doc_id: str = Path(..., description="文档唯一标识符"),
    request: Request = None,
):
    """
    从向量数据库中读取某个文档切分后的所有文本块。

    用途：
    - 调试：确认 PDF 解析是否正确
    - 审核：查看 AI 回答引用的原文长什么样
    - 优化：分析分块是否合理（有没有句子被截断）

    参数:
        doc_id: 文档 ID
        request: FastAPI 请求对象，用来获取 app.state.vector_store

    返回:
        dict: 包含分块数组，每个元素有 chunk_index、page、content 等字段
    """
    store = request.app.state.vector_store

    # 如果 Qdrant 没连上，提前返回友好提示，而不是抛 500 错误
    if not store.is_connected():
        return {
            "code": "VECTOR_STORE_UNAVAILABLE",
            "message": "向量数据库不可用，无法获取分块",
            "data": [],
        }

    try:
        chunks = await store.get_chunks_by_doc_id(doc_id)
        return {
            "code": "SUCCESS",
            "message": "OK",
            "data": chunks,
        }
    except Exception as e:
        logger.error(f"获取文档 {doc_id} 的分块失败: {e}")
        return {
            "code": "ERROR",
            "message": f"获取分块失败：{str(e)}",
            "data": [],
        }


# ====== 6. 删除文档 ======
@router.delete(
    "/{doc_id}",
    summary="删除文档",
    description="删除文档及其在向量数据库中的所有数据，同时清理磁盘上的 PDF 文件和元数据文件。"
)
async def delete_document(
    doc_id: str = Path(..., description="文档唯一标识符"),
    service: DocumentService = Depends(get_document_service),
):
    """
    彻底删除一个文档。

    删除操作包括：
    1. 从 Qdrant 删除该文档的所有向量（如果 Qdrant 可用）
    2. 从磁盘删除 PDF 文件
    3. 从磁盘删除 .meta.json 元数据文件
    4. 从内存字典 _documents 中移除记录
    """
    result = await service.delete_document(doc_id)
    return {
        "code": "SUCCESS",
        "message": "文档已删除",
        "data": {
            "doc_id": result["doc_id"],
            "deleted": result["deleted"],  # True 表示确实删掉了
        }
    }
