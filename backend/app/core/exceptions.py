"""
全局异常处理器。

什么是异常？
程序运行中出了意外情况（比如用户请求了一个不存在的文档），Python 会"抛出"一个异常。
如果不处理，用户会收到一段难看的 Python 报错，体验很差。

这个文件做了两件事：
1. 定义我们自己的业务异常类（如 DocumentNotFound、PDFParseError）
2. 告诉 FastAPI："如果遇到这些异常，请这样优雅地回复用户"

类比：
- 异常 = 餐厅里客人点了一道没有的菜
- 异常类 = 菜单上的分类（"这道菜没有"、"这道菜今天卖完了"）
- 异常处理器 = 服务员的统一话术："抱歉，这道菜暂时没有，您可以看看别的"
"""
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError


class RAGBaseException(Exception):
    """
    业务异常基类。所有自定义异常都继承它。

    为什么要自定义异常？
    Python 内置的 Exception 太笼统了。我们需要知道：
    - 这是"文档找不到"还是"服务器内部错误"？
    - 应该返回 HTTP 404 还是 500？
    - 前端应该显示什么错误代码？

    属性说明：
        code: 机器可读的错误代码，前端可以用它做国际化或特定处理
        message: 人类可读的错误信息，直接展示给用户
        status_code: HTTP 状态码，告诉浏览器/客户端这次请求的结果类型
    """
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code           # 如 "DOC_NOT_FOUND"
        self.message = message     # 如 "文档 doc_xxx 不存在"
        self.status_code = status_code  # 如 404
        # 调用父类构造函数，这样 Python 的标准异常机制也能正常工作
        super().__init__(message)


class DocumentNotFound(RAGBaseException):
    """当用户请求了一个不存在的文档 ID 时抛出。"""
    def __init__(self, doc_id: str):
        # 调用父类构造函数，设置错误代码、信息、HTTP 状态码
        super().__init__("DOC_NOT_FOUND", f"文档 {doc_id} 不存在", 404)


class PDFParseError(RAGBaseException):
    """当 PDF 文件损坏或格式异常，无法解析时抛出。"""
    def __init__(self, filename: str):
        super().__init__("PDF_PARSE_ERROR", f"无法解析文件 {filename}", 422)


class VectorStoreError(RAGBaseException):
    """当 Qdrant 向量数据库操作失败时抛出。"""
    def __init__(self, message: str):
        super().__init__("VECTOR_STORE_ERROR", message, 500)


class LLMUnavailableError(RAGBaseException):
    """当大语言模型（如 OpenAI/DeepSeek）无法连接或返回错误时抛出。"""
    def __init__(self, message: str = "LLM 服务不可用"):
        super().__init__("LLM_UNAVAILABLE", message, 503)


class NoRelevantDocsError(RAGBaseException):
    """当用户提问，但知识库中没有找到相关内容时抛出。"""
    def __init__(self):
        super().__init__("NO_RELEVANT_DOCS", "未找到相关文档", 404)


class InvalidFileTypeError(RAGBaseException):
    """当用户上传了非 PDF 文件时抛出。"""
    def __init__(self):
        super().__init__("INVALID_FILE_TYPE", "仅允许上传 PDF 文件", 400)


class FileTooLargeError(RAGBaseException):
    """当上传的文件超过大小限制时抛出。"""
    def __init__(self, max_mb: int = 50):
        super().__init__("FILE_TOO_LARGE", f"文件大小超过 {max_mb}MB 限制", 413)


class EmptyQueryError(RAGBaseException):
    """当用户提交了空问题（只有空格或什么都没写）时抛出。"""
    def __init__(self):
        super().__init__("EMPTY_QUERY", "问题不能为空", 400)


class QueryTooLongError(RAGBaseException):
    """当用户问题超过 2000 字符时抛出，防止恶意输入拖垮 LLM。"""
    def __init__(self, max_chars: int = 2000):
        super().__init__("QUERY_TOO_LONG", f"问题长度超过 {max_chars} 个字符", 400)


def setup_exception_handlers(app):
    """
    注册 FastAPI 的全局异常处理器。

    FastAPI 使用装饰器模式注册处理器。下面三个 @app.exception_handler
    分别处理三种层级的异常。
    """

    @app.exception_handler(RAGBaseException)
    async def handle_rag_exception(request: Request, exc: RAGBaseException):
        """
        处理我们自己定义的业务异常。

        返回统一的 JSON 格式，前端拿到后可以直接解析展示。
        例如：{ "code": "DOC_NOT_FOUND", "message": "文档 doc_xxx 不存在", "details": null }
        """
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message, "details": None}
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError):
        """
        处理请求参数校验失败（如用户传了字符串但后端要求数字）。

        这是 FastAPI 内置的异常，发生在路由函数执行之前。
        exc.errors() 会返回详细的字段级错误信息。
        """
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "code": "VALIDATION_ERROR",
                "message": "请求参数校验失败",
                "details": exc.errors()  # 详细错误列表，方便前端定位是哪个字段错了
            }
        )

    @app.exception_handler(Exception)
    async def handle_generic(request: Request, exc: Exception):
        """
        处理所有未被上面捕获的异常（兜底）。

        包括：
        - 代码 Bug（如 NoneType 没有某个属性）
        - 第三方库内部异常
        - 任何意料之外的错误

        注意：生产环境不要把 str(exc) 直接返回给用户，可能泄露敏感信息。
        这里为了调试方便暂时直接返回，后续可以加环境判断。
        """
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"code": "INTERNAL_ERROR", "message": str(exc), "details": None}
        )
