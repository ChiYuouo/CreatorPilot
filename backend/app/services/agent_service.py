"""Agent 会话服务：短期记忆（Redis）+ 图调度。

职责边界：
- 会话历史按 user_id + session_id 隔离，存 Redis，TTL 7 天；
- 历史条数按 agent_history_limit 截断，控制 token 成本；
- 图执行通过事件队列边跑边吐（asyncio.Queue），API 层只消费；
- LLM/图异常统一转为 error 事件 + 结束流，不让 SSE 半路裸断。

与 FastAPI 解耦：Agent 图不依赖数据库，业务工具按当前请求注入用户与会话工厂。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import redis.asyncio as aioredis

from app.agents import (
    CONFIG_EMITTER_KEY,
    EventEmitter,
    build_agent_graph,
    build_default_tool_registry,
)
from app.core.config import settings
from app.llm import LLMClient
from app.llm.errors import LLMError
from app.agents.registry import AgentToolFactory, BUSINESS_TOOL_NAMES
from app.services.agent_operation_service import AgentOperationService
from app.services.agent_analytics_service import AgentAnalyticsService
from app.services.agent_automation_service import AgentAutomationService

_SESSION_KEY_PREFIX = "agent:session"


class AgentService:
    """Agent 对话服务（每个实例绑定一个 LLM 客户端与图）。"""

    def __init__(
        self,
        llm: LLMClient,
        redis: aioredis.Redis,
        *,
        max_tool_rounds: int | None = None,
        history_limit: int | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self.llm = llm
        self.redis = redis
        if session_factory is None:
            from app.db.session import SessionLocal
            session_factory = SessionLocal
        self._session_factory = session_factory
        self._history_limit = history_limit or settings.agent_history_limit
        self._registry = build_default_tool_registry()
        self._graph = build_agent_graph(
            llm, self._registry, max_tool_rounds or settings.agent_max_tool_rounds
        )

    # ------------------------------------------------------------ 会话记忆

    def _session_key(self, user_id: int, session_id: str) -> str:
        return f"{_SESSION_KEY_PREFIX}:{user_id}:{session_id}"

    def _operation_context_key(self, user_id: int, session_id: str) -> str:
        return f"agent:operation-context:{user_id}:{session_id}"

    async def delete_session(self, user_id: int, session_id: str) -> None:
        """按用户删除聊天历史及工具记忆，不影响已创建的业务任务。"""
        await self.redis.delete(
            self._session_key(user_id, session_id),
            self._operation_context_key(user_id, session_id),
        )

    async def get_history(self, user_id: int, session_id: str) -> list[dict[str, Any]]:
        """读取会话历史；数据损坏时按空处理（失败关闭）。"""
        raw = await self.redis.get(self._session_key(user_id, session_id))
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []
        return [m for m in data if isinstance(m, dict) and m.get("role")]

    async def _save_history(
        self, user_id: int, session_id: str, messages: list[dict[str, Any]]
    ) -> None:
        await self.redis.set(
            self._session_key(user_id, session_id),
            json.dumps(messages, ensure_ascii=False),
            ex=settings.agent_session_ttl_seconds,
        )

    # ------------------------------------------------------------ 执行

    async def run(
        self,
        user_id: int,
        session_id: str,
        user_message: str,
    ) -> AsyncIterator[dict[str, Any]]:
        """执行一轮对话，产出事件流（含 session / stage / token / done / error）。"""
        history = await self.get_history(user_id, session_id)
        history.append({"role": "user", "content": user_message})
        history = history[-self._history_limit :]

        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

        async def emitter(event: dict[str, Any]) -> None:
            await queue.put(event)

        task = asyncio.create_task(self._run_graph_and_close(user_id, session_id, history, emitter, queue))
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event
        finally:
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    async def _run_graph_and_close(
        self,
        user_id: int,
        session_id: str,
        history: list[dict[str, Any]],
        emitter: EventEmitter,
        queue: "asyncio.Queue[dict[str, Any] | None]",
    ) -> None:
        """后台任务：跑图 → 存历史 → 发 done → 放结束哨兵。"""
        try:
            context_key = self._operation_context_key(user_id, session_id)
            raw_context = await self.redis.get(context_key)
            try:
                operation_context = json.loads(raw_context) if raw_context else []
            except (TypeError, json.JSONDecodeError):
                operation_context = []
            if not isinstance(operation_context, list):
                operation_context = []
            operation_context = [item for item in operation_context if isinstance(item, dict)][-6:]
            operations = AgentToolFactory(
                AgentOperationService(user_id, self._session_factory),
                AgentAnalyticsService(user_id, self._session_factory),
                AgentAutomationService(user_id, self._session_factory),
            )

            async def operation_emitter(event: dict[str, Any]) -> None:
                if event.get("type") == "tool_result" and event.get("name") in BUSINESS_TOOL_NAMES:
                    receipt = {"name": event["name"], "ok": event["ok"], "output": event["output"]}
                    if len(json.dumps(receipt, ensure_ascii=False)) <= 32_000:
                        operation_context.append(receipt)
                        del operation_context[:-6]
                        # 成功及失败回执立即保存，保留真实任务编号和查询失败原因。
                        await self.redis.set(context_key, json.dumps(operation_context, ensure_ascii=False),
                                             ex=settings.agent_session_ttl_seconds)
                await emitter(event)

            config: dict[str, Any] = {"configurable": {
                CONFIG_EMITTER_KEY: operation_emitter, "operation_tools_factory": operations.registry,
            }}
            result = await self._graph.ainvoke({"messages": history, "operation_context": list(operation_context)}, config=config)
            final_content = str(result.get("final_content", ""))
            new_messages = result.get("messages", history)
            await self._save_history(user_id, session_id, new_messages)
        except LLMError as exc:
            await queue.put({"type": "error", "message": str(exc)})
        except Exception as exc:  # noqa: BLE001 - SSE 流内兜底，避免裸断
            await queue.put({"type": "error", "message": f"Agent 执行异常：{exc}"})
        else:
            await queue.put(
                {"type": "done", "final_content": final_content}
            )
        finally:
            await queue.put(None)


def new_session_id() -> str:
    """生成会话 ID。"""
    return uuid.uuid4().hex
