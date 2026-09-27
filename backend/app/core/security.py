"""安全模块：密码哈希与 JWT 签发/校验。

Token 采用双 token 机制：
- access token：短时效，用于接口鉴权
- refresh token：长时效，仅用于换取新 token 对
"""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings

ALGORITHM = "HS256"
ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"


def hash_password(password: str) -> str:
    """明文密码 -> bcrypt 哈希。"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """校验明文密码与 bcrypt 哈希是否匹配。"""
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def _create_token(subject: int, token_type: str, expires_delta: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(subject),
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def create_access_token(user_id: int) -> str:
    return _create_token(user_id, ACCESS_TOKEN_TYPE, timedelta(minutes=settings.access_token_expire_minutes))


def create_refresh_token(user_id: int) -> str:
    return _create_token(user_id, REFRESH_TOKEN_TYPE, timedelta(days=settings.refresh_token_expire_days))


def decode_token(token: str) -> dict:
    """解码并校验 JWT。无效或过期时抛出 jwt.PyJWTError。"""
    return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])


def create_media_preview_token(user_id: int, asset_id: int) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": str(user_id), "asset_id": asset_id, "type": "media_preview",
                       "iat": now, "exp": now + timedelta(seconds=settings.media_preview_expire_seconds)},
                      settings.secret_key, algorithm=ALGORITHM)
