"""RAG query pipeline service."""
import time
from typing import List, Optional, AsyncGenerator, Dict, Any
from llama_index.llms.openai import OpenAI

from app.core.config import Settings
from app.core.exceptions import EmptyQueryError, QueryTooLongError, NoRelevantDocsError, LLMUnavailableError
from app.core.logger import setup_logger

logger = setup_logger("rag_kb.rag")


def _patch_llama_index_models(model_name: str):
    """Register a custom model so llama_index's OpenAI wrapper accepts it.

    llama_index validates model names against hardcoded lists; third-party
    OpenAI-compatible endpoints (DeepSeek, etc.) are not in those lists.
    This patches the model registry at import time to allow arbitrary models.
    """
    try:
        from llama_index.llms.openai import utils as openai_utils

        if model_name not in openai_utils.ALL_AVAILABLE_MODELS:
            openai_utils.ALL_AVAILABLE_MODELS[model_name] = 128_000
        if model_name not in openai_utils.CHAT_MODELS:
            openai_utils.CHAT_MODELS[model_name] = True
        logger.debug(f"Registered custom model: {model_name}")
    except Exception:
        pass  # best-effort; if this fails the LLM call will fail with a clear error


class RAGService:
    """Orchestrates the RAG pipeline: retrieve -> synthesize -> answer."""

    def __init__(
        self,
        settings: Settings,
        embedding_service,
        vector_store,
    ):
        self.settings = settings
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self._llm = None
        # Answer quality agent (loaded lazily)
        self._answer_agent = None
        # Register custom model if using a third-party endpoint
        if settings.openai_base_url:
            _patch_llama_index_models(settings.llm_model)

    @property
    def answer_agent(self):
        """Lazy-load the AnswerAgent."""
        if self._answer_agent is None:
            from app.services.answer_agent import AnswerAgent
            self._answer_agent = AnswerAgent(self.llm)
        return self._answer_agent

    @property
    def llm(self):
        """Lazy-load the LLM."""
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
        """Execute a RAG query and return answer with sources."""
        top_k = self._validate_query(question, top_k)

        start_time = time.time()
        sources = []
        context = ""

        try:
            # Step 1: Generate query embedding
            try:
                query_vector = await self._embed_query(question)
            except Exception as e:
                logger.error(f"Embedding failed: {e}")
                return self._fallback_answer(
                    "嵌入模型暂时不可用，请稍后重试。",
                    int((time.time() - start_time) * 1000),
                )

            # Step 2: Search Qdrant (skip if unavailable)
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
                    logger.warning(f"Qdrant search failed (continuing without context): {e}")
            else:
                logger.warning("Qdrant unavailable — answering without document context")

            if not context:
                # No documents indexed yet
                return self._fallback_answer(
                    "知识库中没有相关文档。请先上传国家标准 PDF 文件。",
                    int((time.time() - start_time) * 1000),
                )

            # Step 3: Generate answer with LLM
            prompt = self._build_prompt(question, context)
            raw_answer = await self._generate(prompt)

            # Step 4: Post-process with AnswerAgent for quality
            if context:
                reviewed = self.answer_agent.rewrite_if_needed(question, context, raw_answer)
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
            raise
        except Exception as e:
            logger.error(f"RAG query failed: {str(e)}")
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
        """Execute a RAG query with streaming SSE response."""
        top_k = self._validate_query(question, top_k)

        start_time = time.time()

        yield self._sse_event("start", {"query_time_ms": 0})

        try:
            # Step 1: Generate query embedding
            try:
                query_vector = await self._embed_query(question)
            except Exception as e:
                logger.error(f"Embedding failed: {e}")
                yield self._sse_event("chunk", {"content": "嵌入模型暂时不可用，请稍后重试。"})
                yield self._sse_event("sources", {"sources": []})
                yield self._sse_event("end", {"query_time_ms": int((time.time() - start_time) * 1000)})
                return

            # Step 2: Search Qdrant (skip if unavailable)
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
                    logger.warning(f"Qdrant search failed: {e}")

            if not context:
                yield self._sse_event("chunk", {"content": "知识库中没有相关文档。请先上传国家标准 PDF 文件。"})
                yield self._sse_event("sources", {"sources": []})
                yield self._sse_event("end", {"query_time_ms": int((time.time() - start_time) * 1000)})
                return

            # Step 3: Generate streaming LLM answer
            prompt = self._build_prompt(question, context)

            try:
                response = self.llm.stream_complete(prompt)
                for chunk in response:
                    content = chunk.delta if hasattr(chunk, 'delta') else str(chunk)
                    if content:
                        yield self._sse_event("chunk", {"content": content})
            except AttributeError:
                # Fallback: non-streaming LLM
                answer = self.llm.complete(prompt)
                text = answer.text if hasattr(answer, 'text') else str(answer)
                chunk_size = 10
                for i in range(0, len(text), chunk_size):
                    yield self._sse_event("chunk", {"content": text[i:i + chunk_size]})
            except Exception as e:
                logger.error(f"LLM generation failed: {e}")
                yield self._sse_event("chunk", {"content": f"抱歉，AI 回答生成失败：{str(e)}"})

            # Send sources
            yield self._sse_event("sources", {"sources": sources})

            query_time_ms = int((time.time() - start_time) * 1000)
            yield self._sse_event("end", {"query_time_ms": query_time_ms})

        except Exception as e:
            logger.error(f"Streaming query failed: {str(e)}")
            yield self._sse_event("chunk", {"content": f"抱歉，问答服务暂时不可用：{str(e)}"})
            yield self._sse_event("end", {"query_time_ms": int((time.time() - start_time) * 1000)})

    def _build_context_and_sources(self, results: List[dict]) -> tuple:
        """Build context string and source list from search results."""
        context_parts = []
        sources = []
        for hit in results:
            payload = hit["payload"]
            full_content = payload.get('content', '')
            context_parts.append(
                f"[来源: {payload.get('doc_name', '')}, 第{payload.get('page', '?')}页]\n"
                f"{full_content}"
            )
            # Include a readable excerpt (first 200 chars) for frontend display
            excerpt = full_content[:200].replace('\n', ' ').strip()
            if len(full_content) > 200:
                excerpt += '...'
            sources.append({
                "doc_id": payload.get("doc_id", ""),
                "doc_name": payload.get("doc_name", ""),
                "page": payload.get("page"),
                "chunk_index": payload.get("chunk_index"),
                "score": round(hit["score"], 4),
                "excerpt": excerpt,
            })
        return "\n\n---\n\n".join(context_parts), sources
        return "\n\n---\n\n".join(context_parts), sources

    def _validate_query(self, question: str, top_k: int) -> int:
        """Validate query parameters and return clamped top_k."""
        if not question or not question.strip():
            raise EmptyQueryError()
        if len(question) > 2000:
            raise QueryTooLongError()
        return min(max(top_k, 1), self.settings.max_top_k)

    async def _embed_query(self, text: str) -> List[float]:
        """Generate embedding for a query."""
        from fastapi.concurrency import run_in_threadpool
        return await run_in_threadpool(self.embedding_service.embed_query, text)

    async def _generate(self, prompt: str) -> str:
        """Generate an answer from the LLM."""
        from fastapi.concurrency import run_in_threadpool

        def _sync_generate():
            response = self.llm.complete(prompt)
            return response.text if hasattr(response, 'text') else str(response)

        return await run_in_threadpool(_sync_generate)

    def _build_prompt(self, question: str, context: str) -> str:
        """Build the RAG prompt."""
        return f"""你是一个专业的知识库问答助手，基于提供的国家标准文档内容回答问题。

请遵循以下规则：
1. 仅根据以下文档内容回答问题，不要使用你的先验知识
2. 如果文档中没有相关信息，请明确说明"根据提供的文档，未找到相关信息"
3. 引用具体规范条文时，注明来源
4. 答案要准确、简洁、结构化

文档内容：
{context}

用户问题：{question}

请回答："""

    def _fallback_answer(self, message: str, query_time_ms: int) -> dict:
        """Return a graceful fallback answer when services are unavailable."""
        return {
            "answer": message,
            "sources": [],
            "query_time_ms": query_time_ms,
            "model": "fallback",
        }

    def _sse_event(self, event_type: str, data: dict) -> str:
        """Format a Server-Sent Event."""
        import json
        payload = json.dumps({"type": event_type, **data}, ensure_ascii=False)
        return f"data: {payload}\n\n"
