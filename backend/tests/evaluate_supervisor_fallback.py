"""通过故障注入评测真实 Supervisor 节点，不调用模型。

在 backend 目录运行：.venv/Scripts/python.exe tests/evaluate_supervisor_fallback.py
本脚本评测路由控制流程，不评测语义意图分类准确率。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.agents.supervisor import make_supervisor_node
from app.llm.errors import LLMError
from app.llm.types import LLMResponse


def decision(route, **permissions):
    return json.dumps({"route": route, **permissions})


def expected(route="direct_reply", publish=False, analysis=False, automation=False):
    return {"route": route, "allow_publish": publish,
            "allow_analysis": analysis, "allow_automation": automation}


class ScriptedLLM:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def chat(self, messages, **kwargs):
        self.calls.append({"messages": messages, "options": kwargs})
        response = self.responses[len(self.calls) - 1]
        if isinstance(response, Exception):
            raise response
        return LLMResponse(content=response)


def build_cases():
    malformed = [
        ("empty", ""), ("null_content", None), ("plain_text", "I have published it"),
        ("truncated_json", '{"route":'), ("missing_route", '{"allow_publish":true}'),
        ("unknown_route", decision("unknown_agent")), ("null_route", decision(None)),
        ("array_route", decision([])), ("object_route", decision({})),
        ("multiple_objects", decision("operations_agent") + decision("direct_reply")),
        ("boolean_route", decision(True)),
        ("numeric_route", decision(1)),
        ("empty_route", decision("")),
        ("uppercase_route", decision("CONTENT_AGENT")),
        ("trailing_comma", '{"route":"content_agent",}'),
        ("single_quotes", "{'route':'content_agent'}"),
        ("wrong_route_key", '{"routing":"content_agent"}'),
    ]
    cases = []
    for name, response in malformed:
        cases.append({"id": f"retry_{name}", "category": "retry_recovery",
                      "responses": [response, decision("content_agent")],
                      "expected": expected("content_agent"), "expected_calls": 2})
        cases.append({"id": f"fallback_{name}", "category": "malformed_fallback",
                      "responses": [response, response],
                      "expected": expected(), "expected_calls": 2})
    for route in ("content_agent", "operations_agent", "direct_reply"):
        cases.append({"id": f"normal_{route}", "category": "normal_routing",
                      "responses": [decision(route)], "expected": expected(route), "expected_calls": 1})
    for route in ("content_agent", "direct_reply"):
        cases.append({"id": f"permissions_closed_{route}", "category": "permission_guard",
                      "responses": [decision(route, allow_publish=True, allow_analysis=True, allow_automation=True)],
                      "expected": expected(route), "expected_calls": 1})
    for name, value, allowed in (
        ("true", True, True), ("string", "true", False), ("integer", 1, False),
        ("false", False, False), ("null", None, False),
        ("array", [True], False), ("object", {"allowed": True}, False),
    ):
        cases.append({"id": f"operations_permissions_{name}", "category": "permission_guard",
                      "responses": [decision("operations_agent", allow_publish=value, allow_analysis=value, allow_automation=value)],
                      "expected": expected("operations_agent", allowed, allowed, allowed), "expected_calls": 1})
    # 验证重试成功后使用新路由，并按新路由限制业务权限。
    cases.extend([
        {"id": "retry_operations_with_permissions", "category": "retry_recovery",
         "responses": ["错误输出", decision("operations_agent", allow_publish=True, allow_analysis=True, allow_automation=True)],
         "expected": expected("operations_agent", True, True, True), "expected_calls": 2},
        {"id": "retry_direct_reply_closes_permissions", "category": "retry_recovery",
         "responses": ["错误输出", decision("direct_reply", allow_publish=True, allow_analysis=True, allow_automation=True)],
         "expected": expected(), "expected_calls": 2},
    ])
    # LLMError 由服务层处理，此处预期节点将异常向上抛出。
    cases.extend([
        {"id": "first_call_llm_error", "category": "llm_error_propagation",
         "responses": [LLMError("模拟超时异常")], "expected_exception": "LLMError", "expected_calls": 1},
        {"id": "retry_llm_error", "category": "llm_error_propagation",
         "responses": ["错误输出", LLMError("模拟连接异常")],
         "expected_exception": "LLMError", "expected_calls": 2},
    ])
    return cases


CATEGORY_NAMES = {
    "normal_routing": "正常路由返回",
    "permission_guard": "业务权限开关约束",
    "retry_recovery": "错误输出后重试恢复",
    "malformed_fallback": "连续错误输出后降级",
    "llm_error_propagation": "模型调用异常向上抛出",
}


CHECK_NAMES = {
    "call_count": "调用次数",
    "first_call_json_mode": "首次使用 JSON 模式",
    "retry_regular_mode": "重试使用普通模式",
    "retry_hint_added": "重试追加纠正提示",
    "expected_error": "预期异常",
    "expected_state": "预期路由和权限",
    "stage_events": "阶段事件完整性",
}


def rate(passed, total):
    return f"{passed / total:.2%}" if total else "无样本"


def cell(value):
    """转义表格内容；详细原始数据仍保存在 JSON 中。"""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    if len(text) > 180:
        text = text[:180] + "…（完整内容见原始记录）"
    return text.replace("|", "\\|").replace("\n", "<br>").replace("\r", "")


def metric_row(name, passed, total):
    return f"| {name} | {total} | {passed} | {total - passed} | {rate(passed, total)} |"


def write_markdown_report(report, output):
    """根据本次评测结果生成中文 Markdown 报告。"""
    stem = 'supervisor_fallback'
    title = 'Supervisor 路由兜底'
    cases = report['cases']
    total, passed = (len(cases), sum((case['passed'] for case in cases)))
    lines = [f'# {title}评测报告', '', f"评测时间（北京时间）：{report['evaluated_at']}", '', f"测试范围：{report['scope']}。", '', f'**总计 {total} 条，通过 {passed} 条，失败 {total - passed} 条，总体通过率 {rate(passed, total)}。**', '', '## 分类统计', '', '| 测试分类 | 用例数 | 通过数 | 失败数 | 通过率 |', '|---|---:|---:|---:|---:|']
    for category, label in CATEGORY_NAMES.items():
        subset = [c for c in cases if c['category'] == category]
        lines.append(metric_row(label, sum((c['passed'] for c in subset)), len(subset)))
    lines += ['', '通过标准：返回的路由与权限、模型调用次数、重试模式及阶段事件均符合预期；模型调用异常用例则应向上抛出 LLMError。', '', '范围限制：使用预设模型响应，不评测真实模型的意图识别准确率；异常向上抛出通过不等于服务层错误响应已被验证。']
    lines += ['', '## 失败说明', '']
    failed = [c for c in cases if not c['passed']]
    if not failed:
        lines.append('本轮未发现失败用例。')
    else:
        lines += ['| 用例 ID | 失败检查 | 实际异常或结果 |', '|---|---|---|']
        for case in failed:
            checks = '、'.join((CHECK_NAMES.get(k, k) for k, v in case.get('checks', {}).items() if not v))
            lines.append(f"| {case['id']} | {checks} | {cell(case.get('error') or case.get('actual') or case.get('result'))} |")
        if any((c.get('error', {}).get('type') == 'TypeError' for c in failed if c.get('error'))):
            lines += ['', '定位：route 为数组或对象时，合法路由集合判断抛出 TypeError，提前终止节点，未进入预期重试或降级。服务层如何返回该错误不在本轮测试范围内。']
    lines += ['', '## 逐条用例', '']
    lines += ['| 用例 ID | 分类 | 注入响应 | 预期 | 实际结果或异常 | 调用次数（实际/预期） | 结果 |', '|---|---|---|---|---|---|---|']
    for c in cases:
        lines.append(f"| {c['id']} | {CATEGORY_NAMES[c['category']]} | {cell(c['injected_responses'])} | {cell(c['expected'])} | {cell(c['error'] or c['actual'])} | {c['actual_calls']}/{c['expected_calls']} | {('通过' if c['passed'] else '未通过')} |")
    lines += ['', '## 复现信息', '', f"- Python：{report['python_version']}", f"- Git 提交：{report['git_head']}（被测文件内容哈希见原始记录）", f'- 在 backend 目录运行：`.venv/Scripts/python.exe tests/evaluate_{stem}.py`', f'- [完整原始记录]({stem}.json)', '']
    output.with_suffix('.md').write_text('\n'.join(lines), encoding='utf-8')

async def main():
    cases = build_cases()
    if len({case["id"] for case in cases}) != len(cases):
        raise ValueError("测试用例 ID 必须唯一")
    records = []
    for case in cases:
        llm = ScriptedLLM(case["responses"])
        events = []

        async def emitter(event):
            events.append(event)

        result = None
        error = None
        try:
            result = await make_supervisor_node(llm)(
                {"messages": [{"role": "user", "content": "测试请求"}],
                 "allow_publish": True, "allow_analysis": True, "allow_automation": True},
                {"configurable": {"agent_emitter": emitter}},
            )
        except Exception as exc:
            error = {"type": type(exc).__name__, "message": str(exc)}
        checks = {
            "call_count": len(llm.calls) == case["expected_calls"],
            "first_call_json_mode": llm.calls[0]["options"].get("json_mode") is True,
            "retry_regular_mode": len(llm.calls) < 2 or not llm.calls[1]["options"].get("json_mode", False),
            "retry_hint_added": len(llm.calls) < 2 or len(llm.calls[1]["messages"]) == len(llm.calls[0]["messages"]) + 1,
        }
        if "expected_exception" in case:
            checks["expected_error"] = error is not None and error["type"] == case["expected_exception"] and result is None
        else:
            checks["expected_state"] = error is None and result == case["expected"]
            checks["stage_events"] = (len(events) == 2 and events[0].get("status") == "start"
                                      and events[-1].get("status") == "done"
                                      and events[-1].get("route") == case["expected"]["route"])
        records.append({"id": case["id"], "category": case["category"],
                        "injected_responses": [str(r) if isinstance(r, Exception) else r for r in case["responses"]],
                        "expected": case.get("expected", {"exception": case.get("expected_exception")}),
                        "expected_calls": case["expected_calls"], "actual_calls": len(llm.calls),
                        "actual": result, "error": error, "events": events,
                        "checks": checks, "passed": all(checks.values())})
    categories = {}
    for category in sorted({r["category"] for r in records}):
        subset = [r for r in records if r["category"] == category]
        passed = sum(r["passed"] for r in subset)
        categories[category] = {"total": len(subset), "passed": passed, "pass_rate": passed / len(subset)}
    summary = {"total": len(records), "passed": sum(r["passed"] for r in records),
               "failed": sum(not r["passed"] for r in records),
               "pass_rate": sum(r["passed"] for r in records) / len(records),
               "categories": categories, "failed_case_ids": [r["id"] for r in records if not r["passed"]]}
    sources = ["app/agents/supervisor.py", "app/agents/events.py", "tests/evaluate_supervisor_fallback.py"]
    report = {
        "evaluated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "scope": "真实 Supervisor 节点与预设模型响应；不评测语义准确率或服务层异常处理",
        "python_version": platform.python_version(),
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=BACKEND, text=True).strip(),
        "source_sha256": {s: hashlib.sha256((BACKEND / s).read_bytes()).hexdigest() for s in sources},
        "summary": summary, "cases": records,
    }
    output = BACKEND / "tests" / "evaluation_results" / "supervisor_fallback.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown_report(report, output)
    print(f"Supervisor 路由兜底：共 {summary['total']} 条，通过 {summary['passed']} 条，失败 {summary['failed']} 条，通过率 {summary['pass_rate']:.2%}")
    print(f"中文报告：{output.with_suffix('.md')}")
    return 0 if summary["passed"] == summary["total"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
