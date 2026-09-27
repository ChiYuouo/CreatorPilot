"""Agent 共享状态。

约定：
- messages 一律为 OpenAI 格式纯 dict（role/content/tool_calls...），
  不引入 langchain 消息类型，与 app.llm.client 保持一致。
- 图为线性执行（supervisor → 子节点 → END），节点返回整份新列表覆盖状态；
  操作工具的历史结果独立保存，不将内部 tool 消息混入聊天历史。
"""

from __future__ import annotations

from typing import Any, TypedDict

# Supervisor 可下发的路由
ROUTE_CONTENT_AGENT = "content_agent"
ROUTE_DIRECT_REPLY = "direct_reply"
ROUTE_OPERATIONS_AGENT = "operations_agent"


class AgentState(TypedDict, total=False):
    messages: list[dict[str, Any]]
    route: str
    final_content: str
    allow_publish: bool
    allow_analysis: bool
    allow_automation: bool
    operation_context: list[dict[str, Any]]
