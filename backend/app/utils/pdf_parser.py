"""
PDF 解析工具，支持复杂文档。

这个文件负责把用户上传的 PDF 文件变成"一段一段的文本"。

为什么需要专门的解析器？
PDF 不是普通的文本文件，它是一种排版格式。同样一段文字，在 PDF 内部可能由多个
零散的字形命令拼成，直接打开可能是一堆乱码。我们需要专门的库来提取有意义的文本。

使用的库：PyMuPDF（也叫 fitz）
- 优点：速度快，支持提取文本、表格、图片、元数据
- 安装：pip install PyMuPDF

基本概念：
- TextChunk = 一个文本片段，包含内容、页码、在页面上的坐标（bbox）
- parse = 简单提取每页的文字
- parse_with_tables = 不仅提取文字，还提取表格（转成文本形式）
"""
import fitz  # PyMuPDF，fitz 是 PyMuPDF 的底层 C 库名，保留了这个别名
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass
import logging

# 使用 Python 标准 logging，因为 PDFParser 可能在 setup_logger 之前被导入
logger = logging.getLogger(__name__)


@dataclass
class TextChunk:
    """
    文本片段数据类。

    @dataclass 是 Python 的装饰器，它会自动帮我们生成 __init__、__repr__ 等方法。
    不需要手写 class TextChunk: def __init__(self, content, page, bbox): ... 这些样板代码。

    属性:
        content: 提取出的文本内容
        page: 所属页码（从 1 开始，方便人类阅读）
        bbox: 文本块在页面上的坐标 (x0, y0, x1, y1)，可选，用于后续高亮定位
    """
    content: str
    page: int
    bbox: Optional[tuple] = None


class PDFParser:
    """
    PDF 文档解析器。

    职责：把 PDF 文件转换成程序能处理的文本块列表。

    两个提取策略：
    1. parse() — 简单模式：按页提取纯文本，速度快
    2. parse_with_tables() — 增强模式：不仅提取文本，还把表格转成文本，信息更完整
    """

    def __init__(self, dpi: int = 200):
        """
        初始化解析器。

        参数:
            dpi: 扫描件 OCR 时用的分辨率（dots per inch）。
                 目前未实现 OCR，保留这个参数供以后扩展。
                 值越大越清晰但越慢。200 DPI 是一个平衡点。
        """
        self.dpi = dpi

    def parse(self, file_path: Path) -> List[TextChunk]:
        """
        按页提取 PDF 文本。

        流程：
        1. 用 fitz.open() 打开 PDF 文件
        2. 遍历每一页，调用 page.get_text() 提取文字
        3. 如果某页没有文字（可能是扫描件/图片），记录警告
        4. 关闭文档（放在 finally 里确保一定执行，防止内存泄漏）

        参数:
            file_path: PDF 文件的磁盘路径（Path 对象比纯字符串更安全，支持跨平台）

        返回:
            List[TextChunk]: 每个元素是一页的文本内容
        """
        chunks = []
        doc = fitz.open(str(file_path))  # fitz 需要字符串路径

        try:
            # len(doc) = PDF 总页数
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)  # 加载第 page_num 页（从 0 开始）
                text = page.get_text()          # 提取该页所有文本

                if text.strip():  # .strip() 去掉首尾空白，检查是否真的有字
                    chunks.append(TextChunk(
                        content=text,
                        page=page_num + 1  # 人类习惯页码从 1 开始
                    ))
                else:
                    # 扫描页 — 整页都是图片，没有可提取的文字
                    # 后续可以考虑接入 OCR（如 paddleocr、easyocr）
                    logger.warning(f"第 {page_num + 1} 页似乎是扫描件，OCR 功能尚未实现")

        finally:
            # 无论上面是否出错，都要关闭文档，释放文件句柄和内存
            doc.close()

        return chunks

    def parse_with_tables(self, file_path: Path) -> List[TextChunk]:
        """
        从 PDF 中提取文本和表格。

        与 parse() 的区别：
        - parse() 只提取纯文本，会丢失表格的行列结构
        - parse_with_tables() 会找到表格，把每个单元格的内容按行列拼成文本，
          这样 LLM 能理解"第 1 行第 2 列的值是 xxx"

        返回的 chunks 包括：
        - 普通文本块（带坐标）
        - 表格块（以 "[Table N]" 开头，下面是表格内容）
        """
        chunks = []
        doc = fitz.open(str(file_path))

        try:
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)

                # === 提取文本块 ===
                # get_text("blocks") 返回页面上的独立文本块，每个块包含坐标信息
                # 这比 get_text() 更细粒度，方便后续定位
                blocks = page.get_text("blocks")
                for block in blocks:
                    # block 是一个元组：(x0, y0, x1, y1, text, block_no, block_type)
                    x0, y0, x1, y1, text, block_no, block_type = block
                    if text.strip():
                        chunks.append(TextChunk(
                            content=text.strip(),
                            page=page_num + 1,
                            bbox=(x0, y0, x1, y1)  # 记录位置，后续可用于高亮原文
                        ))

                # === 提取表格 ===
                # find_tables() 是 PyMuPDF 的表格检测功能，它会分析页面线条，
                # 识别出表格区域，并转成 pandas DataFrame
                tables = page.find_tables()
                if tables.tables:
                    for idx, table in enumerate(tables.tables):
                        df = table.to_pandas()  # 转成表格对象
                        # 把表格转成字符串形式，方便 LLM 阅读
                        # to_string() 会保留行列对齐，比 csv 更易读
                        chunks.append(TextChunk(
                            content=f"[Table {idx + 1}]\n{df.to_string()}",
                            page=page_num + 1
                        ))

        finally:
            doc.close()

        return chunks

    def get_metadata(self, file_path: Path) -> dict:
        """
        获取 PDF 的元数据（属性信息）。

        元数据包括：标题、作者、主题、创建工具、总页数等。
        这些信息来自 PDF 文件头部的 XMP/Info 字典，不是每页内容。

        参数:
            file_path: PDF 文件路径

        返回:
            dict: 包含 title, author, subject, creator, total_pages 的字典
        """
        doc = fitz.open(str(file_path))
        try:
            return {
                "title": doc.metadata.get("title", ""),    # .get(key, default) 不存在时返回空字符串
                "author": doc.metadata.get("author", ""),
                "subject": doc.metadata.get("subject", ""),
                "creator": doc.metadata.get("creator", ""),
                "total_pages": len(doc),  # 总页数直接从文档对象获取
            }
        finally:
            doc.close()
