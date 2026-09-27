"""LLM 层异常。

所有 LLM 调用错误统一抛 LLMError，message 为中文、可定位。
API 层捕获后转换为统一响应格式 {code, message}，业务层不感知 HTTP。
"""

from __future__ import annotations


class LLMError(Exception):
    """LLM 调用失败（配置缺失、网络、鉴权、超时、模型返回异常等）。"""
