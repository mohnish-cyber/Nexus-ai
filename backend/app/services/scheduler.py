"""Database-backed automation scheduler.

Runs either embedded in the API process (development) or as its own worker
process (`python -m app.worker`). Jobs live in the `automations` table, so
they survive restarts. Each due job is claimed with a lease (`locked_until`)
before running, so several scheduler instances never run the same job twice.

    poll → claim due jobs → run by kind (reminder / agent_task / price_watch /
    weather_check) → evaluate condition → notify → compute next run → release
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import socket
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import and_, or_, select, update

from app.core.errors import ErrorInfo, NexusError
from app.database.session import session_scope
from app.models import Automation, AutomationRun
from app.models.base import utcnow
from app.services import notifications
from app.services.automation_service import compute_next_run

logger = logging.getLogger(__name__)

LEASE = timedelta(minutes=15)
MAX_FAILURES = 5


class AutomationScheduler:
    def __init__(self, poll_seconds: float = 20.0, concurrency: int = 4) -> None:
        self.poll_seconds = poll_seconds
        self.worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
        self._task: asyncio.Task[None] | None = None
        self._sem = asyncio.Semaphore(concurrency)
        self.last_tick_at = None
        self.jobs_run = 0

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        if not self.running:
            self._task = asyncio.create_task(self._loop(), name="automation-scheduler")
            logger.info("Automation scheduler started (%s, every %ss)", self.worker_id, self.poll_seconds)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Scheduler tick failed")
            await asyncio.sleep(self.poll_seconds)

    # ------------------------------------------------------------------
    async def tick(self) -> int:
        now = utcnow()
        self.last_tick_at = now
        async with session_scope() as db:
            due = (await db.execute(
                select(Automation.id).where(
                    Automation.status == "active",
                    Automation.next_run_at.is_not(None),
                    Automation.next_run_at <= now,
                    or_(Automation.locked_until.is_(None), Automation.locked_until < now),
                ).order_by(Automation.next_run_at).limit(20)
            )).scalars().all()
        claimed = []
        for job_id in due:
            async with session_scope() as db:
                res = await db.execute(
                    update(Automation)
                    .where(and_(Automation.id == job_id,
                                or_(Automation.locked_until.is_(None), Automation.locked_until < now)))
                    .values(locked_until=now + LEASE, locked_by=self.worker_id)
                )
                if res.rowcount == 1:
                    claimed.append(job_id)
        if claimed:
            await asyncio.gather(*(self._guarded(job_id) for job_id in claimed))
        return len(claimed)

    async def _guarded(self, job_id: uuid.UUID) -> None:
        async with self._sem:
            await self.run_job(job_id)

    async def run_job(self, job_id: uuid.UUID) -> dict[str, Any]:
        async with session_scope() as db:
            job = await db.get(Automation, job_id)
            if job is None:
                return {}
            run = AutomationRun(automation_id=job.id, user_id=job.user_id)
            db.add(run)
            await db.flush()
            run_id = run.id
            snapshot = {"id": job.id, "user_id": job.user_id, "name": job.name, "kind": job.kind,
                        "config": dict(job.config or {}), "timezone": job.timezone,
                        "last_result": dict(job.last_result or {})}
        self.jobs_run += 1
        started = utcnow()
        result: dict[str, Any] = {}
        error: ErrorInfo | None = None
        try:
            executor = EXECUTORS[snapshot["kind"]]
            result = await asyncio.wait_for(executor(snapshot), timeout=600)
        except NexusError as exc:
            error = exc.info
        except TimeoutError:
            error = ErrorInfo("automation_timeout", "The automation took too long and was stopped.")
        except Exception as exc:
            logger.exception("Automation %s crashed", job_id)
            error = ErrorInfo("automation_crashed", "The automation failed unexpectedly.",
                              reason=f"{exc.__class__.__name__}: {str(exc)[:200]}")

        failed_notice = False
        async with session_scope() as db:
            job = await db.get(Automation, job_id)
            run = await db.get(AutomationRun, run_id)
            if run is not None:
                run.status = "failed" if error else "succeeded"
                run.condition_met = result.get("condition_met")
                run.result = result
                run.error = error.to_dict() if error else None
                run.finished_at = utcnow()
            if job is not None:
                job.last_run_at = started
                job.run_count += 1
                job.locked_until = None
                job.locked_by = None
                job.last_result = {**result, "error": error.to_dict() if error else None, "at": started.isoformat()}
                if error:
                    job.failure_count += 1
                    if job.failure_count >= MAX_FAILURES:
                        job.status = "failed"
                        failed_notice = True
                    # retry with backoff, but never later than the regular schedule
                    backoff = started + timedelta(minutes=5 * (2 ** min(job.failure_count, 5)))
                    regular = compute_next_run(job.trigger_type, job.schedule, job.timezone, utcnow(), job.last_run_at)
                    job.next_run_at = min(d for d in (backoff, regular) if d is not None) if job.trigger_type != "once" else backoff
                else:
                    job.failure_count = 0
                    job.next_run_at = compute_next_run(job.trigger_type, job.schedule, job.timezone, utcnow(),
                                                       job.last_run_at)
                    if job.next_run_at is None:
                        job.status = "completed"
        if error is not None and failed_notice:
            await notifications.create_notification(
                snapshot["user_id"], f"Automation stopped: {snapshot['name']}",
                f"It failed {MAX_FAILURES} times in a row. Last error: {error.message}"
                + (f" ({error.reason})" if error.reason else ""),
                kind="automation", automation_id=snapshot["id"])
        return result


# ---------------------------------------------------------------------------
# Executors
# ---------------------------------------------------------------------------


async def _run_reminder(job: dict[str, Any]) -> dict[str, Any]:
    message = job["config"].get("message") or job["name"]
    await notifications.create_notification(job["user_id"], "Reminder", message, kind="reminder",
                                            automation_id=job["id"], data={"task_id": job["config"].get("task_id")})
    return {"condition_met": True, "summary": f"Reminded: {message}"}


async def _run_weather(job: dict[str, Any]) -> dict[str, Any]:
    from app.services import weather
    from app.services.preferences import get_preferences

    prefs = await get_preferences(job["user_id"])
    cfg = job["config"]
    place = await weather.resolve_place(cfg.get("location"), prefs)
    offset = int(cfg.get("day_offset", 0))
    data = await weather.forecast(place, days=offset + 1, units=(prefs.get("regional") or {}).get("units", "metric"))
    day = data["days"][offset] if len(data["days"]) > offset else None
    met = bool(day and day["rain_expected"])
    if met:
        await notifications.create_notification(
            job["user_id"], job["name"],
            f"{cfg.get('message') or 'Rain is expected.'} ({day['summary']}, {day['precipitation_probability']}% chance "
            f"on {day['date']} in {data['place']})",
            kind="automation", automation_id=job["id"])
    return {"condition_met": met, "summary": f"{data['place']} {day['date'] if day else ''}: "
                                               f"{day['summary'] if day else 'no data'}"}


async def _run_price_watch(job: dict[str, Any]) -> dict[str, Any]:
    from app.core.errors import ToolExecutionError
    from app.security.url_guard import safe_fetch
    from app.services.price import extract_price

    cfg = job["config"]
    page = await safe_fetch(cfg["url"], max_bytes=4 * 1024 * 1024)
    if page.status_code >= 400:
        raise ToolExecutionError(f"The product page returned HTTP {page.status_code}.", code="price_fetch_failed",
                                 reason="The shop may block automated checks.")
    info = extract_price(page.text)
    if info is None:
        raise ToolExecutionError("Could not find a price on the product page.", code="price_not_found",
                                 reason="The page layout isn't machine-readable, or the price loads with JavaScript.")
    threshold = float(cfg["threshold"])
    met = info.price < threshold if cfg.get("direction", "below") == "below" else info.price > threshold
    prev = job.get("last_result") or {}
    changed = prev.get("price") != info.price
    if met and (not prev.get("condition_met") or changed):
        name = cfg.get("product") or info.title or "The product"
        cur = info.currency or ""
        await notifications.create_notification(
            job["user_id"], f"Price alert: {name[:80]}",
            f"Now {cur} {info.price:,.2f} ({cfg.get('direction', 'below')} your {cur} {threshold:,.2f} target). {cfg['url']}",
            kind="automation", automation_id=job["id"], data={"url": cfg["url"], "price": info.price})
    return {"condition_met": met, "price": info.price, "currency": info.currency, "method": info.method,
            "confidence": info.confidence, "summary": f"Price {info.price} ({info.confidence} confidence)"}


async def _run_agent_task(job: dict[str, Any]) -> dict[str, Any]:
    from app.core.context import RequestContext
    from app.core.nexus_core import ChatRequest, nexus_core
    from app.security.auth import load_user
    from app.services import conversation_service as convs
    from app.services.preferences import get_preferences

    user = await load_user(job["user_id"])
    if user is None:
        raise NexusError("The automation's owner no longer exists.", code="user_missing")
    conv_id = job["config"].get("conversation_id")
    if conv_id:
        try:
            await convs.get_messages(user.id, uuid.UUID(conv_id), limit=1)
        except NexusError:
            conv_id = None
    if not conv_id:
        conv = await convs.get_or_create(user.id, None, f"Automation: {job['name']}")
        conv_id = str(conv.id)
        async with session_scope() as db:
            row = await db.get(Automation, job["id"])
            if row is not None:
                row.config = {**(row.config or {}), "conversation_id": conv_id}
    ctx = RequestContext(user=user, interactive=False, origin="automation",
                         preferences=await get_preferences(user.id))
    msg = await nexus_core.handle(ctx, ChatRequest(text=job["config"]["prompt"], conversation_id=uuid.UUID(conv_id)))
    ok = msg.get("status") != "error"
    await notifications.create_notification(
        user.id, job["name"], msg.get("content", "")[:4000], kind="automation", automation_id=job["id"],
        data={"conversation_id": conv_id, "ok": ok})
    if not ok:
        err = (msg.get("meta") or {}).get("error") or {}
        raise NexusError(err.get("message") or "The automation's agent run failed.", code=err.get("code") or "agent_failed",
                         reason=err.get("reason"), next_step=err.get("next_step"))
    return {"condition_met": True, "summary": msg.get("content", "")[:300], "conversation_id": conv_id}


EXECUTORS = {
    "reminder": _run_reminder,
    "weather_check": _run_weather,
    "price_watch": _run_price_watch,
    "agent_task": _run_agent_task,
}

scheduler: AutomationScheduler | None = None


def get_scheduler(poll_seconds: float = 20.0) -> AutomationScheduler:
    global scheduler
    if scheduler is None:
        scheduler = AutomationScheduler(poll_seconds=poll_seconds)
    return scheduler
