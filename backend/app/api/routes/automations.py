from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import current_user
from app.core.errors import ValidationFailedError
from app.security.auth import CurrentUser
from app.security.rate_limit import rate_limiter
from app.services import automation_service as autos
from app.services.preferences import get_preferences, resolve_timezone
from app.services.scheduler import get_scheduler
from app.services.timeparse import parse_when
from app.tools.tasks import PriceWatchConfig, ScheduleSpec, build_schedule

router = APIRouter(prefix="/api/automations", tags=["automations"])


@router.get("")
async def list_automations(user: CurrentUser = Depends(current_user)) -> list[dict[str, Any]]:
    return [autos.automation_to_dict(a) for a in await autos.list_automations(user.id)]


class AutomationBody(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    kind: Literal["reminder", "agent_task", "price_watch", "weather_check"]
    schedule: ScheduleSpec
    message: str | None = Field(default=None, max_length=500)
    prompt: str | None = Field(default=None, max_length=2000)
    price_watch: PriceWatchConfig | None = None
    location: str | None = Field(default=None, max_length=120)
    day_offset: int = Field(default=0, ge=0, le=2)


@router.post("", status_code=201)
async def create_automation(body: AutomationBody, user: CurrentUser = Depends(current_user)) -> dict[str, Any]:
    tz = resolve_timezone(await get_preferences(user.id))
    trigger, schedule = build_schedule(body.schedule, tz)
    if body.kind == "reminder":
        if not body.message:
            raise ValidationFailedError("A reminder needs a message.", code="invalid_automation")
        config: dict[str, Any] = {"message": body.message}
    elif body.kind == "agent_task":
        if not body.prompt:
            raise ValidationFailedError("An agent task needs a prompt.", code="invalid_automation")
        config = {"prompt": body.prompt}
    elif body.kind == "price_watch":
        if body.price_watch is None:
            raise ValidationFailedError("A price watch needs a URL and a threshold.", code="invalid_automation")
        config = {**body.price_watch.model_dump(mode="json"), "message": body.message}
    else:
        config = {"location": body.location, "day_offset": body.day_offset, "condition": "rain",
                  "message": body.message or "Rain is expected - take an umbrella."}
    a = await autos.create_automation(user.id, name=body.name, kind=body.kind, trigger_type=trigger,
                                      schedule=schedule, tz=tz, config=config)
    return autos.automation_to_dict(a)


class StatusBody(BaseModel):
    status: Literal["active", "paused"]


@router.patch("/{automation_id}")
async def set_status(automation_id: uuid.UUID, body: StatusBody, user: CurrentUser = Depends(current_user)) -> dict[str, Any]:
    return autos.automation_to_dict(await autos.set_status(user.id, automation_id, body.status))


@router.post("/{automation_id}/run")
async def run_now(automation_id: uuid.UUID, user: CurrentUser = Depends(current_user)) -> dict[str, Any]:
    """Run an automation immediately (does not change its schedule)."""
    rate_limiter.check(f"run-automation:{user.id}", 10)
    a = await autos.get_automation(user.id, automation_id)
    result = await get_scheduler().run_job(a.id)
    refreshed = await autos.get_automation(user.id, automation_id)
    return {"result": result, "automation": autos.automation_to_dict(refreshed)}


@router.get("/{automation_id}/runs")
async def runs(automation_id: uuid.UUID, user: CurrentUser = Depends(current_user)) -> list[dict[str, Any]]:
    return [
        {"id": str(r.id), "status": r.status, "condition_met": r.condition_met, "result": r.result, "error": r.error,
         "started_at": r.started_at.isoformat(), "finished_at": r.finished_at.isoformat() if r.finished_at else None}
        for r in await autos.list_runs(user.id, automation_id)
    ]


@router.delete("/{automation_id}", status_code=204)
async def delete(automation_id: uuid.UUID, user: CurrentUser = Depends(current_user)) -> None:
    await autos.delete_automation(user.id, automation_id)


class ParseBody(BaseModel):
    when: str = Field(min_length=1, max_length=100)


@router.post("/parse-time")
async def parse_time(body: ParseBody, user: CurrentUser = Depends(current_user)) -> dict[str, Any]:
    tz = resolve_timezone(await get_preferences(user.id))
    when = parse_when(body.when, tz)
    return {"utc": when.isoformat(), "timezone": tz}
