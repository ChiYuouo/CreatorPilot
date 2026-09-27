"""Analytics Agent：根据业务服务整理的指标生成报告。"""

from __future__ import annotations

import json
from typing import Any

from app.agents.prompts import ANALYTICS_AGENT_SYSTEM
from app.llm.client import LLMClient
from app.llm.errors import LLMError


async def generate_analytics_report(llm: LLMClient, payload: dict[str, Any]) -> str:
    response = await llm.chat(
        [
            {"role": "system", "content": ANALYTICS_AGENT_SYSTEM},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        temperature=0.2,
    )
    report = (response.content or "").strip()
    if not report:
        raise LLMError("模型没有返回分析报告，请重试")
    return report
