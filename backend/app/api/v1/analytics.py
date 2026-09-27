"""数据分析接口：手工登记发布内容与每日累计指标。"""

from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.llm import LLMClient, get_llm_client
from app.schemas.analytics import (
    AnalyticsReport,
    AnalyticsReportPage,
    ContentWithMetrics,
    MetricRead,
    MetricWrite,
    PublishedContentWrite,
    MetricsSyncRequest,
    MetricsSyncRead,
    ReportGenerationRequest,
)
from app.schemas.automation import AutomationRunRead
from app.services import analytics_report_service, analytics_service
from app.services import metrics_sync_service

router = APIRouter()


@router.get("/sync-runs", response_model=list[MetricsSyncRead])
async def list_sync_runs(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> list[MetricsSyncRead]:
    return [MetricsSyncRead.model_validate(run) for run in await metrics_sync_service.list_runs(db, user.id)]


@router.post("/sync-runs", response_model=MetricsSyncRead, status_code=status.HTTP_202_ACCEPTED)
async def create_sync_run(request: MetricsSyncRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> MetricsSyncRead:
    return MetricsSyncRead.model_validate(await metrics_sync_service.create_run(db, user.id, request.account_id))


@router.delete("/sync-runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sync_run(run_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> None:
    await metrics_sync_service.delete_run(db, user.id, run_id)


@router.post("/reports/recent", response_model=AnalyticsReport)
async def recent_report(
    days: int = Query(default=30),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    llm: LLMClient = Depends(get_llm_client),
) -> AnalyticsReport:
    return await analytics_report_service.recent_contents_report(db, user.id, days, llm)


@router.post("/analysis-runs", response_model=AutomationRunRead, status_code=status.HTTP_202_ACCEPTED)
async def create_analysis_run(request: ReportGenerationRequest, user: User = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)) -> AutomationRunRead:
    return AutomationRunRead.model_validate(await analytics_report_service.create_report_run(db, user.id, request))


@router.get("/analysis-runs/{run_id}", response_model=AutomationRunRead)
async def get_analysis_run(run_id: int, user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)) -> AutomationRunRead:
    return AutomationRunRead.model_validate(await analytics_report_service.get_report_run(db, user.id, run_id))


@router.post("/reports/batch", response_model=AnalyticsReport)
async def batch_report(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
                       llm: LLMClient = Depends(get_llm_client)) -> AnalyticsReport:
    return await analytics_report_service.batch_contents_report(db, user.id, llm)


@router.get("/reports", response_model=AnalyticsReportPage)
async def list_reports(limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0),
                       user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> AnalyticsReportPage:
    return await analytics_report_service.list_reports(db, user.id, limit, offset)


@router.get("/reports/{report_id}", response_model=AnalyticsReport)
async def get_report(report_id: int, user: User = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)) -> AnalyticsReport:
    return await analytics_report_service.get_report(db, user.id, report_id)


@router.delete("/reports/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(report_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> None:
    await analytics_report_service.delete_report(db, user.id, report_id)


@router.get("/contents", response_model=list[ContentWithMetrics])
async def list_contents(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[ContentWithMetrics]:
    contents = await analytics_service.list_contents(db, user.id)
    return [ContentWithMetrics.model_validate(item) for item in contents]


@router.post("/contents", response_model=ContentWithMetrics, status_code=status.HTTP_201_CREATED)
async def create_content(
    request: PublishedContentWrite,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> ContentWithMetrics:
    content = await analytics_service.create_content(db, user.id, request)
    return ContentWithMetrics.model_validate(content)


@router.get("/contents/{content_id}", response_model=ContentWithMetrics)
async def get_content(
    content_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> ContentWithMetrics:
    content = await analytics_service.get_content(db, user.id, content_id)
    return ContentWithMetrics.model_validate(content)


@router.post("/contents/{content_id}/report", response_model=AnalyticsReport)
async def content_report(
    content_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    llm: LLMClient = Depends(get_llm_client),
) -> AnalyticsReport:
    return await analytics_report_service.single_content_report(db, user.id, content_id, llm)


@router.put("/contents/{content_id}", response_model=ContentWithMetrics)
async def update_content(
    content_id: int, request: PublishedContentWrite,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> ContentWithMetrics:
    content = await analytics_service.update_content(db, user.id, content_id, request)
    return ContentWithMetrics.model_validate(content)


@router.delete("/contents/{content_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_content(
    content_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> None:
    await analytics_service.delete_content(db, user.id, content_id)


@router.put("/contents/{content_id}/metrics", response_model=MetricRead)
async def save_metric(
    content_id: int, request: MetricWrite,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> MetricRead:
    metric = await analytics_service.save_metric(db, user.id, content_id, request)
    return MetricRead.model_validate(metric)


@router.delete("/contents/{content_id}/metrics/{metric_date}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_metric(
    content_id: int, metric_date: date,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> None:
    await analytics_service.delete_metric(db, user.id, content_id, metric_date)
