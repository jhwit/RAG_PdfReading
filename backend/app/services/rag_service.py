"""
RAG 查询流水线服务。

RAG 是什么？
全称 Retrieval-Augmented Generation（检索增强生成）。
通俗解释：AI 不是凭空回答，而是先查资料，再基于查到的资料回答。

为什么需要 RAG？
1. 解决"幻觉"问题：大模型可能编造不存在的信息，有了资料约束，回答更可信
2. 解决"知识时效"问题：模型训练数据有截止日期，RAG 可以查最新的文档
3. 解决"私有知识"问题：国家标准、公司内部文档不会出现在公开训练数据里，
   只有把文档喂给模型，它才能回答相关问题

本文件的 RAG 流程：
    用户提问
        ↓
    [1. 嵌入查询] 把问题转成 1024 维向量
        ↓
    [2. 向量检索] 在 Qdrant 中找最相似的 top_k 个文本块
        ↓
    [3. 构建上下文] 把检索到的文本块拼接成一个长字符串
        ↓
    [4. 生成回答] 把"问题 + 上下文"发给 LLM，让它基于资料回答
        ↓
    [5. 质量审核] AnswerAgent 检查回答是否空洞/跑题，必要时重写
        ↓
    返回：回答 + 引用来源

两种模式：
- query(): 普通模式，等 LLM 全部生成完再返回（适合简单场景）
- query_stream(): 流式模式，生成一个字发一个字（适合聊天界面）
"""
import time
from typing import List, Optional, AsyncGenerator, Dict, Any
from llama_index.llms.openai import OpenAI

from app.core.config import Settings
from app.core.exceptions import EmptyQueryError, QueryTooLongError, NoRelevantDocsError, LLMUnavailableError
from app.core.logger import setup_logger

logger = setup_logger("rag_kb.rag")


def _patch_llama_index_models(model_name: str):
    """
    注册自定义模型，使 llama_index 的 OpenAI 包装器能够接受它。

    背景问题：
    llama_index 内部有一个硬编码的模型列表（ALL_AVAILABLE_MODELS）。
    如果你用第三方 API（如 DeepSeek、OpenRouter），模型名（如 "deepseek-chat"）
    不在列表里，llama_index 会直接报错 "Unknown model"。

    解决方法：
    在导入时动态把模型名注册到列表里，并标记为 chat 模型。
    128_000 是上下文窗口大小（token 数），表示模型最多能处理多长的输入。

    参数:
        model_name: 要注册的模型名，如 "deepseek-chat"
    """
    try:
        from llama_index.llms.openai import utils as openai_utils

        if model_name not in openai_utils.ALL_AVAILABLE_MODELS:
            openai_utils.ALL_AVAILABLE_MODELS[model_name] = 128_000
        if model_name not in openai_utils.CHAT_MODELS:
            openai_utils.CHAT_MODELS[model_name] = True
        logger.debug(f"已注册自定义模型: {model_name}")
    except Exception:
        pass  # 尽力而为；如果这里失败，后续 LLM 调用会给出更明确的错误


class RAGService:
    """
    编排 RAG 流水线：检索 → 综合 → 回答。

    这个类本身不保存状态，每次 HTTP 请求都会新建一个实例（通过 query.py 的 get_rag_service）。
    所以它只需要配置（settings）和两个共享服务（embedding_service、vector_store）。

    懒加载设计：
    - _llm: 第一次使用时才创建 OpenAI 客户端（因为创建对象就有开销）
    - _answer_agent: 第一次需要质量审核时才初始化
    """

    def __init__(
        self,
        settings: Settings,
        embedding_service,
        vector_store,
        kg_service=None,
    ):
        """
        初始化 RAG 服务。

        参数:
            settings: 全局配置
            embedding_service: 嵌入模型服务（把文字转成向量）
            vector_store: 向量存储（Qdrant，用于语义搜索）
            kg_service: 知识图谱服务（可选），用于图谱增强检索
        """
        self.settings = settings
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.kg_service = kg_service
        self._llm = None
        self._answer_agent = None
        # 如果配置了第三方 API 地址，预先注册模型名，避免 llama_index 报错
        if settings.openai_base_url:
            _patch_llama_index_models(settings.llm_model)

    @property
    def answer_agent(self):
        """
        懒加载 AnswerAgent（回答质量审核代理）。

        为什么懒加载？
        AnswerAgent 需要 LLM 实例才能工作。如果用户查询时 Qdrant 不可用、
        没有相关文档，直接返回降级提示，根本用不到 AnswerAgent。
        懒加载避免不必要的初始化开销。
        """
        if self._answer_agent is None:
            from app.services.answer_agent import AnswerAgent
            self._answer_agent = AnswerAgent(self.llm)
        return self._answer_agent

    @property
    def llm(self):
        """
        懒加载 LLM（大语言模型客户端）。

        创建参数：
        - model: 模型名（如 "gpt-4o" 或 "deepseek-chat"）
        - temperature: 温度，0.1 表示很保守，输出稳定可预测
        - api_key / api_base: 认证信息，从 .env 读取

        注意 api_base 不是 base_url：
        llama_index 的 OpenAI 包装器使用的是 api_base（兼容 OpenAI SDK 旧版命名）。
        """
        if self._llm is None:
            kwargs = {
                "model": self.settings.llm_model,
                "temperature": self.settings.llm_temperature,
            }
            if self.settings.openai_api_key:
                kwargs["api_key"] = self.settings.openai_api_key
            if self.settings.openai_base_url:
                kwargs["api_base"] = self.settings.openai_base_url
            self._llm = OpenAI(**kwargs)
        return self._llm

    async def query(
        self,
        question: str,
        top_k: int = 5,
        filter_doc_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        执行 RAG 查询并返回带引用的回答（普通模式）。

        参数:
            question: 用户的问题
            top_k: 检索多少个最相似的文本块（默认 5）
            filter_doc_ids: 只从指定文档中检索（可选）

        返回:
            dict: 包含 answer（回答）、sources（来源列表）、query_time_ms（耗时）、model（模型名）
        """
        top_k = self._validate_query(question, top_k)

        start_time = time.time()  # 记录开始时间，用于计算耗时
        sources = []              # 引用来源列表
        context = ""             # 拼接后的上下文字符串

        try:
            # === 步骤 1：生成查询嵌入 ===
            # 把用户问题转成向量，这样才能在向量数据库中找"意思相近"的段落
            try:
                query_vector = await self._embed_query(question)
            except Exception as e:
                logger.error(f"嵌入生成失败: {e}")
                return self._fallback_answer(
                    "嵌入模型暂时不可用，请稍后重试。",
                    int((time.time() - start_time) * 1000),
                )

            # === 步骤 2：搜索 Qdrant ===
            # 在向量数据库中找和查询向量最相似的文本块
            kg_context = ""  # 知识图谱补充上下文
            if self.vector_store.is_connected():
                try:
                    results = await self.vector_store.search(
                        vector=query_vector,
                        top_k=top_k,
                        filter_doc_ids=filter_doc_ids,
                    )
                    if results:
                        # 召回相邻 chunk，解决单 chunk 上下文不足问题
                        results = await self._expand_with_neighbors(results, window=1)
                        context, sources = self._build_context_and_sources(results)
                        logger.info(
                            f"检索到 {len(results)} 个 chunk，"
                            f"上下文总长 {len(context)} 字符"
                        )
                except Exception as e:
                    logger.warning(f"Qdrant 搜索失败（继续无上下文回答）: {e}")
            else:
                logger.warning("Qdrant 不可用 — 将在无文档上下文的情况下回答")

            # === 步骤 2.5：知识图谱查询（补充检索） ===
            # 当向量检索找到一些结果后，再用知识图谱查询补充：
            # - 找到问题中实体关联的其他条款（引用链）
            # - 找到同一概念在不同条款中的定义
            if self.kg_service and context:
                try:
                    kg_results = await self.kg_service.query(
                        question=question,
                        doc_ids=[s["doc_id"] for s in sources[:3]] if sources else None,
                    )
                    if kg_results:
                        kg_context = "\n\n---\n\n【知识图谱补充信息】\n\n" + "\n\n".join(kg_results[:5])
                        logger.debug(f"知识图谱补充了 {len(kg_results)} 条信息")
                except Exception as e:
                    logger.warning(f"知识图谱查询失败（不影响主流程）: {e}")

            # 如果没有任何上下文（文档库为空或检索无结果），返回友好提示
            if not context:
                return self._fallback_answer(
                    "知识库中没有相关文档。请先上传国家标准 PDF 文件。",
                    int((time.time() - start_time) * 1000),
                )

            # === 步骤 3：使用 LLM 生成回答 ===
            # 把"问题 + 向量检索上下文 + 知识图谱上下文"组装成 prompt
            full_context = context + kg_context if kg_context else context
            prompt = self._build_prompt(question, full_context)
            raw_answer = await self._generate(prompt)

            # === 步骤 4：质量后处理 ===
            # AnswerAgent 会检查：回答是不是太短？是不是在循环说废话？
            # 如果是，就用 LLM 基于上下文重新写一个高质量回答
            if full_context:
                reviewed = self.answer_agent.rewrite_if_needed(question, full_context, raw_answer)
                final_answer = reviewed["answer"]
            else:
                final_answer = raw_answer

            query_time_ms = int((time.time() - start_time) * 1000)

            return {
                "answer": final_answer,
                "sources": sources,
                "query_time_ms": query_time_ms,
                "model": self.settings.llm_model,
            }

        except (EmptyQueryError, QueryTooLongError):
            # 这两种是业务异常，直接抛出让全局异常处理器处理
            raise
        except Exception as e:
            # 其他意外错误，记录日志，返回降级回答
            logger.error(f"RAG 查询失败: {str(e)}")
            return self._fallback_answer(
                f"抱歉，问答服务暂时不可用：{str(e)}",
                int((time.time() - start_time) * 1000),
            )

    async def query_stream(
        self,
        question: str,
        top_k: int = 5,
        filter_doc_ids: Optional[List[str]] = None,
    ) -> AsyncGenerator[str, None]:
        """
        执行流式 SSE 响应的 RAG 查询。

        与普通 query() 的区别：
        - query() 返回一个完整的 dict
        - query_stream() 是一个异步生成器，每次 yield 一段 SSE 格式的字符串

        SSE 事件类型：
        - start: 查询开始
        - chunk: LLM 生成的文字片段（可以多次）
        - sources: 引用来源列表（所有 chunk 发完后发送）
        - end: 查询结束，附带总耗时

        参数:
            question, top_k, filter_doc_ids: 同 query()

        返回:
            AsyncGenerator: 不断产生 SSE 数据字符串
        """
        top_k = self._validate_query(question, top_k)
        start_time = time.time()

        # 发送"开始"事件，告诉前端可以开始显示 loading 状态了
        yield self._sse_event("start", {"query_time_ms": 0})

        try:
            # === 步骤 1：嵌入查询 ===
            try:
                query_vector = await self._embed_query(question)
            except Exception as e:
                logger.error(f"嵌入生成失败: {e}")
                yield self._sse_event("chunk", {"content": "嵌入模型暂时不可用，请稍后重试。"})
                yield self._sse_event("sources", {"sources": []})
                yield self._sse_event("end", {"query_time_ms": int((time.time() - start_time) * 1000)})
                return

            # === 步骤 2：搜索 Qdrant ===
            context = ""
            sources = []
            if self.vector_store.is_connected():
                try:
                    results = await self.vector_store.search(
                        vector=query_vector,
                        top_k=top_k,
                        filter_doc_ids=filter_doc_ids,
                    )
                    if results:
                        context, sources = self._build_context_and_sources(results)
                except Exception as e:
                    logger.warning(f"Qdrant 搜索失败: {e}")

            # === 步骤 2.5：知识图谱查询（补充检索） ===
            kg_context = ""
            if self.kg_service and context:
                try:
                    kg_results = await self.kg_service.query(
                        question=question,
                        doc_ids=[s["doc_id"] for s in sources[:3]] if sources else None,
                    )
                    if kg_results:
                        kg_context = "\n\n---\n\n【知识图谱补充信息】\n\n" + "\n\n".join(kg_results[:5])
                except Exception as e:
                    logger.warning(f"知识图谱查询失败（不影响主流程）: {e}")

            if not context:
                yield self._sse_event("chunk", {"content": "知识库中没有相关文档。请先上传国家标准 PDF 文件。"})
                yield self._sse_event("sources", {"sources": []})
                yield self._sse_event("end", {"query_time_ms": int((time.time() - start_time) * 1000)})
                return

            # === 步骤 3：流式生成回答 ===
            full_context = context + kg_context if kg_context else context
            prompt = self._build_prompt(question, full_context)

            try:
                # stream_complete 返回一个生成器，每次吐出一个 token（几个字）
                response = self.llm.stream_complete(prompt)
                for chunk in response:
                    # chunk 可能是对象，取 .delta 属性获取文本增量
                    content = chunk.delta if hasattr(chunk, 'delta') else str(chunk)
                    if content:
                        yield self._sse_event("chunk", {"content": content})
            except AttributeError:
                # 降级方案：如果模型不支持流式，就用普通模式，然后手动切成小段发送
                answer = self.llm.complete(prompt)
                text = answer.text if hasattr(answer, 'text') else str(answer)
                chunk_size = 10
                for i in range(0, len(text), chunk_size):
                    yield self._sse_event("chunk", {"content": text[i:i + chunk_size]})
            except Exception as e:
                logger.error(f"LLM 生成失败: {e}")
                yield self._sse_event("chunk", {"content": f"抱歉，AI 回答生成失败：{str(e)}"})

            # === 步骤 4：发送来源和结束事件 ===
            yield self._sse_event("sources", {"sources": sources})
            query_time_ms = int((time.time() - start_time) * 1000)
            yield self._sse_event("end", {"query_time_ms": query_time_ms})

        except Exception as e:
            logger.error(f"流式查询失败: {str(e)}")
            yield self._sse_event("chunk", {"content": f"抱歉，问答服务暂时不可用：{str(e)}"})
            yield self._sse_event("end", {"query_time_ms": int((time.time() - start_time) * 1000)})

    async def _expand_with_neighbors(self, results: List[dict], window: int = 1) -> List[dict]:
        """
        对检索结果进行相邻 chunk 扩展（AutoMergingRetriever 思想）。

        国家标准文档的单个 chunk 可能只包含半句话，召回相邻 chunk
        可以补全上下文，显著提升回答质量。

        参数:
            results: 原始检索结果
            window: 向两侧扩展的块数

        返回:
            List[dict]: 扩展后的结果列表（按原始顺序，邻居插入到对应位置）
        """
        if not results or window <= 0:
            return results

        expanded = []
        seen_ids = set()

        for hit in results:
            hit_id = hit.get("id")
            if hit_id in seen_ids:
                continue
            seen_ids.add(hit_id)
            expanded.append(hit)

            payload = hit.get("payload", {})
            doc_id = payload.get("doc_id")
            chunk_index = payload.get("chunk_index")

            if not doc_id or chunk_index is None:
                continue

            try:
                neighbors = await self.vector_store.get_neighbor_chunks(
                    doc_id=doc_id,
                    chunk_index=chunk_index,
                    window=window,
                )
                for nb in neighbors:
                    # 构造和搜索结果一致的格式
                    nb_hit = {
                        "id": nb["id"],
                        "score": hit.get("score", 0.0),  # 继承中心块的分数
                        "payload": {
                            "doc_id": doc_id,
                            "doc_name": nb.get("doc_name", ""),
                            "content": nb.get("content", ""),
                            "page": nb.get("page"),
                            "chunk_index": nb.get("chunk_index"),
                        },
                        "is_neighbor": True,  # 标记为邻居扩展
                    }
                    if nb["id"] not in seen_ids:
                        seen_ids.add(nb["id"])
                        expanded.append(nb_hit)
            except Exception as e:
                logger.debug(f"扩展邻居失败: {e}")
                continue

        return expanded

    def _build_context_and_sources(self, results: List[dict]) -> tuple:
        """
        从搜索结果构建上下文和来源列表。

        上下文（context）：
        把多个文本块拼接成一个长字符串，用 "\n\n---\n\n" 分隔，
        并标注每段的来源（文档名、页码），方便 LLM 引用。

        来源（sources）：
        给前端用的结构化数据，包含文档名、页码、相似度分数、内容摘要。

        参数:
            results: Qdrant 搜索结果列表

        返回:
            tuple: (context 字符串, sources 列表)
        """
        context_parts = []
        sources = []
        for hit in results:
            payload = hit["payload"]
            full_content = payload.get('content', '')
            context_parts.append(
                f"[来源: {payload.get('doc_name', '')}, 第{payload.get('page', '?')}页]\n"
                f"{full_content}"
            )
            # 给前端展示的内容摘要（前 200 字符）
            excerpt = full_content[:200].replace('\n', ' ').strip()
            if len(full_content) > 200:
                excerpt += '...'
            sources.append({
                "doc_id": payload.get("doc_id", ""),
                "doc_name": payload.get("doc_name", ""),
                "page": payload.get("page"),
                "chunk_index": payload.get("chunk_index"),
                "score": round(hit["score"], 4),  # 保留 4 位小数
                "excerpt": excerpt,
            })
        return "\n\n---\n\n".join(context_parts), sources

    def _validate_query(self, question: str, top_k: int) -> int:
        """
        验证查询参数。

        检查项：
        1. 问题不能为空或纯空格
        2. 问题不能超过 2000 字符（防止恶意输入拖垮 LLM）
        3. top_k 限制在 1~max_top_k 之间（防止要太多结果导致超时）

        参数:
            question: 用户问题
            top_k: 请求的结果数量

        返回:
            int: 校验后的 top_k 值

        抛出:
            EmptyQueryError: 问题为空
            QueryTooLongError: 问题过长
        """
        if not question or not question.strip():
            raise EmptyQueryError()
        if len(question) > 2000:
            raise QueryTooLongError()
        return min(max(top_k, 1), self.settings.max_top_k)

    async def _embed_query(self, text: str) -> List[float]:
        """
        为查询生成嵌入向量。

        因为 embedding 模型是同步的（CPU/GPU 计算不能 await），
        用 run_in_threadpool 把它放到线程池中执行，不阻塞事件循环。

        参数:
            text: 查询文本

        返回:
            List[float]: 1024 维向量
        """
        from fastapi.concurrency import run_in_threadpool
        return await run_in_threadpool(self.embedding_service.embed_query, text)

    async def _generate(self, prompt: str) -> str:
        """
        从 LLM 生成回答。

        同样是同步操作（等 API 返回），用线程池包装。

        参数:
            prompt: 组装好的提示词

        返回:
            str: LLM 生成的回答文本
        """
        from fastapi.concurrency import run_in_threadpool

        def _sync_generate():
            response = self.llm.complete(prompt)
            return response.text if hasattr(response, 'text') else str(response)

        return await run_in_threadpool(_sync_generate)

    def _build_prompt(self, question: str, context: str) -> str:
        """
        构建发给 LLM 的提示词（Prompt）。

        Prompt 工程（Prompt Engineering）是 RAG 的核心之一。
        一个好的提示词要告诉模型：
        1. 它是谁（专业助手）
        2. 它的任务（基于资料回答问题）
        3. 约束条件（不能编造、要引用来源、要结构化）
        4. 输入数据（文档内容）
        5. 具体问题

        参数:
            question: 用户问题
            context: 检索到的参考资料

        返回:
            str: 完整提示词字符串
        """
        return f"""你是一个专业的知识库问答助手，基于提供的国家标准文档内容回答问题。

请遵循以下规则：
1. 优先根据以下文档内容回答问题，如果文档中有相关信息，必须引用具体条文
2. 如果文档中没有直接相关信息，但有关联内容，请基于关联内容尽力回答，并说明信息来源
3. 只有当文档完全没有任何相关信息时，才说明"根据提供的文档，未找到相关信息"
4. 引用具体规范条文时，注明来源（如"第6.4.1条规定..."）
5. 答案要准确、简洁、结构化

文档内容：
{context}

用户问题：{question}

请回答："""

    def _fallback_answer(self, message: str, query_time_ms: int) -> dict:
        """
        服务不可用时返回优雅的降级回答。

        降级回答的好处：
        - 用户知道发生了什么（不是一片空白）
        - 用户知道下一步该做什么（如"请先上传文档"）
        - 保留统一的响应格式，前端不需要额外处理

        参数:
            message: 给用户的提示信息
            query_time_ms: 已耗时（毫秒）

        返回:
            dict: 标准格式的降级响应
        """
        return {
            "answer": message,
            "sources": [],
            "query_time_ms": query_time_ms,
            "model": "fallback",
        }

    def _sse_event(self, event_type: str, data: dict) -> str:
        """
        格式化 Server-Sent Event 数据。

        SSE 格式要求：
            data: {json}\n\n
        每段数据以两个换行符结束，这是 SSE 协议的规定。

        参数:
            event_type: 事件类型（start/chunk/sources/end）
            data: 事件携带的数据字典

        返回:
            str: SSE 格式的字符串
        """
        import json
        # ensure_ascii=False 保证中文不被转义成 \uXXXX
        payload = json.dumps({"type": event_type, **data}, ensure_ascii=False)
        return f"data: {payload}\n\n"
