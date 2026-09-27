"""发布中心接口。登录与发布均由独立平台进程执行。"""

import secrets
import time
import jwt

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.exceptions import AppError
from app.core.config import settings
from app.core.security import create_media_preview_token, decode_token
from app.models.user import User
from app.platforms.login_sessions import QR_CONFIRM_HINT_SECONDS, cancel_login, get_login, start_login
from app.platforms.publisher_process import run_publisher
from app.schemas.publishing import AccountCreate, AccountRead, AccountRemarkUpdate, AssetRead, BatchPublishCreate, BatchPublishRead, LoginSessionRead, LoginStart, PlatformRead, PublishConfirmation, PublishCreate, PublishJobRead, PublishingOverview
from app.platforms.registry import list_platforms
from app.services import publishing_service
from app.tasks.publishing import publish_job
from app.schemas.publishing import VideoPreviewRead

router = APIRouter()


@router.get("/platforms", response_model=list[PlatformRead])
async def platforms(user: User = Depends(get_current_user)) -> list[PlatformRead]:
    return [PlatformRead.model_validate({
        "key": spec.key, "name": spec.name,
        "title_max_length": spec.title_max_length,
        "description_required": spec.description_required,
        "tags_max_count": spec.tags_max_count,
        "category_required": spec.category_required,
        "metrics_sync_supported": spec.metrics_sync_supported,
        "image_publish_supported": spec.image_publish_supported,
        "image_max_count": spec.image_max_count,
        "image_title_max_length": spec.image_title_max_length,
        "image_description_max_length": spec.image_description_max_length,
    }) for spec in list_platforms()]


@router.get("/overview", response_model=PublishingOverview)
async def overview(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> PublishingOverview:
    return await publishing_service.overview(db, user.id)


@router.get("/accounts", response_model=list[AccountRead])
async def accounts(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> list[AccountRead]:
    return [AccountRead.model_validate(item) for item in await publishing_service.list_accounts(db, user.id)]


@router.post("/accounts", response_model=AccountRead, status_code=status.HTTP_201_CREATED)
async def add_account(data: AccountCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> AccountRead:
    item = await publishing_service.create_account(db, user.id, data.platform, data.account_name, data.claim_code, data.remark)
    return AccountRead.model_validate(item)


@router.patch("/accounts/{account_id}", response_model=AccountRead)
async def update_account_remark(account_id: int, data: AccountRemarkUpdate,
                                user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> AccountRead:
    account = await publishing_service.get_account(db, user.id, account_id)
    return AccountRead.model_validate(await publishing_service.update_account_remark(db, account, data.remark))


@router.post("/accounts/login-sessions", response_model=LoginSessionRead, status_code=status.HTTP_202_ACCEPTED)
async def start_account_login(data: LoginStart, user: User = Depends(get_current_user)) -> LoginSessionRead:
    try:
        session = start_login(user.id, data.platform, f"acct_{secrets.token_hex(8)}", data.remark)
    except ValueError as exc:
        raise AppError(422, "unsupported_platform", str(exc)) from exc
    return LoginSessionRead(id=session.id, status=session.status, platform=session.platform)


@router.post("/accounts/{account_id}/login-sessions", response_model=LoginSessionRead, status_code=status.HTTP_202_ACCEPTED)
async def restart_account_login(account_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> LoginSessionRead:
    account = await publishing_service.get_account(db, user.id, account_id)
    session = start_login(user.id, account.platform, account.account_name, account.remark, account.id)
    return LoginSessionRead(id=session.id, status=session.status, platform=session.platform)


@router.get("/login-sessions/{session_id}", response_model=LoginSessionRead)
async def login_session_status(session_id: str, response: Response,
                               remark: str | None = Query(default=None, max_length=100),
                               user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> LoginSessionRead:
    response.headers["Cache-Control"] = "no-store"
    session = get_login(session_id, user.id)
    if remark is not None and session.existing_account_id is None and session.account_id is None:
        session.remark = remark.strip() or None
    if session.status == "success" and session.account_id is None:
        async with session.bind_lock:
            if session.account_id is None:
                account = await publishing_service.bind_logged_in_account(
                    db, user.id, session.platform, session.account_name,
                    session.remark, session.existing_account_id,
                )
                session.account_id = account.id
    pending_hint = (session.status == "qrcode_ready" and session.qrcode_ready_at is not None
                    and time.monotonic() - session.qrcode_ready_at >= QR_CONFIRM_HINT_SECONDS)
    message = session.message or ("扫码后在手机上点击确认；如果长时间没有反应，可以关掉浏览器窗口重新登录。" if pending_hint else None)
    return LoginSessionRead(id=session.id, status=session.status, platform=session.platform,
                            qrcode_data_url=session.qrcode_data_url if session.status == "qrcode_ready" else None,
                            message=message, account_id=session.account_id)


@router.delete("/login-sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def stop_account_login(session_id: str, user: User = Depends(get_current_user)) -> None:
    cancel_login(session_id, user.id)


@router.post("/accounts/{account_id}/check", response_model=AccountRead)
async def check_account(account_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> AccountRead:
    account = await publishing_service.get_account(db, user.id, account_id)
    try:
        valid = bool((await run_publisher("check", platform=account.platform, account_name=account.account_name))["valid"])
    except RuntimeError as exc:
        raise AppError(503, "publisher_unavailable", str(exc)) from exc
    return AccountRead.model_validate(await publishing_service.set_account_status(db, account, valid))


@router.post("/accounts/check-all")
async def check_all_accounts(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    accounts = await publishing_service.list_accounts(db, user.id)
    checked: list[AccountRead] = []
    failed_ids: list[int] = []
    for account in accounts:
        try:
            valid = bool((await run_publisher("check", platform=account.platform, account_name=account.account_name))["valid"])
        except (RuntimeError, KeyError):
            failed_ids.append(account.id)
            continue
        checked.append(AccountRead.model_validate(await publishing_service.set_account_status(db, account, valid)))
    return {"accounts": checked, "failed_ids": failed_ids}


@router.delete("/accounts/expired")
async def clear_expired_accounts(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict[str, int]:
    return {"deleted_count": await publishing_service.clear_expired_accounts(db, user.id)}


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(account_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> None:
    account = await publishing_service.get_account(db, user.id, account_id)
    await publishing_service.delete_account(db, account)


@router.get("/assets", response_model=list[AssetRead])
async def assets(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> list[AssetRead]:
    return [AssetRead.model_validate(item) for item in await publishing_service.list_assets(db, user.id)]


@router.post("/assets", response_model=AssetRead, status_code=status.HTTP_201_CREATED)
async def upload_asset(file: UploadFile = File(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> AssetRead:
    return AssetRead.model_validate(await publishing_service.save_asset(db, user.id, file))


@router.get("/assets/{asset_id}/preview")
async def img_preview(asset_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> FileResponse:
    path = await publishing_service.get_image_path(db, user.id, asset_id)
    mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}[path.suffix.lower()]
    return FileResponse(path, media_type=mime, headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/assets/{asset_id}/video-preview", response_model=VideoPreviewRead)
async def video_preview(asset_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> VideoPreviewRead:
    await publishing_service.get_asset_path(db, user.id, asset_id, media_type="video")
    token = create_media_preview_token(user.id, asset_id)
    return VideoPreviewRead(url=f"/api/v1/publishing/assets/{asset_id}/video?token={token}",
                            expires_in=settings.media_preview_expire_seconds)


@router.head("/assets/{asset_id}/video", include_in_schema=False)
@router.get("/assets/{asset_id}/video")
async def stream_video(asset_id: int, token: str = Query(default=""), db: AsyncSession = Depends(get_db)) -> FileResponse:
    try:
        claims = decode_token(token)
        if claims.get("type") != "media_preview" or claims.get("asset_id") != asset_id or "exp" not in claims:
            raise ValueError("wrong preview token")
        user_id = int(claims["sub"])
    except (jwt.PyJWTError, KeyError, ValueError, TypeError) as exc:
        raise AppError(401, "invalid_preview_token", "预览凭证已失效，请重新打开预览") from exc
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise AppError(401, "invalid_preview_token", "预览凭证已失效，请重新登录")
    path = await publishing_service.get_asset_path(db, user_id, asset_id, media_type="video")
    mime = {".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm"}[path.suffix.lower()]
    return FileResponse(path, media_type=mime, headers={"Cache-Control": "private, no-store",
                                                      "X-Content-Type-Options": "nosniff"})


@router.get("/jobs", response_model=list[PublishJobRead])
async def jobs(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> list[PublishJobRead]:
    return [PublishJobRead.model_validate(item) for item in await publishing_service.list_jobs(db, user.id)]


@router.post("/jobs/{job_id}/cancel", response_model=PublishJobRead)
async def cancel_job(job_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> PublishJobRead:
    return PublishJobRead.model_validate(await publishing_service.cancel_job(db, user.id, job_id))


@router.post("/jobs/{job_id}/confirm", response_model=PublishJobRead)
async def confirm_job(job_id: int, data: PublishConfirmation, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> PublishJobRead:
    return PublishJobRead.model_validate(await publishing_service.confirm_job(
        db, user.id, job_id, published=data.result == "published",
    ))


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(job_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> None:
    await publishing_service.delete_job(db, user.id, job_id)


@router.post("/jobs", response_model=PublishJobRead, status_code=status.HTTP_202_ACCEPTED)
async def submit_job(data: PublishCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> PublishJobRead:
    job = await publishing_service.submit_job(
        db, user.id, account_id=data.account_id, asset_id=data.asset_id,
        title=data.title, description=data.description, tags=data.tags,
        image_asset_ids=data.image_asset_ids,
    )
    return PublishJobRead.model_validate(job)


@router.post("/plans", response_model=BatchPublishRead, status_code=status.HTTP_202_ACCEPTED)
async def submit_plan(data: BatchPublishCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> BatchPublishRead:
    plan, jobs = await publishing_service.submit_batch(
        db, user.id, account_ids=data.account_ids, asset_id=data.asset_id,
        title=data.title, description=data.description, tags=data.tags,
        image_asset_ids=data.image_asset_ids,
        scheduled_at=data.scheduled_at, platform_options=data.platform_options,
    )
    return BatchPublishRead(plan_id=plan.id, jobs=[PublishJobRead.model_validate(job) for job in jobs])
