"""分析报告的数据准备与独立 Analytics Agent 调用。"""

from __future__ import annotations

import json

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.analytics_agent import generate_analytics_report
from app.core.exceptions import AppError
from app.llm.client import LLMClient
from app.llm.errors import LLMError
from app.models.analytics import ContentMetric, PublishedContent, SavedAnalyticsReport
from app.schemas.analytics import AnalyticsReport, AnalyticsReportPage, AnalyticsReportSummary, ReportGenerationRequest
from app.models.automation import AutomationRun
from app.services.analytics_service import get_content
from app.services.analytics_history_service import lock_user_history, trim_reports

_METRIC_FIELDS = ("views", "likes", "comments", "favorites", "shares", "follower_gain")


def _metric_data(metric: ContentMetric) -> dict[str, Any]:
    return {"metric_date": metric.metric_date.isoformat(), "source": metric.source,
            "collected_at": metric.collected_at.isoformat() if metric.collected_at else None,
            "platform_updated_at": metric.platform_updated_at.isoformat() if metric.platform_updated_at else None,
            **{key: getattr(metric, key) for key in _METRIC_FIELDS}}


def _group_rows(groups: dict[str, dict[str, Any]], label: str) -> list[dict[str, Any]]:
    return [
        {
            label: group_name,
            **values,
            **{key: values[key] if values["metric_coverage"][key] else None for key in _METRIC_FIELDS},
            "average_views_per_content": (round(values["views"] / values["metric_coverage"]["views"], 1)
                                          if values["metric_coverage"]["views"] else None),
        }
        for group_name, values in sorted(groups.items())
    ]


async def _run_report(llm: LLMClient, payload: dict[str, Any]) -> str:
    try:
        return await generate_analytics_report(llm, payload)
    except LLMError as exc:
        raise AppError(502, "analytics_report_failed", str(exc)) from exc


async def single_content_report(
    db: AsyncSession, user_id: int, content_id: int, llm: LLMClient
) -> AnalyticsReport:
    content = await get_content(db, user_id, content_id)
    ordered = sorted(content.metrics, key=lambda item: item.metric_date)
    if not any(any(getattr(metric, key) is not None for key in _METRIC_FIELDS) for metric in ordered):
        raise AppError(422, "no_metrics", "请先为这篇内容录入指标")
    payload = {
        "scope": "single_content",
        "content": {
            "title": content.title,
            "platform": content.platform,
            "published_at": content.published_at.isoformat(),
        },
        "snapshot_count": len(ordered),
        "snapshots_included": min(len(ordered), 60),
        "snapshots": [_metric_data(item) for item in ordered[-60:]],
    }
    return await _save_report(db, user_id, llm, payload, scope="single_content",
                              title=content.title, content_id=content_id, content_count=1)


async def recent_contents_report(
    db: AsyncSession, user_id: int, days: int, llm: LLMClient, account_ids: list[int] | None = None,
) -> AnalyticsReport:
    if days not in (7, 30, 90):
        raise AppError(422, "invalid_period", "仅支持近 7、30 或 90 天")
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    if account_ids:
        from app.services.automation_service import validate_accounts
        await validate_accounts(db, user_id, account_ids, sync=False)
    result = await db.execute(
        select(PublishedContent)
        .where(
            PublishedContent.user_id == user_id,
            PublishedContent.published_at >= cutoff,
            PublishedContent.published_at <= now,
            *([PublishedContent.account_id.in_(account_ids)] if account_ids else []),
        )
        .options(selectinload(PublishedContent.metrics))
        .order_by(PublishedContent.published_at)
    )
    contents = list(result.scalars().all())
    measured = [item for item in contents if item.metrics and any(
        getattr(max(item.metrics, key=lambda metric: metric.metric_date), key) is not None for key in _METRIC_FIELDS
    )]
    if not measured:
        raise AppError(422, "no_metrics", "所选时间范围内暂无可分析的内容指标")

    def empty_group() -> dict[str, Any]:
        return {"content_count": 0, **{key: 0 for key in _METRIC_FIELDS},
                "metric_coverage": {key: 0 for key in _METRIC_FIELDS}}
    weeks: dict[str, dict[str, Any]] = defaultdict(empty_group)
    platforms: dict[str, dict[str, Any]] = defaultdict(empty_group)
    ranked: list[dict[str, Any]] = []
    for item in measured:
        latest = max(item.metrics, key=lambda metric: metric.metric_date)
        week = item.published_at.date() - timedelta(days=item.published_at.weekday())
        for group in (weeks[week.isoformat()], platforms[item.platform]):
            group["content_count"] += 1
            for key in _METRIC_FIELDS:
                value = getattr(latest, key)
                if value is not None:
                    group[key] += value
                    group["metric_coverage"][key] += 1
        ranked.append({
            "title": item.title,
            "platform": item.platform,
            "published_at": item.published_at.isoformat(),
            "latest_snapshot": _metric_data(latest),
        })

    payload = {
        "scope": "recent_contents",
        "account_ids": account_ids or [],
        "window_days": days,
        "window_start_utc": cutoff.isoformat(),
        "window_end_utc": now.isoformat(),
        "registered_content_count": len(contents),
        "measured_content_count": len(measured),
        "excluded_without_metrics": len(contents) - len(measured),
        "weekly_by_publish_date": _group_rows(weeks, "week_start"),
        "by_platform": _group_rows(platforms, "platform"),
        "top_five_by_views": sorted(
            [item for item in ranked if item["latest_snapshot"]["views"] is not None],
            key=lambda item: item["latest_snapshot"]["views"], reverse=True
        )[:5],
        "comparison_note": "各内容采用各自最新的累计快照，快照日期与发布时长可能不同。",
        "missing_metrics_note": "null 表示平台未提供或未录入，不能当作 0；汇总仅统计有值记录，各指标覆盖数量见 metric_coverage。",
    }
    return await _save_report(
        db, user_id, llm, payload, scope="recent_contents", title=f"近 {days} 天汇总分析",
        content_count=len(measured),
        excluded_without_metrics=len(contents) - len(measured),
        days=days,
    )


async def _save_report(
    db: AsyncSession, user_id: int, llm: LLMClient, payload: dict[str, Any], **metadata: Any
) -> AnalyticsReport:
    snapshot = json.dumps(payload, ensure_ascii=False)
    # 数据已整理成快照，等待模型时不占用数据库事务。
    await db.commit()
    report = await _run_report(llm, payload)
    await lock_user_history(db, user_id)
    row = SavedAnalyticsReport(user_id=user_id, report=report, input_snapshot=snapshot, **metadata)
    db.add(row)
    await db.flush()
    await trim_reports(db, user_id)
    await db.commit()
    await db.refresh(row)
    return AnalyticsReport.model_validate(row)


async def batch_contents_report(
    db: AsyncSession, user_id: int, llm: LLMClient, account_ids: list[int] | None = None,
) -> AnalyticsReport:
    query = select(PublishedContent).where(PublishedContent.user_id == user_id)
    if account_ids:
        from app.services.automation_service import validate_accounts
        await validate_accounts(db, user_id, account_ids, sync=False)
        query = query.where(PublishedContent.account_id.in_(account_ids))
    result = await db.execute(query
                              .options(selectinload(PublishedContent.metrics))
                              .order_by(PublishedContent.published_at, PublishedContent.id))
    contents = list(result.scalars().all())
    if not contents:
        raise AppError(422, "no_contents", "请先保存已发布内容")
    rows = []
    for content in contents:
        ordered = sorted(content.metrics, key=lambda item: item.metric_date)
        has_metrics = any(getattr(metric, key) is not None for metric in ordered for key in _METRIC_FIELDS)
        rows.append({"id": content.id, "title": content.title, "platform": content.platform,
                     "published_at": content.published_at.isoformat(), "has_metrics": has_metrics,
                     "snapshots": [_metric_data(metric) for metric in ordered]})
    missing = sum(not row["has_metrics"] for row in rows)
    payload = {"scope": "batch_contents", "account_ids": account_ids or [], "content_count": len(rows), "without_metrics_count": missing,
               "contents": rows,
               "analysis_note": "一次分析全部作品，逐篇比较后给出总分析和建议；不同快照是累计值，不可相加。",
               "missing_metrics_note": "null 或空快照表示数据缺失，不等于零；无指标作品只分析元数据，不推测表现。"}
    return await _save_report(db, user_id, llm, payload, scope="batch_contents", title="全部已发布内容分析",
                              content_count=len(rows), without_metrics_count=missing)


async def list_reports(db: AsyncSession, user_id: int, limit: int, offset: int) -> AnalyticsReportPage:
    await lock_user_history(db, user_id)
    await trim_reports(db, user_id)
    await db.commit()
    total = await db.scalar(select(func.count()).select_from(SavedAnalyticsReport)
                            .where(SavedAnalyticsReport.user_id == user_id))
    # 历史列表不加载报告正文和完整输入快照。
    columns = [getattr(SavedAnalyticsReport, name) for name in AnalyticsReportSummary.model_fields]
    result = await db.execute(select(*columns).where(SavedAnalyticsReport.user_id == user_id)
                              .order_by(SavedAnalyticsReport.created_at.desc(), SavedAnalyticsReport.id.desc())
                              .limit(limit).offset(offset))
    return AnalyticsReportPage(items=[AnalyticsReportSummary.model_validate(dict(row))
                                     for row in result.mappings()], total=total or 0)


async def get_report(db: AsyncSession, user_id: int, report_id: int) -> AnalyticsReport:
    row = await db.scalar(select(SavedAnalyticsReport).where(SavedAnalyticsReport.id == report_id,
                                                            SavedAnalyticsReport.user_id == user_id))
    if row is None:
        raise AppError(404, "report_not_found", "报告不存在")
    return AnalyticsReport.model_validate(row)


async def delete_report(db: AsyncSession, user_id: int, report_id: int) -> None:
    await lock_user_history(db, user_id)
    row = await db.scalar(select(SavedAnalyticsReport).where(SavedAnalyticsReport.id == report_id,
                                                            SavedAnalyticsReport.user_id == user_id))
    if row is None:
        raise AppError(404, "report_not_found", "报告不存在")
    await db.delete(row)
    await db.commit()


async def create_report_run(db: AsyncSession, user_id: int, request: ReportGenerationRequest) -> AutomationRun:
    """创建一次性分析运行，复用后台分析执行器，不创建周期计划。"""
    from app.models.publishing import PlatformAccount
    from app.services.automation_service import validate_accounts

    await lock_user_history(db, user_id)
    payload = request.model_dump()
    accounts = sorted(request.account_ids)
    if request.scope == "single_content":
        content = await get_content(db, user_id, request.content_id)
        if accounts and accounts != [content.account_id]:
            raise AppError(422, "content_account_mismatch", "所选作品不属于指定账号")
        if request.sync_first:
            if content.account_id is None:
                raise AppError(422, "content_not_linked", "人工登记作品没有关联账号，不能自动同步")
            accounts = [content.account_id]
    if request.sync_first and not accounts:
        accounts = list((await db.scalars(select(PlatformAccount.id).where(
            PlatformAccount.user_id == user_id, PlatformAccount.is_deleted.is_(False),
        ).order_by(PlatformAccount.id))).all())
        if not accounts or len(accounts) > 20:
            raise AppError(422, "invalid_accounts", "先同步需要 1 至 20 个可用账号，请指定账号")
    await validate_accounts(db, user_id, accounts, sync=request.sync_first)
    payload["account_ids"] = accounts
    # 用户行锁串行化同用户创建；相同活动运行直接复用，不重复生成或同步。
    active = await db.scalars(select(AutomationRun).where(
        AutomationRun.user_id == user_id, AutomationRun.task_id.is_(None),
        AutomationRun.task_type == "analysis_report",
        AutomationRun.status.in_(("queued", "running", "waiting_sync")),
    ))
    for existing in active:
        if existing.payload == payload:
            await db.commit()
            return existing
    names = {"single_content": "单篇作品分析", "recent_contents": f"近 {request.days} 天分析", "batch_contents": "作品汇总分析"}
    run = AutomationRun(task_id=None, user_id=user_id, task_type="analysis_report", task_name=names[request.scope],
                        scheduled_for=datetime.now(timezone.utc), status="queued", payload=payload)
    db.add(run)
    await db.commit()
    from app.tasks.automation import execute_task
    try:
        execute_task.delay(run.id)
    except Exception:
        run.status = "failed"
        run.error_message = "分析任务未能入队，请检查 Redis 和报告 Worker 后重试"
        run.finished_at = datetime.now(timezone.utc)
        await db.commit()
    await db.refresh(run)
    return run


async def get_report_run(db: AsyncSession, user_id: int, run_id: int) -> AutomationRun:
    run = await db.scalar(select(AutomationRun).where(
        AutomationRun.id == run_id, AutomationRun.user_id == user_id,
        AutomationRun.task_type == "analysis_report",
    ))
    if run is None:
        raise AppError(404, "analysis_run_not_found", "分析运行不存在")
    return run
