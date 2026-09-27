"""LLM 层共享类型。

约定：
- ToolCall.arguments 是模型返回的原始 JSON 字符串，消费方必须自行
  json.loads 并做失败关闭校验（模型输出一律视为不可信输入）。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ToolCall:
    """一次函数/工具调用请求。"""

    id: str
    name: str
    arguments: str


@dataclass
class LLMResponse:
    """非流式调用的结构化返回。"""

    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str | None = None


@dataclass
class ContentDelta:
    """流式输出的文本增量。"""

    text: str


@dataclass
class ToolCallDelta:
    """流式输出的工具调用增量片段（未合并，需消费方聚合）。"""

    index: int
    id: str | None
    name: str | None
    arguments: str


StreamEvent = ContentDelta | ToolCallDelta
