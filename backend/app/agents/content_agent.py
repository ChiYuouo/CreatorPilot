"""Content Agent：内容生产专家，只开放创作辅助工具。"""

from app.agents.prompts import CONTENT_AGENT_SYSTEM
from app.agents.tool_agent import make_tool_agent_node
from app.agents.tools import ToolRegistry
from app.llm.client import LLMClient


def make_content_agent_node(llm: LLMClient, registry: ToolRegistry, max_tool_rounds: int):
    return make_tool_agent_node(llm, registry, max_tool_rounds,
                                stage="content_agent", system_prompt=CONTENT_AGENT_SYSTEM)
