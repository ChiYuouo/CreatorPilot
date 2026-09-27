"""Agent 分析工具参数，仅包含业务范围和引用 ID。"""

from typing import Literal

from pydantic import Field

from app.schemas.agent_operations import PositiveId, ToolArguments
from app.schemas.analytics import ReportGenerationRequest


class ListContentsArguments(ToolArguments):
    account_id: PositiveId | None = None
    platform: Literal["douyin", "kuaishou", "xiaohongshu", "bilibili", "tencent", "youtube"] | None = None
    days: Literal[7, 30, 90] | None = None
    offset: int = Field(default=0, ge=0, strict=True)
    limit: int = Field(default=20, ge=1, le=50, strict=True)


class ContentMetricsArguments(ToolArguments):
    content_id: PositiveId
    limit: int = Field(default=10, ge=1, le=60, strict=True)


class SyncMetricsArguments(ToolArguments):
    account_id: PositiveId


class SyncStatusArguments(ToolArguments):
    sync_run_id: PositiveId


class GenerateReportArguments(ReportGenerationRequest):
    account_ids: list[PositiveId] = Field(default_factory=list, max_length=20)


class AnalysisRunArguments(ToolArguments):
    analysis_run_id: PositiveId


class ListReportsArguments(ToolArguments):
    limit: int = Field(default=20, ge=1, le=50, strict=True)
    offset: int = Field(default=0, ge=0, strict=True)


class ReportArguments(ToolArguments):
    report_id: PositiveId
