"""使用记录调用的模拟业务服务，评测真实发布工具的参数校验。

在 backend 目录运行：.venv/Scripts/python.exe tests/evaluate_tool_arguments.py
不调用模型、数据库或真实发布服务。
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

from app.agents.publishing_tools import AgentPublishingTools
from app.agents.tools import ToolRegistry


class RecordingPublishing:
    def __init__(self):
        self.calls = []

    async def record(self, **kwargs):
        self.calls.append(kwargs)
        return {"recorded_arguments": kwargs}

    list_assets = record
    get_asset = record
    list_accounts = record
    list_platforms = record
    list_jobs = record
    get_status = record
    submit_publish = record


# 预期是否合法由测试用例预先指定，不根据被测代码的输出生成。
CASES = [
    ("missing_asset_id", "get_asset", {}, False),
    ("zero_asset_id", "get_asset", {"asset_id": 0}, False),
    ("negative_asset_id", "get_asset", {"asset_id": -1}, False),
    ("string_asset_id", "get_asset", {"asset_id": "1"}, False),
    ("boolean_asset_id", "get_asset", {"asset_id": True}, False),
    ("null_asset_id", "get_asset", {"asset_id": None}, False),
    ("injected_user_id", "get_asset", {"asset_id": 1, "user_id": 2}, False),
    ("negative_offset", "list_assets", {"offset": -1}, False),
    ("zero_limit", "list_assets", {"limit": 0}, False),
    ("excessive_limit", "list_assets", {"limit": 51}, False),
    ("string_limit", "list_assets", {"limit": "20"}, False),
    ("unsupported_media_type", "list_assets", {"media_type": "audio"}, False),
    ("long_search", "list_assets", {"search": "x" * 101}, False),
    ("array_arguments", "list_assets", [], False),
    ("malformed_json", "list_assets", "{", False),
    ("missing_job_id", "get_publish_status", {}, False),
    ("zero_job_id", "get_publish_status", {"job_id": 0}, False),
    ("fractional_job_id", "get_publish_status", {"job_id": 1.5}, False),
    ("injected_path", "get_publish_status", {"job_id": 1, "path": "/tmp/file"}, False),
    ("boolean_jobs_limit", "list_publish_jobs", {"limit": True}, False),
    ("valid_asset", "get_asset", {"asset_id": 1}, True),
    ("default_asset_list", "list_assets", {}, True),
    ("asset_list_boundaries", "list_assets", {"offset": 0, "limit": 50, "media_type": "image", "search": "x" * 100}, True),
    ("valid_job_status", "get_publish_status", {"job_id": 1}, True),
    ("valid_jobs_limit", "list_publish_jobs", {"limit": 1}, True),
    ("long_account_platform", "list_accounts", {"platform": "x" * 33}, False),
    ("numeric_account_platform", "list_accounts", {"platform": 123}, False),
    ("extra_platform_argument", "list_platforms", {"user_id": 2}, False),
    ("scalar_arguments", "list_assets", 42, False),
    ("null_arguments", "list_assets", None, False),
    ("fractional_asset_id", "get_asset", {"asset_id": 1.5}, False),
    ("string_offset", "list_assets", {"offset": "0"}, False),
    ("boolean_offset", "list_assets", {"offset": False}, False),
    ("publish_missing_accounts", "submit_publish", {"asset_id": 1, "title": "test"}, False),
    ("publish_empty_accounts", "submit_publish", {"account_ids": [], "asset_id": 1, "title": "test"}, False),
    ("publish_excessive_accounts", "submit_publish", {"account_ids": list(range(1, 32)), "asset_id": 1, "title": "test"}, False),
    ("publish_zero_account", "submit_publish", {"account_ids": [0], "asset_id": 1, "title": "test"}, False),
    ("publish_boolean_account", "submit_publish", {"account_ids": [True], "asset_id": 1, "title": "test"}, False),
    ("publish_missing_asset", "submit_publish", {"account_ids": [1], "title": "test"}, False),
    ("publish_missing_title", "submit_publish", {"account_ids": [1], "asset_id": 1}, False),
    ("publish_empty_title", "submit_publish", {"account_ids": [1], "asset_id": 1, "title": ""}, False),
    ("publish_long_title", "submit_publish", {"account_ids": [1], "asset_id": 1, "title": "x" * 256}, False),
    ("publish_excessive_images", "submit_publish", {"account_ids": [1], "asset_id": 1, "title": "test", "image_asset_ids": list(range(1, 11))}, False),
    ("publish_excessive_tags", "submit_publish", {"account_ids": [1], "asset_id": 1, "title": "test", "tags": ["tag"] * 21}, False),
    ("publish_invalid_datetime", "submit_publish", {"account_ids": [1], "asset_id": 1, "title": "test", "scheduled_at": "invalid-date"}, False),
    ("default_accounts", "list_accounts", {}, True),
    ("account_platform_boundary", "list_accounts", {"platform": "x" * 32}, True),
    ("valid_platform_list", "list_platforms", {}, True),
    ("valid_publish_minimum", "submit_publish", {"account_ids": [1], "asset_id": 1, "title": "x"}, True),
    ("valid_publish_boundaries", "submit_publish", {"account_ids": list(range(1, 31)), "asset_id": 1, "title": "x" * 255, "image_asset_ids": list(range(1, 10)), "tags": ["tag"] * 20}, True),
]


TOOL_NAMES = {
    "get_asset": "查询素材详情", "list_assets": "查询素材列表",
    "get_publish_status": "查询发布状态", "list_publish_jobs": "查询发布任务",
    "list_accounts": "查询账号", "list_platforms": "查询平台",
    "submit_publish": "提交发布",
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
    stem = 'tool_arguments'
    title = '工具参数校验'
    cases = report['cases']
    total, passed = (len(cases), sum((case['passed'] for case in cases)))
    lines = [f'# {title}评测报告', '', f"评测时间（北京时间）：{report['evaluated_at']}", '', f"测试范围：{report['scope']}。", '', f'**总计 {total} 条，通过 {passed} 条，失败 {total - passed} 条，总体通过率 {rate(passed, total)}。**', '', '## 分类统计', '', '| 测试分类 | 用例数 | 通过数 | 失败数 | 通过率 |', '|---|---:|---:|---:|---:|']
    for valid, label in ((False, '非法参数执行前拦截'), (True, '合法参数通过并调用模拟接口')):
        subset = [c for c in cases if c['expected_valid'] is valid]
        lines.append(metric_row(label, sum((c['passed'] for c in subset)), len(subset)))
    lines += ['', '通过标准：非法参数必须返回失败且业务接口调用次数为 0；合法参数必须返回成功且调用次数为 1。', '', '## 工具覆盖统计', '', '| 工具 | 用例数 | 通过数 | 失败数 | 通过率 |', '|---|---:|---:|---:|---:|']
    for tool in sorted({c['tool'] for c in cases}):
        subset = [c for c in cases if c['tool'] == tool]
        lines.append(metric_row(TOOL_NAMES.get(tool, tool), sum((c['passed'] for c in subset)), len(subset)))
    lines += ['', '范围限制：模拟业务接口只记录调用，不验证数据库、账号归属、平台发布或真实业务执行成功率。']
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
    lines += ['| 用例 ID | 工具 | 参数 | 预期 | 实际成功标记 | 业务调用次数 | 结果 |', '|---|---|---|---|---|---:|---|']
    for c in cases:
        lines.append(f"| {c['id']} | {TOOL_NAMES.get(c['tool'], c['tool'])} | {cell(c['arguments'])} | {('允许执行' if c['expected_valid'] else '执行前拦截')} | {('成功' if c['result']['ok'] else '失败')} | {len(c['business_calls'])} | {('通过' if c['passed'] else '未通过')} |")
    lines += ['', '## 复现信息', '', f"- Python：{report['python_version']}", f"- Git 提交：{report['git_head']}（被测文件内容哈希见原始记录）", f'- 在 backend 目录运行：`.venv/Scripts/python.exe tests/evaluate_{stem}.py`', f'- [完整原始记录]({stem}.json)', '']
    output.with_suffix('.md').write_text('\n'.join(lines), encoding='utf-8')

async def main():
    if len({case[0] for case in CASES}) != len(CASES):
        raise ValueError("测试用例 ID 必须唯一")
    records = []
    for case_id, tool_name, arguments, expected_valid in CASES:
        # 每条用例使用独立请求状态，避免跨用例复用发布提交回执。
        service = RecordingPublishing()
        registry = ToolRegistry()
        for spec in AgentPublishingTools(service).build_specs(allow_publish=True):
            registry.register(spec)
        raw = arguments if isinstance(arguments, str) else json.dumps(arguments)
        before = len(service.calls)
        result = await registry.execute(tool_name, raw)
        calls = service.calls[before:]
        passed = (result["ok"] is expected_valid and len(calls) == (1 if expected_valid else 0))
        records.append({"id": case_id, "tool": tool_name, "arguments": raw,
                        "expected_valid": expected_valid, "result": result,
                        "business_calls": calls, "passed": passed})

    invalid = [r for r in records if not r["expected_valid"]]
    valid = [r for r in records if r["expected_valid"]]
    summary = {
        "total": len(records), "passed": sum(r["passed"] for r in records),
        "failed": sum(not r["passed"] for r in records),
        "pass_rate": sum(r["passed"] for r in records) / len(records),
        "invalid_total": len(invalid), "invalid_blocked_before_execution": sum(r["passed"] for r in invalid),
        "invalid_interception_rate": sum(r["passed"] for r in invalid) / len(invalid),
        "valid_total": len(valid), "valid_accepted_and_executed": sum(r["passed"] for r in valid),
    }
    sources = ["app/agents/tools.py", "app/agents/publishing_tools.py", "app/schemas/agent_operations.py", "app/schemas/publishing.py", "tests/evaluate_tool_arguments.py"]
    report = {
        "evaluated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "scope": "发布工具参数校验；使用记录调用的模拟业务接口；不调用模型或执行真实业务",
        "python_version": platform.python_version(),
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=BACKEND, text=True).strip(),
        "source_sha256": {s: hashlib.sha256((BACKEND / s).read_bytes()).hexdigest() for s in sources},
        "summary": summary, "cases": records,
    }
    output = BACKEND / "tests" / "evaluation_results" / "tool_arguments.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown_report(report, output)
    print(f"工具参数校验：共 {summary['total']} 条，通过 {summary['passed']} 条，失败 {summary['failed']} 条，通过率 {summary['pass_rate']:.2%}")
    print(f"中文报告：{output.with_suffix('.md')}")
    return 0 if summary["passed"] == summary["total"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
