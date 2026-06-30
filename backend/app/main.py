"""
FastAPI 应用入口文件。

这个文件是整个后端服务的"大门"。当你运行 `python app/main.py` 或 `uvicorn app.main:app` 时，
Python 会首先执行这个文件，完成所有初始化工作，然后启动 Web 服务器开始监听请求。

你可以把 FastAPI 理解为一个专门的餐厅：
- lifespan = 餐厅开业/打烊时的准备工作（打开煤气、检查冰箱、关门时打扫卫生）
- app = 餐厅本身
- router = 不同菜品的窗口（上传文档窗口、问答窗口、健康检查窗口）
- middleware = 门口的保安（检查来客身份、允许哪些人进）
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 从其他模块导入我们需要的组件
# FastAPI 推荐把不同功能拆到不同文件里，这样代码更清晰
from app.core.config import get_settings          # 读取配置（如端口号、模型名）
from app.core.exceptions import setup_exception_handlers  # 设置全局错误处理
from app.core.logger import setup_logger          # 设置日志（把运行信息写到文件和屏幕）
from app.api import health, documents, query      # 三个路由模块，分别处理不同 URL
from app.services.vector_store import VectorStore     # Qdrant 向量数据库客户端
from app.services.document_service import DocumentService  # 文档上传/处理服务
from app.utils.embedding import EmbeddingService      # 文本嵌入模型（把文字变成向量）
from app.utils.text_splitter import TextSplitter      # 把长文本切成小段

# 读取 .env 文件里的配置（如 PORT=8000, LLM_MODEL=deepseek-chat）
settings = get_settings()

# 创建一个日志记录器，所有日志会同时输出到屏幕和 logs/app_YYYYMMDD.log 文件
logger = setup_logger("rag_kb")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理器（启动 / 关闭时自动执行）。

    为什么要用它？
    传统的 Web 框架（如 Flask）通常在启动时直接运行初始化代码，
    但 FastAPI 是异步的，需要一种优雅的方式来管理"启动时连接数据库"、
    "关闭时断开连接"这类有先后顺序的操作。

    asynccontextmanager 是一个 Python 语法糖，它保证：
    1. yield 之前的代码在服务器启动时执行（开业准备）
    2. yield 之后的代码在服务器关闭时执行（打烊打扫）
    3. 即使启动失败，也会尝试执行清理代码
    """
    # ====== 启动阶段（服务器开始监听请求前）======
    logger.info(f"正在启动 {settings.app_name} v{settings.app_version}")
    logger.info(f"嵌入模型: {settings.embedding_model}")
    logger.info(f"LLM 模型: {settings.llm_model}")
    logger.info(f"Qdrant 地址: {settings.qdrant_host}:{settings.qdrant_port}")

    # ── 初始化共享服务 ──
    # 这些对象被挂载到 app.state 上，变成"全局变量"，所有请求都能访问
    # 使用单例（只创建一个实例）可以节省内存，避免重复加载 AI 模型

    # 1. VectorStore — 连接 Qdrant 向量数据库
    # Qdrant 专门用来存储和搜索高维向量（如文本嵌入后的 1024 维数字数组）
    # 如果 Qdrant 没启动，这里不会报错，而是记录警告，后续查询时自动重试
    app.state.vector_store = VectorStore(settings)
    await app.state.vector_store.connect()

    # 2. EmbeddingService — 预加载 embedding 模型
    # embedding 模型是把"一段文字"转换成"一组数字"的 AI 模型。
    # 比如 "北京天气" → [0.12, -0.05, 0.88, ...]（1024个数字）
    # 预加载是因为模型文件通常几百 MB，第一次加载要几秒，提前加载能避免用户等待
    app.state.embedding_service = EmbeddingService(settings)
    logger.info("正在预加载嵌入模型（首次加载可能需要几秒到几十秒）...")
    try:
        # 通过访问 .model 属性触发 HuggingFaceEmbedding 的懒加载
        _ = app.state.embedding_service.model
        logger.info(f"嵌入模型加载成功: {settings.embedding_model}")
    except Exception as e:
        # 即使加载失败也不退出，因为用户可能在后续使用中修复问题（如网络恢复）
        logger.warning(f"嵌入模型预加载失败（将在首次使用时重试）: {e}")

    # 3. DocumentService — 文档处理服务（单例）
    # 为什么必须是单例？因为内部有一个 _documents 字典，保存了所有上传文档的元数据。
    # 如果不是单例，每次请求创建一个新实例，之前上传的文档记录就会丢失
    app.state.document_service = DocumentService(
        settings=settings,
        text_splitter=TextSplitter(settings),          # 切分长文本的工具
        embedding_service=app.state.embedding_service, # 复用刚才创建的嵌入服务
        vector_store=app.state.vector_store,           # 复用刚才创建的向量存储
    )
    logger.info("所有服务初始化完成")

    # yield 是关键：它把控制权交给 FastAPI，服务器正式开始接收 HTTP 请求
    yield

    # ====== 关闭阶段（服务器收到停止信号后）======
    # 优雅地关闭 Qdrant 连接，释放网络端口
    await app.state.vector_store.close()
    logger.info("服务器已关闭")


# 创建 FastAPI 应用实例
# 这个 `app` 变量会被 uvicorn 识别并作为 WSGI/ASGI 入口
app = FastAPI(
    title=settings.app_name,           # API 文档页面显示的标题
    version=settings.app_version,      # 版本号
    description="RAG 知识库系统 — 基于 LlamaIndex + Qdrant 的文档问答",  # API 文档描述
    lifespan=lifespan,                 # 绑定上面的生命周期管理器
)

# ====== CORS（跨域资源共享）配置 ======
# 什么是 CORS？
# 浏览器有一个安全策略：网页 A（http://localhost:5173）默认不能向网页 B（http://localhost:8000）发请求。
# 我们的前端运行在 5173 端口，后端在 8000 端口，所以需要告诉浏览器"允许他们通信"。
# allow_origins 就是白名单，只有列出的地址才能调用我们的 API。
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,  # 从 .env 读取，如 ["http://localhost:5173"]
    allow_credentials=True,               # 允许携带 Cookie
    allow_methods=["*"],                  # 允许 GET/POST/DELETE 等所有 HTTP 方法
    allow_headers=["*"],                  # 允许所有请求头（如 Content-Type, Authorization）
)

# 注册全局异常处理器
# 如果没有这个，当代码抛异常时，用户会收到一段丑陋的 Python 报错堆栈。
# 有了它，所有错误都会被包装成统一的 JSON 格式：{ "code": "...", "message": "..." }
setup_exception_handlers(app)

# ====== 注册路由 ======
# 路由（Router）就是"不同 URL 应该交给谁处理"的映射表。
# prefix="/api/v1" 表示所有这些接口前面都要加上 /api/v1，这是 REST API 的版本控制惯例
app.include_router(health.router, prefix="/api/v1")     # /api/v1/health
app.include_router(documents.router, prefix="/api/v1")  # /api/v1/documents/...
app.include_router(query.router, prefix="/api/v1")      # /api/v1/query/...


# ====== 本地开发直接运行入口 ======
# 当你直接执行 `python app/main.py`（而不是用 uvicorn 命令）时，会进入这里
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",              # "模块路径:FastAPI实例变量名"
        host=settings.host,          # 监听哪个网卡，0.0.0.0 表示所有网卡（局域网可访问）
        port=settings.port,          # 监听端口，默认 8000
        reload=settings.debug,       # 开发模式下，代码修改后自动重启服务器
    )
