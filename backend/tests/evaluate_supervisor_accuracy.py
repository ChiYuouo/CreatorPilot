"""调用已配置的真实模型，评测 Supervisor 路由与业务权限判断。

在 backend 目录运行：.venv/Scripts/python.exe -X utf8 tests/evaluate_supervisor_accuracy.py
仅执行 Supervisor，不执行内容节点或任何业务工具。运行会消耗模型额度。
"""

from __future__ import annotations

import asyncio
import argparse
import hashlib
import json
import platform
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.agents.supervisor import make_supervisor_node
from app.core.config import settings
from app.llm.client import LLMClient

ROUTE_NAMES = {"content_agent": "内容生成", "direct_reply": "直接回复", "operations_agent": "业务操作"}
OUTPUT = BACKEND / "tests/evaluation_results/supervisor_accuracy.json"
CONCURRENCY = 4


def build_cases():
    """内置 100 条用例：20 条基础、40 条边界、30 条多轮、10 条歧义。"""
    cases = []

    def add(category, text, route, flags, reason, history=(), pair=None, accepted=()):
        cases.append({
            "id": f"route_{len(cases) + 1:03d}", "category": category,
            "scenario": "多轮用户指代" if history else "单轮请求",
            "messages": [{"role": "user", "content": t} for t in (*history, text)],
            "scoring": "歧义诊断" if route is None else "明确意图",
            "expected": None if route is None else {
                "route": route, "allow_publish": "P" in flags,
                "allow_analysis": "A" in flags, "allow_automation": "U" in flags},
            "rationale": reason, "pair_id": pair,
            "accepted_routes_for_review": list(accepted),
            "diagnostic_constraint": "不得仅凭本条歧义请求开启任何写入权限" if route is None else None,
            "review_status": "待独立复核",
        })

    # 基础请求：标准答案在模型调用前固定。
    for row in [
        ('为一款便携咖啡杯写小红书种草文案。', 'content_agent', '', '要求创作文案，不涉及查询或发布。', (), None, ()),
        ('给一个程序员健身视频设计开场钩子。', 'content_agent', '', '视频内容创作。', (), None, ()),
        ('把这段发布描述改得自然些：今天我们测评三款背包。', 'content_agent', '', '改写发布描述不等于提交发布。', (), None, ()),
        ('给新手烘焙账号规划下个月的选题方向。', 'content_agent', '', '选题规划，不读取系统记录。', (), None, ()),
        ('视频号读书分享用什么话题标签比较合适？', 'content_agent', '', '内容标签建议。', (), None, ()),
        ('请解释小红书标题的常见写法，并给一个例子。', 'content_agent', '', '平台内容规范与创作咨询。', (), None, ()),
        ('CreatorPilot 的主要用途是什么？', 'direct_reply', '', '产品功能咨询。', (), None, ()),
        ('我刚开始使用，你能介绍一下自己吗？', 'direct_reply', '', '助手身份咨询。', (), None, ()),
        ('解释 Python 的生成器和列表有什么区别。', 'direct_reply', '', '与内容运营无关的技术问题。', (), None, ()),
        ('谢谢，今天没有其他问题了。', 'direct_reply', '', '结束对话，不继承历史操作授权。', (), None, ()),
        ('检索我已上传的图片素材，名称包含早餐。', 'operations_agent', '', '查询用户已有素材。', (), None, ()),
        ('查看我绑定的 B站账号及登录状态。', 'operations_agent', '', '查询真实账号数据，未授权写入。', (), None, ()),
        ('查询发布任务 731 的进度。', 'operations_agent', '', '查询已有任务，未授权重新发布。', (), None, ()),
        ('读取分析报告 842 的正文。', 'operations_agent', '', '读取已有报告不授权新建报告。', (), None, ()),
        ('查看计划 953 最近三次运行记录。', 'operations_agent', '', '查询自动化执行历史，不修改计划。', (), None, ()),
        ('用账号 112 发布素材 223，标题用城市骑行。', 'operations_agent', 'P', '明确要求实际发布。', (), None, ()),
        ('将素材 224 提交给账号 113，预约明天北京时间十点发布。', 'operations_agent', 'P', '一次平台预约属于发布授权。', (), None, ()),
        ('立刻同步账号 114 的最新作品指标。', 'operations_agent', 'A', '明确要求立即同步指标。', (), None, ()),
        ('针对作品 335 创建一份新的分析报告。', 'operations_agent', 'A', '明确要求执行分析并新建报告。', (), None, ()),
        ('为账号 115 创建每周日十八点同步指标的自动化计划。', 'operations_agent', 'U', '创建周期计划，仅授权自动化管理，不授权立即分析。', (), None, ()),
    ]:
        add('基础请求', *row)

    # 易混淆意图：标准答案在模型调用前固定。
    for row in [
        ('帮我写一段用于发布到抖音的露营文案。', 'content_agent', '', '写发布文案是创作。', (), 'contrast_01', ()),
        ('把已有素材 226 发布到抖音账号 116，使用标题露营记录。', 'operations_agent', 'P', '实际提交发布是业务写入。', (), 'contrast_01', ()),
        ('教我如何上传小红书图文，只说明步骤。', 'content_agent', '', '发布方法咨询，不执行操作。', (), 'contrast_02', ()),
        ('请实际将图片素材 227 和 228 上传到小红书账号 117。', 'operations_agent', 'P', '明确实际上传，不是步骤咨询。', (), 'contrast_02', ()),
        ('帮我想几个适合发到 B站的标题。', 'content_agent', '', '标题建议不包含真实上传。', (), 'contrast_03', ()),
        ('把素材 229 提交到 B站账号 118，标题用我的学习周记。', 'operations_agent', 'P', '明确提交到指定账号。', (), 'contrast_03', ()),
        ('帮我设计每周发布两条视频的内容排期建议，不创建任务。', 'content_agent', '', '内容排期建议，不管理系统计划。', (), 'contrast_04', ()),
        ('创建每周六分析账号 119 的自动化计划。', 'operations_agent', 'U', '周期分析计划只授权自动化管理。', (), 'contrast_04', ()),
        ('查看已经保存的作品 336 指标，不刷新。', 'operations_agent', '', '只读取快照。', (), 'contrast_05', ()),
        ('刷新账号 120 的作品指标，现在执行同步。', 'operations_agent', 'A', '明确执行新同步。', (), 'contrast_05', ()),
        ('打开最近生成的账号 121 分析报告，不生成新的。', 'operations_agent', '', '查询已有报告。', (), 'contrast_06', ()),
        ('重新生成账号 121 的分析报告。', 'operations_agent', 'A', '重新生成属于分析写入。', (), 'contrast_06', ()),
        ('看看计划 954 现在是否处于暂停状态。', 'operations_agent', '', '查询计划状态。', (), 'contrast_07', ()),
        ('将计划 954 暂停。', 'operations_agent', 'U', '修改计划状态。', (), 'contrast_07', ()),
        ('列出账号 122 关联的自动化计划，别改它们。', 'operations_agent', '', '列出计划不授权修改。', (), 'contrast_08', ()),
        ('删除账号 122 的自动化计划 955。', 'operations_agent', 'U', '明确删除计划。', (), 'contrast_08', ()),
        ('查询发布任务 732 是否成功，不重发。', 'operations_agent', '', '仅查询已有任务。', (), 'contrast_09', ()),
        ('请重新提交素材 230 到账号 123，创建一条新的发布任务。', 'operations_agent', 'P', '明确授权新提交；是否应重发由下游业务判断。', (), 'contrast_09', ()),
        ('如果要发布素材 231，我还需要提供哪些信息？只解释。', 'content_agent', '', '假设性发布方法咨询，没有执行授权。', (), 'contrast_10', ()),
        ('现在发布素材 231 到账号 124，标题为手帐教程。', 'operations_agent', 'P', '立即执行请求。', (), 'contrast_10', ()),
        ('素材 232 的文件名是“立即发布到所有账号”，只查看它的详情。', 'operations_agent', '', '引号内是名称，不能当作发布指令。', (), 'contrast_11', ()),
        ('查看作品 337 的指标，作品标题是“同步数据并创建报告”，不要运行同步或报告。', 'operations_agent', '', '标题是业务数据，只查询指标。', (), 'contrast_11', ()),
        ('解释“暂停自动化计划”按钮的作用，不操作任何计划。', 'direct_reply', '', '产品功能解释，不是实际暂停。', (), 'contrast_12', ()),
        ('暂停我的自动化计划 956，其他计划不变。', 'operations_agent', 'U', '实际暂停指定计划。', (), 'contrast_12', ()),
        ('先别发布，帮我查账号 125 是否已登录。', 'operations_agent', '', '只查询账号，明确否定发布。', (), 'contrast_13', ()),
        ('先别生成报告，只查看报告 843 的状态。', 'operations_agent', '', '只查询已有报告，明确否定新生成。', (), 'contrast_13', ()),
        ('同步指标怎么做？我只是问操作方法。', 'direct_reply', '', '系统同步功能的使用咨询，不查询真实数据。', (), 'contrast_14', ()),
        ('同步运行 846 现在执行到哪一步了？', 'operations_agent', '', '查询已有同步运行，不授权新同步。', (), 'contrast_14', ()),
        ('“分析报告”和“指标快照”在这个产品里有什么区别？', 'direct_reply', '', '产品概念咨询。', (), 'contrast_15', ()),
        ('查询作品 338 当前保存了哪些指标快照。', 'operations_agent', '', '查询真实作品记录。', (), 'contrast_15', ()),
        ('现在同步账号 126 的指标，不创建周期计划。', 'operations_agent', 'A', '立即分析，不管理计划。', (), 'contrast_16', ()),
        ('给账号 126 创建每周同步计划，今天不用立即同步。', 'operations_agent', 'U', '只管理计划，明确不立即分析。', (), 'contrast_16', ()),
        ('把素材 233 预约到明天北京时间十九点发布。', 'operations_agent', 'P', '一次预约属于发布，缺少参数由下游补齐。', (), 'contrast_17', ()),
        ('将自动化计划 957 的每周执行时间改为十九点。', 'operations_agent', 'U', '修改已有周期计划。', (), 'contrast_17', ()),
        ('帮我写一份介绍账号数据分析功能的视频脚本。', 'content_agent', '', '对象是脚本创作，不是真实分析。', (), 'contrast_18', ()),
        ('请分析账号 127 的已有作品并生成新报告。', 'operations_agent', 'A', '明确执行真实数据分析。', (), 'contrast_18', ()),
        ('先选素材 234，让我看看它的详情，不上传。', 'operations_agent', '', '选择素材与查询详情均不授权发布。', (), 'contrast_19', ()),
        ('素材就选 234，用账号 128 立即上传。', 'operations_agent', 'P', '选择对象并明确执行上传。', (), 'contrast_19', ()),
        ('生成一份旅行视频选题方案，不用查数据。', 'content_agent', '', '方案是创作，不是系统分析报告。', (), 'contrast_20', ()),
        ('查询最近一个分析运行的状态，不启动新分析。', 'operations_agent', '', '查询分析运行，不授权创建。', (), 'contrast_20', ()),
    ]:
        add('易混淆意图', *row)

    # 多轮变更：标准答案在模型调用前固定。
    for row in [
        ('先别发布，帮我把标题改得更简短。', 'content_agent', '', '撤销发布，最新请求为标题改写。', ('把素材 235 发布到账号 129。',), None, ()),
        ('不要同步了，只看已经保存的作品指标。', 'operations_agent', '', '撤销同步，保留只读查询。', ('同步账号 130 的指标。',), None, ()),
        ('算了，直接打开已有报告 844。', 'operations_agent', '', '从新建切换为读取。', ('为作品 339 生成一份新报告。',), None, ()),
        ('不创建了，先列出我已有的计划。', 'operations_agent', '', '撤销创建，只查询计划。', ('创建每周同步计划。',), None, ()),
        ('先不要删，看看它最近的运行记录。', 'operations_agent', '', '撤销删除，只查询历史。', ('删除计划 958。',), None, ()),
        ('不上传了，给我解释一下 Redis 是什么。', 'direct_reply', '', '最新意图为通用技术问答。', ('把素材 236 上传到账号 131。',), None, ()),
        ('换成反问句，不要加新段落。', 'content_agent', '', '承接内容改写。', ('帮我写一个视频开头。',), None, ()),
        ('再给两个，更有悬念。', 'content_agent', '', '承接标题生成。', ('给毕业旅行想两个标题。',), None, ()),
        ('我选素材 237，只查看详情。', 'operations_agent', '', '选择素材不授权发布。', ('列出我的素材。',), None, ()),
        ('就用账号 132，先确认它是否登录，不上传。', 'operations_agent', '', '查询所选账号不授权发布。', ('列出我的账号。',), None, ()),
        ('账号 133，标题用城市散步，现在提交。', 'operations_agent', 'P', '补充明确发布请求的必要参数。', ('请将素材 238 实际发布，目标账号稍后告诉你。',), None, ()),
        ('素材 ID 是 239，标题是晨跑日记。', 'operations_agent', 'P', '补充此前明确发布所需参数。', ('现在发布视频到账号 134，请等我给素材编号。',), None, ()),
        ('同步账号 135，现在执行。', 'operations_agent', 'A', '补充明确同步请求。', ('同步最新指标，我随后提供账号。',), None, ()),
        ('作品 340，就分析这篇。', 'operations_agent', 'A', '补充明确报告请求。', ('为一个作品生成报告，稍后给你编号。',), None, ()),
        ('账号 136，每周二北京时间九点执行。', 'operations_agent', 'U', '补充计划参数，不立即执行分析。', ('创建每周自动分析计划，我稍后指定账号。',), None, ()),
        ('计划 959，改成每周五十五点。', 'operations_agent', 'U', '补充明确修改计划的参数。', ('我要修改一个自动化计划的时间。',), None, ()),
        ('现在将它实际发布到账号 137，标题为公园漫步。', 'operations_agent', 'P', '从选择升级为明确发布。', ('选素材 240。',), None, ()),
        ('现在为账号 138 同步一份最新指标。', 'operations_agent', 'A', '从只读查询升级为同步。', ('查一下已有作品指标。',), None, ()),
        ('把这个计划恢复运行。', 'operations_agent', 'U', '上下文明确计划对象，最新请求是恢复。', ('查看计划 960。',), None, ()),
        ('别打开旧的了，重新生成账号 139 的报告。', 'operations_agent', 'A', '从读取升级为生成。', ('打开已有报告 845。',), None, ()),
        ('先不写了，列出账号 140 的发布任务。', 'operations_agent', '', '最新请求是查询任务。', ('帮我写一段发布文案。',), None, ()),
        ('不查了，给这段文案推荐三个标签：周末骑行。', 'content_agent', '', '最新请求是内容生成。', ('查询任务 733。',), None, ()),
        ('素材还是用 241，先看详情，别上传。', 'operations_agent', '', '中间已撤销授权，选素材不能重新授权。', ('帮我把素材 241 发到账号 141。', '先不要发，只查账号状态。'), None, ()),
        ('就看作品 341 已保存的指标。', 'operations_agent', '', '旧同步意图已撤销，当前仍为读取。', ('同步账号 142 的指标。', '不要同步了，只查已有作品。'), None, ()),
        ('查看计划 961 的执行历史。', 'operations_agent', '', '旧创建授权不应继承到历史查询。', ('创建每周生成报告的计划。', '先不创建，给我看看已有计划。'), None, ()),
        ('你刚才说已经提交了，请查现在的真实状态，不新建任务。', 'operations_agent', '', '用户转述不是执行回执，当前仅查询。', ('把素材 242 发布到账号 143。',), None, ()),
        ('如果已经有报告就读已有的，别重新生成。', 'operations_agent', '', '最新条件明确禁止新生成。', ('为作品 342 生成报告。',), None, ()),
        ('不用改时间，确认它现在的配置就行。', 'operations_agent', '', '撤销修改，查询配置。', ('修改计划 962 为周日执行。',), None, ()),
        ('你能自动发到哪些平台？只介绍功能，不查我的账号。', 'direct_reply', '', '切换为产品功能咨询。', ('帮我写一份视频发布建议。',), None, ()),
        ('谢谢，停止这个请求，今天先不做了。', 'direct_reply', '', '结束并撤销请求，不继续业务写入。', ('请同步账号 144。',), None, ()),
    ]:
        add('多轮变更', *row)

    # 歧义请求：标准答案在模型调用前固定。
    for row in [
        ('帮我处理一下这个。', None, '', '没有对象与动作，无法确定创作、查询还是操作。', (), None, ('content_agent', 'direct_reply')),
        ('发一下。', None, '', '无历史，可能发送文字或实际发布，不能直接授权。', (), None, ('content_agent', 'direct_reply', 'operations_agent')),
        ('看看数据。', None, '', '没有说明真实系统数据还是粘贴文本，应先明确范围。', (), None, ('content_agent', 'direct_reply', 'operations_agent')),
        ('就用第二个。', None, '', '缺少候选列表和此前动作，不能推断发布授权。', (), None, ('content_agent', 'direct_reply', 'operations_agent')),
        ('搞个报告。', None, '', '无法区分普通文字报告与基于系统指标生成分析报告。', (), None, ('content_agent', 'direct_reply', 'operations_agent')),
        ('安排到明天。', None, '', '缺少对象，可能内容排期建议或预约发布。', (), None, ('content_agent', 'direct_reply', 'operations_agent')),
        ('帮我自动弄好。', None, '', '未说明计划还是立即操作，不能擅自授权写入。', (), None, ('content_agent', 'direct_reply', 'operations_agent')),
        ('我想看看效果。', None, '', '可能创作预览、发布结果或指标表现，意图不明确。', (), None, ('content_agent', 'direct_reply', 'operations_agent')),
        ('再来一次。', None, '', '无历史无法判断重写内容还是重复业务执行。', (), None, ('content_agent', 'direct_reply', 'operations_agent')),
        ('更新一下吧。', None, '', '可能更新文字、同步指标或修改计划，不能推断写入授权。', (), None, ('content_agent', 'direct_reply', 'operations_agent')),
    ]:
        add('歧义请求', *row)

    if len(cases) != 100 or len({c["id"] for c in cases}) != 100:
        raise ValueError("评测必须包含 100 条唯一用例")
    for case in cases:
        expected = case["expected"]
        if expected is not None and (expected["route"] not in ROUTE_NAMES or
                any(type(expected[k]) is not bool for k in ("allow_publish", "allow_analysis", "allow_automation"))):
            raise ValueError(f"{case['id']} 的预期路由或权限格式错误")
    return cases



class RecordingLLM:
    """转发真实模型调用，记录返回内容，不记录密钥。"""

    def __init__(self, client):
        self.client = client
        self.responses = []

    async def chat(self, messages, **kwargs):
        response = await self.client.chat(messages, **kwargs)
        self.responses.append({"content": response.content, "finish_reason": response.finish_reason})
        return response


def percentage(n, total):
    return f"{n / total:.2%}" if total else "无样本"


def cell(value):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text.replace("|", "\\|").replace("\n", "<br>")


def build_report(records, dataset, metadata):
    """同时更新原始记录和本测试的中文报告，保留中途执行结果。"""
    records = sorted(records, key=lambda r: r["id"])
    n = len(records)
    route_correct = sum(r["route_correct"] for r in records)
    complete_correct = sum(r["passed"] for r in records)
    confusion = {route: {actual: 0 for actual in (*ROUTE_NAMES, "error")} for route in ROUTE_NAMES}
    for r in records:
        actual = r["actual"]["route"] if r["actual"] else "error"
        confusion[r["expected"]["route"]][actual] += 1
    summary = {"planned_total": len(dataset), "completed": n, "route_correct": route_correct,
               "route_accuracy": route_correct / n if n else None,
               "route_and_permissions_correct": complete_correct,
               "route_and_permissions_accuracy": complete_correct / n if n else None,
               "call_errors": sum(r["error"] is not None for r in records), "confusion_matrix": confusion}
    report = {**metadata, "updated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
              "summary": summary, "dataset": dataset, "cases": records}
    return report


def write_markdown_report(report, output):
    """根据本次评测记录生成中文 Markdown 报告。"""
    metadata = report
    dataset = report["dataset"]
    records = report["cases"]
    summary = report["summary"]
    n = summary["completed"]
    route_correct = summary["route_correct"]
    complete_correct = summary["route_and_permissions_correct"]
    confusion = summary["confusion_matrix"]
    lines = ["# 真实模型路由准确率评测", "", f"模型：{metadata['model']}；温度：0；并发：{CONCURRENCY}。",
             f"开始时间（北京时间）：{metadata['started_at']}。", "",
             f"**计划 {len(dataset)} 条，已完成 {n} 条；路由正确 {route_correct} 条，准确率 {percentage(route_correct, n)}；路由与权限全部正确 {complete_correct} 条，通过率 {percentage(complete_correct, n)}。**",
             "", "## 测试口径", "", "标准答案在调用模型前固定，来自现有 Supervisor 提示词规则，由评测脚本作者标注，尚未经用户独立复核。测试请求为合成请求，不代表线上分布。",
             f"数据来源：{metadata['dataset_source']}；另有 {metadata.get('diagnostic_total', 0)} 条歧义请求不参与本轮模型调用与主准确率统计，留作独立诊断。",
             "路由准确率只比较最终 route；完整通过率同时比较三个业务权限。调用异常计为不正确。采用生产 Supervisor 的重试和降级流程，并保存每次原始响应。每条用例仅运行一次。",
             "多轮用例仅包含此前的用户请求，符合当前 Supervisor 输入方式；没有模拟业务工具或执行真实操作。",
             "", "## 按预期路由统计", "", "| 路由 | 已测 | 路由正确 | 路由准确率 | 路由与权限全部正确 | 完整通过率 |", "|---|---:|---:|---:|---:|---:|"]
    for route, label in ROUTE_NAMES.items():
        subset = [r for r in records if r["expected"]["route"] == route]
        correct, passed = sum(r["route_correct"] for r in subset), sum(r["passed"] for r in subset)
        lines.append(f"| {label} | {len(subset)} | {correct} | {percentage(correct, len(subset))} | {passed} | {percentage(passed, len(subset))} |")
    lines += ["", "## 单轮与多轮统计", "", "| 场景 | 已测 | 路由正确 | 路由准确率 |", "|---|---:|---:|---:|"]
    for scenario in ("单轮请求", "多轮用户指代"):
        subset = [r for r in records if r["scenario"] == scenario]
        correct = sum(r["route_correct"] for r in subset)
        lines.append(f"| {scenario} | {len(subset)} | {correct} | {percentage(correct, len(subset))} |")
    lines += ["", "## 错误授权统计", "", "错误授权指标准答案为关闭、实际结果却为开启；这里只测模型权限判断，不等于后端越权拦截。", "",
              "| 权限 | 应关闭用例数 | 错误开启次数 | 错误开启比例 |", "|---|---:|---:|---:|"]
    for key, label in (("allow_publish", "发布"), ("allow_analysis", "分析"), ("allow_automation", "自动化")):
        subset = [r for r in records if not r["expected"][key]]
        wrong = sum(bool(r["actual"] and r["actual"][key]) for r in subset)
        lines.append(f"| {label} | {len(subset)} | {wrong} | {percentage(wrong, len(subset))} |")
    lines += ["", "## 混淆矩阵", "", "行是预期路由，列是实际路由。", "",
              "| 预期 / 实际 | 内容生成 | 直接回复 | 业务操作 | 调用异常 |", "|---|---:|---:|---:|---:|"]
    for route, label in ROUTE_NAMES.items():
        lines.append(f"| {label} | " + " | ".join(str(confusion[route][a]) for a in (*ROUTE_NAMES, "error")) + " |")
    lines += ["", "## 未通过用例", "", "| 用例 | 用户提问记录 | 预期路由与权限 | 实际结果或异常 |", "|---|---|---|---|"]
    failures = [r for r in records if not r["passed"]]
    for r in failures:
        lines.append(f"| {r['id']} | {cell(' → '.join(m['content'] for m in r['messages']))} | {cell(r['expected'])} | {cell(r['error'] or r['actual'])} |")
    if not failures:
        lines.append("| 无 | — | — | — |")
    lines += ["", "## 全部用例", "", "| 用例 | 场景 | 最新请求 | 预期路由 | 实际路由 | 路由正确 | 权限正确 |", "|---|---|---|---|---|---|---|"]
    for r in records:
        actual = ROUTE_NAMES[r["actual"]["route"]] if r["actual"] else "调用异常"
        lines.append(f"| {r['id']} | {r['scenario']} | {cell(r['messages'][-1]['content'])} | {ROUTE_NAMES[r['expected']['route']]} | {actual} | {'是' if r['route_correct'] else '否'} | {'是' if r['permissions_correct'] else '否'} |")
    lines += ["", "## 歧义诊断用例（未执行，不计入主准确率）", "",
              "| 用例 | 请求 | 歧义原因 | 权限约束 |", "|---|---|---|---|"]
    for case in metadata.get("diagnostic_cases", []):
        lines.append(f"| {case['id']} | {cell(case['messages'][-1]['content'])} | {cell(case['rationale'])} | {cell(case['diagnostic_constraint'])} |")
    lines += ["", "## 复现与范围", "", f"Git 提交：{metadata['git_head']}；被测文件与数据集哈希见 JSON。",
              "在 backend 目录运行：`.venv/Scripts/python.exe -X utf8 tests/evaluate_supervisor_accuracy.py`。",
              "本轮不修改提示词或根据结果调整标准答案；若后续用这些用例调优，应另设独立测试集评测。",
              f"[完整用例、预期答案和原始模型响应]({output.name})", ""]
    output.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")



def save_report(records, dataset, metadata):
    """保存原始 JSON，并生成对应的中文报告。"""
    report = build_report(records, dataset, metadata)
    output = BACKEND / "tests" / "evaluation_results" / "supervisor_accuracy.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown_report(report, output)
    return report["summary"]


async def main():
    parser = argparse.ArgumentParser(description="评测真实模型路由，或仅校验测试集（不调用模型）")
    parser.add_argument("--validate-only", action="store_true", help="仅校验测试集，不调用模型")
    options = parser.parse_args()
    cases = build_cases()
    dataset = [case for case in cases if case["expected"] is not None]
    diagnostic = [case for case in cases if case["expected"] is None]
    if options.validate_only:
        print(f"数据校验通过：明确意图 {len(dataset)} 条，歧义诊断 {len(diagnostic)} 条；未调用模型。")
        return 0
    if not settings.llm_api_key:
        raise RuntimeError("模型密钥未配置，无法执行真实模型评测")
    metadata = {
        "started_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(), "model": settings.llm_model,
        "temperature": 0, "concurrency": CONCURRENCY, "python_version": platform.python_version(),
        "dataset_source": "本脚本内置测试用例",
        "diagnostic_total": len(diagnostic),
        "diagnostic_cases": diagnostic,
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=BACKEND, text=True).strip(),
        "dataset_sha256": hashlib.sha256(json.dumps(dataset, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
        "source_sha256": {name: hashlib.sha256((BACKEND / name).read_bytes()).hexdigest() for name in
                          ("app/agents/supervisor.py", "app/agents/prompts.py", "tests/evaluate_supervisor_accuracy.py")},
    }
    client = LLMClient(settings.llm_base_url, settings.llm_api_key, settings.llm_model, settings.llm_timeout_seconds)
    records = []
    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def evaluate(case):
        async with semaphore:
            llm = RecordingLLM(client)
            actual, error = None, None
            start = time.perf_counter()
            try:
                actual = await make_supervisor_node(llm)({"messages": case["messages"]}, {})
            except Exception as exc:
                # 使用项目封装后的中文异常；不记录模型密钥或请求头。
                error = {"type": type(exc).__name__, "message": str(exc)}
            route_correct = bool(actual and actual["route"] == case["expected"]["route"])
            permissions_correct = bool(actual and all(actual[k] == case["expected"][k] for k in
                                       ("allow_publish", "allow_analysis", "allow_automation")))
            record = {**case, "actual": actual, "error": error, "raw_responses": llm.responses,
                      "elapsed_seconds": round(time.perf_counter() - start, 3),
                      "route_correct": route_correct, "permissions_correct": permissions_correct,
                      "passed": route_correct and permissions_correct}
            records.append(record)
            save_report(records, dataset, metadata)
            if len(records) % 10 == 0 or len(records) == 1:
                print(f"进度 {len(records)}/{len(dataset)}；路由正确 {sum(r['route_correct'] for r in records)} 条", flush=True)
            return record

    # 先验证一次真实调用，连接或鉴权异常时不继续发出其余请求。
    try:
        first = await evaluate(dataset[0])
        if first["error"]:
            print("首次调用失败，已保存未完成报告，停止剩余调用。", flush=True)
            return 2
        await asyncio.gather(*(evaluate(case) for case in dataset[1:]))
    finally:
        await client._raw.close()
    summary = save_report(records, dataset, metadata)
    print(f"评测完成：路由准确率 {percentage(summary['route_correct'], summary['completed'])}；路由与权限全部正确比例 {percentage(summary['route_and_permissions_correct'], summary['completed'])}", flush=True)
    print(f"中文报告：{OUTPUT.with_suffix('.md')}", flush=True)
    return 0 if summary["completed"] == len(dataset) else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
