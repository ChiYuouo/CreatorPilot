"""统一业务异常。

错误响应格式：{"code": "<机器可读错误码>", "message": "<人类可读信息>"}
"""

from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """业务异常基类。业务逻辑中需要主动失败时，抛出此异常。"""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """将 AppError 转换为统一 JSON 响应。在 main.py 中注册。"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message},
    )
