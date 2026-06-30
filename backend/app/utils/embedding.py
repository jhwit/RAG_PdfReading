"""
嵌入模型封装。

什么是 Embedding（嵌入）？
嵌入是把"人类的文字"转换成"机器能计算的数学向量"的过程。

举例：
    文字: "北京天气晴朗"
    嵌入向量: [0.12, -0.05, 0.88, ..., 0.33]  ← 1024 个浮点数

为什么需要这个转换？
计算机不懂"晴朗"是什么意思，但它懂得比较两个向量有多"像"。
语义相近的句子（如"北京今天晴天"和"北京天气晴朗"），它们的向量也很接近。
Qdrant 就是基于这种"向量距离"来做语义搜索的。

使用的模型：BAAI/bge-m3（HuggingFace 开源）
- 优点：中文效果极好，支持中英混合，免费
- 输出维度：1024 维
- 运行方式：本地运行，不需要联网（除了首次下载模型）

使用的库：llama-index-embeddings-huggingface
- 它是 LlamaIndex 生态对 HuggingFace 嵌入模型的封装
- 处理了 batching（分批处理）、device 选择（CPU/GPU）等细节
"""
from typing import List
from app.core.config import Settings
from app.core.logger import setup_logger

logger = setup_logger("rag_kb.embedding")


class EmbeddingService:
    """
    HuggingFace 嵌入模型封装。

    职责：
    1. 加载指定的预训练嵌入模型（首次使用时自动从 HuggingFace 下载）
    2. 把一批文本转成向量（用于索引文档）
    3. 把单个查询文本转成向量（用于用户提问时搜索）

    为什么用"懒加载"（Lazy Loading）？
    模型文件通常几百 MB 到几 GB。如果在 __init__ 里立即加载，
    哪怕只是导入这个模块也会卡住几秒。懒加载把它推迟到第一次真正使用时，
    让启动更快，也避免在单元测试等不需要模型的场景下浪费时间。
    """

    def __init__(self, settings: Settings):
        """
        初始化服务（不加载模型）。

        参数:
            settings: 应用配置，包含 embedding_model（模型名）、embedding_device（运行设备）
        """
        self.settings = settings
        self.model_name = settings.embedding_model      # 如 "BAAI/bge-m3"
        self.device = self._resolve_device(settings.embedding_device)  # 最终是 "cuda" 或 "cpu"
        self._model = None                              # 占位，实际模型对象，初始为空

    @staticmethod
    def _resolve_device(device: str) -> str:
        """
        解析设备字符串。

        参数值可能是：
        - "auto"  → 自动检测：有 NVIDIA 显卡就用 cuda，否则用 cpu
        - "cuda"  → 强制使用显卡（如果不可用会报错）
        - "cpu"   → 强制使用 CPU（最慢但兼容性最好）

        为什么要检测 CUDA？
        PyTorch 在 CPU 上跑 embedding 可能每秒处理几十段，在 GPU 上可能每秒几千段，
        差两个数量级。如果有显卡一定要用上。

        参数:
            device: 配置中的原始设备字符串

        返回:
            str: 最终使用的设备名（"cuda" 或 "cpu"）
        """
        if device == "auto":
            import torch
            # torch.cuda.is_available() 检查当前环境是否有可用的 NVIDIA 显卡
            return "cuda" if torch.cuda.is_available() else "cpu"
        return device

    @property
    def model(self):
        """
        懒加载嵌入模型。

        @property 是 Python 的装饰器，让你可以像访问属性一样访问方法：
            self.model    ← 像属性
        而不是：
            self.model()  ← 像方法

        第一次访问时会触发加载，之后直接返回缓存的模型对象。
        """
        if self._model is None:
            # llama_index.embeddings.huggingface 是 LlamaIndex 对 HuggingFace 的适配层
            from llama_index.embeddings.huggingface import HuggingFaceEmbedding
            logger.info(f"正在加载嵌入模型: {self.model_name}，设备: {self.device}")
            self._model = HuggingFaceEmbedding(
                model_name=self.model_name,
                device=self.device,
            )
        return self._model

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        为一批文本生成嵌入向量。

        什么时候调用？
        上传 PDF 时，把所有文本块批量转成向量，然后存入 Qdrant。

        参数:
            texts: 字符串列表，如 ["第 1 条规定...", "第 2 条规定..."]

        返回:
            List[List[float]]: 每个文本对应的 1024 维向量
                               如 [[0.1, -0.2, ...], [0.3, 0.1, ...]]
        """
        if not texts:
            return []  # 防御性编程：空列表直接返回，避免下游报错
        # get_text_embedding_batch 内部会自动分批送入模型，充分利用 GPU 并行
        return self.model.get_text_embedding_batch(texts)

    def embed_query(self, text: str) -> List[float]:
        """
        为单个查询文本生成嵌入向量。

        什么时候调用？
        用户在聊天框输入问题后，把问题转成向量，然后去 Qdrant 搜索相似的文档块。

        参数:
            text: 用户的问题字符串

        返回:
            List[float]: 1024 维向量
        """
        return self.model.get_text_embedding(text)

    def get_dimension(self) -> int:
        """
        获取嵌入向量维度。

        用途：
        Qdrant 创建集合时需要知道向量维度（size），这个值来自配置中的 vector_dimension。
        如果某天换了模型（维度变了），改配置即可，不用改代码。

        返回:
            int: 向量维度，如 1024
        """
        return self.settings.vector_dimension
