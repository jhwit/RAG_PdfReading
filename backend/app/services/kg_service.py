"""
知识图谱服务（Knowledge Graph Service）— LLM Prompt 版。

这个版本不依赖 LlamaIndex 的 KnowledgeGraphIndex，而是直接用 LLM（DeepSeek）
通过 Prompt 从每个文本块中提取三元组（Subject-Predicate-Object）。

为什么不用 LlamaIndex KG？
1. LlamaIndex 的 KG 组件内部会强制加载 OpenAI 嵌入模型，即使传了自定义模型也可能绕过
2. 模型白名单限制（Unknown model 报错）
3. 完全自主可控，Prompt 可以针对国家标准文档定制

存储格式（JSON）：
{
  "doc_id": "doc_xxx",
  "doc_name": "GB50016-2014.pdf",
  "triplets": [
    {"subject": "6.4.1", "predicate": "DEFINES", "object": "疏散楼梯间"},
    {"subject": "6.4.1", "predicate": "CONSTRAINS", "object": "应能天然采光"}
  ],
  "entities": ["疏散楼梯间", "天然采光", "自然通风"]
}

提取策略：
- 每个 chunk 调用一次 LLM（可并行）
- Prompt 专门针对国家标准文档设计，识别条款编号、概念、参数
- 结果校验：确保返回的是合法 JSON，过滤掉低质量三元组
"""
import os
import json
import asyncio
from pathlib import Path
from typing import List, Optional, Dict, Any

from app.core.config import Settings
from app.core.logger import setup_logger

logger = setup_logger("rag_kb.kg")

# 知识图谱提取 Prompt —— 针对国家标准文档定制
_KG_EXTRACTION_PROMPT = """你是一位专业的知识图谱构建专家，擅长从国家标准文档中提取结构化知识三元组。

任务：从以下规范条文中提取所有可识别的知识三元组（实体-关系-实体）。

## 提取规则（必须严格遵守）
1. **条款编号优先**：如果文本中有条款编号（如 "6.4.1"、"5.2.1"），优先作为 subject
2. **概念实体**：识别专业术语（如 "疏散楼梯间"、"耐火等级"、"防火分区"），可作为 subject 或 object
3. **参数数值**：识别具体数值要求（如 "不应小于30m"、"应为一级"、"不宜小于10m"），作为 object
4. **行为动作**：识别"应"、"不应"、"宜"、"不宜"、"可"等情态动词引导的约束，拆分为独立三元组
5. **关系类型（predicate）**从以下选择，如不符合可自定义简短英文词：
   - DEFINES：定义/解释某个概念
   - CONSTRAINS：约束/规定某个参数或行为（最常用）
   - REQUIRES：要求必须满足的条件
   - REFERENCES：引用/提及其他条款
   - APPLIES_TO：适用于某种建筑类型或场景
   - PROHIBITS：禁止某种行为
   - PERMITS：允许某种行为

## 输出要求（非常重要）
- **必须提取**：只要文本中有任何可识别的实体和关系，就必须提取，不要偷懒返回空数组
- 将长复合句拆分为多个简单三元组
- 必须返回严格的 JSON 数组格式
- 每个三元组必须包含明确的 subject、predicate、object 三个字段
- 不要添加任何解释、注释、markdown 代码块标记（如 ```json）
- 确保返回的是合法的 JSON，可以被 Python 的 json.loads 直接解析

## 正确示例（多种形式）

示例1 - 简单定义：
[
  {"subject": "6.4.1", "predicate": "DEFINES", "object": "疏散楼梯间"}
]

示例2 - 多条约束（一个条款有多条规定时拆分）：
[
  {"subject": "6.4.1", "predicate": "CONSTRAINS", "object": "应能天然采光和自然通风"},
  {"subject": "6.4.1", "predicate": "CONSTRAINS", "object": "宜靠外墙设置"},
  {"subject": "6.4.1", "predicate": "CONSTRAINS", "object": "在首层应采用乙级防火门与其他区域分隔"}
]

示例3 - 数值参数：
[
  {"subject": "5.1.2", "predicate": "CONSTRAINS", "object": "建筑高度不应大于24m"},
  {"subject": "5.1.2", "predicate": "CONSTRAINS", "object": "建筑层数不应大于6层"}
]

示例4 - 适用场景：
[
  {"subject": "6.2.1", "predicate": "APPLIES_TO", "object": "医疗建筑"},
  {"subject": "6.2.1", "predicate": "APPLIES_TO", "object": "老年人照料设施"}
]

示例5 - 引用关系：
[
  {"subject": "7.1.1", "predicate": "REFERENCES", "object": "应符合本规范第5.2节的规定"}
]

## 待处理文本（【】内为章节标题，是自动添加的上下文，请据此提取）：
{chunk_text}

请直接输出 JSON 数组，不要添加任何其他文字。如果文本确实没有任何可提取的内容，才返回 []："""


class KGService:
    """
    基于 LLM Prompt 的知识图谱服务。

    职责：
    1. 为每份文档构建知识三元组（上传 PDF 后异步执行）
    2. 查询知识图谱，获取与用户问题相关的实体和关系
    3. 将图谱查询结果与向量检索结果融合，提升回答质量
    """

    def __init__(self, settings: Settings, llm):
        """
        初始化 KG 服务。

        参数:
            settings: 应用配置
            llm: LlamaIndex 的 LLM 实例（用于提取三元组）
        """
        self.settings = settings
        self.llm = llm
        self._kg_dir = Path(settings.kg_dir)
        self._kg_dir.mkdir(parents=True, exist_ok=True)

    def _kg_path(self, doc_id: str) -> Path:
        """获取指定文档的知识图谱文件路径。"""
        return self._kg_dir / f"{doc_id}_kg.json"

    def has_kg(self, doc_id: str) -> bool:
        """检查指定文档是否已构建知识图谱。"""
        return self._kg_path(doc_id).exists()

    async def build_for_document(self, doc_id: str, doc_name: str, chunks: List[dict]):
        """
        为指定文档构建知识三元组。

        流程：
        1. 遍历所有 chunks
        2. 对每个 chunk 调用 LLM 提取三元组
        3. 收集所有三元组，去重，保存为 JSON

        注意：
        - 每个 chunk 调用一次 LLM，成本与 chunk 数量成正比
        - 调用是顺序的（避免并发过高导致 API 限流）
        - 失败会记录警告，但不阻断主流程

        参数:
            doc_id: 文档 ID
            doc_name: 文档原始文件名
            chunks: 该文档的所有文本块
        """
        if not self.settings.enable_kg:
            logger.info(f"知识图谱已禁用，跳过构建: {doc_id}")
            return

        logger.info(f"开始为文档 {doc_id} 提取知识三元组（共 {len(chunks)} 个 chunks）...")

        all_triplets = []
        all_entities = set()

        # 顺序处理每个 chunk（避免并发过高导致 API 限流）
        for i, chunk in enumerate(chunks):
            try:
                triplets = await self._extract_triplets(chunk["content"])
                if triplets:
                    all_triplets.extend(triplets)
                    # 收集所有实体（subject 和 object）
                    for t in triplets:
                        all_entities.add(t.get("subject", ""))
                        all_entities.add(t.get("object", ""))

                # 每处理 10 个 chunk 记录一次进度
                if (i + 1) % 10 == 0 or i == len(chunks) - 1:
                    logger.info(f"  已处理 {i + 1}/{len(chunks)} 个 chunks，提取 {len(all_triplets)} 个三元组")

            except Exception as e:
                import traceback
                logger.warning(f"  提取 chunk {i} 的三元组失败: {type(e).__name__}: {e}")
                logger.warning(f"  详细 traceback:\n{traceback.format_exc()}")
                continue

        # 去重：基于 (subject, predicate, object) 三元组去重
        seen = set()
        unique_triplets = []
        for t in all_triplets:
            key = (t.get("subject", ""), t.get("predicate", ""), t.get("object", ""))
            if key not in seen and all(key):
                seen.add(key)
                unique_triplets.append(t)

        # 过滤空实体
        unique_entities = [e for e in all_entities if e and len(e) >= 2]

        # 保存到 JSON
        kg_data = {
            "doc_id": doc_id,
            "doc_name": doc_name,
            "triplets": unique_triplets,
            "entities": unique_entities,
            "total_chunks": len(chunks),
            "total_triplets": len(unique_triplets),
        }

        try:
            kg_path = self._kg_path(doc_id)
            with open(kg_path, "w", encoding="utf-8") as f:
                json.dump(kg_data, f, ensure_ascii=False, indent=2)
            logger.info(
                f"知识三元组提取完成: {doc_id} → {kg_path} "
                f"({len(unique_triplets)} 个三元组, {len(unique_entities)} 个实体)"
            )
        except Exception as e:
            logger.error(f"保存知识图谱失败 {doc_id}: {e}")

    async def _extract_triplets(self, chunk_text: str) -> List[Dict[str, str]]:
        """
        调用 LLM 从单个 chunk 中提取三元组。

        参数:
            chunk_text: 文本块内容

        返回:
            List[dict]: 三元组列表，每个元素 {"subject": str, "predicate": str, "object": str}
        """
        # 重要：用 replace 而不是 format，因为 chunk_text 中可能包含 {...}
        # 如果用 format，str.format 会把 {} 内的内容当作占位符名，抛出 KeyError
        prompt = _KG_EXTRACTION_PROMPT.replace("{chunk_text}", chunk_text)

        # 优先使用异步方法，fallback 到线程池调用同步方法
        text = ""
        try:
            if hasattr(self.llm, 'acomplete'):
                response = await self.llm.acomplete(prompt)
            else:
                import fastapi.concurrency
                response = await fastapi.concurrency.run_in_threadpool(self.llm.complete, prompt)
            text = response.text if hasattr(response, 'text') else str(response)
        except Exception as e:
            logger.warning(f"LLM 调用失败: {e}")
            raise

        # 解析 LLM 返回的 JSON
        triplets = self._parse_triplets(text)

        # 诊断日志：如果未提取到三元组，记录 LLM 原始输出以便排查
        if not triplets:
            logger.info(f"  未提取到三元组，LLM 原始输出（前400字）: {text[:400]}")

        return triplets

    def _parse_triplets(self, text: str) -> List[Dict[str, str]]:
        """
        解析 LLM 返回的文本，提取 JSON 格式的三元组。

        LLM 输出可能包含 markdown 代码块（```json ... ```），需要清洗。
        本函数做了多层容错处理，以应对各种 LLM 输出格式。

        参数:
            text: LLM 原始输出

        返回:
            List[dict]: 解析后的三元组列表
        """
        if not text or not isinstance(text, str):
            logger.debug(f"LLM 返回空或非字符串内容: {type(text)}")
            return []

        text = text.strip()

        # 去掉 BOM
        if text.startswith('﻿'):
            text = text[1:]

        # 去掉 markdown 代码块标记
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        # 找到 JSON 数组或对象的开始和结束
        start = text.find("[")
        if start < 0:
            # 可能是单个对象（而非数组）
            start = text.find("{")
            if start >= 0:
                end = text.rfind("}")
                if end > start:
                    text = "[" + text[start:end + 1] + "]"
                else:
                    logger.debug(f"无法定位 JSON 对象结束，原始文本: {text[:200]}")
                    return []
            else:
                logger.debug(f"无法找到 JSON 开始标记，原始文本: {text[:200]}")
                return []
        else:
            end = text.rfind("]")
            if end > start:
                text = text[start:end + 1]
            else:
                logger.debug(f"无法定位 JSON 数组结束，原始文本: {text[:200]}")
                return []

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON 解析失败: {e}，原始文本: {text[:300]}")
            return []

        # 支持单个 dict 返回
        if isinstance(data, dict):
            data = [data]

        if not isinstance(data, list):
            logger.debug(f"解析后的数据不是列表: {type(data)}")
            return []

        valid = []
        for item in data:
            if not isinstance(item, dict):
                continue
            # 使用 .get() 安全取值，避免 KeyError
            subject = str(item.get("subject", "")).strip()
            predicate = str(item.get("predicate", "")).strip()
            obj = str(item.get("object", "")).strip()
            if subject and predicate and obj:
                valid.append({
                    "subject": subject,
                    "predicate": predicate,
                    "object": obj,
                })

        return valid

    def _load_kg_data(self, doc_id: str) -> Optional[Dict]:
        """
        加载指定文档的知识图谱数据。

        参数:
            doc_id: 文档 ID

        返回:
            dict: 图谱数据，如果不存在则返回 None
        """
        kg_path = self._kg_path(doc_id)
        if not kg_path.exists():
            return None

        try:
            with open(kg_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"加载知识图谱失败 {doc_id}: {e}")
            return None

    async def query(
        self,
        question: str,
        doc_ids: Optional[List[str]] = None,
    ) -> List[str]:
        """
        查询知识图谱，返回与问题相关的文本内容。

        查询策略（增强版）：
        1. 加载指定文档的图谱 JSON
        2. 用关键词匹配筛选相关三元组（核心匹配）
        3. 扩展关联实体：对匹配到的实体，查询其所有关系（1 跳扩展）
        4. 遍历引用链：对 REFERENCES 关系，加载被引用条款的相关内容
        5. 把扩展后的三元组格式化成自然语言文本

        参数:
            question: 用户问题
            doc_ids: 指定查询哪些文档（None = 全部）

        返回:
            List[str]: 从图谱中检索到的相关文本片段列表
        """
        if not self.settings.enable_kg:
            return []

        if doc_ids is None:
            doc_ids = [
                f.stem.replace("_kg", "")
                for f in self._kg_dir.glob("*_kg.json")
            ]

        if not doc_ids:
            return []

        # 收集所有相关三元组（核心匹配）
        matched_triplets = []

        for doc_id in doc_ids:
            kg_data = self._load_kg_data(doc_id)
            if not kg_data:
                continue

            triplets = kg_data.get("triplets", [])
            matched = self._keyword_match_triplets(question, triplets)
            if matched:
                matched_triplets.extend(matched)

        if not matched_triplets:
            return []

        # === 扩展 1：关联实体扩展（1 跳邻居）===
        # 从匹配的三元组中提取所有实体，查询它们的其他关系
        expanded_triplets = list(matched_triplets)
        seen_keys = set()
        for t in matched_triplets:
            seen_keys.add((t["subject"], t["predicate"], t["object"]))

        entities_to_expand = set()
        for t in matched_triplets:
            entities_to_expand.add(t["subject"])
            entities_to_expand.add(t["object"])

        for entity in entities_to_expand:
            related = await self.get_related_entities(entity, doc_ids)
            for r in related:
                key = (r["subject"], r["relation"], r["object"])
                if key not in seen_keys:
                    seen_keys.add(key)
                    expanded_triplets.append({
                        "subject": r["subject"],
                        "predicate": r["relation"],
                        "object": r["object"],
                    })

        # === 扩展 2：引用链遍历 ===
        # 找到 REFERENCES 关系，加载被引用实体的定义/约束
        reference_targets = set()
        for t in expanded_triplets:
            if t["predicate"] == "REFERENCES":
                # 从 object 中提取条款编号（如 "应符合本规范第5.2.1条规定" → "5.2.1"）
                import re
                refs = re.findall(r'\d+(?:\.\d+)*', t["object"])
                reference_targets.update(refs)

        if reference_targets:
            for doc_id in doc_ids:
                kg_data = self._load_kg_data(doc_id)
                if not kg_data:
                    continue
                for t in kg_data.get("triplets", []):
                    if t["subject"] in reference_targets:
                        key = (t["subject"], t["predicate"], t["object"])
                        if key not in seen_keys:
                            seen_keys.add(key)
                            expanded_triplets.append(t)

        # 格式化成自然语言
        result_texts = []
        for t in expanded_triplets[:20]:  # 最多取 20 个（扩展后可能更多）
            text = f"【知识图谱】{t['subject']} {self._predicate_cn(t['predicate'])} {t['object']}"
            result_texts.append(text)

        logger.info(
            f"知识图谱查询: 核心匹配 {len(matched_triplets)} 条，"
            f"扩展后 {len(expanded_triplets)} 条"
        )
        return result_texts

    def _keyword_match_triplets(
        self,
        question: str,
        triplets: List[Dict[str, str]],
    ) -> List[Dict[str, str]]:
        """
        基于关键词匹配筛选三元组。

        参数:
            question: 用户问题
            triplets: 所有三元组

        返回:
            List[dict]: 匹配到的三元组
        """
        import re

        # 提取关键词（中文词、英文词、数字编号）
        keywords = re.findall(r'[一-鿿]{2,10}|\d+(?:\.\d+)*|[a-zA-Z]{3,}', question)
        stopwords = {"什么", "哪些", "如何", "怎么", "请问", "根据", "关于", "的", "是", "有", "和", "或"}
        keywords = [k for k in keywords if k not in stopwords and len(k) >= 2]

        if not keywords:
            return []

        matched = []
        for t in triplets:
            text = f"{t['subject']} {t['predicate']} {t['object']}"
            score = sum(2 if kw in t['subject'] or kw in t['object'] else 1 for kw in keywords if kw in text)
            if score > 0:
                matched.append((score, t))

        # 按匹配分数排序
        matched.sort(key=lambda x: x[0], reverse=True)
        return [t for score, t in matched[:10]]  # 最多取 10 个

    def _predicate_cn(self, predicate: str) -> str:
        """把英文 predicate 转成中文，方便阅读。"""
        mapping = {
            "DEFINES": "定义了",
            "CONSTRAINS": "约束了",
            "REQUIRES": "要求",
            "REFERENCES": "引用了",
            "APPLIES_TO": "适用于",
            "PROHIBITS": "禁止",
            "PERMITS": "允许",
            "HAS_PROPERTY": "具有属性",
            "RELATED_TO": "关联",
            "SPECIFIES": "规定了",
        }
        return mapping.get(predicate, predicate)

    async def get_related_entities(
        self,
        entity_name: str,
        doc_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        获取与指定实体相关的所有关系。

        参数:
            entity_name: 实体名称
            doc_ids: 指定文档（None = 全部）

        返回:
            List[dict]: 关系列表
        """
        if not self.settings.enable_kg:
            return []

        if doc_ids is None:
            doc_ids = [
                f.stem.replace("_kg", "")
                for f in self._kg_dir.glob("*_kg.json")
            ]

        all_relations = []

        for doc_id in doc_ids:
            kg_data = self._load_kg_data(doc_id)
            if not kg_data:
                continue

            for t in kg_data.get("triplets", []):
                if entity_name in t.get("subject", "") or entity_name in t.get("object", ""):
                    all_relations.append({
                        "subject": t["subject"],
                        "relation": t["predicate"],
                        "object": t["object"],
                        "doc_id": doc_id,
                    })

        return all_relations
