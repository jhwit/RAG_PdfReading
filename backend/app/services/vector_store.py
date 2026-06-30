"""
Qdrant 向量存储封装。

什么是向量数据库？
传统数据库（如 MySQL）按"精确匹配"查询：WHERE name = '张三'
向量数据库按"语义相似度"查询：找出和"北京天气"意思最接近的 5 段文字。

Qdrant 的核心概念：
- Collection（集合）= 关系型数据库的"表"，存放同一类向量
- Point（点）= 表里的"一行"，包含 ID、向量、Payload（附加数据）
- 距离度量：COSINE（余弦相似度），衡量两个向量方向的接近程度

为什么选 Qdrant？
1. 开源免费，支持本地部署
2. 有 Python 异步客户端（AsyncQdrantClient），和 FastAPI 配合好
3. 支持过滤（filter）：可以在语义搜索的同时加条件，如"只查 doc_id = xxx 的文档"
4. 支持 HNSW 索引，亿级向量也能毫秒级搜索

HNSW 是什么？
全称 Hierarchical Navigable Small World，是一种近似最近邻（ANN）算法。
通俗理解：它给向量建了一张"高速公路网"，搜索时不需要和全量向量比较，
只走高速公路就能快速找到最相似的几个，牺牲一点点精度换取极大速度提升。
"""
import time
import asyncio
from typing import List, Optional
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue, MatchAny, Range,
)
from app.core.config import Settings
from app.core.exceptions import VectorStoreError
from app.core.logger import setup_logger

logger = setup_logger("rag_kb.vector_store")

# 重连冷却时间：每次重试间隔至少 30 秒，防止疯狂重连拖垮服务器
RECONNECT_COOLDOWN_S = 30


class VectorStore:
    """
    Qdrant 向量数据库的异步封装。

    设计目标：
    1. 弹性连接：启动时 Qdrant 可能还没启动，不要因此崩溃
    2. 自动重连：一旦 Qdrant 恢复，下次操作时自动重连
    3. 透明降级：Qdrant 不可用时，其他功能（如查看元数据）仍能工作

    核心属性：
        _client: AsyncQdrantClient 实例（连接对象）
        _connected: 当前是否处于已连接状态
        _last_reconnect_attempt: 上次尝试重连的时间戳，用于控制重试频率
    """

    def __init__(self, settings: Settings):
        """
        初始化（不立即连接）。

        参数:
            settings: 包含 Qdrant 主机、端口、集合名等配置
        """
        self.settings = settings
        self.collection = settings.qdrant_collection    # 集合名，如 "documents"
        self.vector_size = settings.vector_dimension    # 向量维度，如 1024
        self._client: Optional[AsyncQdrantClient] = None
        self._connected = False
        self._last_reconnect_attempt = 0.0

    def is_connected(self) -> bool:
        """
        返回当前是否已连接 Qdrant。

        如果已断开且冷却期已过，触发自动重连（异步，不阻塞当前调用）。
        这是一个同步方法，可以在任何代码路径安全调用。

        返回:
            bool: True 表示已连接，False 表示未连接（可能正在后台重连）
        """
        if self._connected and self._client is not None:
            return True

        # 触发异步重连。因为 is_connected() 是同步方法，不能 await，
        # 所以通过 asyncio.get_running_loop().create_task() 在后台调度。
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.create_task(self._try_reconnect())
        except RuntimeError:
            pass  # 没有正在运行的事件循环（如单元测试环境），忽略

        return False

    @property
    def client(self) -> AsyncQdrantClient:
        """
        获取 Qdrant 客户端实例。

        如果未连接，抛出 VectorStoreError，提示调用者先检查 is_connected()。
        使用 @property 让访问更自然：self.client 而不是 self.client()
        """
        if self._client is None:
            raise VectorStoreError("向量存储未连接。Qdrant 不可用。")
        return self._client

    async def connect(self, retry: bool = True):
        """
        初始化 Qdrant 客户端连接。

        设计为"非致命"：即使 Qdrant 完全不可用，也不会让服务器启动失败。
        而是记录警告，后续查询时返回降级提示。

        参数:
            retry: 是否启用重试。启动时默认 True，会尝试 3 次（间隔 2s、4s）。
                   手动重连时也可以设为 False，只试一次。
        """
        logger.info(f"正在连接 Qdrant: {self.settings.qdrant_host}:{self.settings.qdrant_port}")
        max_attempts = 3 if retry else 1

        for attempt in range(1, max_attempts + 1):
            # api_key 如果是空字符串，传给 AsyncQdrantClient 可能触发 HTTPS 模式，
            # 所以显式转成 None
            api_key = self.settings.qdrant_api_key or None
            https = self.settings.qdrant_https or False

            self._client = AsyncQdrantClient(
                host=self.settings.qdrant_host,
                port=self.settings.qdrant_port,
                https=https,
                api_key=api_key,
            )
            try:
                # ensure_collection 会检查集合是否存在，不存在则创建
                await self.ensure_collection()
                self._connected = True
                self._last_reconnect_attempt = time.time()
                logger.info("Qdrant 连接成功")
                return  # 连接成功，结束函数
            except Exception as e:
                logger.warning(f"Qdrant 不可用（尝试 {attempt}/{max_attempts}）: {e}")
                self._connected = False
                # 清理失败的客户端对象，释放资源
                if self._client:
                    try:
                        await self._client.close()
                    except Exception:
                        pass
                    self._client = None
                # 如果还有重试机会，等待后重试（指数退避：2^1=2s, 2^2=4s）
                if attempt < max_attempts:
                    wait = 2 ** attempt
                    logger.info(f"{wait} 秒后重试 Qdrant...")
                    await asyncio.sleep(wait)

        logger.warning("Qdrant 所有重试均失败 — 将在下次请求时自动重试")

    async def _try_reconnect(self):
        """
        若冷却期已过，尝试重连 Qdrant。

        这是内部方法，由 is_connected() 在后台自动触发。
        """
        now = time.time()
        if now - self._last_reconnect_attempt < RECONNECT_COOLDOWN_S:
            return  # 距离上次尝试太近，跳过，避免频繁重连
        self._last_reconnect_attempt = now
        logger.info("正在尝试重连 Qdrant...")
        await self.connect(retry=True)

    async def close(self):
        """
        关闭 Qdrant 客户端连接。

        服务器关闭时调用，优雅释放网络连接和内存。
        """
        if self._client:
            await self._client.close()
            self._client = None
            self._connected = False
            logger.info("Qdrant 连接已关闭")

    async def ensure_collection(self):
        """
        确保集合存在，必要时创建。

        集合 = 数据库里的"表"。第一次启动时集合不存在，需要创建。
        创建时指定：
        - vectors_config: 向量参数（维度、距离算法）
        - hnsw_config: HNSW 索引参数（m=16, ef_construct=200）

        为什么建 payload 索引？
        payload 是附加数据（如 doc_id、status）。如果不建索引，
        按 doc_id 过滤时会做全表扫描，速度慢。建了索引后过滤几乎瞬间完成。
        """
        exists = await self.client.collection_exists(self.collection)
        if not exists:
            logger.info(f"正在创建集合 '{self.collection}'")
            await self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(
                    size=self.vector_size,
                    distance=Distance.COSINE,  # 余弦相似度，适合文本语义搜索
                ),
                hnsw_config={
                    "m": 16,            # 每个节点的最大连接数，越大搜索越准但更耗内存
                    "ef_construct": 200,  # 建索引时的搜索深度，越大索引质量越高
                },
            )
            # 为常用过滤字段创建 payload 索引
            await self.client.create_payload_index(
                collection_name=self.collection,
                field_name="doc_id",
                field_schema="keyword",  # keyword 类型适合精确匹配（如 doc_id = "xxx"）
            )
            await self.client.create_payload_index(
                collection_name=self.collection,
                field_name="status",
                field_schema="keyword",
            )
            logger.info(f"集合 '{self.collection}' 创建完成，已建立索引")

    async def upsert(self, points: List[dict]):
        """
        批量插入或更新向量点。

        "Upsert" = Update or Insert：
        - 如果 ID 已存在，更新该点的向量和 payload
        - 如果 ID 不存在，插入新点

        参数:
            points: 字典列表，每个字典包含 id、vector、payload
        """
        # 把原始字典转换成 Qdrant 的 PointStruct 对象
        qdrant_points = [
            PointStruct(
                id=p["id"],
                vector=p["vector"],
                payload=p["payload"],
            )
            for p in points
        ]
        try:
            await self.client.upsert(
                collection_name=self.collection,
                points=qdrant_points,
            )
            logger.debug(f"已写入 {len(points)} 个向量点")
        except Exception as e:
            raise VectorStoreError(f"写入向量点失败: {str(e)}")

    async def search(
        self,
        vector: List[float],
        top_k: int = 5,
        filter_doc_ids: Optional[List[str]] = None,
        similarity_threshold: Optional[float] = None,
    ) -> List[dict]:
        """
        语义搜索：找出和查询向量最相似的文档块。

        搜索流程：
        1. 如果指定了 filter_doc_ids，先过滤出这些文档的点
        2. 计算查询向量与每个候选点的余弦相似度
        3. 按相似度从高到低排序
        4. 只返回 top_k 个结果，且分数必须 ≥ similarity_threshold

        参数:
            vector: 查询向量（用户问题转换后的 1024 维数组）
            top_k: 最多返回几个结果
            filter_doc_ids: 只搜索这些文档（如用户只想查某几份标准）
            similarity_threshold: 相似度阈值，低于此值的结果丢弃（默认 0.7）

        返回:
            List[dict]: 每个元素包含 id、score（相似度分数）、payload（原文等附加信息）
        """
        if similarity_threshold is None:
            similarity_threshold = self.settings.similarity_threshold

        # 构建过滤条件。Qdrant 的 Filter 支持复杂逻辑（must/should/must_not）
        query_filter = None
        if filter_doc_ids:
            query_filter = Filter(
                must=[
                    FieldCondition(
                        key="doc_id",
                        match=MatchAny(any=filter_doc_ids),  # doc_id 在列表中的任意一个
                    )
                ]
            )

        try:
            response = await self.client.query_points(
                collection_name=self.collection,
                query=vector,
                limit=top_k,
                query_filter=query_filter,
                with_payload=True,           # 返回 payload（原文、页码等）
                score_threshold=similarity_threshold,
            )
            results = [
                {
                    "id": hit.id,
                    "score": hit.score,
                    "payload": hit.payload,
                }
                for hit in (response.points or [])
            ]
            logger.info(
                f"向量检索: 返回 {len(results)}/{top_k} 条，"
                f"阈值={similarity_threshold}，"
                f"最高分={(results[0]['score'] if results else 'N/A')}"
            )
            return results
        except Exception as e:
            raise VectorStoreError(f"搜索失败: {str(e)}")

    async def delete_by_doc_id(self, doc_id: str):
        """
        删除指定文档的所有向量点。

        实现方式：用 Filter 匹配所有 payload.doc_id == doc_id 的点，然后批量删除。

        参数:
            doc_id: 要删除的文档 ID
        """
        try:
            await self.client.delete(
                collection_name=self.collection,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="doc_id",
                            match=MatchValue(value=doc_id),  # 精确匹配
                        )
                    ]
                ),
            )
            logger.info(f"已删除 doc_id={doc_id} 的所有向量点")
        except Exception as e:
            raise VectorStoreError(f"删除向量点失败: {str(e)}")

    async def count(self, doc_id: Optional[str] = None) -> int:
        """
        统计向量点数量。

        参数:
            doc_id: 如果指定，只统计该文档的向量数；否则统计全部

        返回:
            int: 点数量
        """
        if doc_id:
            filter_condition = Filter(
                must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
            )
        else:
            filter_condition = None
        result = await self.client.count(
            collection_name=self.collection,
            count_filter=filter_condition,
        )
        return result.count

    async def get_chunks_by_doc_id(
        self,
        doc_id: str,
        limit: int = 100,
    ) -> List[dict]:
        """
        分页滚动获取指定文档的所有向量分块，按页码和分块索引排序。

        为什么用 scroll 而不是 search？
        - search 需要提供一个查询向量，找"相似的"
        - scroll 只是按条件列出所有点，不需要向量，适合"查看某文档的所有分块"

        参数:
            doc_id: 文档 ID
            limit: 最多返回多少个分块

        返回:
            List[dict]: 每个元素包含 id、chunk_index、page、content、doc_name
        """
        query_filter = Filter(
            must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
        )

        all_points = []
        offset = None           # scroll 分页游标，None 表示第一页
        page_limit = min(limit, 100)  # 每页最多 100 条，防止一次请求太大

        while len(all_points) < limit:
            response = await self.client.scroll(
                collection_name=self.collection,
                scroll_filter=query_filter,
                limit=page_limit,
                offset=offset,
                with_payload=True,
            )
            points, next_offset = response
            if not points:
                break

            for p in points:
                all_points.append({
                    "id": str(p.id),
                    "chunk_index": p.payload.get("chunk_index"),
                    "page": p.payload.get("page"),
                    "content": p.payload.get("content", ""),
                    "doc_name": p.payload.get("doc_name", ""),
                })

            if next_offset is None:
                break  # 没有更多数据了
            offset = next_offset

        # 排序：先按页码，再按 chunk_index，确保阅读顺序正确
        all_points.sort(key=lambda x: (x.get("page") or 0, x.get("chunk_index") or 0))
        return all_points

    async def get_neighbor_chunks(
        self,
        doc_id: str,
        chunk_index: int,
        window: int = 1,
    ) -> List[dict]:
        """
        获取指定 chunk 的相邻块（前后各 window 个）。

        实现 AutoMergingRetriever 思想：检索到一个 chunk 后，自动召回相邻 chunk，
        弥补单 chunk 上下文不足的问题。

        参数:
            doc_id: 文档 ID
            chunk_index: 中心块序号
            window: 向两侧扩展的块数（默认 1 = 前后各 1 个）

        返回:
            List[dict]: 相邻块列表，按 chunk_index 排序，不包含中心块本身
        """
        query_filter = Filter(
            must=[
                FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
                FieldCondition(
                    key="chunk_index",
                    range=Range(
                        gte=max(0, chunk_index - window),
                        lte=chunk_index + window,
                    ),
                ),
            ]
        )

        try:
            response = await self.client.scroll(
                collection_name=self.collection,
                scroll_filter=query_filter,
                limit=window * 2 + 1,
                with_payload=True,
            )
            points, _ = response
            neighbors = []
            for p in (points or []):
                idx = p.payload.get("chunk_index")
                if idx != chunk_index:  # 排除中心块本身
                    neighbors.append({
                        "id": str(p.id),
                        "chunk_index": idx,
                        "page": p.payload.get("page"),
                        "content": p.payload.get("content", ""),
                        "doc_name": p.payload.get("doc_name", ""),
                    })
            neighbors.sort(key=lambda x: x.get("chunk_index") or 0)
            return neighbors
        except Exception as e:
            logger.warning(f"获取相邻块失败 doc_id={doc_id} chunk_index={chunk_index}: {e}")
            return []
