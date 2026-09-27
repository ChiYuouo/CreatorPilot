"""依赖注入：数据库会话、当前用户、Agent 服务。"""

from collections.abc import AsyncIterator

import jwt
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.security import ACCESS_TOKEN_TYPE, decode_token
from app.db.session import SessionLocal
from app.models.user import User
from app.services.agent_service import AgentService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    """每个请求一个数据库会话。"""
    async with SessionLocal() as session:
        yield session


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """从请求头解析 access token，返回当前用户。失败一律 401。"""
    if token is None:
        raise AppError(401, "unauthorized", "未登录")

    try:
        payload = decode_token(token)
    except jwt.PyJWTError:
        raise AppError(401, "invalid_token", "登录状态无效或已过期，请重新登录")

    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise AppError(401, "invalid_token", "令牌类型错误，请使用 access token")

    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError):
        raise AppError(401, "invalid_token", "登录状态无效，请重新登录")

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise AppError(401, "unauthorized", "用户不存在或已被禁用")
    return user


def get_agent_service() -> AgentService:
    """Agent 服务依赖（进程内单例，绑定真实 LLM 与 Redis）。"""
    global _agent_service
    if _agent_service is None:
        from app.core.redis import get_redis
        from app.llm import get_llm_client

        _agent_service = AgentService(llm=get_llm_client(), redis=get_redis())
    return _agent_service


_agent_service: AgentService | None = None
