"""自动化任务与执行历史接口。"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.automation import AutomationRunRead, AutomationTaskRead, AutomationTaskWrite
from app.services import automation_service

router = APIRouter()


@router.get("/tasks", response_model=list[AutomationTaskRead])
async def list_tasks(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[AutomationTaskRead]:
    tasks = await automation_service.list_tasks(db, user.id)
    return [AutomationTaskRead.model_validate(item) for item in tasks]


@router.post("/tasks", response_model=AutomationTaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    request: AutomationTaskWrite,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AutomationTaskRead:
    item = await automation_service.create_task(db, user.id, request)
    return AutomationTaskRead.model_validate(item)


@router.put("/tasks/{task_id}", response_model=AutomationTaskRead)
async def update_task(
    task_id: int,
    request: AutomationTaskWrite,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AutomationTaskRead:
    item = await automation_service.update_task(db, user.id, task_id, request)
    return AutomationTaskRead.model_validate(item)


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await automation_service.delete_task(db, user.id, task_id)


@router.get("/runs", response_model=list[AutomationRunRead])
async def list_runs(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[AutomationRunRead]:
    runs = await automation_service.list_runs(db, user.id)
    return [AutomationRunRead.model_validate(item) for item in runs]
