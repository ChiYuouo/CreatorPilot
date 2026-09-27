"""Redis 客户端（短期记忆 / 缓存）。

单一入口，禁止业务代码自行建连接。
"""

from __future__ import annotations

import redis.asyncio as redis

from app.core.config import settings

_pool: redis.ConnectionPool | None = None


def get_redis() -> redis.Redis:
    """返回共享连接池的 Redis 客户端。decode_responses=True，读出即 str。"""
    global _pool
    if _pool is None:
        _pool = redis.ConnectionPool.from_url(
            settings.redis_url,
            decode_responses=True,
        )
    return redis.Redis(connection_pool=_pool)
