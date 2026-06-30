"""文本分块器测试。"""
from app.core.config import Settings
from app.utils.text_splitter import TextSplitter


def test_split_empty_text():
    splitter = TextSplitter(Settings(chunk_size=512, chunk_overlap=50))
    chunks = splitter.split("", "doc1", "test.pdf", 1)
    assert len(chunks) == 0


def test_split_short_text():
    splitter = TextSplitter(Settings(chunk_size=512, chunk_overlap=50))
    text = "这是一段短文本。"
    chunks = splitter.split(text, "doc1", "test.pdf", 1)
    assert len(chunks) == 1
    assert chunks[0]["content"] == text
    assert chunks[0]["doc_id"] == "doc1"
    assert chunks[0]["doc_name"] == "test.pdf"
    assert chunks[0]["page"] == 1
    assert chunks[0]["chunk_index"] == 0


def test_split_long_text():
    splitter = TextSplitter(Settings(chunk_size=100, chunk_overlap=20))
    text = "A" * 300
    chunks = splitter.split(text, "doc1", "test.pdf", 2)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk["content"]) <= 100


def test_chunk_metadata():
    splitter = TextSplitter(Settings(chunk_size=512, chunk_overlap=50))
    text = "第一段。\n\n第二段。"
    chunks = splitter.split(text, "doc_x", "file.pdf", 5)
    assert len(chunks) > 0
    for chunk in chunks:
        assert "content" in chunk
        assert "doc_id" in chunk
        assert "doc_name" in chunk
        assert "page" in chunk
        assert "chunk_index" in chunk
