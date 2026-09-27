"""分析工具定义与本轮调用控制，业务实现通过接口注入。"""

from typing import Any, Protocol

from app.agents.tools import ToolSpec
from app.schemas.agent_analytics import (
    AnalysisRunArguments, ContentMetricsArguments, GenerateReportArguments, ListContentsArguments,
    ListReportsArguments, ReportArguments, SyncMetricsArguments, SyncStatusArguments,
)

ANALYTICS_TOOL_NAMES = frozenset({
    "list_published_contents", "get_content_metrics", "sync_account_metrics", "get_metrics_sync_status",
    "generate_analysis_report", "get_analysis_run_status", "list_analysis_reports", "get_analysis_report",
})


class AnalyticsHandlers(Protocol):
    async def list_contents(self, account_id: int | None, platform: str | None, days: int | None, offset: int, limit: int) -> dict[str, Any]: ...
    async def get_metrics(self, content_id: int, limit: int) -> dict[str, Any]: ...
    async def sync_metrics(self, account_id: int) -> dict[str, Any]: ...
    async def get_sync_status(self, sync_run_id: int) -> dict[str, Any]: ...
    async def generate_report(self, **data: Any) -> dict[str, Any]: ...
    async def get_analysis_status(self, analysis_run_id: int) -> dict[str, Any]: ...
    async def list_reports(self, limit: int, offset: int) -> dict[str, Any]: ...
    async def get_report(self, report_id: int) -> dict[str, Any]: ...


class AgentAnalyticsTools:
    def __init__(self, analytics: AnalyticsHandlers) -> None:
        self.analytics = analytics
        self._sync_receipts: dict[int, dict[str, Any]] = {}
        self._report_receipt: dict[str, Any] | None = None

    def build_specs(self, *, allow_analysis: bool) -> list[ToolSpec]:
        specs = [
            ("list_published_contents", "查询已保存作品及最新指标，可按账号/平台/近7、30、90天筛选、分页；返回真实作品 ID。", ListContentsArguments, self.analytics.list_contents),
            ("get_content_metrics", "按作品 ID 查询累计指标快照；保留缺失值和采集时间，不将不同日期累计值相加。", ContentMetricsArguments, self.analytics.get_metrics),
            ("get_metrics_sync_status", "按同步运行 ID 查询同步状态和采集数量。", SyncStatusArguments, self.analytics.get_sync_status),
            ("get_analysis_run_status", "按分析运行 ID 查询报告生成进度；成功结果含报告 ID。", AnalysisRunArguments, self.analytics.get_analysis_status),
            ("list_analysis_reports", "分页查询已保存分析报告摘要及真实报告 ID。", ListReportsArguments, self.analytics.list_reports),
            ("get_analysis_report", "按报告 ID 读取已保存分析报告正文。", ReportArguments, self.analytics.get_report),
        ]
        definitions = [ToolSpec(name, description, model.model_json_schema(), handler, model)
                       for name, description, model, handler in specs]

        async def sync(account_id: int) -> dict[str, Any]:
            if not allow_analysis:
                raise PermissionError("当前用户消息未要求同步或生成分析报告，只能查询已有数据")
            if account_id in self._sync_receipts:
                return {**self._sync_receipts[account_id], "reused": True}
            receipt = await self.analytics.sync_metrics(account_id)
            self._sync_receipts[account_id] = receipt
            return receipt

        async def generate(**data: Any) -> dict[str, Any]:
            if not allow_analysis:
                raise PermissionError("当前用户消息未要求同步或生成分析报告，只能查询已有数据")
            if self._report_receipt is not None:
                return {**self._report_receipt, "reused": True, "message": "本轮已创建分析运行，未重复生成报告，请查询已有运行。"}
            self._report_receipt = await self.analytics.generate_report(**data)
            return self._report_receipt

        definitions.append(ToolSpec("sync_account_metrics", "将指定账号的作品指标同步任务提交本机队列；返回同步运行编号，不等待完成。", SyncMetricsArguments.model_json_schema(), sync, SyncMetricsArguments))
        definitions.append(ToolSpec("generate_analysis_report", "后台生成单篇、近7/30/90天、全部或指定账号报告；sync_first=true等待同步成功后才分析。返回分析运行编号，不代表报告已完成。", GenerateReportArguments.model_json_schema(), generate, GenerateReportArguments))
        return definitions
