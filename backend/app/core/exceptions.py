"""Global exception handlers."""
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError


class RAGBaseException(Exception):
    """Base business exception."""
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class DocumentNotFound(RAGBaseException):
    def __init__(self, doc_id: str):
        super().__init__("DOC_NOT_FOUND", f"Document {doc_id} not found", 404)


class PDFParseError(RAGBaseException):
    def __init__(self, filename: str):
        super().__init__("PDF_PARSE_ERROR", f"Failed to parse {filename}", 422)


class VectorStoreError(RAGBaseException):
    def __init__(self, message: str):
        super().__init__("VECTOR_STORE_ERROR", message, 500)


class LLMUnavailableError(RAGBaseException):
    def __init__(self, message: str = "LLM service unavailable"):
        super().__init__("LLM_UNAVAILABLE", message, 503)


class NoRelevantDocsError(RAGBaseException):
    def __init__(self):
        super().__init__("NO_RELEVANT_DOCS", "No relevant documents found", 404)


class InvalidFileTypeError(RAGBaseException):
    def __init__(self):
        super().__init__("INVALID_FILE_TYPE", "Only PDF files are allowed", 400)


class FileTooLargeError(RAGBaseException):
    def __init__(self, max_mb: int = 50):
        super().__init__("FILE_TOO_LARGE", f"File exceeds {max_mb}MB limit", 413)


class EmptyQueryError(RAGBaseException):
    def __init__(self):
        super().__init__("EMPTY_QUERY", "Query cannot be empty", 400)


class QueryTooLongError(RAGBaseException):
    def __init__(self, max_chars: int = 2000):
        super().__init__("QUERY_TOO_LONG", f"Query exceeds {max_chars} characters", 400)


def setup_exception_handlers(app):
    @app.exception_handler(RAGBaseException)
    async def handle_rag_exception(request: Request, exc: RAGBaseException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message, "details": None}
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "details": exc.errors()
            }
        )

    @app.exception_handler(Exception)
    async def handle_generic(request: Request, exc: Exception):
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"code": "INTERNAL_ERROR", "message": str(exc), "details": None}
        )
