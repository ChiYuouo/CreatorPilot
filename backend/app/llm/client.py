"""统一 LLM Client（OpenAI 兼容协议，覆盖 DeepSeek / Qwen 等）。

架构约束：
- 业务代码禁止直接调用模型 API，只能通过本模块（见项目规划书 4.3）。
- 模型返回内容一律视为不可信输入；ToolCall.arguments 为原始 JSON 字符串，
  由消费方负责校验。
- 失败关闭：配置缺失、鉴权失败、超时、网络错误统一抛 LLMError（中文信息）。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AuthenticationError,
    RateLimitError,
)
from openai import AsyncOpenAI

from app.llm.errors import LLMError
from app.llm.types import ContentDelta, LLMResponse, StreamEvent, ToolCall, ToolCallDelta


def merge_tool_call_deltas(deltas: list[ToolCallDelta]) -> list[ToolCall]:
    """将流式返回的工具调用增量片段聚合为完整 ToolCall 列表。

    OpenAI 兼容协议中，流式工具调用按 index 分片：
    id/name 只在首片出现，arguments 逐片追加。片段缺失时失败关闭抛 LLMError。
    """
    partials: dict[int, dict[str, Any]] = {}
    order: list[int] = []
    for d in deltas:
        slot = partials.setdefault(d.index, {"id": "", "name": "", "arguments": ""})
        if d.index not in order:
            order.append(d.index)
        if d.id:
            slot["id"] = d.id
        if d.name:
            slot["name"] = d.name
        slot["arguments"] += d.arguments or ""
    calls: list[ToolCall] = []
    for index in order:
        slot = partials[index]
        if not slot["id"] or not slot["name"]:
            raise LLMError(f"模型流式返回的工具调用不完整（index={index}），已放弃本次结果")
        calls.append(ToolCall(id=slot["id"], name=slot["name"], arguments=slot["arguments"]))
    return calls


class LLMClient:
    """OpenAI 兼容协议的统一模型客户端。

    chat        非流式调用，返回结构化 LLMResponse（含工具调用）。
    chat_stream 流式调用，逐步产出 ContentDelta / ToolCallDelta。
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 120.0,
        *,
        raw_client: AsyncOpenAI | None = None,
    ) -> None:
        if not base_url or not model:
            raise LLMError("LLM 配置不完整：请在 .env 中设置 LLM_BASE_URL / LLM_MODEL")
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        # raw_client 仅供测试注入桩对象；未提供时才创建真实连接。
        self._raw = raw_client or AsyncOpenAI(
            base_url=base_url,
            api_key=api_key or "EMPTY",
            timeout=timeout_seconds,
        )

    def _ensure_ready(self) -> None:
        """失败关闭：没有 key 就直接拒绝调用，不发无效请求。"""
        if not self.api_key:
            raise LLMError("LLM API Key 未配置：请在 backend/.env 中设置 LLM_API_KEY 后重启服务")

    def _build_kwargs(
        self,
        tools: list[dict[str, Any]] | None,
        temperature: float | None,
        max_tokens: int | None,
        json_mode: bool = False,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        if tools:
            kwargs["tools"] = tools
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if json_mode:
            # OpenAI 兼容协议：强约束模型只能输出合法 JSON 对象
            kwargs["response_format"] = {"type": "json_object"}
        return kwargs

    @staticmethod
    def _translate_error(exc: Exception) -> LLMError:
        """把 openai SDK 异常翻译成中文 LLMError。"""
        if isinstance(exc, AuthenticationError):
            return LLMError("LLM API Key 无效或已过期，请检查 backend/.env 中的 LLM_API_KEY")
        if isinstance(exc, RateLimitError):
            return LLMError("LLM 请求频率或额度超限，请稍后重试")
        if isinstance(exc, APITimeoutError):
            return LLMError("LLM 请求超时，请稍后重试或调大 LLM_TIMEOUT_SECONDS")
        if isinstance(exc, APIConnectionError):
            return LLMError("无法连接 LLM 服务，请检查 LLM_BASE_URL 与网络")
        if isinstance(exc, LLMError):
            return exc
        if isinstance(exc, APIError):
            return LLMError(f"LLM 服务返回错误：{exc}")
        return LLMError(f"LLM 调用发生未知错误：{exc}")

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        """非流式调用。json_mode=True 时要求模型只输出 JSON 对象。"""
        self._ensure_ready()
        try:
            resp = await self._raw.chat.completions.create(
                model=self.model,
                messages=messages,
                **self._build_kwargs(tools, temperature, max_tokens, json_mode),
            )
        except Exception as exc:  # noqa: BLE001 - 统一翻译为中文业务异常
            raise self._translate_error(exc) from exc

        if not resp.choices:
            raise LLMError("模型未返回任何候选结果（choices 为空）")
        choice = resp.choices[0]
        message = choice.message
        tool_calls = [
            ToolCall(
                id=tc.id,
                name=tc.function.name,
                arguments=tc.function.arguments or "",
            )
            for tc in (message.tool_calls or [])
        ]
        return LLMResponse(
            content=message.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
        )

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """流式调用。逐步 yield ContentDelta / ToolCallDelta。"""
        self._ensure_ready()
        try:
            stream = await self._raw.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True,
                **self._build_kwargs(tools, temperature, max_tokens),
            )
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    yield ContentDelta(text=delta.content)
                for tc in delta.tool_calls or []:
                    yield ToolCallDelta(
                        index=tc.index,
                        id=tc.id,
                        name=tc.function.name if tc.function else None,
                        arguments=(tc.function.arguments or "") if tc.function else "",
                    )
        except Exception as exc:  # noqa: BLE001 - 统一翻译为中文业务异常
            raise self._translate_error(exc) from exc
