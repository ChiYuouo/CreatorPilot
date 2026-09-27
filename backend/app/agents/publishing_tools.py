"""素材与发布工具定义；通过注入的业务接口执行，不依赖数据库或 API。"""

from typing import Any, Protocol

from app.agents.tools import ToolSpec
from app.schemas.agent_operations import (
    AssetArguments, ListAccountsArguments, ListAssetsArguments, ListJobsArguments,
    PublishStatusArguments, SubmitPublishArguments, ToolArguments,
)

PUBLISHING_TOOL_NAMES = frozenset({
    "list_assets", "get_asset", "list_accounts", "list_platforms",
    "list_publish_jobs", "get_publish_status", "submit_publish",
})


class PublishingHandlers(Protocol):
    """Agent 所需的素材与发布业务接口；实现由会话服务注入。"""

    async def list_assets(self, search: str, media_type: str | None, offset: int, limit: int) -> dict[str, Any]: ...
    async def get_asset(self, asset_id: int) -> dict[str, Any]: ...
    async def list_accounts(self, platform: str | None) -> dict[str, Any]: ...
    async def list_platforms(self) -> dict[str, Any]: ...
    async def list_jobs(self, limit: int) -> dict[str, Any]: ...
    async def get_status(self, job_id: int) -> dict[str, Any]: ...
    async def submit_publish(self, **data: Any) -> dict[str, Any]: ...


class AgentPublishingTools:
    """提供发布工具定义，限制发布意图并复用本轮成功提交回执。"""

    def __init__(self, publishing: PublishingHandlers) -> None:
        self.publishing = publishing
        self._submission: dict[str, Any] | None = None

    def build_specs(self, *, allow_publish: bool) -> list[ToolSpec]:
        specs = [
            ("list_assets", "查询当前用户素材，返回真实 ID/名称/类型，可按名称搜索、按类型筛选并分页。", ListAssetsArguments, self.publishing.list_assets),
            ("get_asset", "按素材 ID 查询详情，确认所选素材；不返回存储路径。", AssetArguments, self.publishing.get_asset),
            ("list_accounts", "查询当前用户账号 ID、平台、备注和登录状态；不返回凭证。", ListAccountsArguments, self.publishing.list_accounts),
            ("list_platforms", "查询支持的发布平台和标题/描述/标签/分区约束。", ToolArguments, self.publishing.list_platforms),
            ("list_publish_jobs", "查询最近发布任务的 ID 和状态。", ListJobsArguments, self.publishing.list_jobs),
            ("get_publish_status", "按任务 ID 查询发布进度，submitted 只表示已提交平台。", PublishStatusArguments, self.publishing.get_status),
        ]
        definitions = [ToolSpec(name, description, model.model_json_schema(), handler, model)
                       for name, description, model, handler in specs]

        async def submit(**data: Any) -> dict[str, Any]:
            if not allow_publish:
                raise PermissionError("当前用户消息未明确要求实际发布，请先确认发布意图")
            if self._submission is not None:
                return {**self._submission, "reused": True, "message": "本轮已提交任务，未再次发布；请查询已有任务。"}
            self._submission = await self.publishing.submit_publish(**data)
            return self._submission
        definitions.append(ToolSpec("submit_publish", "提交已有视频或图文到一个或多个账号；图文需传完整有序 image_asset_ids，asset_id 为首图；可传带时区的 scheduled_at 提交平台预约。只返回创建/排队结果，不能当作上传完成。",
                                  SubmitPublishArguments.model_json_schema(), submit, SubmitPublishArguments))
        return definitions
