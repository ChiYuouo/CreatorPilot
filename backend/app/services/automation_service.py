"""自动化任务：用户隔离、计划时间与执行记录。"""

from datetime import date, datetime, time, timedelta, timezone
from typing import Protocol
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.automation import AutomationRun, AutomationTask
from app.schemas.automation import AutomationTaskWrite
from app.models.publishing import PlatformAccount
from app.platforms.registry import get_platform


async def validate_accounts(db: AsyncSession, user_id: int, account_ids: list[int], *, sync: bool) -> None:
    accounts = list((await db.scalars(select(PlatformAccount).where(
        PlatformAccount.user_id == user_id, PlatformAccount.is_deleted.is_(False),
        PlatformAccount.id.in_(account_ids),
    ))).all())
    if len(accounts) != len(account_ids):
        raise AppError(422, "invalid_accounts", "所选账号不存在或不属于当前用户")
    if sync:
        for account in accounts:
            try:
                supported = get_platform(account.platform).metrics_sync_supported
            except ValueError:
                supported = False
            if not supported or account.status == "expired":
                raise AppError(422, "account_unavailable", "所选账号不支持同步或登录已失效，请先检查账号")


async def validate_task_accounts(db: AsyncSession, user_id: int, data: AutomationTaskWrite) -> None:
    await validate_accounts(db, user_id, data.payload.get("account_ids", []),
                            sync=data.task_type == "metrics_sync" or data.payload.get("sync_first", False))


class WeeklyTiming(Protocol):
    frequency: str
    weekday: int
    hour: int
    minute: int
    timezone: str


def next_run_at(data: WeeklyTiming, now: datetime | None = None) -> datetime:
    """计算严格晚于 now 的下一次 UTC 运行时间。星期采用周一 0 至周日 6。"""
    if data.frequency != "weekly":
        raise ValueError(f"不支持的调度频率：{data.frequency}")
    now = now or datetime.now(timezone.utc)
    local_now = now.astimezone(ZoneInfo(data.timezone))
    for offset in range(8):
        day: date = local_now.date() + timedelta(days=offset)
        if day.weekday() != data.weekday:
            continue
        local = datetime.combine(day, time(data.hour, data.minute), ZoneInfo(data.timezone))
        candidate = local.astimezone(timezone.utc)
        if candidate > now:
            return candidate
    raise RuntimeError("无法计算下次任务时间")


async def list_tasks(db: AsyncSession, user_id: int) -> list[AutomationTask]:
    result = await db.execute(
        select(AutomationTask)
        .where(AutomationTask.user_id == user_id, AutomationTask.deleted_at.is_(None))
        .order_by(AutomationTask.id.desc())
    )
    return list(result.scalars().all())


async def get_task(db: AsyncSession, user_id: int, task_id: int) -> AutomationTask:
    task = await db.scalar(
        select(AutomationTask).where(
            AutomationTask.id == task_id,
            AutomationTask.user_id == user_id,
            AutomationTask.deleted_at.is_(None),
        )
    )
    if task is None:
        raise AppError(404, "automation_task_not_found", "自动化任务不存在")
    return task


async def create_task(
    db: AsyncSession, user_id: int, data: AutomationTaskWrite
) -> AutomationTask:
    await validate_task_accounts(db, user_id, data)
    task = AutomationTask(
        user_id=user_id,
        **data.model_dump(),
        next_run_at=next_run_at(data) if data.enabled else None,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


async def update_task(
    db: AsyncSession, user_id: int, task_id: int, data: AutomationTaskWrite
) -> AutomationTask:
    task = await get_task(db, user_id, task_id)
    if task.task_type != data.task_type:
        raise AppError(422, "task_type_immutable", "任务类型不能修改，请新建任务")
    await validate_task_accounts(db, user_id, data)
    for key, value in data.model_dump().items():
        setattr(task, key, value)
    task.next_run_at = next_run_at(data) if data.enabled else None
    if not data.enabled:
        await _cancel_queued_runs(db, task.id)
    await db.commit()
    await db.refresh(task)
    return task


async def _cancel_queued_runs(db: AsyncSession, task_id: int) -> None:
    await db.execute(
        update(AutomationRun)
        .where(AutomationRun.task_id == task_id, AutomationRun.status.in_(("queued", "waiting_sync")))
        .values(status="canceled", finished_at=datetime.now(timezone.utc))
    )


async def delete_task(db: AsyncSession, user_id: int, task_id: int) -> None:
    """软删除任务，保留历史；尚未运行的记录立即取消。"""
    task = await get_task(db, user_id, task_id)
    task.enabled = False
    task.next_run_at = None
    task.deleted_at = datetime.now(timezone.utc)
    await _cancel_queued_runs(db, task.id)
    await db.commit()


async def list_runs(db: AsyncSession, user_id: int) -> list[AutomationRun]:
    result = await db.execute(
        select(AutomationRun)
        .where(AutomationRun.user_id == user_id)
        .order_by(AutomationRun.scheduled_for.desc(), AutomationRun.id.desc())
        .limit(100)
    )
    return list(result.scalars().all())
