from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(self, message: str, status_code: int = 400, detail: dict | None = None):
        self.message = message
        self.status_code = status_code
        self.detail = detail or {}


class NotFoundError(AppError):
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, status_code=404)


class AuthError(AppError):
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, status_code=401)


class ForbiddenError(AppError):
    def __init__(self, message: str = "Permission denied"):
        super().__init__(message, status_code=403)


class ConflictError(AppError):
    def __init__(self, message: str = "Resource already exists"):
        super().__init__(message, status_code=409)


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message, **exc.detail},
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    import logging
    logger = logging.getLogger(__name__)
    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )
