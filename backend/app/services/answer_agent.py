"""
回答质量审核代理（AnswerAgent）。

为什么需要这个模块？
大语言模型（LLM）虽然强大，但有时会产生以下问题：
1. "幻觉"：明明资料里没有，它却编了一个答案
2. "空泛回答"：只说"根据文档，相关规定如下"，但不说具体内容
3. "循环废话"：如"标准的核心内容就是标准的核心内容"
4. "答非所问"：用户问 A，它回答 B

AnswerAgent 的角色就像"审稿人"：
- LLM 写完了初稿（raw_answer）
- AnswerAgent 审稿，检查质量
- 如果不合格，打回去重写（基于原始资料重新生成）
- 如果合格，直接放行

这样一层后处理，能显著提升用户体验。

实现策略：
因为每次调用 LLM 都要花钱/耗时，AnswerAgent 先用"规则检查"（不调用 LLM）
快速筛选出明显低质量的回答。只有规则检查不通过时，才调用 LLM 重写。
这样既省钱又快。
"""
from app.core.logger import setup_logger

logger = setup_logger("rag_kb.answer_agent")


class AnswerAgent:
    """
    后处理代理，负责审核和改进 LLM 生成的回答。

    两阶段流水线：
      1. 相关性检查（规则-based，零成本）
         → 判断回答是否基于上下文、是否有实质内容
      2. 回答重写（LLM-based，有成本）
         → 只有阶段 1 不通过时才执行，用 LLM 基于上下文重新生成高质量回答

    属性:
        llm: 大语言模型实例，用于重写回答
    """

    def __init__(self, llm):
        """
        初始化审核代理。

        参数:
            llm: 已通过懒加载初始化的 OpenAI/LlamaIndex LLM 实例
        """
        self.llm = llm

    def rewrite_if_needed(self, question: str, context: str, raw_answer: str) -> dict:
        """
        检查原始回答，若质量低则重写。

        执行流程：
        1. 调用 _check_relevance 进行规则检查
        2. 如果通过，直接返回原回答，标记 rewritten=False
        3. 如果不通过，调用 _rewrite 生成新回答，标记 rewritten=True，并记录原因

        参数:
            question: 用户的原始问题
            context: 检索到的参考资料（用于判断回答是否基于资料）
            raw_answer: LLM 生成的初稿

        返回:
            dict: {
                "answer": str,       # 最终回答（可能是原稿，也可能是重写后的）
                "rewritten": bool,   # 是否经过重写
                "reason": str        # 审核结论/重写原因
            }
        """
        # ── 阶段 1：相关性检查 ──
        relevance = self._check_relevance(question, context, raw_answer)

        if relevance["is_good"]:
            logger.info("AnswerAgent: 回答质量合格，无需重写")
            return {"answer": raw_answer, "rewritten": False, "reason": relevance["reason"]}

        # ── 阶段 2：重写 ──
        logger.info(f"AnswerAgent: 质量不达标，原因: {relevance['reason']}，正在重写...")
        rewritten = self._rewrite(question, context, raw_answer, relevance["reason"])
        return {"answer": rewritten, "rewritten": True, "reason": relevance["reason"]}

    def _check_relevance(self, question: str, context: str, answer: str) -> dict:
        """
        判断回答是否真正基于上下文（规则检查，不调用 LLM）。

        检查规则（按优先级排序）：
        1. 空或极短：回答长度小于 10 字符，认为是无效回答
        2. 循环/自指：包含"根据提供的文档"等套话且总长度小于 100，认为是敷衍
        3. 回声问题：回答只是把问题重复了一遍，没有增加新信息
        4. 缺乏实质：上下文很长但回答没有任何结构性标记（如"第 X 条"、"应"、"不应"），
           且长度小于 80，认为是在糊弄

        参数:
            question: 用户问题
            context: 参考资料（用于判断回答是否引用了文档内容）
            answer: LLM 生成的回答

        返回:
            dict: {"is_good": bool, "reason": str}
        """
        answer_clean = answer.strip()

        # 规则 1：为空或过于简短（如只回复了一个字"是"）
        if not answer_clean or len(answer_clean) < 10:
            return {"is_good": False, "reason": "answer_too_short"}

        # 规则 2：循环 / 自指（套话 + 极短内容）
        # 例子："根据提供的文档，相关内容如下"（然后没了）
        # 注意：放宽阈值到 30 字符，避免误杀正常回答
        circular_patterns = [
            "根据提供的文档，未找到相关信息",
            "文档中未找到相关信息",
            "根据文档内容，未找到",
        ]
        has_context = any(p in answer_clean for p in circular_patterns)
        if has_context and len(answer_clean) < 30:
            return {"is_good": False, "reason": "vague_circular_answer"}

        # 规则 3：回答重复了问题（用户问"什么是消防通道"，AI 回答"消防通道是..."这不算，
        # 但如果 AI 回答"什么是消防通道？"就完全是回声）
        if answer_clean == question or answer_clean in question:
            return {"is_good": False, "reason": "answer_echoes_question"}

        # 规则 4：上下文可用但回答未引用任何实质性内容
        # 启发式：国家标准文档通常包含"第 X 条"、"应"、"严禁"、"必须"等词
        # 如果回答里一个都没有，且还很短，大概率是空洞回答
        if context and len(context) > 100:
            structural_markers = ['第', '条', '规定', '应', '不应', '严禁', '必须', '可', '。', '）', '：']
            has_structure = any(m in answer_clean for m in structural_markers)
            if not has_structure and len(answer_clean) < 80:
                return {"is_good": False, "reason": "answer_lacks_substance"}

        # 所有检查都通过
        return {"is_good": True, "reason": "passes_checks"}

    def _rewrite(self, question: str, context: str, bad_answer: str, reason: str) -> str:
        """
        使用 LLM 将低质量回答重写为高质量回答。

        重写策略：
        不是简单地告诉 LLM "写得更好点"，而是给它完整的上下文、原回答、失败原因，
        让它明确知道"为什么不合格"和"应该怎样改"。

        Prompt 设计要点：
        1. 明确角色（专业审核和改写助手）
        2. 给出原始问题（知道用户想要什么）
        3. 给出参考资料（必须基于这些回答，不能编造）
        4. 给出原回答（知道哪里写得不好）
        5. 给出失败原因（针对性改进）
        6. 给出明确的改写要求（结构化、引用条文、诚实说明）

        参数:
            question: 用户问题
            context: 参考资料
            bad_answer: 原低质量回答
            reason: 失败原因（如 "answer_too_short"）

        返回:
            str: 重写后的回答文本
        """
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
            # 如果重写过程中 LLM 也出错了，不要让整个查询失败，
            # 而是退而求其次，返回原始的低质量回答（至少用户能看到点东西）
            logger.warning(f"AnswerAgent 重写失败: {e}，返回原始回答")
            return bad_answer
