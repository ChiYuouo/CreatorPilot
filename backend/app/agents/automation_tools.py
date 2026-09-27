"""自动化工具定义与本轮写入权限；统一注册仍在 registry.py。"""

import json
from typing import Any, Protocol

from app.agents.tools import ToolHandler, ToolSpec
from app.schemas.agent_automation import (
    AutomationRunArguments, AutomationTaskArguments, CreateAutomationArguments,
    ListAutomationArguments, ListAutomationRunsArguments, SetAutomationEnabledArguments,
    UpdateAutomationArguments,
)

AUTOMATION_TOOL_NAMES = frozenset({
    "list_automation_tasks", "get_automation_task", "create_automation_task", "update_automation_task",
    "set_automation_enabled", "delete_automation_task", "list_automation_runs", "get_automation_run",
})


class AutomationHandlers(Protocol):
    async def list_tasks(self, offset: int, limit: int) -> dict[str, Any]: ...
    async def get_task(self, task_id: int) -> dict[str, Any]: ...
    async def create_task(self, **data: Any) -> dict[str, Any]: ...
    async def update_task(self, task_id: int, changes: dict[str, Any]) -> dict[str, Any]: ...
    async def set_enabled(self, task_id: int, enabled: bool) -> dict[str, Any]: ...
    async def delete_task(self, task_id: int) -> dict[str, Any]: ...
    async def list_runs(self, task_id: int | None, offset: int, limit: int) -> dict[str, Any]: ...
    async def get_run(self, run_id: int) -> dict[str, Any]: ...


class AgentAutomationTools:
    def __init__(self, automation: AutomationHandlers) -> None:
        self.automation = automation
        self._receipts: dict[str, dict[str, Any]] = {}

    def build_specs(self, *, allow_automation: bool) -> list[ToolSpec]:
        read_specs = [
            ("list_automation_tasks", "分页查询当前用户每周自动化计划，返回计划 ID、启用状态及下次执行时间。", ListAutomationArguments, self.automation.list_tasks),
            ("get_automation_task", "按计划 ID 查询当前每周计划详情；计划 ID 与运行 ID 不同。", AutomationTaskArguments, self.automation.get_task),
            ("list_automation_runs", "分页查询周期计划执行历史，可按计划 ID 筛选；不包含一次性分析运行。", ListAutomationRunsArguments, self.automation.list_runs),
            ("get_automation_run", "按周期运行 ID 查询真实执行状态、错误或报告 ID，不会触发再次执行。", AutomationRunArguments, self.automation.get_run),
        ]
        write_specs = [
            ("create_automation_task", "创建每周指标同步或分析报告计划；weekday周一0至周日6，默认上海时区；不支持每日、一次性或自动发布计划。", CreateAutomationArguments, self.automation.create_task),
            ("update_automation_task", "按计划 ID 局部修改名称、每周时间、时区或业务范围；仅传要修改的字段，payload局部合并，不修改任务类型。", UpdateAutomationArguments, self.automation.update_task),
            ("set_automation_enabled", "暂停或恢复指定每周计划；暂停取消排队和等待同步的运行，不撤销已执行的同步。", SetAutomationEnabledArguments, self.automation.set_enabled),
            ("delete_automation_task", "按计划 ID 软删除自动化计划，保留执行历史；仅用户明确要求删除时调用。", AutomationTaskArguments, self.automation.delete_task),
        ]
        definitions = [ToolSpec(name, description, model.model_json_schema(), handler, model)
                       for name, description, model, handler in read_specs]

        def guarded(name: str, handler: ToolHandler) -> ToolHandler:
            async def execute(**data: Any) -> dict[str, Any]:
                if not allow_automation:
                    raise PermissionError("当前用户消息未要求创建、修改、暂停、恢复或删除自动化计划，只能查询")
                key = name + json.dumps(data, sort_keys=True, ensure_ascii=False)
                if key in self._receipts:
                    return {**self._receipts[key], "reused": True}
                receipt = await handler(**data)
                if name != "create_automation_task":
                    # 同一轮暂停→恢复→暂停必须真正执行，不能复用过期的修改回执。
                    self._receipts = {key: value for key, value in self._receipts.items()
                                      if key.startswith("create_automation_task")}
                self._receipts[key] = receipt
                return receipt
            return execute

        definitions.extend(ToolSpec(name, description, model.model_json_schema(), guarded(name, handler), model)
                           for name, description, model, handler in write_specs)
        return definitions
