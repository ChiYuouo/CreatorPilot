"""当前用户的分析业务操作；工具定义和注册在 agents 包。"""

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppError
from app.models.analytics import MetricsSyncRun, PublishedContent
from app.schemas.analytics import MetricRead, MetricsSyncRead, PublishedContentRead, ReportGenerationRequest
from app.schemas.automation import AutomationRunRead
from app.services import analytics_report_service, analytics_service, metrics_sync_service, publishing_service


class AgentAnalyticsService:
    def __init__(self, user_id: int, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.user_id = user_id
        self.session_factory = session_factory

    async def list_contents(self, account_id: int | None, platform: str | None, days: int | None,
                            offset: int, limit: int) -> dict[str, Any]:
        async with self.session_factory() as db:
            if account_id is not None:
                await publishing_service.get_account(db, self.user_id, account_id)
            filters = [PublishedContent.user_id == self.user_id]
            if account_id is not None:
                filters.append(PublishedContent.account_id == account_id)
            if platform:
                filters.append(PublishedContent.platform == platform)
            if days:
                now = datetime.now(timezone.utc)
                filters.extend([PublishedContent.published_at >= now - timedelta(days=days),
                                PublishedContent.published_at <= now])
            total = await db.scalar(select(func.count()).select_from(PublishedContent).where(*filters)) or 0
            rows = await db.scalars(select(PublishedContent).where(*filters)
                                    .options(selectinload(PublishedContent.metrics))
                                    .order_by(PublishedContent.published_at.desc(), PublishedContent.id.desc())
                                    .offset(offset).limit(limit))
            items = []
            for row in rows:
                latest = max(row.metrics, key=lambda metric: metric.metric_date, default=None)
                items.append({**PublishedContentRead.model_validate(row).model_dump(mode="json"),
                              "latest_metrics": MetricRead.model_validate(latest).model_dump(mode="json") if latest else None})
            return {"items": items, "total": total, "next_offset": offset + limit if offset + limit < total else None,
                    "message": "作品 ID 属于分析记录，与素材 ID、发布任务 ID 不同；指标为已保存的累计快照，不代表实时数据。"}

    async def get_metrics(self, content_id: int, limit: int) -> dict[str, Any]:
        async with self.session_factory() as db:
            content = await analytics_service.get_content(db, self.user_id, content_id)
            snapshots = sorted(content.metrics, key=lambda metric: metric.metric_date, reverse=True)
            return {"content": PublishedContentRead.model_validate(content).model_dump(mode="json"),
                    "metrics": [MetricRead.model_validate(item).model_dump(mode="json") for item in snapshots[:limit]],
                    "snapshot_count": len(snapshots), "message": "各日期指标是累计值，不可相加；null 表示缺失，不是零。"}

    async def sync_metrics(self, account_id: int) -> dict[str, Any]:
        async with self.session_factory() as db:
            run = await metrics_sync_service.create_run(db, self.user_id, account_id)
            return {"sync_run": MetricsSyncRead.model_validate(run).model_dump(mode="json"),
                    "message": "同步状态以 sync_run 为准；排队不代表已同步完成，请用同步运行 ID 查询。"}

    async def get_sync_status(self, sync_run_id: int) -> dict[str, Any]:
        async with self.session_factory() as db:
            await metrics_sync_service.expire_stale_runs(db, self.user_id)
            await db.commit()
            run = await db.scalar(select(MetricsSyncRun).where(
                MetricsSyncRun.id == sync_run_id, MetricsSyncRun.user_id == self.user_id,
            ))
            if run is None:
                raise AppError(404, "sync_run_not_found", "同步运行不存在")
            return MetricsSyncRead.model_validate(run).model_dump(mode="json")

    async def generate_report(self, **data: Any) -> dict[str, Any]:
        async with self.session_factory() as db:
            run = await analytics_report_service.create_report_run(db, self.user_id, ReportGenerationRequest(**data))
            return {"analysis_run": AutomationRunRead.model_validate(run).model_dump(mode="json"),
                    "message": "已创建或复用分析运行；排队、运行或等待同步不代表报告完成。使用分析运行 ID 查询进度。"}

    async def get_analysis_status(self, analysis_run_id: int) -> dict[str, Any]:
        async with self.session_factory() as db:
            run = await analytics_report_service.get_report_run(db, self.user_id, analysis_run_id)
            return AutomationRunRead.model_validate(run).model_dump(mode="json")

    async def list_reports(self, limit: int, offset: int) -> dict[str, Any]:
        async with self.session_factory() as db:
            page = await analytics_report_service.list_reports(db, self.user_id, limit, offset)
            return page.model_dump(mode="json")

    async def get_report(self, report_id: int) -> dict[str, Any]:
        async with self.session_factory() as db:
            report = await analytics_report_service.get_report(db, self.user_id, report_id)
            return report.model_dump(mode="json")
