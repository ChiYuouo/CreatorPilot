"""LLM 层：统一模型客户端。业务代码禁止绕过本层直调模型 API。"""

from __future__ import annotations

from app.llm.client import LLMClient, merge_tool_call_deltas
from app.llm.errors import LLMError
from app.llm.types import (
    ContentDelta,
    LLMResponse,
    StreamEvent,
    ToolCall,
    ToolCallDelta,
)

__all__ = [
    "ContentDelta",
    "LLMClient",
    "LLMError",
    "LLMResponse",
    "StreamEvent",
    "ToolCall",
    "ToolCallDelta",
    "get_llm_client",
    "merge_tool_call_deltas",
]


def get_llm_client() -> LLMClient:
    """按全局配置构造 LLM 客户端（每次调用新建，便于测试替换）。"""
    from app.core.config import settings

    return LLMClient(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        timeout_seconds=settings.llm_timeout_seconds,
    )
