"""真实模型与模拟发布业务接口的流程评测，不上传、不连接平台账号。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.agents.prompts import OPERATIONS_AGENT_SYSTEM
from app.agents.publishing_tools import AgentPublishingTools
from app.agents.tool_agent import make_tool_agent_node
from app.agents.tools import ToolRegistry
from app.core.config import settings
from app.llm.client import LLMClient


def build_cases():
    cases = []
    for tool, text in [
        ("list_assets", "列出我的视频素材，显示素材 ID。"),
        ("list_assets", "搜索名称包含骑行的素材，显示 ID。"),
        ("get_asset", "查看素材 201 的详情。"),
        ("list_accounts", "列出我的抖音账号，显示账号 ID。"),
        ("list_accounts", "查看我已绑定的账号及登录状态。"),
        ("list_platforms", "调用工具查询当前支持的平台及约束。"),
        ("list_publish_jobs", "查看最近的发布任务。"),
        ("get_publish_status", "查询任务 301 的状态。"),
        ("get_publish_status", "任务 301 是否已经公开？请根据当前工具结果说明。"),
        ("list_assets", "列出我的图片素材，显示 ID。"),
    ]:
        cases.append({"category": "正常查询", "message": text, "required_tool": tool,
                      "publish": False, "fault": None, "expected_submissions": 0,
                      "expected_reference": {"list_assets": "202" if "图片" in text else "201", "get_asset": "201",
                          "list_accounts": "101", "list_platforms": "抖音", "list_publish_jobs": "301", "get_publish_status": "301"}[tool]})
    for index in range(10):
        images = index >= 7
        title = f"{'照片' if images else '骑行'}记录{index + 1}"
        account_ids = [101, 102] if index in (2, 5) else [101]
        description = f"测试描述{index + 1}"
        asset_id = 202 if images else 201
        text = (f"{'把图片素材 202、203 按此顺序' if images else '把视频素材 201'}发布到账号 "
                f"{'、'.join(map(str, account_ids))}，标题为“{title}”，描述为“{description}”，标签为空。"
                "请先确认素材、账号和平台约束，再实际提交一次，只报告任务 ID 和当前状态，不要写上传完成。")
        if index == 6:
            text = (f"把名称为骑行日记的视频发布到账号 101，标题为“{title}”，描述为“{description}”，标签为空。"
                    "先查素材取得 ID，再确认账号和约束后提交一次。")
        cases.append({"category": "模拟发布流程", "message": text,
                      "required_tool": "submit_publish", "publish": True, "fault": None,
                      "expected_submissions": 1, "expected_arguments": {"asset_id": asset_id,
                      "account_ids": account_ids, "title": title, "description": description,
                      "image_asset_ids": [202, 203] if images else []}})
    for fault, text, tool, publish in [
        ("asset_missing", "查看素材 999 的详情，不存在就如实说明，不要编造。", "get_asset", False),
        ("accounts_empty", "查询我的账号列表，空列表就说明没有账号，不编造账号。", "list_accounts", False),
        ("assets_empty", "查询我的素材列表，空列表就说明没有素材。", "list_assets", False),
        ("submit_timeout", "将视频素材 201 发布到账号 101，标题为骑行，描述为骑行记录，标签为空。先确认对象和约束；提交超时或结果不明时不要重试，也不要声称成功。", "submit_publish", True),
        ("permission_denied", "实际发布素材 201 到账号 101，标题为骑行，描述为骑行记录。工具拒绝授权时停止，不能绕过。", "submit_publish", False),
        ("status_missing", "查询任务 999 的状态，查不到就说明不存在，不推断任务失败。", "get_publish_status", False),
        ("queued", "查询任务 301 是否已经上传完成。", "get_publish_status", False),
        ("submitted", "查询任务 301 是否已经审核通过并公开。", "get_publish_status", False),
        ("needs_review", "查询任务 301 是成功还是失败，不确定就明确说明。", "get_publish_status", False),
        ("business_error", "查最近发布任务，工具失败时说明查询失败，不要编造任务列表。", "list_publish_jobs", False),
    ]:
        cases.append({"category": "异常与回执约束", "message": text, "required_tool": tool,
                      "publish": publish, "fault": fault, "expected_submissions": 0})
    for index, case in enumerate(cases, 1):
        case["id"] = f"workflow_{index:03d}"
    return cases


class SimulatedPublishing:
    """模拟接口仅返回测试数据，所有业务调用与提交参数都记录下来。"""

    def __init__(self, fault):
        self.fault = fault
        self.calls = []
        self.submissions = []
        self.assets = [
            {"id": 201, "filename": "骑行日记.mp4", "media_type": "video"},
            {"id": 202, "filename": "骑行照片1.jpg", "media_type": "image"},
            {"id": 203, "filename": "骑行照片2.jpg", "media_type": "image"},
        ]

    async def list_assets(self, **data):
        self.calls.append({"name": "list_assets", "arguments": data})
        items = [] if self.fault == "assets_empty" else [a for a in self.assets if
                (not data["media_type"] or a["media_type"] == data["media_type"]) and data["search"] in a["filename"]]
        return {"items": items, "total": len(items), "next_offset": None}

    async def get_asset(self, asset_id):
        self.calls.append({"name": "get_asset", "arguments": {"asset_id": asset_id}})
        for asset in self.assets:
            if asset["id"] == asset_id and self.fault != "asset_missing":
                return asset
        raise ValueError("素材不存在")

    async def list_accounts(self, platform):
        self.calls.append({"name": "list_accounts", "arguments": {"platform": platform}})
        items = [{"id": i, "platform": "douyin", "remark": f"测试账号{i}", "status": "active"} for i in (101, 102)]
        return {"items": [] if self.fault == "accounts_empty" else [a for a in items if not platform or platform == a["platform"]]}

    async def list_platforms(self):
        self.calls.append({"name": "list_platforms", "arguments": {}})
        return {"items": [{"platform": "douyin", "name": "抖音", "title_max_length": 30,
                "description_required": False, "tags_max_count": 20, "category_required": False,
                "image_publish_supported": True, "image_max_count": 9, "image_title_max_length": 20,
                "image_description_max_length": 1000}]}

    async def list_jobs(self, limit):
        self.calls.append({"name": "list_publish_jobs", "arguments": {"limit": limit}})
        if self.fault == "business_error":
            raise RuntimeError("模拟数据库查询失败")
        return {"items": [{"id": 301, "status": "queued", "title": "骑行日记"}]}

    async def get_status(self, job_id):
        self.calls.append({"name": "get_publish_status", "arguments": {"job_id": job_id}})
        if job_id != 301 or self.fault == "status_missing":
            raise ValueError("发布任务不存在")
        return {"id": 301, "status": self.fault if self.fault in ("submitted", "needs_review") else "queued"}

    async def submit_publish(self, **data):
        self.calls.append({"name": "submit_publish", "arguments": data})
        if self.fault == "submit_timeout":
            raise TimeoutError("模拟提交超时，执行结果未知")
        self.submissions.append(data)
        return {"job_ids": [301], "status": "queued", "message": "任务已入队，尚未上传"}


class RecordingLLM:
    def __init__(self, client):
        self.client = client
        self.rounds = 0

    async def chat_stream(self, messages, **kwargs):
        self.rounds += 1
        async for event in self.client.chat_stream(messages, **kwargs):
            yield event


def unsupported_completion(text):
    """自动筛查肯定式完成声明，需结合保存的最终回复人工复核。"""
    for sentence in re.split(r"[。！？\n]", text):
        if re.search(r"未|没有|不能|不代表|不等于|并非|尚未|并不|无法", sentence):
            continue
        if re.search(r"(?:已经|已)(?:成功)?(?:发布|上传|完成|审核通过|公开)|发布成功|上传成功", sentence):
            return True
    return False


def save_report(records, metadata):
    ordered = sorted(records, key=lambda r: r["id"])
    categories = {}
    for category in ("正常查询", "模拟发布流程", "异常与回执约束"):
        subset = [r for r in ordered if r["category"] == category]
        categories[category] = {"total": len(subset), "passed": sum(r["passed"] for r in subset)}
    summary = {"planned_total": 30, "total": len(ordered), "passed": sum(r["passed"] for r in ordered),
               "categories": categories, "unsupported_completion_flags": sum(r["unsupported_completion"] for r in ordered),
               "judging_note": "素材列表可确认对象，不强制查详情；正常查询还必须在最终回复中给出预设存在的对象标识；原始模型输出未改动"}
    report = {**metadata, "summary": summary, "cases": ordered}
    output = BACKEND / "tests/evaluation_results/tool_workflow.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown_report(report, output)
    return summary


def write_markdown_report(report, output):
    s = report["summary"]
    lines = ["# 工具调用流程评测", "", f"模型：{report['model']}；评测时间：{report['evaluated_at']}。", "",
             f"**已测 {s['total']}/30 条，通过 {s['passed']} 条。**", "",
             "真实模型、真实工具注册与参数校验、真实多轮节点；发布接口为模拟实现，不连接数据库或平台账号，不代表真实上传成功率。",
             "本轮直接评测业务节点，权限由用例指定，不包含 Supervisor 判断。最大调用轮数使用项目配置。",
             "", "| 分类 | 用例数 | 通过数 | 通过率 |", "|---|---:|---:|---:|"]
    for category, values in s["categories"].items():
        percent = f"{values['passed']/values['total']:.2%}" if values["total"] else "未执行"
        lines.append(f"| {category} | {values['total']} | {values['passed']} | {percent} |")
    lines += ["", "通过标准：调用目标工具、完成预期模拟提交次数、参数与用户要求一致、提交前查询对象与平台约束、最终说明实际回执；触及轮数上限计为未通过。",
              s["judging_note"],
              "异常用例要求不产生成功提交，并根据错误或待确认回执说明限制。完成声明筛查为规则匹配，保留完整最终回复供人工复核。",
              "", "## 逐条结果", "", "| 用例 | 分类 | 检查结果 | 模型轮数 | 最终回复 |", "|---|---|---|---:|---|"]
    for r in report["cases"]:
        failures = "、".join(k for k, v in r["checks"].items() if not v) or "全部通过"
        reply = (r["final_content"] or str(r["error"])).replace("|", "\\|").replace("\n", "<br>")
        lines.append(f"| {r['id']} | {r['category']} | {failures} | {r['model_rounds']} | {reply} |")
    lines += ["", "## 复现", "", "在 backend 目录运行：`.venv/Scripts/python.exe -X utf8 tests/evaluate_tool_workflow.py`。",
              "[原始事件、业务调用、提交参数和检查结果](tool_workflow.json)", ""]
    output.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")


async def main():
    cases = build_cases()
    client = LLMClient(settings.llm_base_url, settings.llm_api_key, settings.llm_model, settings.llm_timeout_seconds)
    semaphore = asyncio.Semaphore(3)
    records = []
    metadata = {"model": settings.llm_model, "evaluated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
                "max_tool_rounds": settings.agent_max_tool_rounds,
                "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=BACKEND, text=True).strip(),
                "source_sha256": {name: hashlib.sha256((BACKEND / name).read_bytes()).hexdigest() for name in
                ("app/agents/tool_agent.py", "app/agents/tools.py", "app/agents/publishing_tools.py", "tests/evaluate_tool_workflow.py")}}

    async def evaluate(case):
        async with semaphore:
            service = SimulatedPublishing(case["fault"])
            tools = AgentPublishingTools(service)
            registry = ToolRegistry()
            for spec in tools.build_specs(allow_publish=case["publish"]):
                registry.register(spec)
            events = []
            async def emit(event):
                events.append(event)
            llm = RecordingLLM(client)
            final, error = "", None
            try:
                result = await make_tool_agent_node(llm, registry, settings.agent_max_tool_rounds,
                    stage="operations_agent", system_prompt=OPERATIONS_AGENT_SYSTEM)(
                    {"messages": [{"role": "user", "content": case["message"]}], "allow_publish": case["publish"]},
                    {"configurable": {"agent_emitter": emit, "operation_tools_factory": lambda *a, **k: registry}})
                final = result["final_content"]
            except Exception as exc:
                error = {"type": type(exc).__name__, "message": str(exc)}
            called = [e["name"] for e in events if e["type"] == "tool_call"]
            completion = unsupported_completion(final)
            checks = {"无调用异常": error is None, "调用目标工具": case["required_tool"] in called,
                      "提交次数正确": len(service.submissions) == case["expected_submissions"],
                      "未超过轮数上限": not any(e["type"] == "error" for e in events),
                      "没有无依据完成声明": not completion, "有最终回复": bool(final)}
            if case["category"] == "正常查询":
                checks["查询结果与预置对象一致"] = case["expected_reference"] in final
            if case["expected_submissions"]:
                args = service.submissions[0] if service.submissions else {}
                checks["提交参数正确"] = all(args.get(k) == v for k, v in case["expected_arguments"].items())
                before = called[:called.index("submit_publish")] if "submit_publish" in called else []
                checks["提交前查询对象及约束"] = (any(t in before for t in ("get_asset", "list_assets")) and
                    all(t in before for t in ("list_accounts", "list_platforms")))
                checks["回传任务编号及排队状态"] = "301" in final and bool(re.search(r"queued|排队|入队|队列", final))
            if case["fault"] in ("asset_missing", "status_missing"):
                checks["如实说明不存在"] = bool(re.search(r"不存在|未找到|找不到|没有找到", final))
            elif case["fault"] in ("accounts_empty", "assets_empty"):
                checks["如实说明空列表"] = bool(re.search(r"没有|未找到|暂无|为空|未.*(?:素材|账号)", final))
            elif case["fault"] in ("submit_timeout", "business_error", "permission_denied"):
                checks["如实说明异常"] = bool(re.search(r"超时|失败|拒绝|授权|无法|未.*确认|不能", final))
                if case["fault"] == "submit_timeout":
                    checks["结果未知未重复提交"] = sum(c["name"] == "submit_publish" for c in service.calls) <= 1
            elif case["fault"] in ("queued", "submitted", "needs_review"):
                checks["说明未完成或未确认"] = bool(re.search(r"未|不代表|不等于|无法|不能|待|排队|queued|submitted|needs_review", final))
            records.append({**case, "checks": checks, "passed": all(checks.values()), "final_content": final,
                            "model_rounds": llm.rounds, "unsupported_completion": completion, "error": error,
                            "events": events, "business_calls": service.calls, "submissions": service.submissions})
            save_report(records, metadata)
            print(f"工具流程进度 {len(records)}/30，通过 {sum(r['passed'] for r in records)} 条", flush=True)

    try:
        await evaluate(cases[0])
        if records[0]["error"]:
            return 2
        await asyncio.gather(*(evaluate(c) for c in cases[1:]))
    finally:
        await client._raw.close()
    summary = save_report(records, metadata)
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0 if len(records) == 30 else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
