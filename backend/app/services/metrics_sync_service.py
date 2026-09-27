"""账号归属校验、后台同步记录和作品/每日快照幂等落库。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
import re
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.models.analytics import ContentMetric, MetricsSyncRun, PublishedContent
from app.models.publishing import PlatformAccount
from app.schemas.analytics import MetricWrite, PublishedContentWrite
from app.platforms.registry import get_platform
from app.services.analytics_history_service import ACTIVE_SYNC_STATUSES, HISTORY_LIMIT, lock_user_history, trim_sync_runs

METRIC_FIELDS = ("views", "likes", "comments", "favorites", "shares", "follower_gain")


async def expire_stale_runs(db: AsyncSession, user_id: int) -> None:
    now = datetime.now(timezone.utc)
    await db.execute(update(MetricsSyncRun).where(
        MetricsSyncRun.user_id == user_id,
        ((MetricsSyncRun.status == "running") & (MetricsSyncRun.updated_at < now - timedelta(seconds=settings.metrics_sync_timeout_seconds + 120)))
        | ((MetricsSyncRun.status == "queued") & (MetricsSyncRun.created_at < now - timedelta(hours=1)))
    ).values(status="failed", message="本机数据同步服务未及时完成，请检查 Worker 后重试")
      .execution_options(synchronize_session="fetch"))


async def list_runs(db: AsyncSession, user_id: int) -> list[MetricsSyncRun]:
    await lock_user_history(db, user_id)
    await expire_stale_runs(db, user_id)
    await trim_sync_runs(db, user_id)
    await db.commit()
    return list((await db.scalars(select(MetricsSyncRun).where(MetricsSyncRun.user_id == user_id)
                                .order_by(MetricsSyncRun.created_at.desc(), MetricsSyncRun.id.desc()))).all())


async def create_run(
    db: AsyncSession, user_id: int, account_id: int, *, automation_run_id: int | None = None,
    commit: bool = True,
) -> MetricsSyncRun:
    await lock_user_history(db, user_id)
    # 锁住账号，避免同账号同时采集和写入；不把 Cookie 写进任务或 API。
    account = await db.scalar(select(PlatformAccount).where(
        PlatformAccount.id == account_id, PlatformAccount.user_id == user_id,
        PlatformAccount.is_deleted.is_(False),
    ).with_for_update())
    if account is None:
        raise AppError(404, "account_not_found", "平台账号不存在")
    try:
        supported = get_platform(account.platform).metrics_sync_supported
    except ValueError:
        supported = False
    if not supported:
        raise AppError(422, "metrics_unsupported", "该平台暂不支持作品同步，可手动录入指标进行分析")
    if account.status == "expired":
        raise AppError(422, "account_expired", "请先在账号管理重新登录")
    await expire_stale_runs(db, user_id)
    active = await db.scalar(select(MetricsSyncRun.id).where(
        MetricsSyncRun.account_id == account_id, MetricsSyncRun.status.in_(("queued", "running")),
    ))
    if active is not None:
        raise AppError(409, "sync_in_progress", "该账号已有同步任务，请等待完成")
    active_count = await db.scalar(select(func.count()).select_from(MetricsSyncRun).where(
        MetricsSyncRun.user_id == user_id, MetricsSyncRun.status.in_(ACTIVE_SYNC_STATUSES),
    )) or 0
    if active_count >= HISTORY_LIMIT:
        raise AppError(409, "too_many_sync_runs", "已有 20 个同步任务进行中，请等待完成后再同步")
    run = MetricsSyncRun(user_id=user_id, account_id=account_id, status="queued", automation_run_id=automation_run_id)
    db.add(run)
    await db.flush()
    await trim_sync_runs(db, user_id)
    if not commit:
        return run
    await db.commit()
    from app.tasks.metrics import sync_account
    try:
        sync_account.delay(run.id)
    except Exception:
        run.status = "failed"
        run.message = "同步任务未能入队，请检查 Redis 和本机 Worker 后重试"
        await db.commit()
    await db.refresh(run)
    return run


async def persist_result(db: AsyncSession, run_id: int, result: dict[str, Any]) -> None:
    user_id = await db.scalar(select(MetricsSyncRun.user_id).where(MetricsSyncRun.id == run_id))
    if user_id is None:
        return
    await lock_user_history(db, user_id)
    run = await db.scalar(select(MetricsSyncRun).where(MetricsSyncRun.id == run_id).with_for_update())
    if run is None or run.status != "running":
        return
    account = await db.get(PlatformAccount, run.account_id)
    if account is None or account.is_deleted or account.user_id != run.user_id:
        raise ValueError("账号已不可用")
    if result.get("status") != "completed":
        if result.get("status") == "login_expired":
            account.status = "expired"
            run.status = "failed"
            run.message = "登录态不可用，请到账号管理重新登录或完成平台验证"
            await db.flush()
            await trim_sync_runs(db, user_id)
            await db.commit()
            return
        if result.get("status") == "failed":
            run.status = "failed"
            run.message = "采集失败，未保存本次数据；" + str(result.get("message") or "请检查平台接口")[:400]
            await db.flush()
            await trim_sync_runs(db, user_id)
            await db.commit()
            return
        raise ValueError("采集没有返回成功结果")
    collected_at = datetime.fromisoformat(result["collected_at"])
    if collected_at.tzinfo is None:
        raise ValueError("采集时间必须包含时区")
    metric_date = collected_at.astimezone(ZoneInfo("Asia/Shanghai")).date()
    works = result["works"]
    if not isinstance(works, list):
        raise ValueError("作品列表无效")
    seen: set[str] = set()
    for work in works:
        platform_id = str(work["platform_content_id"])
        if account.platform == "xiaohongshu":
            valid_id = bool(re.fullmatch(r"[0-9a-f]{24}", platform_id))
        elif account.platform == "kuaishou":
            valid_id = bool(re.fullmatch(r"[A-Za-z0-9_-]{1,100}", platform_id))
        else:
            valid_id = platform_id.isascii() and platform_id.isdigit() and len(platform_id) <= 100
        if not valid_id:
            raise ValueError("平台作品标识无效")
        if platform_id in seen:
            continue
        seen.add(platform_id)
        data = PublishedContentWrite(platform=account.platform, title=work["title"], published_at=work["published_at"])
        if data.published_at > collected_at:
            raise ValueError("未公开作品不能作为已发布内容")
        content = await db.scalar(select(PublishedContent).where(
            PublishedContent.user_id == run.user_id, PublishedContent.account_id == account.id,
            PublishedContent.platform_content_id == platform_id,
        ))
        if content is None:
            content = PublishedContent(user_id=run.user_id, account_id=account.id,
                                       platform_content_id=platform_id, **data.model_dump())
            db.add(content)
            await db.flush()
        else:
            content.title = data.title
            # 已有快照日期不能因平台返回的时区/发布时间变化而失效。
            content.published_at = data.published_at
        run.content_count += 1
        values = MetricWrite(metric_date=metric_date, **{key: work.get("metrics", {}).get(key) for key in METRIC_FIELDS})
        if not any(getattr(values, key) is not None for key in METRIC_FIELDS):
            continue
        metric = await db.scalar(select(ContentMetric).where(
            ContentMetric.content_id == content.id, ContentMetric.metric_date == metric_date,
        ))
        # 同日手动修正受保护；自动采集也不会用缺失字段覆盖已有真实数据。
        if metric is not None and metric.source == "manual":
            continue
        if metric is None:
            metric = ContentMetric(content_id=content.id, metric_date=metric_date, source=f"{account.platform}_creator")
            db.add(metric)
        for key in METRIC_FIELDS:
            value = getattr(values, key)
            if value is not None:
                setattr(metric, key, value)
        metric.collected_at = collected_at
        raw_updated = work.get("platform_updated_at")
        metric.platform_updated_at = datetime.fromisoformat(raw_updated) if raw_updated else None
        run.metric_count += 1
    run.status = "completed"
    run.message = f"同步 {run.content_count} 篇作品，更新 {run.metric_count} 条快照；缺失指标保留为空，同日人工记录不覆盖。平台指标可能延迟更新"
    if account.platform == "kuaishou":
        run.message += "；快手仅提供播放、点赞、评论，发布时间使用平台上传时间；范围沿用后台默认筛选"
    if result.get("truncated"):
        run.message += "；已达到分页上限，历史作品可能未全部同步"
    if result.get("skipped"):
        run.message += f"；跳过 {result['skipped']} 条无效或未公开作品"
    await db.flush()
    await trim_sync_runs(db, user_id)
    await db.commit()


async def delete_run(db: AsyncSession, user_id: int, run_id: int) -> None:
    await lock_user_history(db, user_id)
    run = await db.scalar(select(MetricsSyncRun).where(MetricsSyncRun.id == run_id,
                                                      MetricsSyncRun.user_id == user_id).with_for_update())
    if run is None:
        raise AppError(404, "sync_run_not_found", "同步记录不存在")
    if run.status in ACTIVE_SYNC_STATUSES:
        raise AppError(409, "sync_run_active", "同步任务尚未结束，完成后才能删除记录")
    from app.models.automation import AutomationRun
    if run.automation_run_id and await db.scalar(select(AutomationRun.id).where(
        AutomationRun.id == run.automation_run_id,
        AutomationRun.status.in_(("queued", "running", "waiting_sync")),
    )):
        raise AppError(409, "sync_run_active", "自动化任务仍需读取此同步结果，任务结束后才能删除")
    await db.delete(run)
    await db.commit()
