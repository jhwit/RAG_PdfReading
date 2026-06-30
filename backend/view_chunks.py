"""查看指定文档的分块内容（临时调试脚本）。"""
import asyncio
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
COLLECTION = "documents"


async def show_chunks(doc_id: str, limit: int = 20):
    client = AsyncQdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

    response = await client.scroll(
        collection_name=COLLECTION,
        scroll_filter=Filter(
            must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
        ),
        limit=limit,
        with_payload=True,
    )

    points = response[0]  # scroll 返回 (points, next_page_offset)
    print(f"\n文档: {doc_id} | 共 {len(points)} 个分块\n")
    print("=" * 60)

    for i, p in enumerate(points, 1):
        payload = p.payload
        print(f"\n【分块 {i}】 页码: {payload.get('page', '?')} | 索引: {payload.get('chunk_index', '?')}")
        print("-" * 60)
        print(payload.get("content", "[无内容]"))
        print("=" * 60)

    await client.close()


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python view_chunks.py <doc_id>")
        print("示例: python view_chunks.py doc_abc123")
        sys.exit(1)

    doc_id = sys.argv[1]
    asyncio.run(show_chunks(doc_id))
