"""
文本分块工具。

为什么需要分块？
想象你有一本 500 页的国家标准 PDF，全文可能有 30 万字。
AI 模型（LLM）一次能处理的文字是有限的（几千到几万字）。
如果直接把 30 万字塞给 AI，它要么拒绝处理，要么只读前面一部分就"遗忘"了后面的内容。

解决方案：把长文档切成小段（chunk），每段 512 字左右。
用户提问时，只找出和问题最相关的几个小段发给 AI，这样既准确又节省成本。

什么是重叠（overlap）？
如果我们在第 500 个字处一刀切，可能把一个完整的句子切成两半：
    "第 6.4.1 条规定，建" | "筑物高度不得超过..."
这会导致 AI 读不懂。所以相邻块之间要重叠 50 个字符，确保上下文连贯。

什么是上下文增强（Contextual Chunking）？
当你检索到一个 chunk 时，它可能只是一句"不应小于 30m"——
你不知道"什么"不应小于 30m，因为它所在的章节标题被切到另一个块里了。
上下文增强就是在每个 chunk 前面加上它的章节标题，让 chunk "自包含"：
    原始: "不应小于 30m"
    增强后: "【6.4.1 疏散楼梯间】不应小于 30m"
这样即使只检索到这个块，AI 也能理解它在说什么。

切分策略（分层语义切分 + 标题感知）：
1. 预处理：扫描所有段落，识别章节标题（如"6.4.1 疏散楼梯间"），构建标题层级栈
2. 标题段落优先开启新 chunk，确保一个 chunk 不跨越多个条款
3. 普通段落按 chunk_size 合并，尽量保持段落完整
4. 段落过大时，按语义边界切分（句子 > 子句 > 词 > 硬切）
5. 每个 chunk 自动带上所属标题路径前缀
"""
import re
from typing import List
from app.core.config import Settings


class TextSplitter:
    """
    文本切分器。

    职责：接收一大段文字，按语义边界切成小段，并给每块打上元数据标签
          （来自哪份文档、第几页、第几个块）。

    核心改进：标题感知分块 — 自动识别所有章节标题，维护标题层级栈，
              确保标题和内容不被分割，且每个 chunk 都"自包含"语义。
    """

    # 标题检测正则表达式
    # 匹配模式 1: 第X章 XXX  (第一章 总则)
    # 匹配模式 2: 数字编号+中文  (6.4.1 疏散楼梯间, 5.2 防火分区)
    # 匹配模式 3: (X) XXX  ((一) 总则)
    # 匹配模式 4: 附录X XXX  (附录A 耐火等级)
    _TITLE_RE = re.compile(
        r'^(?:'
        r'第[一二三四五六七八九十\d]+章\s+.+?'  # 第一章 总则
        r'|'
        r'\d+(?:\.\d+)*\s+[^\n]{2,40}'  # 6.4.1 疏散楼梯间（标题一般不长）
        r'|'
        r'[（\(][一二三四五六七八九十\d]+[）\)]\s+[^\n]{2,40}'  # (一) 总则
        r'|'
        r'附录[一二三四五六七八九十\dA-Z]\s+[^\n]{2,40}'  # 附录A 耐火等级
        r')$',
        re.MULTILINE
    )

    def __init__(self, settings: Settings):
        """
        初始化切分器。

        参数:
            settings: 应用配置对象，包含 chunk_size、chunk_overlap、chunk_separator
        """
        self.chunk_size = settings.chunk_size          # 每块最大字符数，如 512
        self.chunk_overlap = settings.chunk_overlap    # 相邻块重叠字符数，如 50
        self.separator = settings.chunk_separator      # 优先切分符，如 "\n\n"

    def split(
        self,
        text: str,
        doc_id: str,
        doc_name: str,
        page: int = 1,
        start_index: int = 0,
    ) -> List[dict]:
        """
        将文本切成带元数据的片段。

        执行流程：
        1. 按 separator（双换行）把文本分成段落
        2. 遍历段落，识别所有章节标题，维护标题层级栈
        3. 标题段落优先开启新 chunk（避免标题和内容分离）
        4. 普通段落尝试合并到当前块（尽量保持段落完整）
        5. 如果加入后超过 chunk_size，就把当前块封存，开一个新块
        6. 如果某个段落本身超长，调用 _split_by_semantics 按语义边界切分
        7. 处理最后一段（循环结束后可能还有未封存的 current_chunk）
        8. 给所有 chunk 附加章节标题路径前缀（上下文增强）

        关于 chunk_index（块序号）：
        在 DocumentService 中，PDF 被分成多个 block，每个 block 分别调用 split()。
        传 start_index 可以实现全局递增编号，避免整份文档里大量重复 0、1。

        参数:
            text: 从 PDF 提取出的原始文本
            doc_id: 文档唯一 ID
            doc_name: 原始文件名
            page: 这段文字来自第几页（从 1 开始）
            start_index: 起始块序号（用于跨 block 全局递增）

        返回:
            List[dict]: 每个元素是一个块，包含 content、doc_id、doc_name、page、chunk_index
        """
        if not text.strip():
            return []

        # === 第一步：按分隔符拆成段落 ===
        raw_paragraphs = [p.strip() for p in text.split(self.separator) if p.strip()]

        # === 第二步：预处理 — 识别标题，维护标题栈 ===
        paragraphs = []
        title_stack = []  # [(level, title_text), ...]

        for para in raw_paragraphs:
            title = self._is_title(para)
            if title:
                level = self._get_title_level(title)
                # 弹出同级或更高级的标题（新标题取代旧标题）
                while title_stack and title_stack[-1][0] >= level:
                    title_stack.pop()
                title_stack.append((level, title))
                paragraphs.append({
                    "text": para,
                    "is_title": True,
                    "title_stack": [t for _, t in title_stack],
                })
            else:
                paragraphs.append({
                    "text": para,
                    "is_title": False,
                    "title_stack": [t for _, t in title_stack],
                })

        # === 第三步：按 chunk_size 合并段落 ===
        chunks = []
        current_texts = []
        current_titles = []
        current_len = 0
        chunk_index = start_index

        def _finalize_current_chunk():
            """将 current_texts 封存为 chunk，并计算 overlap 作为下一 chunk 起始。"""
            nonlocal chunk_index
            if not current_texts:
                return ""
            chunk_text = self.separator.join(current_texts)
            chunks.append(self._make_enhanced_chunk(
                chunk_text, current_titles, doc_id, doc_name, page, chunk_index
            ))
            chunk_index += 1
            # 提取末尾 overlap，作为下一 chunk 的起始上下文
            return self._extract_overlap(current_texts)

        for i, para in enumerate(paragraphs):
            para_text = para["text"]
            para_len = len(para_text)

            # 标题段落优先开启新 chunk（避免一个 chunk 跨越多个条款）
            if para.get("is_title") and current_texts:
                overlap = _finalize_current_chunk()
                current_texts = [overlap] if overlap else []
                current_len = len(current_texts[0]) if current_texts else 0
                # current_titles 保持不变（overlap 仍属上一标题上下文）

            # 如果当前 chunk 为空，直接加入
            if not current_texts:
                current_texts.append(para_text)
                current_titles = para["title_stack"]
                current_len = para_len
                continue

            # 尝试把段落加入当前块
            sep_len = len(self.separator)
            if current_len + sep_len + para_len <= self.chunk_size:
                current_texts.append(para_text)
                if para["title_stack"]:
                    current_titles = para["title_stack"]
                current_len += sep_len + para_len
            else:
                # 当前块满了，先封存并提取 overlap
                overlap = _finalize_current_chunk()

                # 处理超长段落（_split_by_semantics 内部自带 overlap）
                if para_len > self.chunk_size:
                    # 先把 overlap 单独存为一个 chunk（如果有）
                    if overlap:
                        chunks.append(self._make_enhanced_chunk(
                            overlap, current_titles, doc_id, doc_name, page, chunk_index
                        ))
                        chunk_index += 1
                    sub_chunks = self._split_by_semantics(para_text)
                    for sc in sub_chunks:
                        chunks.append(self._make_enhanced_chunk(
                            sc, para["title_stack"], doc_id, doc_name, page, chunk_index
                        ))
                        chunk_index += 1
                    current_texts = []
                    current_len = 0
                else:
                    # 新 chunk 以 overlap 开头，然后接当前段落
                    if overlap:
                        current_texts = [overlap, para_text]
                        current_len = len(overlap) + sep_len + para_len
                        # current_titles 保持上一 chunk 的标题；若当前段落有标题则更新
                        if para["title_stack"]:
                            current_titles = para["title_stack"]
                    else:
                        current_texts = [para_text]
                        current_titles = para["title_stack"]
                        current_len = para_len

        # === 第四步：处理剩余内容 ===
        if current_texts:
            chunk_text = self.separator.join(current_texts)
            chunks.append(self._make_enhanced_chunk(
                chunk_text, current_titles, doc_id, doc_name, page, chunk_index
            ))

        return chunks

    def _is_title(self, text: str) -> str:
        """
        判断一段文本是否是章节标题。

        国家标准文档的标题通常：
        - 独占一行（段落本身不长）
        - 以编号或"第X章"开头
        - 不以句号、逗号等标点结尾

        参数:
            text: 段落文本

        返回:
            str: 如果是标题，返回清洗后的标题文本；否则返回空字符串
        """
        text = text.strip()
        if not text or len(text) > 60:
            return ""

        # 不以常见标点结尾（正文句子通常以。！？.!?；;结尾）
        if text[-1] in "。！？.!?；;," or text[-1] in "，、：":
            return ""

        match = self._TITLE_RE.match(text)
        if match:
            return match.group(0).strip()
        return ""

    def _get_title_level(self, title: str) -> int:
        """
        计算标题的层级，用于维护标题栈。

        层级规则：
        - 第X章 / 附录X → level 1
        - X（一位数字） → level 2
        - X.X → level 3
        - X.X.X → level 4
        - 以此类推

        参数:
            title: 标题文本

        返回:
            int: 层级数字（1 表示最高级）
        """
        title = title.strip()
        # 第X章 或 附录X → level 1
        if re.match(r'^第[一二三四五六七八九十\d]+章', title) or \
           re.match(r'^附录[一二三四五六七八九十\dA-Z]', title):
            return 1

        # 提取开头的数字编号
        num_match = re.match(r'^(\d+(?:\.\d+)*)', title)
        if num_match:
            parts = num_match.group(1).split('.')
            return len(parts) + 1  # X→2, X.X→3, X.X.X→4

        # (一) 形式的标题
        if re.match(r'^[（\(][一二三四五六七八九十\d]+[）\)]', title):
            return 3  # 视为三级标题

        return 2  # 默认 level 2

    def _split_by_semantics(self, text: str) -> List[str]:
        """
        按语义边界切分超长段落（分层策略）。

        切分优先级（从优到劣）：
        1. 句子边界（。！？. ! ? ；;）— 最优先，保持句子完整
        2. 子句边界（，, 、：:）— 次优先，保持短语完整
        3. 词边界（空格）— 再次，至少不切单词
        4. 硬切（字符级）— 最后手段

        参数:
            text: 超长段落文本（长度 > chunk_size）

        返回:
            List[str]: 切分后的字符串列表
        """
        if len(text) <= self.chunk_size:
            return [text]

        result = []
        start = 0
        text_len = len(text)

        while start < text_len:
            end = min(start + self.chunk_size, text_len)

            if end < text_len:
                end = self._find_best_split_point(text, start, end)

            result.append(text[start:end].strip())

            if end < text_len:
                start = max(start + 1, end - self.chunk_overlap)
            else:
                start = end

        return result

    def _find_best_split_point(self, text: str, start: int, end: int) -> int:
        """
        在 [start, end] 范围内寻找最佳语义切分点。

        搜索策略：
        1. 定义搜索范围：不能切得太早（至少保留 chunk_size 的 50%）
        2. 按优先级从高到低尝试不同类型的分隔符
        3. 返回找到的切分位置（字符索引，指向分隔符之后）

        参数:
            text: 原始文本
            start: 当前窗口起始位置
            end: 当前窗口理想结束位置（chunk_size 处）

        返回:
            int: 实际切分位置
        """
        search_start = max(start + self.chunk_size // 2, start + 20)

        # === 第一层：句子边界 ===
        sentence_seps = [
            "。", "．", ". ", ".\n", "！", "! ", "？", "? ", "；", "; ", ";\n", "\n",
        ]
        for sep in sentence_seps:
            pos = text.rfind(sep, search_start, end + 1)
            if pos >= 0:
                return pos + len(sep)

        # === 第二层：子句边界 ===
        clause_seps = [
            "，", ", ", ",\n", "、", "：", ": ", ":\n",
        ]
        for sep in clause_seps:
            pos = text.rfind(sep, search_start, end + 1)
            if pos >= 0:
                return pos + len(sep)

        # === 第三层：词边界（空格）===
        pos = text.rfind(" ", search_start, end + 1)
        if pos >= 0:
            return pos + 1

        # === 第四层：硬切（兜底）===
        return end

    def _extract_overlap(self, texts: List[str]) -> str:
        """
        从上一 chunk 的段落列表中提取末尾 overlap 文本。

        策略：直接硬切最后 chunk_overlap 个字符。不需要在句子边界截断，
        因为 overlap 只是给相邻 chunk 提供共享上下文，即使切在词中间也可以接受。

        参数:
            texts: 上一 chunk 的段落列表

        返回:
            str: overlap 文本（可能为空）
        """
        if not texts or self.chunk_overlap <= 0:
            return ""

        full_text = self.separator.join(texts)
        if len(full_text) <= self.chunk_overlap:
            return full_text

        # 直接硬切最后 chunk_overlap 个字符
        return full_text[-self.chunk_overlap:]

    def _make_enhanced_chunk(
        self,
        text: str,
        title_stack: List[str],
        doc_id: str,
        doc_name: str,
        page: int,
        index: int,
    ) -> dict:
        """
        把一个文本字符串包装成带元数据的字典，并附加标题上下文前缀。

        去重策略：如果正文已经以最后一个标题开头，则不再重复添加该标题。

        参数:
            text: 块的内容
            title_stack: 标题层级栈，如 ["6.4 疏散楼梯间和楼梯", "6.4.1 疏散楼梯间"]
            doc_id: 文档 ID
            doc_name: 文档名称
            page: 页码
            index: 块在文档中的全局序号

        返回:
            dict: 标准化的块数据结构
        """
        content = text.strip()
        prefix = ""

        if title_stack:
            last_title = title_stack[-1]
            # 如果正文已经以最后一个标题开头，避免重复
            # 同时处理正文以 "【标题】" 开头的情况（已被增强过的子块）
            if content.startswith(last_title) or content.startswith(f"【{last_title}】"):
                # 只保留上级标题作为前缀
                if len(title_stack) > 1:
                    prefix = "【" + " > ".join(title_stack[:-1]) + "】"
            else:
                prefix = "【" + " > ".join(title_stack) + "】"

        if prefix:
            content = prefix + content

        return {
            "content": content,
            "doc_id": doc_id,
            "doc_name": doc_name,
            "page": page,
            "chunk_index": index,
            "section_title": title_stack[-1] if title_stack else "",
            "title_stack": title_stack,
        }
