"""发布中心：用户隔离、素材存储和发布任务记录。"""

from __future__ import annotations

import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.models.publishing import MediaAsset, PlatformAccount, PublishJob, PublishPlan
from app.platforms.account_claim import account_claim_code
from app.platforms.registry import get_adapter, get_platform
from app.schemas.publishing import PublishingOverview

MAX_VIDEO_BYTES = 512 * 1024 * 1024
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm"}
CANCELLED_MESSAGE = "任务已取消，可以重新发布；请先到平台后台确认没有已经发布的相同作品"


async def list_accounts(db: AsyncSession, user_id: int) -> list[PlatformAccount]:
    return list((await db.scalars(select(PlatformAccount).where(PlatformAccount.user_id == user_id, PlatformAccount.is_deleted.is_(False)).order_by(PlatformAccount.id.desc()))).all())


async def create_account(db: AsyncSession, user_id: int, platform: str, account_name: str, claim_code: str, remark: str | None = None) -> PlatformAccount:
    try:
        get_adapter(platform)
    except ValueError as exc:
        raise AppError(422, "unsupported_platform", str(exc)) from exc
    existing = await db.scalar(select(PlatformAccount).where(PlatformAccount.platform == platform, PlatformAccount.account_name == account_name))
    if existing:
        if existing.user_id != user_id:
            raise AppError(409, "account_already_bound", "该本地账号已绑定其他用户")
        if not existing.is_deleted:
            return existing
    try:
        expected_code = account_claim_code(platform, account_name)
    except FileNotFoundError as exc:
        raise AppError(422, "account_login_missing", str(exc)) from exc
    if not secrets.compare_digest(expected_code, claim_code):
        raise AppError(403, "invalid_claim_code", "绑定码不正确，请在本机重新获取")
    if existing:
        existing.is_deleted = False
        existing.remark = (remark or "").strip() or None
        existing.status = "unchecked"
        account = existing
    else:
        account = PlatformAccount(user_id=user_id, platform=platform, account_name=account_name,
                                  remark=(remark or "").strip() or None, status="unchecked")
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return account


async def get_account(db: AsyncSession, user_id: int, account_id: int) -> PlatformAccount:
    account = await db.scalar(select(PlatformAccount).where(PlatformAccount.id == account_id, PlatformAccount.user_id == user_id, PlatformAccount.is_deleted.is_(False)))
    if account is None:
        raise AppError(404, "account_not_found", "平台账号不存在")
    return account


async def update_account_remark(db: AsyncSession, account: PlatformAccount, remark: str | None) -> PlatformAccount:
    account.remark = (remark or "").strip() or None
    await db.commit()
    await db.refresh(account)
    return account


async def bind_logged_in_account(db: AsyncSession, user_id: int, platform: str, account_name: str,
                                 remark: str | None, account_id: int | None) -> PlatformAccount:
    if account_id is not None:
        account = await get_account(db, user_id, account_id)
    else:
        account = await db.scalar(select(PlatformAccount).where(
            PlatformAccount.platform == platform, PlatformAccount.account_name == account_name,
        ))
        if account is not None and account.user_id != user_id:
            raise AppError(409, "account_already_bound", "该平台账号已绑定其他用户")
        if account is None:
            account = PlatformAccount(user_id=user_id, platform=platform, account_name=account_name)
            db.add(account)
        account.remark = (remark or "").strip() or account.remark
    account.is_deleted = False
    account.status = "valid"
    account.checked_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(account)
    return account


async def delete_account(db: AsyncSession, account: PlatformAccount) -> None:
    active = await db.scalar(select(PublishJob.id).where(
        PublishJob.account_id == account.id,
        or_(
            PublishJob.status.in_(["queued", "running", "cancel_requested"]),
            (PublishJob.scheduled_at.is_not(None)) & (PublishJob.status.in_(["submitted", "needs_review"])),
        ),
    ).limit(1))
    if active is not None:
        raise AppError(409, "account_has_active_jobs", "账号仍有未结束的发布或预约任务")
    account.is_deleted = True
    await db.commit()


async def clear_expired_accounts(db: AsyncSession, user_id: int) -> int:
    accounts = await list_accounts(db, user_id)
    count = 0
    for account in accounts:
        if account.status != "expired":
            continue
        active = await db.scalar(select(PublishJob.id).where(
            PublishJob.account_id == account.id,
            or_(
                PublishJob.status.in_(["queued", "running", "cancel_requested"]),
                (PublishJob.scheduled_at.is_not(None)) & (PublishJob.status.in_(["submitted", "needs_review"])),
            ),
        ).limit(1))
        if active is None:
            account.is_deleted = True
            count += 1
    await db.commit()
    return count


async def set_account_status(db: AsyncSession, account: PlatformAccount, valid: bool) -> PlatformAccount:
    account.status = "valid" if valid else "expired"
    account.checked_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(account)
    return account


async def list_assets(db: AsyncSession, user_id: int) -> list[MediaAsset]:
    return list((await db.scalars(select(MediaAsset).where(MediaAsset.user_id == user_id).order_by(MediaAsset.id.desc()))).all())


IMAGE_FORMATS = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP"}
MAX_IMAGE_BYTES = 20 * 1024 * 1024


def validate_image(path: Path, extension: str) -> None:
    try:
        with Image.open(path) as image:
            if image.format != IMAGE_FORMATS[extension] or image.width * image.height > 40_000_000:
                raise AppError(422, "invalid_image", "图片格式与扩展名不符，或像素超过 4000 万")
            image.verify()
        # JPEG 等格式的 verify 不会完整解码，再确认像素数据可读。
        with Image.open(path) as image:
            image.load()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
        raise AppError(422, "invalid_image", "图片无效或已损坏，请上传 JPG、PNG 或 WebP 图片") from exc


async def get_image_path(db: AsyncSession, user_id: int, asset_id: int) -> Path:
    return await get_asset_path(db, user_id, asset_id, media_type="image")


async def get_asset_path(db: AsyncSession, user_id: int, asset_id: int, *, media_type: str) -> Path:
    asset = await db.scalar(select(MediaAsset).where(MediaAsset.id == asset_id, MediaAsset.user_id == user_id))
    if asset is None or asset.media_type != media_type:
        raise AppError(404, "media_not_found", "素材不存在")
    path = Path(asset.storage_path).resolve()
    root = Path(settings.media_root).resolve() / str(user_id)
    if not path.is_relative_to(root) or not path.is_file():
        raise AppError(404, "media_not_found", "素材文件不存在")
    return path


async def save_asset(db: AsyncSession, user_id: int, upload: UploadFile) -> MediaAsset:
    filename = Path(upload.filename or "").name
    extension = Path(filename).suffix.lower()
    if extension not in VIDEO_EXTENSIONS and extension not in IMAGE_FORMATS:
        await upload.close()
        raise AppError(422, "invalid_media_type", "支持 MP4、MOV、M4V、WebM 视频及 JPG、PNG、WebP 图片")
    media_type = "image" if extension in IMAGE_FORMATS else "video"
    max_bytes = MAX_IMAGE_BYTES if media_type == "image" else MAX_VIDEO_BYTES
    root = Path(settings.media_root).resolve() / str(user_id)
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{uuid.uuid4().hex}{extension}"
    size = 0
    try:
        with target.open("wb") as output:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise AppError(413, "media_too_large", "图片不能超过 20 MB" if media_type == "image" else "视频不能超过 512 MB")
                output.write(chunk)
        if size == 0:
            raise AppError(422, "empty_media", "素材文件不能为空")
        if media_type == "image":
            await run_in_threadpool(validate_image, target, extension)
        asset = MediaAsset(user_id=user_id, filename=filename[:255], media_type=media_type, storage_path=str(target), size_bytes=size)
        db.add(asset)
        await db.commit()
        await db.refresh(asset)
        return asset
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()


async def validate_publish_images(db: AsyncSession, user_id: int, asset_id: int,
                                  image_asset_ids: list[int]) -> list[MediaAsset]:
    """图片模式显式传完整有序列表，asset_id 保留为首图以兼容旧视频契约。"""
    if not image_asset_ids:
        return []
    if len(image_asset_ids) > 9 or len(set(image_asset_ids)) != len(image_asset_ids) or image_asset_ids[0] != asset_id:
        raise AppError(422, "invalid_publish_images", "请选择 1–9 张不重复图片，素材 ID 必须为首图")
    assets = list((await db.scalars(select(MediaAsset).where(
        MediaAsset.id.in_(image_asset_ids), MediaAsset.user_id == user_id,
    ))).all())
    by_id = {asset.id: asset for asset in assets}
    if len(by_id) != len(image_asset_ids):
        raise AppError(404, "publish_input_not_found", "图片素材不存在")
    if any(asset.media_type != "image" for asset in assets):
        raise AppError(422, "invalid_publish_images", "图文发布只能选择图片，不能混入视频")
    return [by_id[id] for id in image_asset_ids]


def validate_image_platform(platform: str, image_asset_ids: list[int], title: str, description: str) -> None:
    if not image_asset_ids:
        return
    spec = get_platform(platform)
    if not spec.image_publish_supported:
        raise AppError(422, "image_publish_unsupported", f"{spec.name}暂不支持图文发布")
    if len(image_asset_ids) > spec.image_max_count:
        raise AppError(422, "invalid_publish_images", f"{spec.name}最多支持 {spec.image_max_count} 张图片")
    if len(title) > spec.image_title_max_length:
        raise AppError(422, "invalid_publish_title", f"{spec.name}图文标题最多 {spec.image_title_max_length} 字")
    body_length = len(title) + (1 + len(description) if description else 0) if platform == "kuaishou" else len(description)
    if body_length > spec.image_description_max_length:
        raise AppError(422, "invalid_publish_description", f"{spec.name}图文正文最多 {spec.image_description_max_length} 字")


async def has_pending_publish(db: AsyncSession, user_id: int, account_id: int,
                              asset_id: int, image_asset_ids: list[int]) -> bool:
    active = (await db.scalars(select(PublishJob).where(
        PublishJob.user_id == user_id, PublishJob.account_id == account_id,
        PublishJob.status.in_(["queued", "running", "cancel_requested", "submitted", "needs_review"]),
    ))).all()
    for job in active:
        previous = json.loads(job.image_asset_ids_json)
        if image_asset_ids:
            if set(previous) == set(image_asset_ids):
                return True
        elif not previous and job.asset_id == asset_id:
            return True
    return False


async def create_job(
    db: AsyncSession, user_id: int, account_id: int, asset_id: int,
    *, title: str, description: str = "", tags: list[str] | None = None,
    image_asset_ids: list[int] | None = None,
) -> PublishJob:
    await _lock_publish_accounts(db, user_id, [account_id])
    account = await get_account(db, user_id, account_id)
    if account.status != "valid":
        raise AppError(422, "account_not_ready", "请先检查平台账号登录态")
    asset = await db.scalar(select(MediaAsset).where(MediaAsset.id == asset_id, MediaAsset.user_id == user_id))
    if asset is None:
        raise AppError(404, "publish_input_not_found", "素材不存在")
    image_asset_ids = image_asset_ids or []
    await validate_publish_images(db, user_id, asset_id, image_asset_ids)
    if asset.media_type != "video" and not image_asset_ids:
        raise AppError(422, "image_publish_unsupported", "图文发布请传入完整有序图片列表")
    spec = get_platform(account.platform)
    title = title.strip()
    description = description.strip()
    validate_image_platform(account.platform, image_asset_ids, title, description)
    tags = [tag.strip().lstrip("#").strip() for tag in (tags or [])]
    if not title or len(title) > spec.title_max_length or "\n" in title:
        raise AppError(422, "invalid_publish_title", f"{spec.name}作品标题须为 1-{spec.title_max_length} 字且不能换行")
    if spec.description_required and not description:
        raise AppError(422, "description_required", f"{spec.name}要求填写描述")
    if len(tags) > spec.tags_max_count or any(not tag or len(tag) > 50 for tag in tags):
        raise AppError(422, "invalid_tags", "标签数量或长度不符合平台要求")
    if await has_pending_publish(db, user_id, account_id, asset_id, image_asset_ids):
        raise AppError(409, "duplicate_publish", "这份内容已提交发布，请先查看现有任务")
    job = PublishJob(
        user_id=user_id, account_id=account_id, asset_id=asset_id,
        image_asset_ids_json=json.dumps(image_asset_ids),
        platform=account.platform,
        title=title,
        description=description,
        tags_json=json.dumps(tags, ensure_ascii=False), status="queued",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def list_jobs(db: AsyncSession, user_id: int) -> list[PublishJob]:
    return list((await db.scalars(select(PublishJob).where(PublishJob.user_id == user_id).order_by(PublishJob.id.desc()).limit(100))).all())


async def cancel_job(db: AsyncSession, user_id: int, job_id: int) -> PublishJob:
    job = await db.scalar(select(PublishJob).where(PublishJob.id == job_id, PublishJob.user_id == user_id))
    if job is None:
        raise AppError(404, "publish_job_not_found", "发布任务不存在")
    if job.status not in ("queued", "running", "cancel_requested"):
        raise AppError(409, "publish_job_not_cancelable", "此任务已结束，无法取消")
    changed = await db.execute(
        update(PublishJob).where(PublishJob.id == job_id, PublishJob.status == job.status)
        .values(status="canceled", error_message=CANCELLED_MESSAGE)
    )
    await db.commit()
    await db.refresh(job)
    if changed.rowcount == 0:
        if job.status == "canceled":
            return job
        raise AppError(409, "publish_job_state_changed", "任务状态刚刚变化，请刷新后重试")
    return job


async def create_batch(
    db: AsyncSession, user_id: int, account_ids: list[int], asset_id: int,
    *, title: str, description: str, tags: list[str], scheduled_at: datetime | None,
    platform_options: dict[str, dict[str, int]], image_asset_ids: list[int] | None = None,
) -> tuple[PublishPlan, list[PublishJob]]:
    """保存发布计划和所有账号任务前，验证每一个发布目标。"""
    await _lock_publish_accounts(db, user_id, account_ids)
    if len(set(account_ids)) != len(account_ids):
        raise AppError(422, "duplicate_account", "同一账号不能重复选择")
    asset = await db.scalar(select(MediaAsset).where(MediaAsset.id == asset_id, MediaAsset.user_id == user_id))
    if asset is None:
        raise AppError(404, "publish_input_not_found", "素材不存在")
    image_asset_ids = image_asset_ids or []
    await validate_publish_images(db, user_id, asset_id, image_asset_ids)
    if asset.media_type != "video" and not image_asset_ids:
        raise AppError(422, "image_publish_unsupported", "图文发布请传入完整有序图片列表")
    if scheduled_at is not None:
        if scheduled_at.tzinfo is None:
            raise AppError(422, "invalid_schedule", "预约时间必须包含时区")
        lead = timedelta(hours=2, minutes=len(account_ids) * 10)
        if scheduled_at.astimezone(timezone.utc) <= datetime.now(timezone.utc) + lead:
            raise AppError(422, "invalid_schedule", f"预约时间须至少提前 {lead.total_seconds() / 3600:g} 小时，留出多账号上传时间")
    clean_title = title.strip()
    clean_description = description.strip()
    clean_tags = [tag.strip().lstrip("#").strip() for tag in tags]
    accounts: list[PlatformAccount] = []
    for account_id in account_ids:
        account = await get_account(db, user_id, account_id)
        if account.status != "valid":
            raise AppError(422, "account_not_ready", f"账号 {account.remark or account.account_name} 登录态不可用")
        spec = get_platform(account.platform)
        validate_image_platform(account.platform, image_asset_ids, clean_title, clean_description)
        if not clean_title or len(clean_title) > spec.title_max_length or "\n" in clean_title:
            raise AppError(422, "invalid_publish_title", f"{spec.name}作品标题须为 1-{spec.title_max_length} 字且不能换行")
        if spec.description_required and not clean_description:
            raise AppError(422, "description_required", f"{spec.name}要求填写描述")
        if len(clean_tags) > spec.tags_max_count or any(not tag or len(tag) > 50 for tag in clean_tags):
            raise AppError(422, "invalid_tags", f"{spec.name}标签数量或长度不符合要求")
        if spec.category_required and int(platform_options.get(account.platform, {}).get("tid", 0)) <= 0:
            raise AppError(422, "category_required", "B 站须选择有效分区 ID")
        if await has_pending_publish(db, user_id, account_id, asset_id, image_asset_ids):
            raise AppError(409, "duplicate_publish", f"账号 {account.remark or account.account_name} 已有这份素材的待处理任务")
        accounts.append(account)
    plan = PublishPlan(
        user_id=user_id, asset_id=asset_id, title=clean_title,
        image_asset_ids_json=json.dumps(image_asset_ids),
        description=clean_description, tags_json=json.dumps(clean_tags, ensure_ascii=False),
        scheduled_at=scheduled_at.astimezone(timezone.utc) if scheduled_at else None,
    )
    db.add(plan)
    await db.flush()
    jobs = [PublishJob(
        user_id=user_id, plan_id=plan.id, account_id=account.id, asset_id=asset_id,
        image_asset_ids_json=json.dumps(image_asset_ids),
        platform=account.platform, title=clean_title, description=clean_description,
        tags_json=json.dumps(clean_tags, ensure_ascii=False),
        options_json=json.dumps(platform_options.get(account.platform, {})),
        scheduled_at=plan.scheduled_at, status="queued",
    ) for account in accounts]
    db.add_all(jobs)
    await db.commit()
    for job in jobs:
        await db.refresh(job)
    return plan, jobs


async def _lock_publish_accounts(db: AsyncSession, user_id: int, account_ids: list[int]) -> None:
    """同账号提交串行校验，避免页面和 Agent 并发绕过重复发布检查。"""
    await db.execute(select(PlatformAccount.id).where(
        PlatformAccount.user_id == user_id, PlatformAccount.id.in_(account_ids),
    ).order_by(PlatformAccount.id).with_for_update())


async def enqueue_publish_jobs(db: AsyncSession, jobs: list[PublishJob]) -> None:
    """页面与 Agent 共用队列投递及失败记录；不自动重试不明确结果。"""
    from app.tasks.publishing import publish_job
    for job in jobs:
        try:
            publish_job.delay(job.id)
        except Exception:
            job.status = "failed"
            job.error_message = "发布任务未能进入队列，请检查 Worker 和 Redis"
    await db.commit()


async def submit_batch(db: AsyncSession, user_id: int, **data: Any) -> tuple[PublishPlan, list[PublishJob]]:
    plan, jobs = await create_batch(db, user_id, **data)
    await enqueue_publish_jobs(db, jobs)
    return plan, jobs


async def submit_job(db: AsyncSession, user_id: int, **data: Any) -> PublishJob:
    job = await create_job(db, user_id, **data)
    await enqueue_publish_jobs(db, [job])
    if job.status == "failed":
        raise AppError(503, "publish_queue_unavailable", job.error_message or "发布任务未能进入队列")
    return job


async def confirm_job(db: AsyncSession, user_id: int, job_id: int, *, published: bool) -> PublishJob:
    """用户在平台后台核对后记录结果；结束待核实状态。"""
    job = await db.scalar(select(PublishJob).where(PublishJob.id == job_id, PublishJob.user_id == user_id))
    if job is None:
        raise AppError(404, "publish_job_not_found", "发布任务不存在")
    if job.status not in ("submitted", "needs_review"):
        raise AppError(409, "publish_job_not_confirmable", "只有待核实任务可以确认结果")
    if published and job.scheduled_at and job.scheduled_at.replace(tzinfo=job.scheduled_at.tzinfo or timezone.utc) > datetime.now(timezone.utc):
        raise AppError(409, "schedule_not_reached", "预约时间尚未到达，请到平台后台管理定时作品")
    next_status = "confirmed" if published else "not_published"
    changed = await db.execute(
        update(PublishJob).where(PublishJob.id == job_id, PublishJob.status == job.status)
        .values(status=next_status, confirmed_at=datetime.now(timezone.utc), error_message=None)
    )
    if changed.rowcount == 0:
        await db.rollback()
        raise AppError(409, "publish_job_state_changed", "任务状态刚刚变化，请刷新后重试")
    await db.commit()
    await db.refresh(job)
    return job


async def delete_job(db: AsyncSession, user_id: int, job_id: int) -> None:
    """删除已确认或确定结束的任务记录，待核实记录必须先确认。"""
    job = await db.scalar(select(PublishJob).where(PublishJob.id == job_id, PublishJob.user_id == user_id))
    if job is None:
        raise AppError(404, "publish_job_not_found", "发布任务不存在")
    if job.status in ("queued", "running", "cancel_requested", "submitted", "needs_review"):
        raise AppError(409, "publish_job_not_deletable", "任务仍在进行或结果待核实，请先确认结果")
    await db.delete(job)
    await db.commit()


async def overview(db: AsyncSession, user_id: int) -> PublishingOverview:
    # 账号是软删除，统计必须和 list_accounts 用同一口径，否则删掉的账号还在计数
    accounts = await db.scalar(select(func.count(PlatformAccount.id)).where(
        PlatformAccount.user_id == user_id, PlatformAccount.is_deleted.is_(False),
    ))
    assets = await db.scalar(select(func.count(MediaAsset.id)).where(MediaAsset.user_id == user_id))
    pending = await db.scalar(select(func.count(PublishJob.id)).where(PublishJob.user_id == user_id, PublishJob.status.in_(["queued", "running", "cancel_requested"])))
    failed = await db.scalar(select(func.count(PublishJob.id)).where(PublishJob.user_id == user_id, PublishJob.status.in_(["failed", "submitted", "needs_review", "not_published"])))
    return PublishingOverview(account_count=accounts or 0, asset_count=assets or 0, pending_count=pending or 0, failed_count=failed or 0)
