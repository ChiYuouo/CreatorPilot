"""数据回收在本机 publishing 队列执行，不依赖 LLM。"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models.analytics import MetricsSyncRun
from app.models.publishing import PlatformAccount
from app.platforms.publisher_process import run_publisher
from app.platforms.registry import get_platform
from app.services.metrics_sync_service import persist_result
from app.services.analytics_history_service import lock_user_history, trim_sync_runs
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


async def execute_sync_run(
    run_id: int, *, session_factory: async_sessionmaker[AsyncSession] | None = None,
    collector: Callable[..., Awaitable[dict[str, Any]]] | None = None,
) -> None:
    engine = None
    if session_factory is None:
        engine = create_async_engine(settings.database_url, poolclass=NullPool)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as db:
            claim = await db.execute(update(MetricsSyncRun).where(
                MetricsSyncRun.id == run_id, MetricsSyncRun.status == "queued",
            ).values(status="running").returning(MetricsSyncRun.id))
            if claim.scalar_one_or_none() is None:
                await db.rollback()
                return
            await db.commit()
            run = await db.get(MetricsSyncRun, run_id)
            user_id = run.user_id
            account = await db.get(PlatformAccount, run.account_id)
            try:
                if account is None or account.is_deleted or account.user_id != run.user_id or not get_platform(account.platform).metrics_sync_supported:
                    raise ValueError("账号不可用")
                account_name, platform = account.account_name, account.platform
                await db.commit()
                result = await (collector or run_publisher)(
                    "collect_works", platform=platform, account_name=account_name,
                    max_pages=settings.metrics_sync_max_pages,
                )
                await persist_result(db, run_id, result)
            except Exception:
                logger.exception("账号作品同步失败: run_id=%s", run_id)
                await db.rollback()
                await lock_user_history(db, user_id)
                await db.execute(update(MetricsSyncRun).where(
                    MetricsSyncRun.id == run_id, MetricsSyncRun.status == "running",
                ).values(status="failed", message="采集失败，未保存本次数据；请检查登录态、平台验证或接口变化，再重新同步"))
                await trim_sync_runs(db, user_id)
                await db.commit()
    finally:
        if engine is not None:
            await engine.dispose()


@celery_app.task(name="app.tasks.metrics.sync_account")
def sync_account(run_id: int) -> None:
    asyncio.run(execute_sync_run(run_id))
