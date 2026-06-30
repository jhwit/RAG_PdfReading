"""PDF 解析器测试。"""
from app.utils.pdf_parser import PDFParser


def test_parse_extracts_text(sample_pdf_path):
    parser = PDFParser()
    chunks = parser.parse(sample_pdf_path)
    assert len(chunks) > 0, "应至少提取一个文本片段"
    assert any("Hello World" in c.content for c in chunks), "应包含嵌入的文本"


def test_get_metadata(sample_pdf_path):
    parser = PDFParser()
    meta = parser.get_metadata(sample_pdf_path)
    assert "total_pages" in meta
    assert meta["total_pages"] > 0


def test_parse_with_tables(sample_pdf_path):
    parser = PDFParser()
    chunks = parser.parse_with_tables(sample_pdf_path)
    assert len(chunks) > 0
    assert all(c.page > 0 for c in chunks)
