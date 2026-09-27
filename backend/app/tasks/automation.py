"""通用调度和任务类型分派；数据库运行记录是状态来源。"""

import asyncio
import logging
from copy import deepcopy
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.exceptions import AppError
from app.llm import get_llm_client
from app.models.automation import AutomationRun, AutomationTask
from app.models.analytics import MetricsSyncRun
from app.models.publishing import PlatformAccount
from app.schemas.automation import MetricsSyncPayload
from app.schemas.analytics import ReportGenerationRequest
from app.services.analytics_report_service import batch_contents_report, recent_contents_report, single_content_report
from app.services.automation_service import next_run_at, validate_accounts
from app.services.metrics_sync_service import create_run, expire_stale_runs
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)
TaskHandler = Callable[[AsyncSession, AutomationRun], Awaitable[dict[str, Any] | None]]


async def queue_due_tasks(now: datetime | None = None) -> list[int]:
    """原子认领到期任务，并返回需要投递的运行 ID。"""
    now = now or datetime.now(timezone.utc)
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as db:
            async with db.begin():
                await db.execute(
                    update(AutomationRun)
                    .where(
                        AutomationRun.status == "running",
                        AutomationRun.started_at < now - timedelta(minutes=15),
                    )
                    .values(status="queued", started_at=None)
                )
                due = await db.execute(
                    select(AutomationTask)
                    .where(
                        AutomationTask.enabled.is_(True),
                        AutomationTask.deleted_at.is_(None),
                        AutomationTask.next_run_at <= now,
                    )
                    .with_for_update(skip_locked=True)
                    .limit(100)
                )
                for task in due.scalars():
                    db.add(AutomationRun(
                        task_id=task.id,
                        user_id=task.user_id,
                        task_type=task.task_type,
                        task_name=task.name,
                        scheduled_for=task.next_run_at,
                        status="queued",
                        payload=deepcopy(task.payload),
                    ))
                    task.next_run_at = next_run_at(task, now)

            # 投递失败的 queued 记录在下一轮重投；worker 认领保证只执行一次。
            result = await db.scalars(
                select(AutomationRun.id)
                .where(AutomationRun.status.in_(("queued", "waiting_sync")))
                .order_by(AutomationRun.id)
                .limit(100)
            )
            return list(result.all())
    finally:
        await engine.dispose()


async def _sync_accounts(db: AsyncSession, run: AutomationRun, account_ids: list[int]) -> dict[str, Any] | None:
    """持久化子任务后交给本机队列；下一轮检查实际完成状态。"""
    stage = run.result or {}
    ids = stage.get("sync_run_ids")
    if ids is None:
        if not account_ids:
            account_ids = list((await db.scalars(select(PlatformAccount.id).where(
                PlatformAccount.user_id == run.user_id, PlatformAccount.is_deleted.is_(False),
            ).order_by(PlatformAccount.id))).all())
        if not account_ids or len(account_ids) > 20:
            raise AppError(422, "invalid_accounts", "先同步需要 1 至 20 个可用账号，请指定账号")
        await validate_accounts(db, run.user_id, account_ids, sync=True)
        children = [await create_run(db, run.user_id, account_id, automation_run_id=run.id, commit=False)
                    for account_id in sorted(account_ids)]
        ids = [child.id for child in children]
        run.result = {"sync_run_ids": ids, "sync_account_ids": account_ids}
        # 子任务与关联记录在同一个事务落库，重投不会重新创建同步。
        await db.commit()
    await expire_stale_runs(db, run.user_id)
    children = list((await db.scalars(select(MetricsSyncRun).where(
        MetricsSyncRun.id.in_(ids), MetricsSyncRun.user_id == run.user_id,
        MetricsSyncRun.automation_run_id == run.id,
    ))).all())
    if len(children) != len(ids):
        raise AppError(422, "sync_result_missing", "同步记录缺失，请重新运行任务")
    failed = next((child for child in children if child.status == "failed"), None)
    if failed:
        raise AppError(422, "sync_failed", f"账号 {failed.account_id} 同步失败：{failed.message or '请检查本机 Worker'}")
    from app.tasks.metrics import sync_account
    for child in children:
        if child.status == "queued":
            try:
                sync_account.delay(child.id)
            except Exception:
                logger.exception("自动化同步投递失败: sync_run_id=%s", child.id)
    if any(child.status != "completed" for child in children):
        return None
    return {**(run.result or {}), "content_count": sum(child.content_count for child in children),
            "metric_count": sum(child.metric_count for child in children),
            "message": "所选账号作品与指标同步已完成"}


async def _metrics_sync(db: AsyncSession, run: AutomationRun) -> dict[str, Any] | None:
    payload = MetricsSyncPayload.model_validate(run.payload)
    return await _sync_accounts(db, run, payload.account_ids)


async def _analysis_report(db: AsyncSession, run: AutomationRun) -> dict[str, Any] | None:
    payload = ReportGenerationRequest.model_validate(run.payload)
    sync_result: dict[str, Any] = {}
    if payload.sync_first:
        result = await _sync_accounts(db, run, payload.account_ids)
        if result is None:
            return None
        sync_result = result
    if payload.scope == "single_content":
        report = await single_content_report(db, run.user_id, payload.content_id, get_llm_client())
    elif payload.scope == "recent_contents":
        report = await recent_contents_report(db, run.user_id, payload.days, get_llm_client(), payload.account_ids)
    else:
        report = await batch_contents_report(db, run.user_id, get_llm_client(), payload.account_ids)
    return {**sync_result, "report_id": report.id, "report": report.report, "scope": report.scope,
            "content_count": report.content_count, "without_metrics_count": report.without_metrics_count,
            "days": report.days, "content_id": report.content_id,
            "excluded_without_metrics": report.excluded_without_metrics}


TASK_HANDLERS: dict[str, TaskHandler] = {
    "metrics_sync": _metrics_sync, "analysis_report": _analysis_report,
}


async def execute_task_for_run(run_id: int) -> None:
    """认领一条运行记录，根据类型执行并保存结果。"""
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as db:
            claim = await db.execute(
                update(AutomationRun)
                .where(AutomationRun.id == run_id, AutomationRun.status.in_(("queued", "waiting_sync")))
                .values(status="running", started_at=datetime.now(timezone.utc))
                .returning(AutomationRun.id)
            )
            if claim.scalar_one_or_none() is None:
                await db.rollback()
                return
            await db.commit()
            run = await db.get(AutomationRun, run_id)
            task = await db.get(AutomationTask, run.task_id) if run.task_id is not None else None
            if run.task_id is not None and (task is None or not task.enabled or task.deleted_at is not None):
                run.status = "canceled"
                run.finished_at = datetime.now(timezone.utc)
                await db.commit()
                return

            handler = TASK_HANDLERS.get(run.task_type)
            if handler is None:
                run.status = "failed"
                run.error_message = "不支持的自动化任务类型"
            else:
                try:
                    result = await handler(db, run)
                except AppError as exc:
                    await db.rollback()
                    run = await db.get(AutomationRun, run_id)
                    run.status = "failed"
                    run.error_message = exc.message[:500]
                except Exception:  # noqa: BLE001 - 后台异常需记录，避免停在 running
                    logger.exception("自动化任务执行失败: run_id=%s", run_id)
                    await db.rollback()
                    run = await db.get(AutomationRun, run_id)
                    run.status = "failed"
                    run.error_message = "自动化任务执行失败，请稍后检查任务日志"
                else:
                    run.status = "waiting_sync" if result is None else "succeeded"
                    if result is not None:
                        run.result = result
            run.finished_at = None if run.status == "waiting_sync" else datetime.now(timezone.utc)
            await db.commit()
    finally:
        await engine.dispose()


@celery_app.task(name="app.tasks.automation.dispatch_due_tasks")
def dispatch_due_tasks() -> None:
    run_ids = asyncio.run(queue_due_tasks())
    for run_id in run_ids:
        try:
            execute_task.delay(run_id)
        except Exception:  # noqa: BLE001 - queued 记录保留，下一轮重投
            logger.exception("自动化任务投递失败: run_id=%s", run_id)


@celery_app.task(name="app.tasks.automation.execute_task", time_limit=600, soft_time_limit=540)
def execute_task(run_id: int) -> None:
    asyncio.run(execute_task_for_run(run_id))
