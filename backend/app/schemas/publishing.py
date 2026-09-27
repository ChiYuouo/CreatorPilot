"""平台发布页面的数据契约。"""

import json
from datetime import datetime, timedelta
from typing import Annotated, Literal

from pydantic import BaseModel, Field, computed_field

from app.core.config import settings


class AccountCreate(BaseModel):
    platform: str = "douyin"
    account_name: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    claim_code: str = Field(pattern=r"^[0-9a-f]{16}$")
    remark: str | None = Field(default=None, max_length=100)


class LoginStart(BaseModel):
    platform: str = "douyin"
    remark: str | None = Field(default=None, max_length=100)


class AccountRemarkUpdate(BaseModel):
    remark: str | None = Field(default=None, max_length=100)


class LoginSessionRead(BaseModel):
    id: str
    status: str
    platform: str
    qrcode_data_url: str | None = None
    message: str | None = None
    account_id: int | None = None


class AccountRead(BaseModel):
    id: int
    platform: str
    account_name: str
    remark: str | None
    status: str
    checked_at: datetime | None
    created_at: datetime
    model_config = {"from_attributes": True}


class AssetRead(BaseModel):
    id: int
    media_type: Literal["video", "image"]
    filename: str
    size_bytes: int
    created_at: datetime
    model_config = {"from_attributes": True}


class VideoPreviewRead(BaseModel):
    url: str
    expires_in: int


class PlatformRead(BaseModel):
    key: str
    name: str
    title_max_length: int
    description_required: bool
    tags_max_count: int
    category_required: bool = False
    metrics_sync_supported: bool = False
    image_publish_supported: bool = False
    image_max_count: int = 0
    image_title_max_length: int = 20
    image_description_max_length: int = 1000


class PublishCreate(BaseModel):
    account_id: int = Field(gt=0)
    asset_id: int = Field(gt=0)
    image_asset_ids: list[Annotated[int, Field(gt=0)]] = Field(default_factory=list, max_length=9)
    title: str = Field(min_length=1, max_length=255)
    description: str = ""
    tags: list[str] = Field(default_factory=list, max_length=20)


class BatchPublishCreate(BaseModel):
    account_ids: list[int] = Field(min_length=1, max_length=30)
    asset_id: int = Field(gt=0)
    image_asset_ids: list[Annotated[int, Field(gt=0)]] = Field(default_factory=list, max_length=9)
    title: str = Field(min_length=1, max_length=255)
    description: str = ""
    tags: list[str] = Field(default_factory=list, max_length=20)
    scheduled_at: datetime | None = None
    platform_options: dict[str, dict[str, int]] = Field(default_factory=dict)


class PublishConfirmation(BaseModel):
    result: Literal["published", "not_published"]


class PublishJobRead(BaseModel):
    id: int
    platform: str
    title: str
    account_id: int
    plan_id: int | None
    asset_id: int
    description: str
    tags_json: str = Field(exclude=True)
    image_asset_ids_json: str = Field(exclude=True)
    status: Literal["queued", "running", "cancel_requested", "canceled", "submitted", "failed", "needs_review", "confirmed", "not_published"]
    error_message: str | None
    submitted_at: datetime | None
    confirmed_at: datetime | None
    scheduled_at: datetime | None
    created_at: datetime
    model_config = {"from_attributes": True}

    @computed_field
    @property
    def image_asset_ids(self) -> list[int]:
        return json.loads(self.image_asset_ids_json)

    @computed_field
    @property
    def tags(self) -> list[str]:
        return json.loads(self.tags_json)

    @computed_field
    @property
    def auto_stop_at(self) -> datetime | None:
        """未结束的任务会被自动停止的时间点，供前端显示倒计时。"""
        if self.status not in ("queued", "running"):
            return None
        return self.created_at + timedelta(seconds=settings.publish_timeout_seconds)


class PublishingOverview(BaseModel):
    account_count: int
    asset_count: int
    pending_count: int
    failed_count: int


class BatchPublishRead(BaseModel):
    plan_id: int
    jobs: list[PublishJobRead]
