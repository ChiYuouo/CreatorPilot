"""Agent 事件模型。

Agent 层对外（API/SSE）只通过事件流交互：
- 事件是纯 dict，不依赖 FastAPI / SSE 类型，保证 agents 包独立可测。
- emit 回调由调用方注入（经 LangGraph RunnableConfig 传递），无回调时静默跳过。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.runnables import RunnableConfig

# 事件发射回调：传入事件 dict，返回可等待对象
EventEmitter = Callable[[dict[str, Any]], Awaitable[None]]

# RunnableConfig.configurable 中携带 emit 回调的键名
CONFIG_EMITTER_KEY = "agent_emitter"


async def emit_event(config: RunnableConfig, event: dict[str, Any]) -> None:
    """向调用方注入的事件回调发射事件；未注入回调时静默跳过。"""
    configurable = config.get("configurable") or {}
    emitter: EventEmitter | None = configurable.get(CONFIG_EMITTER_KEY)
    if emitter is not None:
        await emitter(event)


def stage_event(stage: str, status: str, **extra: Any) -> dict[str, Any]:
    """聊天阶段事件：supervisor / content_agent / direct_reply。"""
    return {"type": "stage", "stage": stage, "status": status, **extra}


def token_event(text: str) -> dict[str, Any]:
    """文本增量事件（打字机效果）。"""
    return {"type": "token", "text": text}


def tool_call_event(call_id: str, name: str, arguments: str) -> dict[str, Any]:
    """模型发起一次工具调用。"""
    return {"type": "tool_call", "id": call_id, "name": name, "arguments": arguments}


def tool_result_event(call_id: str, name: str, ok: bool, output: Any) -> dict[str, Any]:
    """一次工具调用结束。"""
    return {"type": "tool_result", "id": call_id, "name": name, "ok": ok, "output": output}


def error_event(message: str) -> dict[str, Any]:
    """Agent 内部错误（不终止流的非致命错误也用它）。"""
    return {"type": "error", "message": message}


def done_event(final_content: str) -> dict[str, Any]:
    """本轮执行结束，携带完整最终回复文本。"""
    return {"type": "done", "final_content": final_content}
