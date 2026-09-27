"""后台发布任务；直接调用独立 Publisher 进程。"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.exceptions import AppError
from app.models.publishing import MediaAsset, PlatformAccount, PublishJob
from app.platforms.base import LoginExpired
from app.platforms.publisher_process import PublishCancelled, PublishTimeout, SubprocessPublisher
from app.services.publishing_service import CANCELLED_MESSAGE, get_asset_path, validate_publish_images, validate_image_platform
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


class ScheduleWindowMissed(RuntimeError):
    """当前平台预约已无法安全提交。"""


async def execute_publish_job(job_id: int) -> None:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as db:
            claim = await db.execute(
                update(PublishJob).where(PublishJob.id == job_id, PublishJob.status == "queued")
                .values(status="running").returning(PublishJob.id)
            )
            if claim.scalar_one_or_none() is None:
                await db.rollback()
                return
            await db.commit()
            job = await db.get(PublishJob, job_id)
            account = await db.get(PlatformAccount, job.account_id)
            asset = await db.get(MediaAsset, job.asset_id)
            # 先结束这个读事务：接下来要跑几十秒到几分钟的上传，事务一直挂着的话，
            # PostgreSQL 的 now()（= 事务开始时刻）会把收尾写入的 updated_at 记成上传前的旧时间，
            # 而"失联任务回收"要靠 updated_at 判断任务是否还在动。
            await db.commit()

            async def cancel_requested() -> bool:
                # 状态只要离开 running，就说明用户已取消或任务已被强制收尾，本机进程应立刻停止
                async with session_factory() as check_db:
                    current = await check_db.scalar(select(PublishJob.status).where(PublishJob.id == job_id))
                    return current != "running"

            try:
                if account is None or asset is None or account.user_id != job.user_id or asset.user_id != job.user_id:
                    raise RuntimeError("账号或素材已不可用")
                image_ids = json.loads(job.image_asset_ids_json)
                await validate_publish_images(db, job.user_id, job.asset_id, image_ids)
                validate_image_platform(job.platform, image_ids, job.title, job.description)
                image_paths = [str(await get_asset_path(db, job.user_id, id, media_type="image")) for id in image_ids]
                await db.commit()
                scheduled_at = job.scheduled_at
                if scheduled_at is not None:
                    scheduled_at = scheduled_at.replace(tzinfo=scheduled_at.tzinfo or timezone.utc)
                    if scheduled_at <= datetime.now(timezone.utc) + timedelta(hours=2):
                        raise ScheduleWindowMissed("预约时间已不足 2 小时，未向平台上传；请重新选择更晚的时间")
                result = await SubprocessPublisher().publish(job.platform, {
                    "account_name": account.account_name,
                    "video_path": asset.storage_path,
                    "media_type": "image" if image_ids else "video",
                    "image_paths": image_paths,
                    "title": job.title,
                    "description": job.description,
                    "tags": json.loads(job.tags_json),
                    "options": json.loads(job.options_json),
                    "scheduled_at": scheduled_at.isoformat() if scheduled_at else None,
                    # 有头运行，抖音弹出扫码或安全验证时可以在窗口里人工完成
                    "headless": False,
                }, cancel_requested=cancel_requested)
                if result["status"] == "login_expired":
                    raise LoginExpired("平台账号登录态已失效，本次没有上传任何内容")
                if result["status"] == "failed" and result.get("submission_attempted") is False:
                    raise AppError(422, "publish_form_failed", result.get("message", "平台表单填写失败，尚未提交"))
                if result["status"] != "submitted":
                    raise RuntimeError("上传器没有确认提交结果")
            except AppError as exc:
                # 素材检查发生在调用 Publisher 之前，确定尚未向平台上传。
                await db.execute(update(PublishJob).where(
                    PublishJob.id == job_id, PublishJob.status == "running",
                ).values(status="failed", error_message=str(exc)))
            except (PublishCancelled, PublishTimeout) as exc:
                logger.warning("发布任务已停止: job_id=%s", job_id)
                await db.execute(update(PublishJob).where(
                    PublishJob.id == job_id, PublishJob.status == "running",
                ).values(status="canceled", error_message=(
                    CANCELLED_MESSAGE if isinstance(exc, PublishCancelled)
                    else f"{exc}；确认平台没有重复作品后可以重新发布"
                )))
            except LoginExpired as exc:
                # 登录态失效时上传根本没开始，不存在"结果不明确"，也不该锁死重发
                logger.warning("账号登录态失效，未开始上传: job_id=%s", job_id)
                await db.execute(update(PublishJob).where(
                    PublishJob.id == job_id, PublishJob.status == "running",
                ).values(status="failed", error_message=f"{exc}；请到发布中心重新登录该账号后再提交"))
            except ScheduleWindowMissed as exc:
                await db.execute(update(PublishJob).where(
                    PublishJob.id == job_id, PublishJob.status == "running",
                ).values(status="failed", error_message=str(exc)))
            except Exception:
                logger.exception("素材发布失败: job_id=%s", job_id)
                await db.execute(update(PublishJob).where(
                    PublishJob.id == job_id, PublishJob.status == "running",
                ).values(status="needs_review", error_message=(
                    "发布结果不明确，请先到平台后台核实；为避免重复发布，不能直接重试这份内容"
                )))
            else:
                finished = await db.execute(update(PublishJob).where(
                    PublishJob.id == job_id, PublishJob.status == "running",
                ).values(status="submitted", submitted_at=datetime.now(timezone.utc)))
                if finished.rowcount == 0:
                    await db.execute(update(PublishJob).where(
                        PublishJob.id == job_id, PublishJob.status == "canceled",
                    ).values(status="needs_review", error_message="取消请求与平台提交同时发生，请到平台后台核实结果"))
            await db.commit()
    finally:
        await engine.dispose()


@celery_app.task(
    name="app.tasks.publishing.publish_job",
    # 业务超时先于 Celery 超时触发，留出杀进程和写库的余量
    time_limit=settings.publish_timeout_seconds + 300,
    soft_time_limit=settings.publish_timeout_seconds + 270,
)
def publish_job(job_id: int) -> None:
    asyncio.run(execute_publish_job(job_id))


STALE_JOB_MESSAGE = "本机发布进程已中断（Worker 停止或异常退出），任务已自动结束；请到平台后台确认没有相同作品后再重新发布"


async def reap_stale_publish_jobs() -> int:
    """回收没人管的 running 任务。

    只有 Worker 能把任务推进终态；Worker 被关掉或崩掉时，认领过的任务会永远停在 running。
    上传有自己的业务超时，所以超过「业务超时 + 余量」仍无进展的，一定是没人管了。
    """
    deadline = datetime.now(timezone.utc) - timedelta(seconds=settings.publish_timeout_seconds + 120)
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as db:
            reaped = await db.execute(update(PublishJob).where(
                PublishJob.status == "running", PublishJob.updated_at < deadline,
            ).values(status="canceled", error_message=STALE_JOB_MESSAGE))
            await db.commit()
            return reaped.rowcount
    finally:
        await engine.dispose()


@celery_app.task(name="app.tasks.publishing.reap_stale_jobs")
def reap_stale_jobs() -> None:
    count = asyncio.run(reap_stale_publish_jobs())
    if count:
        logger.warning("回收了 %s 个失联的发布任务", count)
