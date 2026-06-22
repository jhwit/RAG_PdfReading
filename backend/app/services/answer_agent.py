"""Answer quality agent — verifies and rewrites LLM answers for accuracy."""
from app.core.logger import setup_logger

logger = setup_logger("rag_kb.answer_agent")


class AnswerAgent:
    """A post-processing agent that reviews and improves LLM-generated answers.

    Two-stage pipeline:
      1. Relevance check — is the answer grounded in the provided context?
      2. Answer rewrite — if the answer is vague, empty, or circular, rewrite it
         into a meaningful, well-structured response based on the actual context.
    """

    def __init__(self, llm):
        self.llm = llm

    def rewrite_if_needed(self, question: str, context: str, raw_answer: str) -> dict:
        """Inspect the raw answer and rewrite if it's low quality.

        Returns {"answer": str, "rewritten": bool, "reason": str}
        """
        # ── Stage 1: Relevance check ──
        relevance = self._check_relevance(question, context, raw_answer)

        if relevance["is_good"]:
            logger.info("AnswerAgent: answer is acceptable, no rewrite needed")
            return {"answer": raw_answer, "rewritten": False, "reason": relevance["reason"]}

        # ── Stage 2: Rewrite ──
        logger.info(f"AnswerAgent: rewriting — {relevance['reason']}")
        rewritten = self._rewrite(question, context, raw_answer, relevance["reason"])
        return {"answer": rewritten, "rewritten": True, "reason": relevance["reason"]}

    def _check_relevance(self, question: str, context: str, answer: str) -> dict:
        """Determine if the answer is genuinely grounded in the context."""
        # Quick pattern-based checks (no LLM call)
        answer_clean = answer.strip()

        # Pattern 1: Empty or trivial
        if not answer_clean or len(answer_clean) < 10:
            return {"is_good": False, "reason": "answer_too_short"}

        # Pattern 2: Circular / self-referencing (e.g. "标准核心内容就是标准的核心内容")
        circular_patterns = [
            "根据提供的文档",
            "根据文档内容",
            "文档中未找到相关信息",
        ]
        has_context = any(p in answer_clean for p in circular_patterns)
        if has_context and len(answer_clean) < 100:
            return {"is_good": False, "reason": "vague_circular_answer"}

        # Pattern 3: Answer repeats the question verbatim without adding value
        if answer_clean == question or answer_clean in question:
            return {"is_good": False, "reason": "answer_echoes_question"}

        # Pattern 4: Answer mentions no document content when context is available
        if context and len(context) > 100:
            # Check if answer references any substantial content from context
            # Simple heuristic: answer should have at least some structural markers
            structural_markers = ['第', '条', '规定', '应', '不应', '严禁', '必须', '可', '。', '）', '：']
            has_structure = any(m in answer_clean for m in structural_markers)
            if not has_structure and len(answer_clean) < 80:
                return {"is_good": False, "reason": "answer_lacks_substance"}

        return {"is_good": True, "reason": "passes_checks"}

    def _rewrite(self, question: str, context: str, bad_answer: str, reason: str) -> str:
        """Use the LLM to rewrite a poor answer into a high-quality one."""
        rewrite_prompt = f"""你是一个专业的知识审核和改写助手。你需要将以下不理想的回答，改写成高质量、准确、有实质内容的回答。

## 原始用户问题
{question}

## 参考文档内容（必须基于此回答）
{context}

## 原始回答（需要改写）
{bad_answer}

## 改写原因
{reason}

## 改写要求：
1. 必须严格基于上面的参考文档内容回答，不要编造信息
2. 如果文档中有明确的规范条文，请引用条号（如"第6.4.1条"）和具体内容
3. 答案要结构清晰、准确、有实质内容
4. 如果文档确实没有直接覆盖问题，请诚实说明并给出最相关的内容
5. 使用专业、清晰的中文表达

请直接输出改写后的答案（不要包含"改写后的答案："等前缀）："""

        try:
            response = self.llm.complete(rewrite_prompt)
            text = response.text if hasattr(response, 'text') else str(response)
            return text.strip()
        except Exception as e:
            logger.warning(f"AnswerAgent rewrite failed: {e}, returning original")
            return bad_answer
