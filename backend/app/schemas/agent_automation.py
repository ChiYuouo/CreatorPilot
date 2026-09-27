"""自动化工具参数；计划沿用现有每周调度规则。"""

from typing import Any

from pydantic import ConfigDict, Field, field_validator, model_validator

from app.schemas.agent_operations import PositiveId, ToolArguments
from app.schemas.automation import AutomationTaskWrite


class ListAutomationArguments(ToolArguments):
    offset: int = Field(default=0, ge=0, strict=True)
    limit: int = Field(default=20, ge=1, le=50, strict=True)


class AutomationTaskArguments(ToolArguments):
    task_id: PositiveId


class AutomationRunArguments(ToolArguments):
    run_id: PositiveId


class ListAutomationRunsArguments(ListAutomationArguments):
    task_id: PositiveId | None = None


def validate_payload_ids(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("payload 必须为对象")
    ids = value.get("account_ids", [])
    if not isinstance(ids, list) or any(type(item) is not int or item <= 0 for item in ids):
        raise ValueError("账号 ID 必须为正整数")
    if "sync_first" in value and type(value["sync_first"]) is not bool:
        raise ValueError("sync_first 必须为布尔值")
    return value


class CreateAutomationArguments(AutomationTaskWrite):
    model_config = ConfigDict(extra="forbid", strict=True)
    timezone: str = "Asia/Shanghai"

    @field_validator("payload", mode="before")
    @classmethod
    def strict_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_payload_ids(value)


class AutomationChanges(ToolArguments):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    weekday: int | None = Field(default=None, ge=0, le=6, strict=True)
    hour: int | None = Field(default=None, ge=0, le=23, strict=True)
    minute: int | None = Field(default=None, ge=0, le=59, strict=True)
    timezone: str | None = None
    payload: dict[str, Any] | None = None

    @model_validator(mode="before")
    @classmethod
    def nonempty_changes(cls, value: Any) -> Any:
        if isinstance(value, dict) and (not value or any(item is None for item in value.values())):
            raise ValueError("至少提供一个修改字段，字段不能为 null")
        return value

    @field_validator("payload")
    @classmethod
    def strict_payload(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return validate_payload_ids(value) if value is not None else None


class UpdateAutomationArguments(AutomationTaskArguments):
    changes: AutomationChanges


class SetAutomationEnabledArguments(AutomationTaskArguments):
    enabled: bool = Field(strict=True)
