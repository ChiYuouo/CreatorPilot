"""当前用户的素材、账号与发布业务操作；不定义或注册 Agent 工具。"""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.exceptions import AppError
from app.models.publishing import MediaAsset, PublishJob
from app.schemas.publishing import AccountRead, AssetRead, PublishJobRead
from app.platforms.registry import list_platforms
from app.services import publishing_service


class AgentOperationService:
    """绑定已鉴权用户，查询与提交复用现有发布业务入口。"""

    def __init__(self, user_id: int, session_factory: async_sessionmaker[AsyncSession]):
        self.user_id = user_id
        self.session_factory = session_factory

    async def list_assets(self, search: str, media_type: str | None, offset: int, limit: int) -> dict[str, Any]:
        filters = [MediaAsset.user_id == self.user_id]
        if search:
            filters.append(MediaAsset.filename.contains(search, autoescape=True))
        if media_type:
            filters.append(MediaAsset.media_type == media_type)
        async with self.session_factory() as db:
            total = await db.scalar(select(func.count()).select_from(MediaAsset).where(*filters)) or 0
            items = await db.scalars(select(MediaAsset).where(*filters).order_by(MediaAsset.id.desc()).offset(offset).limit(limit))
            return {"items": [AssetRead.model_validate(item).model_dump(mode="json") for item in items],
                    "total": total, "next_offset": offset + limit if offset + limit < total else None}

    async def get_asset(self, asset_id: int) -> dict[str, Any]:
        async with self.session_factory() as db:
            item = await db.scalar(select(MediaAsset).where(MediaAsset.id == asset_id, MediaAsset.user_id == self.user_id))
            if item is None:
                raise AppError(404, "asset_not_found", "素材不存在")
            return AssetRead.model_validate(item).model_dump(mode="json")

    async def list_accounts(self, platform: str | None) -> dict[str, Any]:
        async with self.session_factory() as db:
            items = await publishing_service.list_accounts(db, self.user_id)
            return {"items": [AccountRead.model_validate(item).model_dump(mode="json") for item in items
                              if platform is None or item.platform == platform]}

    async def list_platforms(self) -> dict[str, Any]:
        return {"items": [{"platform": spec.key, "name": spec.name, "title_max_length": spec.title_max_length,
                           "description_required": spec.description_required, "tags_max_count": spec.tags_max_count,
                           "category_required": spec.category_required,
                           "image_publish_supported": spec.image_publish_supported, "image_max_count": spec.image_max_count,
                           "image_title_max_length": spec.image_title_max_length,
                           "image_description_max_length": spec.image_description_max_length} for spec in list_platforms()]}

    async def list_jobs(self, limit: int) -> dict[str, Any]:
        async with self.session_factory() as db:
            items = await publishing_service.list_jobs(db, self.user_id)
            return {"items": [PublishJobRead.model_validate(item).model_dump(mode="json") for item in items[:limit]]}

    async def get_status(self, job_id: int) -> dict[str, Any]:
        async with self.session_factory() as db:
            job = await db.scalar(select(PublishJob).where(PublishJob.user_id == self.user_id, PublishJob.id == job_id))
            if job is None:
                raise AppError(404, "job_not_found", "发布任务不存在")
            return PublishJobRead.model_validate(job).model_dump(mode="json")

    async def submit_publish(self, **data: Any) -> dict[str, Any]:
        async with self.session_factory() as db:
            plan, jobs = await publishing_service.submit_batch(db, self.user_id, **data)
            return {"plan_id": plan.id, "jobs": [PublishJobRead.model_validate(job).model_dump(mode="json") for job in jobs],
                                "message": "任务已创建，状态以 jobs 为准；queued 仅表示排队，尚未上传完成。"}
