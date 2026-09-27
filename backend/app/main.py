"""FastAPI 应用入口。

职责边界：
- API 服务、用户管理、数据管理
- Agent 调用（Phase 2 起，编排逻辑在 app.agents，不在本层）
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import AppError, app_error_handler


def create_app() -> FastAPI:
    app = FastAPI(title="CreatorPilot API", version="1.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api/v1")

    @app.get("/health", tags=["system"])
    async def health() -> dict:
        return {"status": "ok"}

    app.add_exception_handler(AppError, app_error_handler)

    return app


app = create_app()
