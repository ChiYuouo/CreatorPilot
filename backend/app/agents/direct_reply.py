"""Direct Reply 节点：通用对话，流式直答。"""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from app.agents.events import emit_event, stage_event, token_event
from app.agents.prompts import DIRECT_REPLY_SYSTEM
from app.agents.state import AgentState
from app.llm.client import LLMClient
from app.llm.types import ContentDelta


def make_direct_reply_node(llm: LLMClient):
    """工厂：绑定 LLM 的直答节点。"""

    async def direct_reply_node(
        state: AgentState, config: RunnableConfig
    ) -> dict[str, Any]:
        await emit_event(config, stage_event("direct_reply", "start"))
        messages = [
            {"role": "system", "content": DIRECT_REPLY_SYSTEM},
            *state["messages"],
        ]
        parts: list[str] = []
        async for event in llm.chat_stream(messages):
            if isinstance(event, ContentDelta) and event.text:
                parts.append(event.text)
                await emit_event(config, token_event(event.text))
        final_content = "".join(parts)
        await emit_event(config, stage_event("direct_reply", "done"))
        return {
            "final_content": final_content,
            "messages": [
                *state["messages"],
                {"role": "assistant", "content": final_content},
            ],
        }

    return direct_reply_node
