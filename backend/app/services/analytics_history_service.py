"""每个用户独立保留最近 20 条分析历史；活动同步任务不删除。"""

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import MetricsSyncRun, SavedAnalyticsReport
from app.models.user import User
from app.models.automation import AutomationRun

HISTORY_LIMIT = 20
ACTIVE_SYNC_STATUSES = ("queued", "running")


async def lock_user_history(db: AsyncSession, user_id: int) -> None:
    # API 和 Worker 使用同一用户行锁，避免并发新增突破保留上限。
    await db.execute(select(User.id).where(User.id == user_id).with_for_update())


async def trim_reports(db: AsyncSession, user_id: int) -> None:
    old_ids = select(SavedAnalyticsReport.id).where(SavedAnalyticsReport.user_id == user_id).order_by(
        SavedAnalyticsReport.created_at.desc(), SavedAnalyticsReport.id.desc(),
    ).offset(HISTORY_LIMIT)
    await db.execute(delete(SavedAnalyticsReport).where(SavedAnalyticsReport.user_id == user_id,
                                                       SavedAnalyticsReport.id.in_(old_ids)))


async def trim_sync_runs(db: AsyncSession, user_id: int) -> None:
    protected = select(AutomationRun.id).where(
        AutomationRun.user_id == user_id, AutomationRun.status.in_(("queued", "running", "waiting_sync")),
    )
    keep = MetricsSyncRun.status.in_(ACTIVE_SYNC_STATUSES) | MetricsSyncRun.automation_run_id.in_(protected)
    active_count = await db.scalar(select(func.count()).select_from(MetricsSyncRun).where(
        MetricsSyncRun.user_id == user_id, keep,
    )) or 0
    old_ids = select(MetricsSyncRun.id).where(
        MetricsSyncRun.user_id == user_id, MetricsSyncRun.status.in_(("completed", "failed")),
        (MetricsSyncRun.automation_run_id.is_(None) | MetricsSyncRun.automation_run_id.not_in(protected)),
    ).order_by(MetricsSyncRun.created_at.desc(), MetricsSyncRun.id.desc()).offset(max(0, HISTORY_LIMIT - active_count))
    await db.execute(delete(MetricsSyncRun).where(MetricsSyncRun.user_id == user_id,
                                                 MetricsSyncRun.id.in_(old_ids)))
