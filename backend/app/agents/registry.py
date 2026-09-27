"""Agent 工具的唯一组装与注册入口；每轮注入业务接口并保留独立回执。"""

from app.agents.analytics_tools import ANALYTICS_TOOL_NAMES, AgentAnalyticsTools, AnalyticsHandlers
from app.agents.automation_tools import AUTOMATION_TOOL_NAMES, AgentAutomationTools, AutomationHandlers
from app.agents.publishing_tools import PUBLISHING_TOOL_NAMES, AgentPublishingTools, PublishingHandlers
from app.agents.tools import ToolRegistry, ToolSpec, get_builtin_tool_specs

BUSINESS_TOOL_NAMES = PUBLISHING_TOOL_NAMES | ANALYTICS_TOOL_NAMES | AUTOMATION_TOOL_NAMES


def _build_registry(specs: list[ToolSpec]) -> ToolRegistry:
    registry = ToolRegistry()
    for spec in specs:
        registry.register(spec)
    return registry


def build_default_tool_registry() -> ToolRegistry:
    """内容 Agent 只开放内置创作工具，不注入业务操作能力。"""
    return _build_registry(get_builtin_tool_specs())


class AgentToolFactory:
    """会话服务使用的统一入口；新增业务工具集只在此处组装。"""

    def __init__(self, publishing: PublishingHandlers, analytics: AnalyticsHandlers | None = None,
                 automation: AutomationHandlers | None = None) -> None:
        self.publishing = AgentPublishingTools(publishing)
        self.analytics = AgentAnalyticsTools(analytics) if analytics is not None else None
        self.automation = AgentAutomationTools(automation) if automation is not None else None

    def registry(self, allow_publish: bool, *, allow_analysis: bool = False, allow_automation: bool = False) -> ToolRegistry:
        specs = get_builtin_tool_specs()
        specs.extend(self.publishing.build_specs(allow_publish=allow_publish))
        if self.analytics is not None:
            specs.extend(self.analytics.build_specs(allow_analysis=allow_analysis))
        if self.automation is not None:
            specs.extend(self.automation.build_specs(allow_automation=allow_automation))
        return _build_registry(specs)
