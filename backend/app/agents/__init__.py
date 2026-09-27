"""聊天 Agent 与事件接口（Phase 2 起）。

LangGraph 编排：Supervisor 路由 → Content Agent / Operations Agent / Direct Reply。
本包与 FastAPI 层解耦：
- 模型调用统一依赖 app.llm，工具参数复用 schemas，不依赖数据库、Service 或 FastAPI；
- 对外输出纯 dict 事件流（events.py），由 API 层转为 SSE；
- 工具调用统一走 ToolRegistry（失败关闭）。
"""

from app.agents.events import CONFIG_EMITTER_KEY, EventEmitter
from app.agents.graph import build_agent_graph
from app.agents.state import ROUTE_CONTENT_AGENT, ROUTE_DIRECT_REPLY, ROUTE_OPERATIONS_AGENT, AgentState
from app.agents.tools import ToolRegistry, ToolResult, ToolSpec
from app.agents.registry import AgentToolFactory, build_default_tool_registry

__all__ = [
    "CONFIG_EMITTER_KEY",
    "EventEmitter",
    "ROUTE_CONTENT_AGENT",
    "ROUTE_DIRECT_REPLY",
    "ROUTE_OPERATIONS_AGENT",
    "AgentState",
    "AgentToolFactory",
    "ToolRegistry",
    "ToolResult",
    "ToolSpec",
    "build_agent_graph",
    "build_default_tool_registry",
]
