"""Tool Calling 框架。

安全约定（失败关闭）：
- 模型传入的 arguments 是不可信 JSON 字符串，统一在 execute 内解析与校验；
- 未知工具 / 参数非法 / handler 抛错，一律返回 {"ok": False, "output": 中文错误}，
  作为 tool 消息回喂给模型，让模型自行修正，不中断流程；
- 工具输出必须可 JSON 序列化（存入消息上下文）。
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from pydantic import BaseModel, ValidationError

# 工具执行结果：ok 表示是否成功，output 为回喂给模型的内容
ToolResult = dict[str, Any]

ToolHandler = Callable[..., Awaitable[Any]]


@dataclass
class ToolSpec:
    """一个可被模型调用的工具定义。"""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON 数据结构定义
    handler: ToolHandler
    argument_model: type[BaseModel] | None = None


class ToolRegistry:
    """工具注册中心：负责定义收集、OpenAI 工具 schema 导出、统一执行。"""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"工具重复注册：{spec.name}")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def to_openai_tools(self) -> list[dict[str, Any]]:
        """导出 OpenAI 兼容的 tools 参数。"""
        return [
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.parameters,
                },
            }
            for spec in self._tools.values()
        ]

    async def execute(self, name: str, arguments: str) -> ToolResult:
        """解析、校验并执行一次工具调用，永不抛异常（错误回喂模型）。"""
        spec = self.get(name)
        if spec is None:
            known = "、".join(self._tools) or "（无）"
            return {"ok": False, "output": f"未知工具 {name}，可用工具：{known}"}

        if arguments.strip():
            try:
                args = json.loads(arguments)
            except json.JSONDecodeError as exc:
                return {"ok": False, "output": f"工具 {name} 的参数不是合法 JSON：{exc}"}
        else:
            args = {}

        if not isinstance(args, dict):
            return {"ok": False, "output": f"工具 {name} 的参数必须是 JSON 对象"}

        required = spec.parameters.get("required", [])
        properties = spec.parameters.get("properties", {})
        missing = [key for key in required if key not in args]
        if missing:
            return {"ok": False, "output": f"工具 {name} 缺少必填参数：{missing}"}
        extra = [key for key in args if key not in properties]
        if extra:
            return {"ok": False, "output": f"工具 {name} 收到未定义参数：{extra}"}

        if spec.argument_model is not None:
            try:
                args = spec.argument_model.model_validate(args).model_dump()
            except ValidationError as exc:
                errors = [{"field": ".".join(map(str, item["loc"])), "message": item["msg"]}
                          for item in exc.errors()]
                return {"ok": False, "output": {"code": "invalid_arguments", "errors": errors}}

        try:
            output = await spec.handler(**args)
        except Exception as exc:  # noqa: BLE001 - 工具错误回喂模型
            return {"ok": False, "output": f"工具 {name} 执行失败：{exc}"}
        return {"ok": True, "output": output}


# ---------------------------------------------------------------- 内置工具


_WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]

PLATFORM_GUIDELINES: dict[str, dict[str, Any]] = {
    "xiaohongshu": {
        "platform": "xiaohongshu",
        "title_limit": "标题 20 字以内，前置强情绪/数字词",
        "body_limit": "正文 1000 字以内，分段短句，多用 emoji 分隔",
        "tags": "5-8 个话题标签，含 1 个大流量词 + 2 个精准词",
        "rhythm": "晚 18:00-22:00 发布效果更好，每周 3-5 篇",
        "style": "口语化、真实感、第一人称经验分享",
    },
    "douyin": {
        "platform": "douyin",
        "title_limit": "作品标题控制在 30 字以内，突出视频主题",
        "body_limit": "视频描述与作品标题独立，写发布页文案；不要把拍摄或口播脚本放进作品描述",
        "tags": "3-5 个话题标签，带热点话题优先",
        "rhythm": "午 12:00-14:00 / 晚 18:00-23:00 发布",
        "style": "强节奏、悬念前置、口语化",
    },
    "kuaishou": {
        "platform": "kuaishou",
        "title_limit": "标题简短、清楚地说明视频主题",
        "body_limit": "视频描述与标题分别生成，发布页主要使用描述",
        "tags": "最多 3 个相关话题标签",
        "rhythm": "发布时间由用户按受众活跃时段决定",
        "style": "自然口语化，突出视频内容",
    },
    "bilibili": {
        "platform": "bilibili",
        "title_limit": "标题 40 字以内，可用「｜」分隔主题与亮点",
        "body_limit": "简介 200 字内，正文信息密度可以更高",
        "tags": "5-10 个标签，覆盖分区词 + 精准词",
        "rhythm": "晚 17:00-22:00 发布，中长视频注重完播率",
        "style": "知识型、梗文化、结构完整（开头-干货-总结）",
    },
    "youtube": {
        "platform": "youtube",
        "title_limit": "标题 70 字符以内，含主关键词",
        "body_limit": "简介首行放核心信息与时间戳",
        "tags": "5-8 个标签，英文为主",
        "rhythm": "目标时区的晚高峰前 1-2 小时发布",
        "style": "标题党适度，开头 15 秒讲清价值",
    },
}


async def get_current_datetime() -> dict[str, Any]:
    """当前时间（含星期），供内容规划使用。"""
    now = datetime.now()
    return {
        "datetime": now.strftime("%Y-%m-%d %H:%M"),
        "weekday": _WEEKDAYS[now.weekday()],
    }


async def get_platform_guidelines(platform: str) -> dict[str, Any]:
    """平台内容规范要点。platform 取值见 guidelines 的 platform 字段。"""
    guidelines = PLATFORM_GUIDELINES.get(platform)
    if guidelines is None:
        supported = "、".join(PLATFORM_GUIDELINES)
        raise ValueError(f"不支持的平台 {platform}，支持：{supported}")
    return guidelines


def get_builtin_tool_specs() -> list[ToolSpec]:
    """内置工具定义；统一由 registry.py 注册。"""
    return [
        ToolSpec(
            name="get_current_datetime",
            description="获取当前日期时间与星期，用于内容排期与发布时间建议",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=get_current_datetime,
        ),
        ToolSpec(
            name="get_platform_guidelines",
            description="获取指定内容平台的创作规范要点（标题限制、正文限制、标签建议、发布时间、风格）",
            parameters={
                "type": "object",
                "properties": {"platform": {"type": "string", "enum": list(PLATFORM_GUIDELINES), "description": "平台标识"}},
                "required": ["platform"],
            },
            handler=get_platform_guidelines,
        ),
    ]
