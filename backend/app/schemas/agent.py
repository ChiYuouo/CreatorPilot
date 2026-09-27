"""Agent 对话相关 DTO。"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class AgentChatRequest(BaseModel):
    """POST /agent/chat 请求体。"""

    session_id: str | None = Field(
        default=None,
        max_length=64,
        description="会话 ID；不传则由服务端新建",
    )
    message: str = Field(
        min_length=1,
        max_length=8000,
        description="用户消息",
    )

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not value.isalnum():
            raise ValueError("session_id 只能包含字母与数字")
        return value


class AgentHistoryResponse(BaseModel):
    """GET /agent/sessions/{session_id}/messages 响应。"""

    session_id: str
    messages: list[dict]
