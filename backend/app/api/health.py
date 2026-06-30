"""
健康检查端点。

这个文件只提供一个接口：GET /api/v1/health

"健康检查"是什么？
就像你去医院体检，医生检查你的心跳、血压是否正常。
健康检查接口就是给监控系统（或前端）用的"体检报告"，告诉它们：
- 后端服务还活着吗？
- 数据库连得上吗？
- 已经运行多久了？

为什么要单独做一个接口？
1. 前端可以在页面加载时调用，如果返回异常就提示"服务维护中"
2. 云平台的负载均衡器会定期调用，如果失败就把这台服务器从集群中踢掉
3. 运维人员可以写脚本自动监控服务状态
"""
import time
from fastapi import APIRouter, Request
from app.core.config import get_settings

# 创建路由实例。tags 用于 API 文档分组，所有带 "Health" tag 的接口会显示在一起
router = APIRouter(tags=["Health"])

# 记录服务器启动时间（模块导入时执行一次）
# time.time() 返回当前时间戳（秒），是一个浮点数
_start_time = time.time()


@router.get(
    "/health",
    summary="健康检查",
    description="检查服务及依赖（Qdrant 向量数据库）的状态"
)
async def health_check(request: Request):
    """
    处理 GET /api/v1/health 请求。

    参数:
        request: FastAPI 自动注入的当前请求对象，包含 app.state（我们的全局服务）

    返回:
        dict: 统一格式的响应，包含服务状态、版本、Qdrant 连接状态、运行时长
    """
    settings = get_settings()

    # 计算运行时长：当前时间 - 启动时间
    uptime = int(time.time() - _start_time)

    # 尝试获取 Qdrant 连接状态
    # 用 try-except 是因为如果 vector_store 还没初始化（极端情况），不会导致整个接口 500 错误
    try:
        store = request.app.state.vector_store
        vs_status = "connected" if store.is_connected() else "disconnected"
    except Exception:
        vs_status = "disconnected"

    # 整体健康状态：只要 Qdrant 连不上，就认为是 "degraded"（降级），
    # 因为这时无法上传新文档和进行语义搜索，但可能还能返回静态信息
    overall = "healthy" if vs_status == "connected" else "degraded"

    return {
        "code": "SUCCESS",
        "message": f"服务状态: {overall}",
        "data": {
            "status": overall,               # healthy / degraded
            "version": settings.app_version, # 如 "0.1.0"
            "vector_store": vs_status,       # connected / disconnected
            "embedding_model": settings.embedding_model,  # 如 "BAAI/bge-m3"
            "uptime_seconds": uptime,        # 已运行多少秒
        }
    }
