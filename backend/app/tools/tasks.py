"""Tasks, reminders and automations."""

from __future__ import annotations

import re
import uuid
from typing import Any, Literal

from pydantic import Field, HttpUrl, field_validator

from app.core.context import RequestContext
from app.core.errors import ValidationFailedError
from app.security.risk import RiskLevel
from app.security.url_guard import validate_url_syntax
from app.services import automation_service as autos
from app.services import tasks_service
from app.services.timeparse import humanize, parse_when
from app.tools.base import Assessment, NoParams, Tool, ToolOutput, ToolParams


async def schedule_reminder(ctx: RequestContext, message: str, when_utc, task_id: str | None = None):
    return await autos.create_automation(
        ctx.user.id,
        name=f"Reminder: {message[:80]}",
        kind="reminder",
        trigger_type="once",
        schedule={"run_at": when_utc.isoformat()},
        tz=ctx.timezone,
        config={"message": message, **({"task_id": task_id} if task_id else {})},
    )


class ReminderParams(ToolParams):
    message: str = Field(min_length=1, max_length=500, description="What to remind the user about")
    when: str = Field(min_length=1, max_length=100,
                      description="When, in natural language or ISO-8601, e.g. 'tomorrow at 8 AM', 'in 20 minutes'")


class CreateReminderTool(Tool):
    name = "create_reminder"
    description = ("Schedule a one-time reminder notification. 'when' is interpreted in the user's timezone. "
                   "Returns the exact scheduled time - repeat it to the user.")
    Params = ReminderParams
    category = "automation"

    def describe_call(self, params: ReminderParams) -> str:
        return f"Scheduling a reminder: {params.message[:60]}"

    async def run(self, params: ReminderParams, ctx: RequestContext) -> ToolOutput:
        when = parse_when(params.when, ctx.timezone)
        a = await schedule_reminder(ctx, params.message, when)
        human = humanize(when, ctx.timezone)
        return ToolOutput(
            summary=f"Reminder set for {human}",
            content=f"Reminder scheduled (automation id {a.id}) for {human} ({ctx.timezone}): {params.message}",
            data={"automation_id": str(a.id), "run_at": when.isoformat(), "when": human},
        )


class CreateTaskParams(ToolParams):
    title: str = Field(min_length=1, max_length=300)
    notes: str | None = Field(default=None, max_length=2000)
    due: str | None = Field(default=None, max_length=100, description="Due date/time in natural language or ISO")
    priority: Literal["low", "normal", "high"] = "normal"
    remind: bool = Field(default=False, description="Also schedule a reminder at the due time")


class CreateTaskTool(Tool):
    name = "create_task"
    description = "Add a to-do task (optionally with a due date and a reminder at that time)."
    Params = CreateTaskParams
    category = "automation"

    def describe_call(self, params: CreateTaskParams) -> str:
        return f"Adding task “{params.title[:60]}”"

    async def run(self, params: CreateTaskParams, ctx: RequestContext) -> ToolOutput:
        due = parse_when(params.due, ctx.timezone) if params.due else None
        task = await tasks_service.create_task(ctx.user.id, params.title, notes=params.notes, due_at=due,
                                               priority=params.priority, source="assistant")
        extra = ""
        data: dict[str, Any] = {"task_id": str(task.id)}
        if params.remind and due:
            a = await schedule_reminder(ctx, params.title, due, task_id=str(task.id))
            await tasks_service.update_task(ctx.user.id, task.id, automation_id=a.id)
            extra = f" with a reminder {humanize(due, ctx.timezone)}"
            data["automation_id"] = str(a.id)
        due_txt = f", due {humanize(due, ctx.timezone)}" if due else ""
        return ToolOutput(summary=f"Added task “{params.title[:50]}”{due_txt}{extra}",
                          content=f"Task created (id {task.id}): {params.title}{due_txt}{extra}", data=data)


class ListTasksParams(ToolParams):
    view: Literal["open", "today", "overdue", "upcoming", "done", "all"] = "open"


class ListTasksTool(Tool):
    name = "list_tasks"
    description = "List the user's tasks. view='today' returns open tasks due today (and overdue ones)."
    Params = ListTasksParams
    category = "automation"

    def describe_call(self, params: ListTasksParams) -> str:
        return f"Checking your {params.view} tasks"

    async def run(self, params: ListTasksParams, ctx: RequestContext) -> ToolOutput:
        rows = await tasks_service.list_tasks(ctx.user.id, view=params.view, tz=ctx.timezone)
        lines = []
        for t in rows:
            due = f" (due {humanize(t.due_at, ctx.timezone)})" if t.due_at else ""
            lines.append(f"- [{t.status}] {t.title}{due} · priority {t.priority} · id {t.id}")
        return ToolOutput(summary=f"{len(rows)} {params.view} tasks",
                          content="\n".join(lines) or f"No {params.view} tasks.", data={"count": len(rows)})


class CompleteTaskParams(ToolParams):
    task_id: uuid.UUID | None = None
    title: str | None = Field(default=None, max_length=300, description="Used to find the task when id is unknown")


class CompleteTaskTool(Tool):
    name = "complete_task"
    description = "Mark a task as done."
    Params = CompleteTaskParams
    category = "automation"

    def describe_call(self, params: CompleteTaskParams) -> str:
        return f"Completing task {params.title or params.task_id}"

    async def run(self, params: CompleteTaskParams, ctx: RequestContext) -> ToolOutput:
        if params.task_id:
            task = await tasks_service.get_task(ctx.user.id, params.task_id)
        elif params.title:
            task = await tasks_service.find_task(ctx.user.id, params.title)
        else:
            raise ValidationFailedError("Say which task to complete.", code="invalid_arguments")
        await tasks_service.update_task(ctx.user.id, task.id, status="done")
        return ToolOutput(summary=f"Completed “{task.title[:60]}”", content=f"Task {task.id} marked done.",
                          data={"task_id": str(task.id)})


# ---------------------------------------------------------------------------
# Automations
# ---------------------------------------------------------------------------

_HHMM = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
_WEEKDAYS = {"monday": 1, "tuesday": 2, "wednesday": 3, "thursday": 4, "friday": 5, "saturday": 6, "sunday": 0}


class ScheduleSpec(ToolParams):
    type: Literal["daily", "weekly", "every_hours", "once", "cron"]
    time: str | None = Field(default=None, description="HH:MM (24h) in the user's timezone, for daily/weekly")
    weekday: Literal["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"] | None = None
    hours: int | None = Field(default=None, ge=1, le=168, description="For every_hours")
    at: str | None = Field(default=None, description="For once: natural language or ISO time")
    cron: str | None = Field(default=None, description="Raw 5-field cron expression (advanced)")


class PriceWatchConfig(ToolParams):
    url: HttpUrl
    threshold: float = Field(gt=0)
    direction: Literal["below", "above"] = "below"
    product: str | None = Field(default=None, max_length=200)

    @field_validator("url")
    @classmethod
    def _safe(cls, v: HttpUrl) -> HttpUrl:
        validate_url_syntax(str(v))
        return v


class CreateAutomationParams(ToolParams):
    name: str = Field(min_length=2, max_length=200)
    kind: Literal["agent_task", "price_watch", "weather_check"] = Field(
        description="agent_task: run a prompt (e.g. news digest); price_watch: alert on a price threshold; "
                    "weather_check: alert when rain is expected")
    schedule: ScheduleSpec
    prompt: str | None = Field(default=None, max_length=2000, description="For agent_task: what NEXUS should do each run")
    price_watch: PriceWatchConfig | None = None
    location: str | None = Field(default=None, max_length=120, description="For weather_check (default: saved location)")
    day_offset: int = Field(default=0, ge=0, le=2, description="For weather_check: 0 = same day, 1 = next day")
    message: str | None = Field(default=None, max_length=300, description="Notification text when the condition is met")


def build_schedule(spec: ScheduleSpec, tz: str) -> tuple[str, dict[str, Any]]:
    if spec.type in ("daily", "weekly"):
        m = _HHMM.match(spec.time or "")
        if not m:
            raise ValidationFailedError("A daily/weekly schedule needs a time like '08:00'.", code="invalid_schedule")
        hour, minute = int(m.group(1)), int(m.group(2))
        if spec.type == "daily":
            return "cron", {"cron": f"{minute} {hour} * * *"}
        if not spec.weekday:
            raise ValidationFailedError("A weekly schedule needs a weekday.", code="invalid_schedule")
        return "cron", {"cron": f"{minute} {hour} * * {_WEEKDAYS[spec.weekday]}"}
    if spec.type == "every_hours":
        return "interval", {"seconds": int(spec.hours or 24) * 3600}
    if spec.type == "once":
        return "once", {"run_at": parse_when(spec.at or "", tz).isoformat()}
    return "cron", {"cron": spec.cron or ""}


class CreateAutomationTool(Tool):
    name = "create_automation"
    description = ("Create a recurring background automation that runs on a schedule even when the app is closed: "
                   "daily AI news digest (agent_task), price alerts (price_watch), rain alerts (weather_check). "
                   "For one-off reminders use create_reminder instead.")
    Params = CreateAutomationParams
    category = "automation"
    timeout_seconds = 30

    def assess(self, params: CreateAutomationParams, ctx: RequestContext) -> Assessment:
        risk = RiskLevel.MEDIUM if params.kind == "agent_task" else RiskLevel.LOW
        return Assessment(risk, f"Create automation “{params.name[:60]}” ({params.schedule.type})",
                          scope=f"automation:{params.kind}",
                          details={"name": params.name, "kind": params.kind,
                                   "schedule": params.schedule.model_dump(exclude_none=True),
                                   "prompt": params.prompt})

    async def run(self, params: CreateAutomationParams, ctx: RequestContext) -> ToolOutput:
        trigger, schedule = build_schedule(params.schedule, ctx.timezone)
        if params.kind == "agent_task":
            if not params.prompt:
                raise ValidationFailedError("An agent task needs a prompt describing what to do.", code="invalid_automation")
            config: dict[str, Any] = {"prompt": params.prompt}
        elif params.kind == "price_watch":
            if params.price_watch is None:
                raise ValidationFailedError("A price watch needs a product URL and threshold.", code="invalid_automation")
            config = {**params.price_watch.model_dump(mode="json"), "message": params.message}
        else:
            config = {"location": params.location, "day_offset": params.day_offset, "condition": "rain",
                      "message": params.message or "Rain is expected - take an umbrella."}
        a = await autos.create_automation(ctx.user.id, name=params.name, kind=params.kind, trigger_type=trigger,
                                          schedule=schedule, tz=ctx.timezone, config=config)
        next_txt = humanize(a.next_run_at, ctx.timezone) if a.next_run_at else "never"
        return ToolOutput(
            summary=f"Automation “{params.name[:50]}” created (next run {next_txt})",
            content=f"Automation {a.id} created: {autos.describe_schedule(trigger, schedule)}; next run {next_txt}.",
            data={"automation_id": str(a.id), "next_run_at": a.next_run_at.isoformat() if a.next_run_at else None},
        )


class ListAutomationsTool(Tool):
    name = "list_automations"
    description = "List the user's automations and scheduled reminders."
    Params = NoParams
    category = "automation"

    def describe_call(self, params) -> str:
        return "Listing your automations"

    async def run(self, params: NoParams, ctx: RequestContext) -> ToolOutput:
        rows = await autos.list_automations(ctx.user.id, include_completed=False)
        lines = [
            f"- {a.name} [{a.kind}, {a.status}] {autos.describe_schedule(a.trigger_type, a.schedule)}; next: "
            f"{humanize(a.next_run_at, ctx.timezone) if a.next_run_at else '—'} · id {a.id}"
            for a in rows
        ]
        return ToolOutput(summary=f"{len(rows)} active automations", content="\n".join(lines) or "No automations.",
                          data={"count": len(rows)})


class CancelAutomationParams(ToolParams):
    automation_id: uuid.UUID


class CancelAutomationTool(Tool):
    name = "cancel_automation"
    description = "Delete an automation or scheduled reminder."
    Params = CancelAutomationParams
    risk = RiskLevel.MEDIUM
    category = "automation"

    def assess(self, params: CancelAutomationParams, ctx: RequestContext) -> Assessment:
        return Assessment(RiskLevel.MEDIUM, f"Delete automation {params.automation_id}", scope="automation",
                          details={"automation_id": str(params.automation_id)})

    async def run(self, params: CancelAutomationParams, ctx: RequestContext) -> ToolOutput:
        a = await autos.delete_automation(ctx.user.id, params.automation_id)
        return ToolOutput(summary=f"Deleted automation “{a.name[:60]}”", content=f"Automation {a.id} deleted.",
                          data={"automation_id": str(a.id)})
