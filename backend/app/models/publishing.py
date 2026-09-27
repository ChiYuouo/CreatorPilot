"""Phase 6 平台账号、图片/视频素材与发布任务。"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class PlatformAccount(Base, TimestampMixin):
    __tablename__ = "platform_accounts"
    __table_args__ = (UniqueConstraint("platform", "account_name", name="uq_platform_account_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    account_name: Mapped[str] = mapped_column(String(100), nullable=False)
    remark: Mapped[str | None] = mapped_column(String(100))
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="unchecked")
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MediaAsset(Base, TimestampMixin):
    __tablename__ = "media_assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(16), nullable=False, default="video", server_default="video")
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)


class PublishPlan(Base, TimestampMixin):
    __tablename__ = "publish_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("media_assets.id"), nullable=False)
    image_asset_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]", server_default="[]")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PublishJob(Base, TimestampMixin):
    __tablename__ = "publish_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("platform_accounts.id"), nullable=False)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("publish_plans.id"), index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("media_assets.id"), nullable=False)
    image_asset_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]", server_default="[]")
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    options_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    error_message: Mapped[str | None] = mapped_column(String(500))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
