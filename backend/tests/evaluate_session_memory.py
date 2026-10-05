"""评测真实会话服务的隔离与截断逻辑；Redis 使用可控内存模拟。"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.core.config import settings
from app.services.agent_service import AgentService


class MemoryRedis:
    """记录 TTL 设置并模拟到期；不代表真实 Redis 集成验证。"""

    def __init__(self):
        self.values = {}
        self.expires = {}
        self.now = 0
        self.writes = []

    async def set(self, key, value, ex=None):
        self.values[key] = value
        self.expires[key] = self.now + ex if ex is not None else None
        self.writes.append({"key": key, "ttl": ex})

    async def get(self, key):
        expiration = self.expires.get(key)
        if expiration is not None and self.now >= expiration:
            self.values.pop(key, None)
        return self.values.get(key)

    async def delete(self, *keys):
        for key in keys:
            self.values.pop(key, None)


class RecordingGraph:
    def __init__(self):
        self.inputs = []

    async def ainvoke(self, state, config):
        self.inputs.append(state)
        emitter = config["configurable"]["agent_emitter"]
        await emitter({"type": "tool_result", "name": "get_asset", "ok": True,
                       "output": {"marker": state["messages"][-1]["content"]}})
        return {"messages": [*state["messages"], {"role": "assistant", "content": "模拟回复"}],
                "final_content": "模拟回复"}


def build_cases():
    return ([{"category": "跨用户隔离", "size": n} for n in range(1, 7)] +
            [{"category": "跨会话隔离", "size": n} for n in range(1, 7)] +
            [{"category": "并发读写隔离", "size": n} for n in (3, 5, 10, 20, 30, 50)] +
            [{"category": "定向删除隔离", "size": n} for n in range(1, 5)] +
            [{"category": "历史输入截断", "size": n} for n in (20, 25, 50, 100)] +
            [{"category": "TTL 设置与模拟到期", "size": n} for n in (0, 1)] +
            [{"category": "损坏历史兜底", "size": n} for n in (0, 1)])


def write_markdown_report(report, output):
    s = report["summary"]
    lines = ["# 会话记忆逻辑评测", "", f"评测时间：{report['evaluated_at']}。", "",
             f"**共 {s['total']} 条，通过 {s['passed']} 条，失败 {s['total'] - s['passed']} 条。**", "",
             "运行真实 AgentService；Redis 与图执行使用模拟接口。验证键隔离、读写删除范围、历史输入截断、TTL 参数和损坏数据兜底；不验证真实 Redis 服务到期、HTTP 鉴权或业务资源越权。",
             "内存接口立即返回，并发用例用于验证多会话调度后的数据归属，不构成真实网络并发压力或吞吐测试。",
             "", "| 分类 | 总数 | 通过 |", "|---|---:|---:|"]
    for category, value in s["categories"].items():
        lines.append(f"| {category} | {value['total']} | {value['passed']} |")
    lines += ["", "## 逐条记录", "", "| 用例 | 分类 | 参数 | 结果 | 说明 |", "|---|---|---:|---|---|"]
    for r in report["cases"]:
        detail = json.dumps(r["details"], ensure_ascii=False).replace("|", "\\|")
        lines.append(f"| {r['id']} | {r['category']} | {r['size']} | {'通过' if r['passed'] else '未通过'} | {detail} |")
    lines += ["", "历史截断限制的是送入图的消息条数；本次回复追加后保存的历史可能为上限加一，不能声称持久化历史始终不超过上限。",
              "", "在 backend 目录运行：`.venv/Scripts/python.exe -X utf8 tests/evaluate_session_memory.py`。",
              "[原始检查结果](session_memory.json)", ""]
    output.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")


async def main():
    records = []
    for index, case in enumerate(build_cases(), 1):
        redis = MemoryRedis()
        service = AgentService(llm=object(), redis=redis, history_limit=20, session_factory=object())
        graph = RecordingGraph()
        service._graph = graph
        category, n = case["category"], case["size"]
        checks, details = [], {}
        async def save(user, session, marker):
            await service._save_history(user, session, [{"role": "user", "content": marker}])
            await redis.set(service._operation_context_key(user, session), json.dumps([{"marker": marker}], ensure_ascii=False), ex=settings.agent_session_ttl_seconds)
        async def marker(user, session):
            return await service.get_history(user, session)
        try:
            if category in ("跨用户隔离", "跨会话隔离", "定向删除隔离"):
                first, second = ((n, "shared"), (n + 100, "shared")) if category != "跨会话隔离" else ((n, "first"), (n, "second"))
                await save(*first, "甲标记")
                await save(*second, "乙标记")
                if category == "定向删除隔离":
                    await service.delete_session(*first)
                    checks = [await marker(*first) == [], (await marker(*second))[0]["content"] == "乙标记",
                              await redis.get(service._operation_context_key(*first)) is None,
                              "乙标记" in await redis.get(service._operation_context_key(*second))]
                else:
                    checks = [(await marker(*first))[0]["content"] == "甲标记", (await marker(*second))[0]["content"] == "乙标记",
                              "甲标记" in await redis.get(service._operation_context_key(*first)),
                              "乙标记" in await redis.get(service._operation_context_key(*second))]
                details = {"历史与工具记忆均隔离": all(checks)}
            elif category == "并发读写隔离":
                await asyncio.gather(*(save(i, f"session{i % 3}", f"标记{i}") for i in range(n)))
                histories = await asyncio.gather(*(marker(i, f"session{i % 3}") for i in range(n)))
                checks = [history[0]["content"] == f"标记{i}" for i, history in enumerate(histories)]
                details = {"并发会话数": n, "读取匹配数": sum(checks)}
            elif category == "历史输入截断":
                await service._save_history(1, "history", [{"role": "user", "content": str(i)} for i in range(n)])
                events = [event async for event in service.run(1, "history", "最新请求")]
                inputs = graph.inputs[0]["messages"]
                stored = await service.get_history(1, "history")
                checks = [len(inputs) == 20, inputs[-1]["content"] == "最新请求", events[-1]["type"] == "done"]
                details = {"初始历史条数": n, "图输入条数": len(inputs), "回复后存储条数": len(stored)}
            elif category == "TTL 设置与模拟到期":
                await save(1, "ttl", "TTL标记")
                if n == 0:
                    checks = [w["ttl"] == settings.agent_session_ttl_seconds for w in redis.writes]
                    details = {"TTL参数秒数": settings.agent_session_ttl_seconds, "验证写入数": len(checks)}
                else:
                    redis.now = settings.agent_session_ttl_seconds + 1
                    checks = [await marker(1, "ttl") == [], await redis.get(service._operation_context_key(1, "ttl")) is None]
                    details = {"虚拟时钟到期后历史及工具记忆为空": all(checks)}
            else:
                await redis.set(service._session_key(1, "bad"), "{" if n == 0 else '{"role":"user"}')
                checks = [await marker(1, "bad") == []]
                details = {"错误JSON或非列表按空历史处理": all(checks)}
            records.append({"id": f"memory_{index:03d}", **case, "passed": all(checks), "details": details})
        except Exception as exc:
            records.append({"id": f"memory_{index:03d}", **case, "passed": False, "details": {"error": str(exc)}})
    categories = {}
    for r in records:
        entry = categories.setdefault(r["category"], {"total": 0, "passed": 0})
        entry["total"] += 1
        entry["passed"] += r["passed"]
    summary = {"total": len(records), "passed": sum(r["passed"] for r in records), "categories": categories}
    report = {"evaluated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
              "redis_mode": "内存模拟", "summary": summary, "cases": records}
    output = BACKEND / "tests/evaluation_results/session_memory.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown_report(report, output)
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["passed"] == summary["total"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
