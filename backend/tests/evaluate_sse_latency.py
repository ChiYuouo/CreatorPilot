"""用本地 HTTP SSE、真实模型和真实会话服务测量响应延迟。"""

from __future__ import annotations

import asyncio
import json
import math
import socket
import sys
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import httpx
import uvicorn
from fastapi import FastAPI

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.api.v1.agent import router
from app.core.config import settings
from app.core.deps import get_agent_service, get_current_user
from app.llm.client import LLMClient
from app.services.agent_service import AgentService


class MemoryRedis:
    """本地存储替身，不参与 Redis 性能评测。"""
    def __init__(self):
        self.values = {}

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, ex=None):
        self.values[key] = value


def build_cases():
    return [("直接回复", text) for text in [
        "用一句话解释什么是质数。", "用一句话解释什么是二分查找。", "用一句话解释什么是数据库事务。",
        "用一句话解释 HTTP 请求。", "用一句话解释 Python 字典。", "用一句话介绍你自己。",
        "请简短回答，12 加 13 等于几？", "用一句话解释什么是递归。", "用一句话解释什么是缓存。",
        "用一句话解释什么是操作系统。",
    ]] + [("内容生成", text) for text in [
        "给晨跑视频写一个十字以内标题。", "给猫咪视频写一个十字以内标题。", "把标题改短：适合新手的五个做饭小技巧。",
        "给露营视频写一句开场白，不查平台规范。", "给读书分享写一句结尾互动问题。", "为旅行笔记推荐两个话题标签，不查平台规范。",
        "把这句文案润色得口语化：今天分享三个整理技巧。", "给咖啡探店写一个十字以内标题。",
        "给健身视频写一句结尾。", "为城市骑行视频写一个十字以内标题。",
    ]]


def percentile(values, p):
    """使用最近秩法计算分位数，保留统计口径。"""
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(len(ordered) * p) - 1)], 3)


def save_report(records):
    metrics = {}
    for key in ("first_event_seconds", "first_token_seconds", "total_seconds"):
        values = [r[key] for r in records if r.get(key) is not None and not r["error"]]
        metrics[key] = {"samples": len(values), "p50": percentile(values, 0.5), "p95": percentile(values, 0.95)}
    report = {"evaluated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(), "model": settings.llm_model,
              "scope": "本地 HTTP SSE，真实模型与 AgentService，内存替代 Redis，测试用户替代登录鉴权；并发 1；不含反向代理、平台业务或旧版本对照",
              "summary": {"planned": 20, "completed": len(records), "successful": sum(not r["error"] for r in records), "metrics": metrics}, "cases": records}
    output = BACKEND / "tests/evaluation_results/sse_latency.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown_report(report, output)
    return report["summary"]


def write_markdown_report(report, output):
    s = report["summary"]
    names = {"first_event_seconds": "首个有效阶段事件", "first_token_seconds": "首个非空内容片段", "total_seconds": "请求完整结束"}
    lines = ["# SSE 响应延迟评测", "", f"模型：{report['model']}；时间：{report['evaluated_at']}。", "",
             report["scope"] + "。", "", f"**完成 {s['completed']}/20 条请求，成功 {s['successful']} 条。**", "",
             "计时从客户端发起 HTTP 请求开始；session 事件不计作有效事件。分位数采用最近秩法，只统计成功请求。样本量较小，P95 仅描述本轮，不代表线上性能承诺。",
             "", "| 指标 | 样本数 | P50（秒） | P95（秒） |", "|---|---:|---:|---:|"]
    for key, label in names.items():
        value = s["metrics"][key]
        lines.append(f"| {label} | {value['samples']} | {value['p50']} | {value['p95']} |")
    lines += ["", "## 单条记录", "", "| 用例 | 类别 | 首事件（秒） | 首内容（秒） | 完整结束（秒） | 错误 |", "|---|---|---:|---:|---:|---|"]
    for r in report["cases"]:
        lines.append(f"| {r['id']} | {r['category']} | {r['first_event_seconds']} | {r['first_token_seconds']} | {r['total_seconds']} | {r['error'] or '无'} |")
    lines += ["", "无可复现的旧版本基线，本报告不能支持“从 X 秒降低到 Y 秒”或吞吐提升结论。",
              "", "在 backend 目录运行：`.venv/Scripts/python.exe -X utf8 tests/evaluate_sse_latency.py`。",
              "[原始 SSE 事件与耗时](sse_latency.json)", ""]
    output.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")


async def main():
    llm = LLMClient(settings.llm_base_url, settings.llm_api_key, settings.llm_model, settings.llm_timeout_seconds)
    service = AgentService(llm, MemoryRedis(), session_factory=object())
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=999999)
    app.dependency_overrides[get_agent_service] = lambda: service
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
    server_task = asyncio.create_task(server.serve(sockets=[sock]))
    records = []
    try:
        while not server.started:
            if server_task.done():
                await server_task
                raise RuntimeError("本地测试服务未启动")
            await asyncio.sleep(0.05)
        async with httpx.AsyncClient(timeout=180, trust_env=False) as client:
            for index, (category, message) in enumerate(build_cases(), 1):
                start = time.perf_counter()
                first_event, first_token, error = None, None, None
                events = []
                try:
                    async with client.stream("POST", f"http://127.0.0.1:{port}/api/v1/agent/chat", json={"message": message}) as response:
                        response.raise_for_status()
                        async for line in response.aiter_lines():
                            if not line.startswith("data: "):
                                continue
                            event = json.loads(line[6:])
                            elapsed = time.perf_counter() - start
                            events.append(event)
                            if event["type"] in ("stage", "token", "tool_call", "tool_result") and first_event is None:
                                first_event = round(elapsed, 3)
                            if event["type"] == "token" and event.get("text") and first_token is None:
                                first_token = round(elapsed, 3)
                            if event["type"] == "error":
                                error = event["message"]
                    if first_token is None or not any(e["type"] == "done" for e in events):
                        error = error or "未收到内容或完成事件"
                except Exception as exc:
                    error = str(exc)
                records.append({"id": f"latency_{index:03d}", "category": category, "message": message,
                                "first_event_seconds": first_event, "first_token_seconds": first_token,
                                "total_seconds": round(time.perf_counter() - start, 3), "error": error, "events": events})
                save_report(records)
                print(f"SSE 延迟进度 {index}/20", flush=True)
    finally:
        server.should_exit = True
        await server_task
        sock.close()
        await llm._raw.close()
    print(json.dumps(save_report(records), ensure_ascii=False), flush=True)
    return 0 if all(not r["error"] for r in records) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
