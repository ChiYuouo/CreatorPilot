"""认证接口：注册 / 登录 / 刷新 token。"""

import jwt
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.exceptions import AppError
from app.core.security import (
    REFRESH_TOKEN_TYPE,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse
from app.schemas.user import UserRead
from app.services import user_service

router = APIRouter()


def _build_token_response(user) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user=UserRead.model_validate(user),
    )


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(data: RegisterRequest, db: AsyncSession = Depends(get_db)) -> UserRead:
    user = await user_service.register(db, data)
    return UserRead.model_validate(user)


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    user = await user_service.authenticate(db, data.email, data.password)
    if user is None:
        raise AppError(401, "invalid_credentials", "邮箱或密码错误")
    return _build_token_response(user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(data: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    try:
        payload = decode_token(data.refresh_token)
    except jwt.PyJWTError:
        raise AppError(401, "invalid_token", "refresh token 无效或已过期")

    if payload.get("type") != REFRESH_TOKEN_TYPE:
        raise AppError(401, "invalid_token", "令牌类型错误，请提供 refresh token")

    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError):
        raise AppError(401, "invalid_token", "refresh token 无效")

    user = await user_service.get_by_id(db, user_id)
    if user is None or not user.is_active:
        raise AppError(401, "invalid_token", "用户不存在或已被禁用")

    return _build_token_response(user)
