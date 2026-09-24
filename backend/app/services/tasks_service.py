"""To-do tasks."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.core.errors import NotFoundError
from app.database.session import session_scope
from app.models import Task
from app.models.base import utcnow


def task_to_dict(t: Task) -> dict[str, Any]:
    return {
        "id": str(t.id),
        "title": t.title,
        "notes": t.notes,
        "status": t.status,
        "priority": t.priority,
        "due_at": t.due_at.isoformat() if t.due_at else None,
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
        "automation_id": str(t.automation_id) if t.automation_id else None,
        "source": t.source,
        "created_at": t.created_at.isoformat(),
    }


async def create_task(user_id: uuid.UUID, title: str, *, notes: str | None = None, due_at: datetime | None = None,
                      priority: str = "normal", source: str = "user") -> Task:
    async with session_scope() as db:
        t = Task(user_id=user_id, title=title[:300], notes=notes, due_at=due_at, priority=priority, source=source)
        db.add(t)
        await db.flush()
        return t


async def list_tasks(user_id: uuid.UUID, *, view: str = "open", tz: str = "UTC", limit: int = 200) -> list[Task]:
    """view: open | today | overdue | upcoming | done | all"""
    now = utcnow()
    zone = ZoneInfo(tz)
    local_now = now.astimezone(zone)
    start_today = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_today = start_today + timedelta(days=1)
    stmt = select(Task).where(Task.user_id == user_id)
    if view == "done":
        stmt = stmt.where(Task.status == "done")
    elif view != "all":
        stmt = stmt.where(Task.status == "open")
    if view == "today":
        stmt = stmt.where(Task.due_at.is_not(None), Task.due_at < end_today)
    elif view == "overdue":
        stmt = stmt.where(Task.due_at.is_not(None), Task.due_at < now)
    elif view == "upcoming":
        stmt = stmt.where(Task.due_at.is_not(None), Task.due_at >= now)
    stmt = stmt.order_by(Task.due_at.is_(None), Task.due_at, Task.created_at.desc()).limit(limit)
    async with session_scope() as db:
        return list((await db.execute(stmt)).scalars().all())


async def get_task(user_id: uuid.UUID, task_id: uuid.UUID) -> Task:
    async with session_scope() as db:
        t = await db.get(Task, task_id)
    if t is None or t.user_id != user_id:
        raise NotFoundError("That task was not found.", code="task_not_found")
    return t


async def find_task(user_id: uuid.UUID, query: str) -> Task:
    async with session_scope() as db:
        rows = (await db.execute(
            select(Task).where(Task.user_id == user_id, Task.status == "open",
                               func.lower(Task.title).like(f"%{query.lower()}%")).limit(2)
        )).scalars().all()
    if not rows:
        raise NotFoundError(f"No open task matches “{query}”.", code="task_not_found")
    return rows[0]


async def update_task(user_id: uuid.UUID, task_id: uuid.UUID, **fields: Any) -> Task:
    async with session_scope() as db:
        t = await db.get(Task, task_id)
        if t is None or t.user_id != user_id:
            raise NotFoundError("That task was not found.", code="task_not_found")
        for k in ("title", "notes", "priority", "due_at", "automation_id"):
            if k in fields:
                setattr(t, k, fields[k])
        if "status" in fields and fields["status"]:
            t.status = fields["status"]
            t.completed_at = utcnow() if t.status == "done" else None
        await db.flush()
        return t


async def delete_task(user_id: uuid.UUID, task_id: uuid.UUID) -> None:
    async with session_scope() as db:
        t = await db.get(Task, task_id)
        if t is None or t.user_id != user_id:
            raise NotFoundError("That task was not found.", code="task_not_found")
        await db.delete(t)
