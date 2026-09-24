"""Automation definitions and schedule computation (the runner lives in
`app/services/scheduler.py`)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from croniter import croniter
from sqlalchemy import select

from app.core.errors import NotFoundError, ValidationFailedError
from app.database.session import session_scope
from app.models import Automation, AutomationRun
from app.models.base import utcnow

KINDS = {"reminder", "agent_task", "price_watch", "weather_check"}
TRIGGERS = {"once", "interval", "cron"}
MIN_INTERVAL_SECONDS = {"reminder": 60, "agent_task": 3600, "price_watch": 3600, "weather_check": 3600}


def validate_schedule(kind: str, trigger_type: str, schedule: dict[str, Any], tz: str) -> None:
    if kind not in KINDS:
        raise ValidationFailedError(f"Unknown automation type '{kind}'.", code="invalid_automation")
    if trigger_type not in TRIGGERS:
        raise ValidationFailedError(f"Unknown trigger '{trigger_type}'.", code="invalid_automation")
    try:
        ZoneInfo(tz)
    except Exception as exc:
        raise ValidationFailedError(f"Unknown timezone '{tz}'.", code="invalid_timezone") from exc
    if trigger_type == "once":
        if "run_at" not in schedule:
            raise ValidationFailedError("A one-time automation needs a run time.", code="invalid_automation")
        datetime.fromisoformat(str(schedule["run_at"]))
    elif trigger_type == "interval":
        seconds = int(schedule.get("seconds", 0))
        minimum = MIN_INTERVAL_SECONDS.get(kind, 3600)
        if seconds < minimum:
            raise ValidationFailedError(
                f"That runs too often (minimum every {minimum // 60} minutes for this type).",
                code="interval_too_short")
    else:
        expr = str(schedule.get("cron", ""))
        if not croniter.is_valid(expr):
            raise ValidationFailedError(f"'{expr}' is not a valid cron expression.", code="invalid_cron",
                                        next_step="Use 5 fields, e.g. '0 8 * * *' for 8 AM daily.")
        it = croniter(expr, datetime(2026, 1, 1))
        first = it.get_next(datetime)
        second = it.get_next(datetime)
        if (second - first).total_seconds() < MIN_INTERVAL_SECONDS.get(kind, 3600):
            raise ValidationFailedError("That schedule runs too often.", code="interval_too_short")


def compute_next_run(trigger_type: str, schedule: dict[str, Any], tz: str, after: datetime,
                     last_run: datetime | None = None) -> datetime | None:
    if trigger_type == "once":
        if last_run is not None:
            return None
        run_at = datetime.fromisoformat(str(schedule["run_at"]))
        if run_at.tzinfo is None:
            run_at = run_at.replace(tzinfo=ZoneInfo(tz))
        return run_at.astimezone(UTC)
    if trigger_type == "interval":
        base = last_run or after
        nxt = base + timedelta(seconds=int(schedule["seconds"]))
        return max(nxt, after)
    zone = ZoneInfo(tz)
    local_after = after.astimezone(zone)
    nxt = croniter(str(schedule["cron"]), local_after).get_next(datetime)
    if nxt.tzinfo is None:
        nxt = nxt.replace(tzinfo=zone)
    return nxt.astimezone(UTC)


_DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def describe_schedule(trigger_type: str, schedule: dict[str, Any]) -> str:
    if trigger_type == "once":
        return "one-time"
    if trigger_type == "cron":
        parts = str(schedule.get("cron", "")).split()
        if len(parts) == 5 and parts[0].isdigit() and parts[1].isdigit() and parts[2] == "*" and parts[3] == "*":
            at = f"{int(parts[1]):02d}:{int(parts[0]):02d}"
            if parts[4] == "*":
                return f"daily at {at}"
            if parts[4].isdigit():
                return f"every {_DAYS[int(parts[4]) % 7]} at {at}"
            if parts[4] == "1-5":
                return f"weekdays at {at}"
    if trigger_type == "interval":
        s = int(schedule.get("seconds", 0))
        if s % 86400 == 0:
            return f"every {s // 86400} day(s)"
        if s % 3600 == 0:
            return f"every {s // 3600} hour(s)"
        return f"every {s // 60} minute(s)"
    return f"cron '{schedule.get('cron')}'"


def automation_to_dict(a: Automation) -> dict[str, Any]:
    return {
        "id": str(a.id),
        "name": a.name,
        "kind": a.kind,
        "trigger_type": a.trigger_type,
        "schedule": a.schedule,
        "schedule_text": describe_schedule(a.trigger_type, a.schedule),
        "timezone": a.timezone,
        "config": a.config,
        "status": a.status,
        "next_run_at": a.next_run_at.isoformat() if a.next_run_at else None,
        "last_run_at": a.last_run_at.isoformat() if a.last_run_at else None,
        "last_result": a.last_result,
        "run_count": a.run_count,
        "failure_count": a.failure_count,
        "created_at": a.created_at.isoformat(),
    }


async def create_automation(user_id: uuid.UUID, *, name: str, kind: str, trigger_type: str,
                            schedule: dict[str, Any], tz: str, config: dict[str, Any]) -> Automation:
    validate_schedule(kind, trigger_type, schedule, tz)
    now = utcnow()
    next_run = compute_next_run(trigger_type, schedule, tz, now)
    async with session_scope() as db:
        a = Automation(user_id=user_id, name=name[:200], kind=kind, trigger_type=trigger_type, schedule=schedule,
                       timezone=tz, config=config, status="active", next_run_at=next_run)
        db.add(a)
        await db.flush()
        return a


async def list_automations(user_id: uuid.UUID, include_completed: bool = True) -> list[Automation]:
    stmt = select(Automation).where(Automation.user_id == user_id)
    if not include_completed:
        stmt = stmt.where(Automation.status.in_(("active", "paused")))
    stmt = stmt.order_by(Automation.status, Automation.next_run_at)
    async with session_scope() as db:
        return list((await db.execute(stmt)).scalars().all())


async def get_automation(user_id: uuid.UUID, automation_id: uuid.UUID) -> Automation:
    async with session_scope() as db:
        a = await db.get(Automation, automation_id)
    if a is None or a.user_id != user_id:
        raise NotFoundError("That automation was not found.", code="automation_not_found")
    return a


async def set_status(user_id: uuid.UUID, automation_id: uuid.UUID, status: str) -> Automation:
    if status not in ("active", "paused"):
        raise ValidationFailedError("Status must be active or paused.", code="invalid_status")
    async with session_scope() as db:
        a = await db.get(Automation, automation_id)
        if a is None or a.user_id != user_id:
            raise NotFoundError("That automation was not found.", code="automation_not_found")
        a.status = status
        if status == "active":
            a.failure_count = 0
            a.next_run_at = compute_next_run(a.trigger_type, a.schedule, a.timezone, utcnow(), a.last_run_at)
            if a.next_run_at is None:
                a.status = "completed"
        await db.flush()
        return a


async def delete_automation(user_id: uuid.UUID, automation_id: uuid.UUID) -> Automation:
    async with session_scope() as db:
        a = await db.get(Automation, automation_id)
        if a is None or a.user_id != user_id:
            raise NotFoundError("That automation was not found.", code="automation_not_found")
        await db.delete(a)
        return a


async def list_runs(user_id: uuid.UUID, automation_id: uuid.UUID, limit: int = 20) -> list[AutomationRun]:
    async with session_scope() as db:
        return list((await db.execute(
            select(AutomationRun).where(AutomationRun.user_id == user_id, AutomationRun.automation_id == automation_id)
            .order_by(AutomationRun.started_at.desc()).limit(limit)
        )).scalars().all())
