"""
文档处理与管理服务。

这个文件是"文档模块"的业务逻辑核心。它协调多个组件完成从上传文件到可搜索索引的全流程：

    用户上传 PDF
        ↓
    [验证文件] 检查是不是 PDF、有没有超大小限制
        ↓
    [保存磁盘] 用 UUID 重命名，避免文件名冲突和安全问题
        ↓
    [记录状态] 写入内存字典 + .meta.json 文件，前端可以立即看到"待处理"
        ↓
    （异步）启动后台任务：
        [解析 PDF] PyMuPDF 提取文字和表格
        [切分文本] TextSplitter 切成 512 字的小段
        [生成向量] EmbeddingService 把每段转成 1024 维向量
        [存入 Qdrant] VectorStore 把向量 + 原文存入数据库
        ↓
    [更新状态] "completed" 或 "failed"

为什么要做成单例？
这个服务内部有一个 _documents 字典，保存所有文档的元数据。
如果是多实例，A 实例上传的文档，B 实例是看不到的，前端刷新就可能"丢文档"。
挂在 app.state 上单例化，确保所有请求共享同一份数据。
"""
import uuid
import os
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from fastapi import UploadFile
from fastapi.concurrency import run_in_threadpool

from app.core.config import Settings
from app.core.exceptions import (
    DocumentNotFound, PDFParseError, InvalidFileTypeError, FileTooLargeError
)
from app.core.logger import setup_logger
from app.utils.pdf_parser import PDFParser
from app.utils.text_splitter import TextSplitter
from app.utils.embedding import EmbeddingService
from app.services.vector_store import VectorStore

logger = setup_logger("rag_kb.document")

# 允许的 MIME 类型。MIME 类型是文件内容类型的标准标识，如 "application/pdf"、"image/png"
ALLOWED_MIME = {"application/pdf"}


class DocumentService:
    """
    文档生命周期管理服务。

    管理范围：上传、解析、分块、嵌入、索引、查询、删除。

    重要设计决策：
    1. 单例模式 — _documents 字典必须在所有请求间共享
    2. 异步后台处理 — 上传接口立即返回，解析等耗时操作在后台执行，不阻塞用户
    3. 磁盘持久化 — 即使服务器重启，从 .meta.json 文件恢复文档列表
    """

    def __init__(
        self,
        settings: Settings,
        text_splitter: TextSplitter,
        embedding_service: EmbeddingService,
        vector_store: VectorStore,
    ):
        """
        初始化服务。

        参数:
            settings: 全局配置
            text_splitter: 文本切分器实例
            embedding_service: 嵌入模型服务实例
            vector_store: Qdrant 向量存储实例
        """
        self.settings = settings
        self.text_splitter = text_splitter
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.pdf_parser = PDFParser()
        # 内存中的文档元数据仓库。键是 doc_id，值是文档信息字典
        # 所有对该字典的读写操作都是同步的（不涉及 IO），所以不需要锁
        self._documents: Dict[str, Dict[str, Any]] = {}
        # KG 服务懒加载（需要 LLM，初始化时不创建）
        self._kg_service = None
        # 启动时尝试从磁盘恢复之前上传的文档记录
        self._recover_from_disk()

    def _get_kg_service(self):
        """
        懒加载知识图谱服务。

        为什么懒加载？
        KGService 需要 LlamaIndex 的 LLM 实例来提取三元组。
        LLM 实例创建有一定开销（需要验证 api_key、base_url 等），
        而且如果用户关闭了 enable_kg，根本不需要创建它。
        """
        if self._kg_service is None and self.settings.enable_kg:
            from llama_index.llms.openai import OpenAI as LlamaOpenAI
            from app.services.kg_service import KGService

            kwargs = {
                "model": self.settings.llm_model,
                "temperature": 0.1,
            }
            if self.settings.openai_api_key:
                kwargs["api_key"] = self.settings.openai_api_key
            if self.settings.openai_base_url:
                kwargs["api_base"] = self.settings.openai_base_url

            # 注册自定义模型（DeepSeek 等第三方模型不在 llama_index 硬编码列表中）
            try:
                from llama_index.llms.openai import utils as openai_utils
                model_name = self.settings.llm_model
                if model_name not in openai_utils.ALL_AVAILABLE_MODELS:
                    openai_utils.ALL_AVAILABLE_MODELS[model_name] = 128_000
                if model_name not in openai_utils.CHAT_MODELS:
                    openai_utils.CHAT_MODELS[model_name] = True
            except Exception:
                pass

            llm = LlamaOpenAI(**kwargs)
            self._kg_service = KGService(self.settings, llm)
        return self._kg_service

    def _recover_from_disk(self):
        """
        从磁盘恢复文档元数据。

        场景：服务器重启了，但用户之前上传的文档还在 data/documents/ 目录里。
        每个文档有一个 .meta.json 文件（如 doc_abc123.meta.json），保存了文件名、
        状态、页数等信息。这个函数扫描目录，把这些文件读回内存。

        如果恢复失败（文件损坏），只记录警告，不阻止启动。
        """
        import json
        doc_dir = Path(self.settings.doc_dir)
        if not doc_dir.exists():
            return  # 目录不存在，说明还没上传过任何文档

        # glob("*.meta.json") 查找目录下所有以 .meta.json 结尾的文件
        meta_files = sorted(doc_dir.glob("*.meta.json"))
        if not meta_files:
            return

        for mf in meta_files:
            try:
                with open(mf, "r", encoding="utf-8") as f:
                    doc = json.load(f)
                # 兼容处理：如果旧文件没有 doc_id 字段，从文件名推导
                doc_id = doc.get("doc_id", mf.stem.replace(".meta", ""))
                self._documents[doc_id] = doc
            except Exception as e:
                logger.warning(f"从 {mf.name} 恢复元数据失败: {e}")

        logger.info(f"从磁盘恢复了 {len(self._documents)} 份文档")

    def _save_meta_to_disk(self, doc_id: str):
        """
        将单个文档的元数据持久化到磁盘。

        什么时候调用？
        - 刚创建文档记录时（pending 状态）
        - 后台处理完成或失败时（更新状态）

        为什么要持久化？
        _documents 只存在内存中。如果服务器重启，内存清空，
        没有磁盘文件的话，用户上传的文档就"消失"了。

        参数:
            doc_id: 要保存的文档 ID
        """
        import json
        doc = self._documents.get(doc_id)
        if not doc:
            return  # 防御：如果文档已删除，不用保存

        meta_path = Path(self.settings.doc_dir) / f"{doc_id}.meta.json"
        try:
            with open(meta_path, "w", encoding="utf-8") as f:
                # ensure_ascii=False 保证中文正常写入，而不是变成 \uXXXX
                # indent=2 让 JSON 文件有缩进，方便人类阅读
                # default=str 处理 datetime 等不可 JSON 序列化的类型（转成字符串）
                json.dump(doc, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            logger.warning(f"持久化文档 {doc_id} 的元数据失败: {e}")

    def validate_file(self, file: UploadFile) -> None:
        """
        验证上传文件的合法性。

        校验三层防线：
        1. Content-Type: 浏览器上报的 MIME 类型必须是 application/pdf
        2. 魔数（Magic Number）: 读取文件头几个字节，检查是否以 %PDF- 开头
           （MIME 类型可以被伪造，魔数检查更可靠）
        3. 文件大小: 不能超过 max_file_size_mb（默认 50MB）

        参数:
            file: FastAPI 包装的文件上传对象

        抛出:
            InvalidFileTypeError: 不是 PDF 或魔数不匹配
            FileTooLargeError: 文件超过大小限制
        """
        # === 第一层：Content-Type 检查 ===
        if file.content_type not in ALLOWED_MIME:
            raise InvalidFileTypeError()

        # === 第二层：魔数检查 ===
        # 读取前 8 个字节。PDF 文件的文件头固定以 %PDF- 开头
        header = file.file.read(8)
        file.file.seek(0)  # 把文件指针移回开头，后续操作（如保存）可以从头读取
        if not header.startswith(b"%PDF-"):
            raise InvalidFileTypeError()

        # === 第三层：文件大小检查 ===
        # seek(0, os.SEEK_END) 跳到文件末尾，tell() 返回当前位置 = 总字节数
        file.file.seek(0, os.SEEK_END)
        size = file.file.tell()
        file.file.seek(0)  # 再次移回开头
        if size > self.settings.max_file_size_mb * 1024 * 1024:
            raise FileTooLargeError()

    async def save_upload(self, file: UploadFile) -> Tuple[Path, str]:
        """
        将上传的文件保存到磁盘。

        安全措施：
        - 不用原始文件名，而是用 UUID（随机唯一 ID）命名，防止：
          a) 同名文件覆盖
          b) 恶意文件名（如 ../../../etc/passwd）造成目录遍历攻击

        参数:
            file: 用户上传的文件

        返回:
            Tuple[Path, str]: (保存后的文件路径, 生成的文档 ID)
        """
        os.makedirs(self.settings.doc_dir, exist_ok=True)  # 如果目录不存在就创建

        # uuid.uuid4() 生成全球唯一的随机 ID，取前 10 个字符作为短 ID
        doc_id = f"doc_{uuid.uuid4().hex[:10]}"
        safe_name = f"{doc_id}.pdf"  # 强制 .pdf 后缀
        file_path = Path(self.settings.doc_dir) / safe_name

        # await file.read() 异步读取上传的文件内容到内存
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)

        return file_path, doc_id

    async def process_document(self, file: UploadFile) -> dict:
        """
        处理文档上传请求（入口函数）。

        设计模式："异步任务分离"
        用户上传文件后，最在意的是"有没有成功接收"。解析 PDF、生成向量这些操作
        可能要几十秒，如果让用户干等着，体验很差。
        所以：
        1. 验证 + 保存（几百毫秒）→ 立即返回 pending 状态
        2. 真正的处理放在 asyncio.create_task() 里在后台跑

        参数:
            file: 上传的文件

        返回:
            dict: 包含 doc_id、filename、status="pending" 等信息的文档记录
        """
        # === 步骤 1：验证 ===
        self.validate_file(file)

        # === 步骤 2：保存 ===
        file_path, doc_id = await self.save_upload(file)
        filename = file.filename or "unknown.pdf"  # 如果浏览器没传文件名，给个默认的

        # === 步骤 3：创建初始记录 ===
        # 用户立刻能在列表里看到这个文档，状态是"待处理"
        doc_record = {
            "doc_id": doc_id,
            "filename": filename,
            "status": "pending",
            "total_pages": 0,
            "total_chunks": 0,
            "message": "文档已加入处理队列",
            "created_at": datetime.utcnow().isoformat(),  # UTC 时间，带时区无关性
            "updated_at": datetime.utcnow().isoformat(),
        }
        self._documents[doc_id] = doc_record
        self._save_meta_to_disk(doc_id)  # 立即持久化，防止重启丢失

        # === 步骤 4：启动后台处理 ===
        # asyncio.create_task() 创建一个后台任务，不等待它完成，函数立即返回
        asyncio.create_task(self._process_background(file_path, doc_id, filename))

        return doc_record

    async def _process_background(self, file_path: Path, doc_id: str, filename: str):
        """
        后台任务：解析 → 分块 → 嵌入 → 索引。

        这是一个"长任务"，可能持续几秒到几十秒，取决于 PDF 大小和硬件性能。
        全程在后台运行，不影响其他用户请求。

        技术要点：
        - run_in_threadpool: PyMuPDF 和 embedding 模型是 CPU 密集型操作，
          会阻塞事件循环。用线程池把它们放到独立线程执行，让主事件循环继续处理 HTTP 请求。
        - 状态更新: 每个阶段都更新 doc_record["message"]，前端轮询时能看到实时进度。

        参数:
            file_path: PDF 在磁盘上的路径
            doc_id: 文档唯一 ID
            filename: 原始文件名
        """
        doc_record = self._documents.get(doc_id)
        if not doc_record:
            return  # 处理开始前文档已被删除，优雅退出

        try:
            # === 阶段 1：解析 PDF ===
            doc_record["status"] = "processing"
            doc_record["message"] = "正在解析 PDF"
            doc_record["updated_at"] = datetime.utcnow().isoformat()

            # parse_with_tables 是 CPU 密集型操作，用线程池避免阻塞主事件循环
            chunks = await run_in_threadpool(
                self.pdf_parser.parse_with_tables, file_path
            )
            metadata = await run_in_threadpool(
                self.pdf_parser.get_metadata, file_path
            )
            # 页数优先用 PDF 元数据，如果元数据没有则用解析出的块数兜底
            doc_record["total_pages"] = metadata.get("total_pages", len(chunks))
            doc_record["metadata"] = {
                "title": metadata.get("title", ""),
                "author": metadata.get("author", ""),
                "subject": metadata.get("subject", ""),
                "total_pages": metadata.get("total_pages", len(chunks)),
            }
            doc_record["message"] = f"已解析 {len(chunks)} 页"

            # === 阶段 2：切分文本 ===
            all_chunks = []
            global_chunk_index = 0  # 全局块序号，跨所有 PDF blocks 递增
            for chunk in chunks:
                text_chunks = self.text_splitter.split(
                    text=chunk.content,
                    doc_id=doc_id,
                    doc_name=filename,
                    page=chunk.page,
                    start_index=global_chunk_index,  # 传入当前全局序号
                )
                if text_chunks:
                    # 更新全局序号：下一个 block 从当前最后一个块的序号 + 1 开始
                    global_chunk_index = text_chunks[-1]["chunk_index"] + 1
                all_chunks.extend(text_chunks)

            doc_record["message"] = f"已切分为 {len(all_chunks)} 个文本块"
            doc_record["total_chunks"] = len(all_chunks)

            # 极端情况：PDF 是扫描件且没有 OCR，提取不到任何文字
            if not all_chunks:
                doc_record["status"] = "completed"
                doc_record["message"] = "PDF 中未找到可识别的文字内容"
                doc_record["updated_at"] = datetime.utcnow().isoformat()
                return

            # === 阶段 3：生成嵌入向量（批量）===
            batch_size = self.settings.embedding_batch_size  # 默认 32
            texts = [c["content"] for c in all_chunks]  # 提取纯文本内容
            all_embeddings = []

            for i in range(0, len(texts), batch_size):
                batch_texts = texts[i:i + batch_size]
                batch_embeddings = await run_in_threadpool(
                    self.embedding_service.embed_texts, batch_texts
                )
                all_embeddings.extend(batch_embeddings)

                # 更新进度信息，前端轮询时能看到"正在嵌入：32/150"
                done_count = min(i + batch_size, len(texts))
                doc_record["message"] = f"正在生成向量: {done_count}/{len(texts)}"
                doc_record["updated_at"] = datetime.utcnow().isoformat()

            # === 阶段 4：准备 Qdrant 数据点 ===
            # Qdrant 每条记录叫一个"点"（Point），包含：
            # - id: 唯一标识（用 UUID）
            # - vector: 1024 维向量
            # - payload: 附加信息（原文、页码、文档 ID 等）
            points = []
            for i, chunk in enumerate(all_chunks):
                import uuid as _uuid
                points.append({
                    "id": str(_uuid.uuid4()),
                    "vector": all_embeddings[i],
                    "payload": {
                        "doc_id": doc_id,
                        "doc_name": filename,
                        "content": chunk["content"],
                        "page": chunk["page"],
                        "chunk_index": chunk["chunk_index"],
                        "status": doc_record["status"],
                        "created_at": doc_record["created_at"],
                    },
                })

            # === 阶段 5：写入 Qdrant ===
            doc_record["message"] = f"正在索引 {len(points)} 个向量"
            if self.vector_store.is_connected():
                await self.vector_store.upsert(points)
                doc_record["message"] = "向量索引完成"
            else:
                logger.warning("Qdrant 不可用 — 向量未索引")
                doc_record["message"] = "已处理但向量未索引（Qdrant 不可用）"

            # === 阶段 6：构建知识图谱 ===
            # 在向量索引完成后，异步构建知识图谱（不阻塞返回 completed 状态）
            # KG 构建调用 LLM，耗时较长，失败不影响主流程
            if self.settings.enable_kg and all_chunks:
                doc_record["message"] = "正在构建知识图谱..."
                try:
                    kg_service = self._get_kg_service()
                    if kg_service:
                        await kg_service.build_for_document(doc_id, filename, all_chunks)
                        doc_record["message"] = "处理完成（含知识图谱）"
                except Exception as e:
                    logger.warning(f"知识图谱构建失败（不影响文档检索）: {e}")
                    doc_record["message"] = "处理完成（知识图谱构建失败）"

            doc_record["status"] = "completed"
            doc_record["updated_at"] = datetime.utcnow().isoformat()

        except Exception as e:
            # 任何阶段出错，记录日志，更新状态为 failed
            logger.error(f"处理文档 {doc_id} 失败: {str(e)}")
            doc_record["status"] = "failed"
            doc_record["message"] = str(e)
            doc_record["updated_at"] = datetime.utcnow().isoformat()

        # 无论成功还是失败，都要保存最终状态到磁盘
        self._save_meta_to_disk(doc_id)

    def get_document(self, doc_id: str) -> dict:
        """
        获取单个文档记录。

        参数:
            doc_id: 文档 ID

        返回:
            dict: 文档的完整信息

        抛出:
            DocumentNotFound: 文档不存在时抛出，由全局异常处理器转为 HTTP 404
        """
        if doc_id not in self._documents:
            raise DocumentNotFound(doc_id)
        return self._documents[doc_id]

    def get_documents(self) -> List[dict]:
        """
        获取所有文档记录，最新的排在最前面。

        排序依据：created_at（创建时间），降序（reverse=True）
        这样用户上传的新文档会显示在列表顶部。

        返回:
            List[dict]: 文档列表
        """
        docs = list(self._documents.values())
        docs.sort(key=lambda d: d.get("created_at", ""), reverse=True)
        return docs

    def get_status(self, doc_id: str) -> dict:
        """
        获取文档的处理状态（供前端轮询）。

        返回:
            dict: 包含 doc_id、status、progress（0-100）、message、updated_at
        """
        doc = self.get_document(doc_id)
        return {
            "doc_id": doc["doc_id"],
            "status": doc["status"],
            "progress": self._compute_progress(doc),
            "message": doc.get("message", ""),
            "updated_at": doc.get("updated_at", ""),
        }

    async def delete_document(self, doc_id: str) -> dict:
        """
        删除文档及其所有关联数据。

        清理三件事：
        1. 向量：从 Qdrant 删除该文档的所有向量点
        2. 文件：删除磁盘上的 PDF 和 .meta.json
        3. 内存：从 _documents 字典移除

        参数:
            doc_id: 要删除的文档 ID

        返回:
            dict: { doc_id, deleted: True }
        """
        if doc_id not in self._documents:
            raise DocumentNotFound(doc_id)

        # 1. 删除向量（如果 Qdrant 不可用则跳过，不阻止文件清理）
        if self.vector_store.is_connected():
            await self.vector_store.delete_by_doc_id(doc_id)

        # 2. 删除磁盘文件（PDF + 元数据 + 知识图谱）
        file_path = Path(self.settings.doc_dir) / f"{doc_id}.pdf"
        meta_path = Path(self.settings.doc_dir) / f"{doc_id}.meta.json"
        kg_path = Path(self.settings.kg_dir) / f"{doc_id}_kg.json"
        if file_path.exists():
            os.remove(file_path)
        if meta_path.exists():
            os.remove(meta_path)
        if kg_path.exists():
            os.remove(kg_path)

        # 3. 从内存移除
        del self._documents[doc_id]

        return {"doc_id": doc_id, "deleted": True}

    def _compute_progress(self, doc: dict) -> int:
        """
        估算文档处理进度百分比（0~100）。

        不同状态的固定值：
        - pending: 0（还没开始）
        - completed: 100（已完成）
        - failed: 0（失败了，进度重置）

        processing 状态的动态估算：
        - 从 message 中解析，如 "正在生成向量: 64/150" → 64/150 ≈ 43%
        - 如果解析失败，默认返回 50（表示处理中但具体进度未知）

        参数:
            doc: 文档记录字典

        返回:
            int: 0~100 的进度值
        """
        status = doc.get("status", "pending")
        if status == "pending":
            return 0
        if status == "completed":
            return 100
        if status == "failed":
            return 0

        # processing 状态 — 尝试从消息中解析进度
        msg = doc.get("message", "")
        if "/" in msg:
            try:
                # 格式通常是 "正在生成向量: 64/150"
                parts = msg.split(":")[-1].strip()  # 取冒号后面的 "64/150"
                done, total = parts.split("/")
                return int(int(done) / int(total) * 100)
            except (ValueError, ZeroDivisionError):
                pass  # 解析失败，fallback 到默认进度

        return 50  # 默认：处理中，但具体进度未知
