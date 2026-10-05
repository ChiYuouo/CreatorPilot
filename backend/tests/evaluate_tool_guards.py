"""用预设模型输出验证调用轮数上限、无回执兜底和错误恢复。"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.agents.tool_agent import make_tool_agent_node
from app.agents.tools import ToolRegistry, ToolSpec
from app.llm.types import ContentDelta, ToolCallDelta


class Arguments(BaseModel):
    asset_id: int = Field(strict=True, gt=0)


def call(arguments='{"asset_id":201}', name="get_asset", fragmented=False):
    if fragmented:
        return [ToolCallDelta(0, "call1", name, arguments[:5]), ToolCallDelta(0, None, None, arguments[5:])]
    return [ToolCallDelta(0, "call1", name, arguments)]


class ScriptedLLM:
    def __init__(self, responses, repeat=False):
        self.responses = responses
        self.repeat = repeat
        self.rounds = 0
        self.inputs = []

    async def chat_stream(self, messages, **kwargs):
        index = min(self.rounds, len(self.responses) - 1) if self.repeat else self.rounds
        self.inputs.append(list(messages))
        self.rounds += 1
        for event in self.responses[index]:
            yield event


def build_cases():
    cases = []
    for text in ("已经发布完成", "已上传成功", "任务301已经完成", "账号已同步", "报告已生成", "计划已创建"):
        cases.append({"category": "无回执声明拦截", "responses": [[ContentDelta(text)], [ContentDelta(text)]],
                      "stage": "operations_agent", "limit": 5, "kind": "receipt", "repeat": False})
    for stage in ("operations_agent", "content_agent"):
        for limit in (1, 2, 3, 5):
            cases.append({"category": "轮数上限终止", "responses": [call()], "stage": stage,
                          "limit": limit, "kind": "cap", "repeat": True})
    for name, arguments, tool in (("缺少必填", "{}", "get_asset"), ("类型错误", '{"asset_id":"201"}', "get_asset"),
                                  ("未知工具", '{"asset_id":201}', "unknown"), ("业务抛错", '{"asset_id":999}', "get_asset")):
        cases.append({"category": "工具错误回传与恢复", "label": name,
                      "responses": [call(arguments, tool), call(), [ContentDelta("查询到素材201")]],
                      "stage": "operations_agent", "limit": 5, "kind": "recovery", "repeat": False})
    for stage in ("operations_agent", "content_agent"):
        cases.append({"category": "流式工具参数拼接", "responses": [call(fragmented=True), [ContentDelta("查询到素材201")]],
                      "stage": stage, "limit": 5, "kind": "fragment", "repeat": False})
    for index, case in enumerate(cases, 1):
        case["id"] = f"guard_{index:03d}"
    return cases


def write_markdown_report(report, output):
    summary = report["summary"]
    lines = ["# 工具循环与回执保护评测", "", f"**共 {summary['total']} 条，通过 {summary['passed']} 条。**", "",
             "使用真实 ToolRegistry 和工具调用节点，模型输出与业务函数采用模拟实现。验证可执行控制流程，不代表真实模型工具选择能力。",
             "无回执测试只覆盖没有调用业务工具时的兜底；失败工具回执后的事实一致性还依赖模型遵循提示词，不据此声称完全消除幻觉。",
             "", "| 分类 | 用例数 | 通过数 |", "|---|---:|---:|"]
    for category, value in summary["categories"].items():
        lines.append(f"| {category} | {value['total']} | {value['passed']} |")
    lines += ["", "## 逐条检查", "", "| 用例 | 分类 | 检查结果 |", "|---|---|---|"]
    for r in report["cases"]:
        checks = "、".join(f"{k}：{'通过' if v else '未通过'}" for k, v in r["checks"].items())
        lines.append(f"| {r['id']} | {r['category']} | {checks} |")
    lines += ["", "在 backend 目录运行：`.venv/Scripts/python.exe -X utf8 tests/evaluate_tool_guards.py`。",
              "[原始事件和检查结果](tool_guards.json)", ""]
    output.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")


async def main():
    records = []
    for case in build_cases():
        executed = []
        async def handler(asset_id):
            if asset_id == 999:
                raise RuntimeError("模拟素材不存在")
            executed.append(asset_id)
            return {"id": asset_id}
        registry = ToolRegistry()
        registry.register(ToolSpec("get_asset", "查询素材", Arguments.model_json_schema(), handler, Arguments))
        llm = ScriptedLLM(case["responses"], case["repeat"])
        events = []
        async def emit(event):
            events.append(event)
        checks, result, error = {}, None, None
        try:
            result = await make_tool_agent_node(llm, registry, case["limit"], stage=case["stage"], system_prompt="测试工具调用流程")(
                {"messages": [{"role": "user", "content": "查询素材201"}]},
                {"configurable": {"agent_emitter": emit, "operation_tools_factory": lambda *a, **k: registry}})
            tool_results = [e for e in events if e["type"] == "tool_result"]
            if case["kind"] == "receipt":
                tokens = "".join(e["text"] for e in events if e["type"] == "token")
                checks = {"重试一次": llm.rounds == 2, "原无依据声明未流出": case["responses"][0][0].text not in tokens,
                          "返回无法确认提示": "未取得业务工具结果" in result["final_content"], "未执行业务": not executed}
            elif case["kind"] == "cap":
                checks = {"调用轮数未超限": llm.rounds == case["limit"], "收到轮数上限事件": any(e["type"] == "error" for e in events),
                          "结果说明超限": "超过上限" in result["final_content"]}
            elif case["kind"] == "recovery":
                tools_in_third_round = [m for m in llm.inputs[2] if m["role"] == "tool"]
                checks = {"错误回传后成功": len(tool_results) == 2 and not tool_results[0]["ok"] and tool_results[1]["ok"],
                          "合法业务执行一次": executed == [201], "错误作为tool消息回喂": len(tools_in_third_round) == 2,
                          "最终生成回复": result["final_content"] == "查询到素材201"}
            else:
                checks = {"参数片段正确拼接": executed == [201], "工具成功": len(tool_results) == 1 and tool_results[0]["ok"]}
        except Exception as exc:
            error = str(exc)
            checks = {"无未处理异常": False}
        records.append({"id": case["id"], "category": case["category"], "stage": case["stage"],
                        "limit": case["limit"], "checks": checks, "passed": all(checks.values()),
                        "model_rounds": llm.rounds, "result": result, "events": events, "error": error})
    categories = {}
    for r in records:
        value = categories.setdefault(r["category"], {"total": 0, "passed": 0})
        value["total"] += 1
        value["passed"] += r["passed"]
    summary = {"total": len(records), "passed": sum(r["passed"] for r in records), "categories": categories}
    report = {"evaluated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(), "summary": summary, "cases": records}
    output = BACKEND / "tests/evaluation_results/tool_guards.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown_report(report, output)
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["passed"] == summary["total"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
