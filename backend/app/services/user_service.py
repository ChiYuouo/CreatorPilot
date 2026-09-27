"""用户业务逻辑。路由层保持轻薄，逻辑集中于此。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.security import hash_password, verify_password
from app.models.user import User
from app.schemas.auth import RegisterRequest


async def get_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_by_id(db: AsyncSession, user_id: int) -> User | None:
    return await db.get(User, user_id)


async def register(db: AsyncSession, data: RegisterRequest) -> User:
    """注册新用户。邮箱已存在时抛出 409。"""
    existing = await get_by_email(db, data.email)
    if existing is not None:
        raise AppError(409, "email_already_exists", "该邮箱已被注册")

    user = User(
        email=data.email,
        nickname=data.nickname,
        hashed_password=hash_password(data.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate(db: AsyncSession, email: str, password: str) -> User | None:
    """校验邮箱密码。成功返回用户，失败返回 None（不区分邮箱不存在与密码错误）。"""
    user = await get_by_email(db, email)
    if user is None:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    if not user.is_active:
        return None
    return user
