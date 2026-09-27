"""已发布内容与累计指标的用户隔离读写。"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppError
from app.models.analytics import ContentMetric, PublishedContent
from app.schemas.analytics import MetricWrite, PublishedContentWrite


async def list_contents(db: AsyncSession, user_id: int) -> list[PublishedContent]:
    result = await db.execute(
        select(PublishedContent)
        .where(PublishedContent.user_id == user_id)
        .options(selectinload(PublishedContent.metrics))
        .order_by(PublishedContent.published_at.desc(), PublishedContent.id.desc())
    )
    return list(result.scalars().all())


async def get_content(db: AsyncSession, user_id: int, content_id: int) -> PublishedContent:
    content = await db.scalar(
        select(PublishedContent)
        .where(PublishedContent.id == content_id, PublishedContent.user_id == user_id)
        .options(selectinload(PublishedContent.metrics))
    )
    if content is None:
        raise AppError(404, "published_content_not_found", "已发布内容不存在")
    return content


async def create_content(
    db: AsyncSession, user_id: int, data: PublishedContentWrite
) -> PublishedContent:
    content = PublishedContent(user_id=user_id, **data.model_dump())
    db.add(content)
    await db.commit()
    return await get_content(db, user_id, content.id)


async def update_content(
    db: AsyncSession, user_id: int, content_id: int, data: PublishedContentWrite
) -> PublishedContent:
    content = await get_content(db, user_id, content_id)
    if content.account_id is not None and data.platform != content.platform:
        raise AppError(422, "synced_platform_readonly", "同步作品的平台不可修改")
    if content.metrics and any(metric.metric_date < data.published_at.date() for metric in content.metrics):
        raise AppError(422, "published_after_metrics", "发布日期不能晚于已有指标日期")
    for key, value in data.model_dump().items():
        setattr(content, key, value)
    await db.commit()
    return await get_content(db, user_id, content_id)


async def delete_content(db: AsyncSession, user_id: int, content_id: int) -> None:
    content = await get_content(db, user_id, content_id)
    await db.delete(content)
    await db.commit()


async def save_metric(
    db: AsyncSession, user_id: int, content_id: int, data: MetricWrite
) -> ContentMetric:
    content = await get_content(db, user_id, content_id)
    if data.metric_date < content.published_at.date():
        raise AppError(422, "metric_before_publish", "指标日期不能早于发布日期")
    metric = next((item for item in content.metrics if item.metric_date == data.metric_date), None)
    if metric is None:
        metric = ContentMetric(content_id=content_id, **data.model_dump())
        db.add(metric)
    else:
        for key, value in data.model_dump().items():
            setattr(metric, key, value)
    metric.source = "manual"
    metric.collected_at = None
    metric.platform_updated_at = None
    await db.commit()
    await db.refresh(metric)
    return metric


async def delete_metric(
    db: AsyncSession, user_id: int, content_id: int, metric_date: date
) -> None:
    content = await get_content(db, user_id, content_id)
    metric = next((item for item in content.metrics if item.metric_date == metric_date), None)
    if metric is None:
        raise AppError(404, "metric_not_found", "该日期的指标不存在")
    await db.delete(metric)
    await db.commit()
