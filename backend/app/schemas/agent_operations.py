"""业务工具参数：复用发布 DTO，只开放业务参数，不接受用户身份或路径。"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.publishing import BatchPublishCreate

PositiveId = Annotated[int, Field(strict=True, gt=0)]


class ToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ListAssetsArguments(ToolArguments):
    search: str = Field(default="", max_length=100)
    media_type: Literal["video", "image"] | None = None
    offset: int = Field(default=0, ge=0, strict=True)
    limit: int = Field(default=20, ge=1, le=50, strict=True)


class AssetArguments(ToolArguments):
    asset_id: PositiveId


class ListAccountsArguments(ToolArguments):
    platform: str | None = Field(default=None, max_length=32)


class PublishStatusArguments(ToolArguments):
    job_id: PositiveId


class ListJobsArguments(ToolArguments):
    limit: int = Field(default=20, ge=1, le=50, strict=True)


class SubmitPublishArguments(BatchPublishCreate):
    model_config = ConfigDict(extra="forbid")
    account_ids: list[PositiveId] = Field(min_length=1, max_length=30)
    asset_id: PositiveId
    image_asset_ids: list[PositiveId] = Field(default_factory=list, max_length=9)
