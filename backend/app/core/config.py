"""
应用配置模块。

这个文件负责管理所有"可调整的参数"，比如：
- 服务器监听哪个端口？
- 使用哪个 AI 模型？
- Qdrant 数据库地址是什么？
- 上传的 PDF 最大允许多大？

为什么要集中管理？
想象你搬家了，数据库地址变了。如果配置分散在 10 个文件里，你要改 10 处。
集中在一个文件（加上 .env 环境变量），改一处就搞定。

Pydantic Settings 是什么？
它是 Python 的一个库，能自动读取 .env 文件，还能检查你写的值是否合理
（比如 PORT 必须是数字，不能写 "abc"）。如果写错了，启动时就会报错，
而不是等到运行时才发现。
"""
from functools import lru_cache          # lru_cache 是缓存装饰器，避免重复读取 .env
from pydantic_settings import BaseSettings  # Pydantic 的配置基类
from typing import Optional              # Optional[str] 表示 "str 或 None"


class Settings(BaseSettings):
    """
    所有配置项的集合。每个类属性对应一个可配置项。

    Pydantic Settings 的魔法：
    1. 它会自动在当前目录找 .env 文件
    2. .env 里的大写变量名（如 LLM_MODEL）会自动映射到这个类的小写属性（llm_model）
    3. 如果 .env 里没有，就使用下面的默认值
    """

    # === 应用基础配置 ===
    app_name: str = "RAG Knowledge Base"     # 应用名称，显示在 API 文档页面
    app_version: str = "0.1.1"               # 版本号，方便排查问题时确认代码版本
    debug: bool = False                      # 调试模式：True 时自动重启，输出更详细日志
    host: str = "0.0.0.0"                    # 0.0.0.0 表示监听所有网卡（包括局域网 IP）
    port: int = 8000                         # Web 服务器端口，访问 http://localhost:8000

    # === CORS（跨域）配置 ===
    # 如果你的前端跑在 http://localhost:5173，后端在 8000，浏览器会阻止它们通信。
    # 这里列出允许访问后端的地址。生产环境应该写死具体域名，不要写 *。
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # === LLM / 嵌入模型配置 ===
    # LLM（大语言模型）负责回答用户问题；嵌入模型负责把文字转成向量。
    embedding_model: str = "BAAI/bge-m3"     # HuggingFace 上的开源嵌入模型，中文效果好
    embedding_device: str = "auto"           # "auto" 会自动检测是否有 NVIDIA 显卡（cuda），没有就用 CPU
    llm_model: str = "gpt-4o"                # 默认使用 OpenAI 的 gpt-4o（可在 .env 里改）
    llm_temperature: float = 0.1             # 温度：0 = 最保守/确定，1 = 最有创意/随机。问答场景用低温度更稳定
    openai_api_key: Optional[str] = None     # API Key，从 .env 的 OPENAI_API_KEY 读取
    openai_base_url: Optional[str] = None    # 如果使用第三方代理（如 DeepSeek、OpenRouter），填他们的地址

    # === Qdrant 向量数据库配置 ===
    # Qdrant 是一个专门存储和搜索"高维向量"的数据库。
    # 传统数据库按文字搜索，Qdrant 按"语义相似度"搜索（找意思相近的段落）。
    qdrant_host: str = "localhost"           # Qdrant 服务器地址，本地开发用 localhost
    qdrant_port: int = 6333                  # Qdrant 默认端口
    qdrant_collection: str = "documents"     # 集合名 = 数据库里的"表名"，存放所有文档向量
    qdrant_api_key: Optional[str] = None     # 远程 Qdrant（如 Qdrant Cloud）需要 API Key
    qdrant_https: bool = False               # 是否使用 HTTPS，远程部署时设为 True

    # === 文件路径配置 ===
    data_dir: str = "./data"                 # 数据根目录
    doc_dir: str = "./data/documents"        # 上传的 PDF 存放目录
    vector_dir: str = "./data/vectors"       # 本地向量存储备份目录（当前未使用）

    # === 文本分块配置 ===
    # 为什么需要分块？
    # LLM 一次能处理的文字有限（几千到几万字），一本几百页的标准不可能一次性塞进去。
    # 所以要把长文档切成小段落，每段单独存向量。查询时只取最相关的几段。
    chunk_size: int = 1024                   # 每个文本块最大字符数（约 500 个汉字）
    chunk_overlap: int = 100                 # 相邻块重叠字符数，防止句子被拦腰截断
    chunk_separator: str = "\n\n"            # 优先在双换行处切分（通常是段落边界）

    # === 检索配置 ===
    default_top_k: int = 5                   # 默认检索返回多少个最相似的文本块
    max_top_k: int = 20                      # 用户最多能要多少个（防止恶意请求拖慢服务器）
    similarity_threshold: float = 0.5        # 相似度阈值：低于 0.5 的结果认为不相关，直接丢弃

    # === 处理限制 ===
    max_file_size_mb: int = 50               # 单个 PDF 最大 50MB，防止用户上传电影拖垮服务器
    embedding_batch_size: int = 32           # 每次给嵌入模型多少段文本。显存大的显卡可以调大，加快处理速度
    vector_dimension: int = 1024             # 嵌入向量维度。bge-m3 模型输出 1024 维数字

    # === 知识图谱配置 ===
    enable_kg: bool = True                   # 是否启用知识图谱构建和查询
    kg_dir: str = "./data/kg"                # 知识图谱 JSON 文件存放目录

    class Config:
        """
        Pydantic Settings 的内部配置。
        env_file 告诉它去哪里找环境变量文件。
        """
        env_file = ".env"                    # 从当前目录的 .env 文件读取配置
        env_file_encoding = "utf-8"          # .env 文件使用 UTF-8 编码（支持中文注释）


@lru_cache()
def get_settings() -> Settings:
    """
    获取配置实例（带缓存）。

    为什么要缓存？
    Settings 对象创建时会读取 .env 文件、做各种校验，有一定开销。
    使用 @lru_cache() 后，第一次调用会创建对象，之后直接返回同一个对象，
    避免重复读取文件。

    返回:
        Settings: 包含所有配置项的对象
    """
    return Settings()
