"""按当前用户管理自动化；复用原业务入口，不在 Agent 内操作数据库。"""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.exceptions import AppError
from app.models.automation import AutomationRun, AutomationTask
from app.schemas.automation import AutomationRunRead, AutomationTaskRead, AutomationTaskWrite
from app.services import automation_service


class AgentAutomationService:
    def __init__(self, user_id: int, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.user_id = user_id
        self.session_factory = session_factory

    async def list_tasks(self, offset: int, limit: int) -> dict[str, Any]:
        async with self.session_factory() as db:
            filters = [AutomationTask.user_id == self.user_id, AutomationTask.deleted_at.is_(None)]
            total = await db.scalar(select(func.count()).select_from(AutomationTask).where(*filters)) or 0
            rows = await db.scalars(select(AutomationTask).where(*filters).order_by(AutomationTask.id.desc()).offset(offset).limit(limit))
            return {"items": [AutomationTaskRead.model_validate(row).model_dump(mode="json") for row in rows],
                    "total": total, "next_offset": offset + limit if offset + limit < total else None}

    async def get_task(self, task_id: int) -> dict[str, Any]:
        async with self.session_factory() as db:
            task = await automation_service.get_task(db, self.user_id, task_id)
            return AutomationTaskRead.model_validate(task).model_dump(mode="json")

    async def create_task(self, **data: Any) -> dict[str, Any]:
        async with self.session_factory() as db:
            task = await automation_service.create_task(db, self.user_id, AutomationTaskWrite(**data))
            return {"task": AutomationTaskRead.model_validate(task).model_dump(mode="json"),
                    "message": "每周计划已保存；下次执行时间不表示任务已经执行，完成后可查询运行历史及报告。"}

    async def update_task(self, task_id: int, changes: dict[str, Any]) -> dict[str, Any]:
        async with self.session_factory() as db:
            task = await automation_service.get_task(db, self.user_id, task_id)
            data = AutomationTaskWrite.model_validate(task, from_attributes=True).model_dump()
            # 参数模型序列化后可包含未提供字段的 None，不覆盖原值。
            changes = {key: value for key, value in changes.items() if value is not None}
            if "payload" in changes:
                changes["payload"] = {**data["payload"], **changes["payload"]}
            data.update(changes)
            updated = await automation_service.update_task(db, self.user_id, task_id, AutomationTaskWrite(**data))
            return AutomationTaskRead.model_validate(updated).model_dump(mode="json")

    async def set_enabled(self, task_id: int, enabled: bool) -> dict[str, Any]:
        return await self.update_task(task_id, {"enabled": enabled})

    async def delete_task(self, task_id: int) -> dict[str, Any]:
        async with self.session_factory() as db:
            await automation_service.delete_task(db, self.user_id, task_id)
            return {"task_id": task_id, "deleted": True,
                    "message": "计划已删除，历史保留；排队及等待同步的运行已取消，已经执行的同步不会撤销。"}

    async def list_runs(self, task_id: int | None, offset: int, limit: int) -> dict[str, Any]:
        async with self.session_factory() as db:
            # 删除计划的历史仍可按原 ID 查询，不要求计划尚未软删除。
            if task_id is not None:
                owned = await db.scalar(select(AutomationTask.id).where(AutomationTask.id == task_id, AutomationTask.user_id == self.user_id))
                if owned is None:
                    raise AppError(404, "automation_task_not_found", "自动化任务不存在")
            filters = [AutomationRun.user_id == self.user_id, AutomationRun.task_id.is_not(None)]
            if task_id is not None:
                filters.append(AutomationRun.task_id == task_id)
            total = await db.scalar(select(func.count()).select_from(AutomationRun).where(*filters)) or 0
            rows = await db.scalars(select(AutomationRun).where(*filters).order_by(AutomationRun.scheduled_for.desc(), AutomationRun.id.desc()).offset(offset).limit(limit))
            return {"items": [AutomationRunRead.model_validate(row).model_dump(mode="json") for row in rows],
                    "total": total, "next_offset": offset + limit if offset + limit < total else None}

    async def get_run(self, run_id: int) -> dict[str, Any]:
        async with self.session_factory() as db:
            run = await db.scalar(select(AutomationRun).where(AutomationRun.id == run_id, AutomationRun.user_id == self.user_id, AutomationRun.task_id.is_not(None)))
            if run is None:
                raise AppError(404, "automation_run_not_found", "自动化运行不存在")
            return AutomationRunRead.model_validate(run).model_dump(mode="json")
