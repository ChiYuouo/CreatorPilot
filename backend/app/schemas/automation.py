"""自动化任务与运行记录 DTO；任务类型的配置在此验证。"""

from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AccountPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_ids: list[int] = Field(default_factory=list, max_length=20)

    @field_validator("account_ids")
    @classmethod
    def valid_accounts(cls, value: list[int]) -> list[int]:
        if any(item <= 0 for item in value) or len(value) != len(set(value)):
            raise ValueError("账号 ID 必须为正数且不能重复")
        return value


class AnalysisReportPayload(AccountPayload):
    sync_first: bool = False


class MetricsSyncPayload(AccountPayload):
    account_ids: list[int] = Field(min_length=1, max_length=20)


class AutomationTaskWrite(BaseModel):
    task_type: Literal["analysis_report", "metrics_sync"] = "analysis_report"
    name: str = Field(min_length=1, max_length=100)
    frequency: Literal["weekly"] = "weekly"
    weekday: int = Field(ge=0, le=6)
    hour: int = Field(ge=0, le=23)
    minute: int = Field(ge=0, le=59)
    timezone: str = Field(min_length=1, max_length=64)
    payload: dict[str, Any]
    enabled: bool = True

    @model_validator(mode="after")
    def validate_payload(self) -> "AutomationTaskWrite":
        schema = {"analysis_report": AnalysisReportPayload,
                  "metrics_sync": MetricsSyncPayload}[self.task_type]
        self.payload = schema.model_validate(self.payload).model_dump()
        return self

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("任务名称不能为空")
        return value

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("无效的时区") from exc
        return value


class AutomationTaskRead(BaseModel):
    id: int
    task_type: str
    name: str
    frequency: str
    weekday: int
    hour: int
    minute: int
    timezone: str
    payload: dict[str, Any]
    enabled: bool
    next_run_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AutomationRunRead(BaseModel):
    id: int
    task_id: int | None
    task_type: str
    task_name: str
    scheduled_for: datetime
    status: Literal["queued", "running", "waiting_sync", "succeeded", "failed", "canceled"]
    payload: dict[str, Any]
    result: dict[str, Any] | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
