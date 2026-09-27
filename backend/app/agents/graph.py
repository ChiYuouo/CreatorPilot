"""聊天图：Supervisor 路由到内容生成、业务操作或直答。

与 FastAPI 解耦：图的构造只依赖 LLM 客户端与工具注册中心，
调用方通过 RunnableConfig 注入事件回调（见 events.CONFIG_EMITTER_KEY）。
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.content_agent import make_content_agent_node
from app.agents.direct_reply import make_direct_reply_node
from app.agents.state import (
    ROUTE_CONTENT_AGENT,
    ROUTE_DIRECT_REPLY,
    ROUTE_OPERATIONS_AGENT,
    AgentState,
)
from app.agents.supervisor import make_supervisor_node
from app.agents.tools import ToolRegistry
from app.agents.tool_agent import make_tool_agent_node
from app.agents.prompts import OPERATIONS_AGENT_SYSTEM
from app.llm.client import LLMClient


def _route_of(state: dict) -> str:
    """条件路由：Supervisor 未给出合法路由时失败关闭为直答。"""
    route = state.get("route")
    if route not in (ROUTE_CONTENT_AGENT, ROUTE_DIRECT_REPLY, ROUTE_OPERATIONS_AGENT):
        return ROUTE_DIRECT_REPLY
    return route


def build_agent_graph(
    llm: LLMClient,
    registry: ToolRegistry,
    max_tool_rounds: int = 5,
) -> CompiledStateGraph:
    builder = StateGraph(AgentState)
    builder.add_node("supervisor", make_supervisor_node(llm))
    builder.add_node("content_agent", make_content_agent_node(llm, registry, max_tool_rounds))
    builder.add_node("direct_reply", make_direct_reply_node(llm))
    builder.add_node("operations_agent", make_tool_agent_node(
        llm, registry, max_tool_rounds, stage="operations_agent", system_prompt=OPERATIONS_AGENT_SYSTEM,
    ))

    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges(
        "supervisor",
        _route_of,
        {
            ROUTE_CONTENT_AGENT: "content_agent",
            ROUTE_DIRECT_REPLY: "direct_reply",
            ROUTE_OPERATIONS_AGENT: "operations_agent",
        },
    )
    builder.add_edge("content_agent", END)
    builder.add_edge("direct_reply", END)
    builder.add_edge("operations_agent", END)
    return builder.compile()
