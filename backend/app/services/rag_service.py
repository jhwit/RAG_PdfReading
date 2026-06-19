"""RAG query pipeline service."""
import time
from typing import List, Optional, AsyncGenerator, Dict, Any
from llama_index.llms.openai import OpenAI

from app.core.config import Settings
from app.core.exceptions import EmptyQueryError, QueryTooLongError, NoRelevantDocsError, LLMUnavailableError
from app.core.logger import setup_logger

logger = setup_logger("rag_kb.rag")


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

        try:
            # Generate query embedding
            query_vector = await self._embed_query(question)

            # Search Qdrant
            results = await self.vector_store.search(
                vector=query_vector,
                top_k=top_k,
                filter_doc_ids=filter_doc_ids,
            )

            if not results:
                raise NoRelevantDocsError()

            # Build context from retrieved chunks
            context_parts = []
            sources = []
            for hit in results:
                payload = hit["payload"]
                context_parts.append(f"[来源: {payload.get('doc_name', '')}, 第{payload.get('page', '?')}页]\n{payload.get('content', '')}")
                sources.append({
                    "doc_id": payload.get("doc_id", ""),
                    "doc_name": payload.get("doc_name", ""),
                    "page": payload.get("page"),
                    "chunk_index": payload.get("chunk_index"),
                    "score": round(hit["score"], 4),
                })

            context = "\n\n---\n\n".join(context_parts)

            # Generate answer with LLM
            prompt = self._build_prompt(question, context)
            answer = await self._generate(prompt)

            query_time_ms = int((time.time() - start_time) * 1000)

            return {
                "answer": answer,
                "sources": sources,
                "query_time_ms": query_time_ms,
                "model": self.settings.llm_model,
            }

        except (EmptyQueryError, QueryTooLongError, NoRelevantDocsError):
            raise
        except Exception as e:
            logger.error(f"RAG query failed: {str(e)}")
            raise LLMUnavailableError(str(e))

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
            # Generate query embedding
            query_vector = await self._embed_query(question)

            # Search Qdrant
            results = await self.vector_store.search(
                vector=query_vector,
                top_k=top_k,
                filter_doc_ids=filter_doc_ids,
            )

            if not results:
                yield self._sse_event("error", {"message": "No relevant documents found"})
                yield self._sse_event("end", {"query_time_ms": int((time.time() - start_time) * 1000)})
                return

            # Build context
            context_parts = []
            sources = []
            for hit in results:
                payload = hit["payload"]
                context_parts.append(f"[来源: {payload.get('doc_name', '')}, 第{payload.get('page', '?')}页]\n{payload.get('content', '')}")
                sources.append({
                    "doc_id": payload.get("doc_id", ""),
                    "doc_name": payload.get("doc_name", ""),
                    "page": payload.get("page"),
                    "chunk_index": payload.get("chunk_index"),
                    "score": round(hit["score"], 4),
                })

            context = "\n\n---\n\n".join(context_parts)
            prompt = self._build_prompt(question, context)

            # Streaming LLM response
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
                # Simulate streaming by chunking the output
                chunk_size = 10
                for i in range(0, len(text), chunk_size):
                    yield self._sse_event("chunk", {"content": text[i:i + chunk_size]})

            # Send sources
            yield self._sse_event("sources", {"sources": sources})

            query_time_ms = int((time.time() - start_time) * 1000)
            yield self._sse_event("end", {"query_time_ms": query_time_ms})

        except Exception as e:
            logger.error(f"Streaming query failed: {str(e)}")
            yield self._sse_event("error", {"message": str(e)})
            yield self._sse_event("end", {"query_time_ms": int((time.time() - start_time) * 1000)})

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

    def _sse_event(self, event_type: str, data: dict) -> str:
        """Format a Server-Sent Event."""
        import json
        payload = json.dumps({"type": event_type, **data}, ensure_ascii=False)
        return f"data: {payload}\n\n"
