"""Agent 对话路由（SSE 流式）。

路由保持轻薄：参数校验 + 事件流转，编排在 services/agent_service.py。
SSE 帧格式：`data: {JSON}\n\n`，事件结构见 app/agents/events.py。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Path, Response
from fastapi.responses import StreamingResponse

from app.core.deps import get_agent_service, get_current_user
from app.models.user import User
from app.schemas.agent import AgentChatRequest, AgentHistoryResponse
from app.services.agent_service import AgentService, new_session_id

router = APIRouter()


_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲，保证打字机效果
}


@router.post("/agent/chat")
async def agent_chat(
    request: AgentChatRequest,
    user: User = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
) -> StreamingResponse:
    """与 Agent 对话（SSE 流式返回事件流）。"""
    session_id = request.session_id or new_session_id()

    async def event_stream() -> AsyncIterator[str]:
        yield _sse_frame({"type": "session", "session_id": session_id})
        async for event in service.run(user.id, session_id, request.message):
            yield _sse_frame(event)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.get("/agent/sessions/{session_id}/messages")
async def agent_history(
    session_id: str,
    user: User = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
) -> AgentHistoryResponse:
    """读取会话历史（页面刷新后恢复上下文）。"""
    messages = await service.get_history(user.id, session_id)
    return AgentHistoryResponse(session_id=session_id, messages=messages)


@router.delete("/agent/sessions/{session_id}", status_code=204)
async def delete_agent_session(
    session_id: str = Path(min_length=1, max_length=64, pattern=r"^[^\W_]+$"),
    user: User = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
) -> Response:
    """删除当前用户的会话；重复删除也返回成功。"""
    await service.delete_session(user.id, session_id)
    return Response(status_code=204)


def _sse_frame(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
