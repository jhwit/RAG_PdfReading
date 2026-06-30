"""
查询 / 问答 API 端点。

这个文件处理用户提问：
- POST /api/v1/query         → 普通问答（一次性返回完整回答）
- POST /api/v1/query/stream  → 流式问答（SSE，像 ChatGPT 那样打字效果）

SSE（Server-Sent Events）是什么？
传统的 HTTP 请求是"一问一答"：前端发请求 → 后端思考 5 秒 → 返回完整回答。
SSE 是"一问多答"：后端开始回答后，每生成几个字就发一次，前端可以实时显示，
用户体验更好，感觉 AI 在"打字"。

技术实现：
后端返回的 Content-Type 是 text/event-stream，每段数据格式为：
    data: {"type":"chunk","content":"你好"}\n\n
前端用 EventSource 接收，每次收到数据就追加到屏幕上。
"""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import StreamingResponse
from app.core.config import get_settings
from app.models.schemas import QueryRequest
from app.services.rag_service import RAGService

router = APIRouter(prefix="/query", tags=["Query"])


def get_rag_service(request: Request) -> RAGService:
    """
    创建 RAGService 实例并注入共享依赖。

    为什么不直接复用 app.state 上的 RAGService？
    因为 RAGService 是无状态的（不保存对话历史），每次请求新建一个更简单。
    它只依赖 embedding_service 和 vector_store，这两个是单例，复用即可。

    参数:
        request: FastAPI 自动注入的请求对象

    返回:
        RAGService: 配置了当前请求所需依赖的 RAG 服务实例
    """
    settings = get_settings()
    rag = RAGService(
        settings=settings,                        # 读取当前配置
        embedding_service=request.app.state.embedding_service,  # 复用预加载的嵌入模型
        vector_store=request.app.state.vector_store,            # 复用 Qdrant 连接
    )
    # 如果启用了知识图谱，创建 KGService 并注入
    if settings.enable_kg:
        from app.services.kg_service import KGService
        rag.kg_service = KGService(settings, rag.llm)
    return rag


# ====== 普通问答 ======
@router.post(
    "",
    summary="提交问答查询",
    description="提交自然语言问题。系统会检索相关文档片段，并用 LLM 生成带引用的回答。"
)
async def query(
    body: QueryRequest,                               # FastAPI 自动把请求 JSON 转换成 QueryRequest 对象
    service: RAGService = Depends(get_rag_service),   # 通过依赖注入获取 RAGService
):
    """
    处理普通问答请求（非流式）。

    执行流程：
    1. 验证问题长度（空问题或超过 2000 字符会被拒绝）
    2. 用 embedding 模型把问题转成向量
    3. 在 Qdrant 中搜索最相似的文本块（top_k 个）
    4. 把文本块拼接成上下文，连同问题一起发给 LLM
    5. LLM 生成回答
    6. 用 AnswerAgent 检查回答质量，必要时重写
    7. 返回 {answer, sources, query_time_ms, model}

    参数:
        body: 包含 query（问题）、top_k（检索数量）、filter_doc_ids（过滤文档）
        service: RAG 服务实例

    返回:
        dict: 包含回答文本、引用来源、耗时、模型名的统一响应
    """
    result = await service.query(
        question=body.query,
        top_k=body.top_k,
        filter_doc_ids=body.filter_doc_ids,
    )
    return {
        "code": "SUCCESS",
        "message": "查询已处理",
        "data": result,
    }


# ====== 流式问答 ======
@router.post(
    "/stream",
    summary="流式问答查询（SSE）",
    description="提交问题并通过 Server-Sent Events 接收流式回答，像 ChatGPT 那样逐字显示。"
)
async def query_stream(
    body: QueryRequest,
    service: RAGService = Depends(get_rag_service),
):
    """
    处理流式问答请求。

    与普通问答的区别：
    - 普通问答：LLM 生成完整回答后，一次性返回给前端（用户要等几秒）
    - 流式问答：LLM 每生成一个 token（几个字），就立即推送给前端（用户立刻看到字出现）

    返回 StreamingResponse 而不是普通 dict，因为：
    StreamingResponse 支持异步生成器（async generator），可以一边生成数据一边发送，
    而不是等所有数据准备好再发。

    headers 中的几个关键头：
    - Cache-Control: no-cache   → 禁止浏览器缓存，因为每次回答都不同
    - Connection: keep-alive    → 保持连接，不要中途断开
    - X-Accel-Buffering: no     → 禁用 Nginx 等反向代理的缓冲，确保实时推送
    """
    return StreamingResponse(
        service.query_stream(
            question=body.query,
            top_k=body.top_k,
            filter_doc_ids=body.filter_doc_ids,
        ),
        media_type="text/event-stream",  # 告诉浏览器这是 SSE 流
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
