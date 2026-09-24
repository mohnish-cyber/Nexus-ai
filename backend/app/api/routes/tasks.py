from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import current_user
from app.core.context import RequestContext
from app.security.auth import CurrentUser
from app.services import tasks_service
from app.services.preferences import get_preferences, resolve_timezone
from app.services.timeparse import parse_when
from app.tools.tasks import schedule_reminder

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("")
async def list_tasks(view: Literal["open", "today", "overdue", "upcoming", "done", "all"] = "open",
                     user: CurrentUser = Depends(current_user)) -> list[dict[str, Any]]:
    tz = resolve_timezone(await get_preferences(user.id))
    return [tasks_service.task_to_dict(t) for t in await tasks_service.list_tasks(user.id, view=view, tz=tz)]


class TaskBody(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    notes: str | None = Field(default=None, max_length=4000)
    due: str | None = Field(default=None, max_length=100, description="ISO or natural language")
    priority: Literal["low", "normal", "high"] = "normal"
    remind: bool = False


@router.post("", status_code=201)
async def create_task(body: TaskBody, user: CurrentUser = Depends(current_user)) -> dict[str, Any]:
    prefs = await get_preferences(user.id)
    tz = resolve_timezone(prefs)
    due = parse_when(body.due, tz) if body.due else None
    task = await tasks_service.create_task(user.id, body.title, notes=body.notes, due_at=due, priority=body.priority)
    if body.remind and due:
        ctx = RequestContext(user=user, preferences=prefs)
        a = await schedule_reminder(ctx, body.title, due, task_id=str(task.id))
        task = await tasks_service.update_task(user.id, task.id, automation_id=a.id)
    return tasks_service.task_to_dict(task)


class TaskPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    notes: str | None = Field(default=None, max_length=4000)
    status: Literal["open", "done", "cancelled"] | None = None
    priority: Literal["low", "normal", "high"] | None = None
    due_at: datetime | None = None


@router.patch("/{task_id}")
async def update_task(task_id: uuid.UUID, body: TaskPatch, user: CurrentUser = Depends(current_user)) -> dict[str, Any]:
    fields = body.model_dump(exclude_unset=True)
    return tasks_service.task_to_dict(await tasks_service.update_task(user.id, task_id, **fields))


@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: uuid.UUID, user: CurrentUser = Depends(current_user)) -> None:
    await tasks_service.delete_task(user.id, task_id)
