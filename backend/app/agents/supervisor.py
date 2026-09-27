"""Supervisor Agent：理解意图、决策路由。

设计（对应规划书 5.1）：
- LLM 结构化决策，输出路由及发布、分析、自动化写入权限；
- 输入只含**用户侧消息清单**（见 _build_decision_messages 的历史教训）；
- 解析失败先换常规模式重试一次，仍失败才失败关闭降级 direct_reply；
- 对话按 LLM 结果走 content_agent / operations_agent / direct_reply；
"""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.agents.events import emit_event, stage_event
from app.agents.prompts import SUPERVISOR_SYSTEM
from app.agents.state import ROUTE_CONTENT_AGENT, ROUTE_DIRECT_REPLY, ROUTE_OPERATIONS_AGENT, AgentState
from app.llm.client import LLMClient
from app.llm.types import LLMResponse

_VALID_ROUTES = {ROUTE_CONTENT_AGENT, ROUTE_DIRECT_REPLY, ROUTE_OPERATIONS_AGENT}

# 决策输入里保留的最近用户消息条数与单条截断长度
_MAX_USER_TURNS = 8
_MAX_MESSAGE_CHARS = 120

_RETRY_HINT = (
    "上一次输出无法解析。请只输出一个 JSON 对象，"
    '例如 {"route": "content_agent", "reason": "理由"}，不要输出任何其他内容。'
)
_FALLBACK_REASON = "Supervisor 决策输出无法解析，降级为通用对话"


def _parse_route(resp: LLMResponse) -> tuple[str, str, bool, bool, bool] | None:
    """解析模型输出的路由 JSON；无法解析返回 None（由调用方决定重试或降级）。"""
    text = (resp.content or "").strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or data.get("route") not in _VALID_ROUTES:
        return None
    return (str(data["route"]), str(data.get("reason", ""))[:50],
            data["route"] == ROUTE_OPERATIONS_AGENT and data.get("allow_publish") is True,
            data["route"] == ROUTE_OPERATIONS_AGENT and data.get("allow_analysis") is True,
            data["route"] == ROUTE_OPERATIONS_AGENT and data.get("allow_automation") is True)


def _build_decision_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """构造 Supervisor 的决策输入：只有用户提问清单，不含 assistant 正文。

    把完整对话历史喂进来时，模型会看到
    「一个助手正在跟用户聊天」，于是接管助手角色直接续写回答、不再输出路由 JSON；
    历史越长越严重，且一旦出现 direct_reply 的回复，后续轮次会稳定降级、
    形成自我锁死。只给用户侧消息后问题消失，路由判断所需的指代线索依然完整。
    """
    user_messages = [m for m in messages if m.get("role") == "user"]
    user_messages = user_messages[-_MAX_USER_TURNS:]
    lines = [
        f"{index}. {str(m.get('content', '')).replace(chr(10), ' ')[:8000 if index == len(user_messages) else _MAX_MESSAGE_CHARS]}"
        for index, m in enumerate(user_messages, start=1)
    ]
    record = "\n".join(lines) if lines else "（无）"
    return [
        {"role": "system", "content": SUPERVISOR_SYSTEM},
        {
            "role": "user",
            "content": (
                f"用户提问记录（按时间从早到晚）：\n{record}\n\n"
                "请判断最新一条（最后一条）消息的意图，只输出路由 JSON。"
            ),
        },
    ]


def make_supervisor_node(llm: LLMClient):
    """工厂：绑定 LLM 的 supervisor 节点。"""

    async def supervisor_node(
        state: AgentState, config: RunnableConfig
    ) -> dict[str, Any]:
        await emit_event(config, stage_event("supervisor", "start"))
        messages = _build_decision_messages(state["messages"])

        # 第一次用 json_mode 强约束；失败换常规模式追加纠正提示重试一次
        parsed = _parse_route(await llm.chat(messages, temperature=0.0, json_mode=True))
        if parsed is None:
            retry_messages = [*messages, {"role": "user", "content": _RETRY_HINT}]
            parsed = _parse_route(await llm.chat(retry_messages, temperature=0.0))

        route, reason, allow_publish, allow_analysis, allow_automation = parsed or (ROUTE_DIRECT_REPLY, _FALLBACK_REASON, False, False, False)
        await emit_event(
            config, stage_event("supervisor", "done", route=route, reason=reason)
        )
        return {"route": route, "allow_publish": allow_publish, "allow_analysis": allow_analysis,
                "allow_automation": allow_automation}

    return supervisor_node
