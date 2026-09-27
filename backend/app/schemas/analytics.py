"""已发布内容、每日累计指标与分析结果 DTO。"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from typing import Annotated, Literal

Platform = Literal["xiaohongshu", "douyin", "kuaishou", "bilibili", "tencent", "youtube"]


class PublishedContentWrite(BaseModel):
    platform: Platform
    title: str = Field(min_length=1, max_length=255)
    published_at: datetime

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("标题不能为空")
        return value

    @field_validator("published_at")
    @classmethod
    def published_at_with_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("发布时间必须包含时区")
        return value


class PublishedContentRead(BaseModel):
    id: int
    account_id: int | None = None
    platform_content_id: str | None = None
    platform: Platform
    title: str
    published_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MetricWrite(BaseModel):
    metric_date: date
    views: int | None = Field(default=None, ge=0)
    likes: int | None = Field(default=None, ge=0)
    comments: int | None = Field(default=None, ge=0)
    favorites: int | None = Field(default=None, ge=0)
    shares: int | None = Field(default=None, ge=0)
    follower_gain: int | None = Field(default=None, ge=0)


class MetricRead(MetricWrite):
    source: str = "manual"
    collected_at: datetime | None = None
    platform_updated_at: datetime | None = None
    id: int
    content_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ContentWithMetrics(PublishedContentRead):
    metrics: list[MetricRead]


class AnalyticsReportSummary(BaseModel):
    id: int | None = None
    title: str = ""
    content_id: int | None = None
    created_at: datetime | None = None
    without_metrics_count: int = 0
    scope: str
    content_count: int
    excluded_without_metrics: int = 0
    days: int | None = None

    model_config = {"from_attributes": True}


class AnalyticsReport(AnalyticsReportSummary):
    report: str


class AnalyticsReportPage(BaseModel):
    items: list[AnalyticsReportSummary]
    total: int


class MetricsSyncRequest(BaseModel):
    account_id: int = Field(gt=0)


class ReportGenerationRequest(BaseModel):
    """一次分析的业务范围；默认与已有自动报告的全部作品分析兼容。"""

    model_config = ConfigDict(extra="forbid")
    scope: Literal["batch_contents", "recent_contents", "single_content"] = "batch_contents"
    account_ids: list[Annotated[int, Field(gt=0, strict=True)]] = Field(default_factory=list, max_length=20)
    content_id: int | None = Field(default=None, gt=0, strict=True)
    days: Literal[7, 30, 90] | None = None
    sync_first: bool = Field(default=False, strict=True)

    @field_validator("account_ids")
    @classmethod
    def valid_accounts(cls, value: list[int]) -> list[int]:
        if any(item <= 0 for item in value) or len(value) != len(set(value)):
            raise ValueError("账号 ID 必须为正数且不能重复")
        return value

    @model_validator(mode="after")
    def valid_scope(self) -> "ReportGenerationRequest":
        if self.scope == "single_content":
            if self.content_id is None or self.days is not None or len(self.account_ids) > 1:
                raise ValueError("单篇分析必须指定作品 ID，不接受天数或多个账号")
        elif self.content_id is not None:
            raise ValueError("仅单篇分析接受作品 ID")
        if self.scope == "recent_contents" and self.days is None:
            raise ValueError("近期分析必须指定 7、30 或 90 天")
        if self.scope != "recent_contents" and self.days is not None:
            raise ValueError("仅近期分析接受天数")
        return self


class MetricsSyncRead(BaseModel):
    id: int
    account_id: int
    status: Literal["queued", "running", "completed", "failed"]
    content_count: int
    metric_count: int
    message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
