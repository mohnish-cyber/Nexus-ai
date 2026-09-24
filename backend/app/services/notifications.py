"""Notifications: persisted in the database, pushed live over WebSockets.

The background scheduler (embedded or in a separate worker process) only
writes rows. A small relay loop in the API process picks up new rows and
pushes them to connected clients, so both deployment modes share one path.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import select, update

from app.database.session import session_scope
from app.models import Notification
from app.models.base import utcnow

logger = logging.getLogger(__name__)


def notification_to_dict(n: Notification) -> dict[str, Any]:
    return {
        "id": str(n.id),
        "title": n.title,
        "body": n.body,
        "kind": n.kind,
        "status": n.status,
        "automation_id": str(n.automation_id) if n.automation_id else None,
        "data": n.data or {},
        "created_at": n.created_at.isoformat(),
    }


async def create_notification(user_id: uuid.UUID, title: str, body: str, kind: str = "system",
                              automation_id: uuid.UUID | None = None, data: dict[str, Any] | None = None) -> Notification:
    async with session_scope() as db:
        n = Notification(user_id=user_id, title=title[:200], body=body[:8000], kind=kind,
                         automation_id=automation_id, data=data or {})
        db.add(n)
        await db.flush()
        return n


async def list_notifications(user_id: uuid.UUID, status: str | None = None, limit: int = 50) -> list[Notification]:
    stmt = select(Notification).where(Notification.user_id == user_id)
    if status:
        stmt = stmt.where(Notification.status == status)
    stmt = stmt.order_by(Notification.created_at.desc()).limit(limit)
    async with session_scope() as db:
        return list((await db.execute(stmt)).scalars().all())


async def mark_read(user_id: uuid.UUID, ids: list[uuid.UUID] | None = None) -> int:
    stmt = update(Notification).where(Notification.user_id == user_id, Notification.status == "unread")
    if ids:
        stmt = stmt.where(Notification.id.in_(ids))
    async with session_scope() as db:
        result = await db.execute(stmt.values(status="read", read_at=utcnow()))
        return result.rowcount or 0


class NotificationHub:
    """In-process fan-out of events to a user's connected WebSockets."""

    def __init__(self) -> None:
        self._subscribers: dict[uuid.UUID, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)
        self._relay_task: asyncio.Task[None] | None = None
        self._high_water: datetime | None = None

    def subscribe(self, user_id: uuid.UUID) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=200)
        self._subscribers[user_id].add(q)
        return q

    def unsubscribe(self, user_id: uuid.UUID, q: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers[user_id].discard(q)
        if not self._subscribers[user_id]:
            self._subscribers.pop(user_id, None)

    def publish(self, user_id: uuid.UUID, event: dict[str, Any]) -> None:
        for q in list(self._subscribers.get(user_id, ())):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("Dropping event for slow client of user %s", user_id)

    def connected_users(self) -> int:
        return len(self._subscribers)

    # ------------------------------------------------------------------
    async def _relay(self, interval: float) -> None:
        self._high_water = utcnow()
        while True:
            try:
                await asyncio.sleep(interval)
                async with session_scope() as db:
                    rows = (await db.execute(
                        select(Notification).where(Notification.created_at > self._high_water)
                        .order_by(Notification.created_at).limit(200)
                    )).scalars().all()
                for n in rows:
                    self.publish(n.user_id, {"type": "notification", "notification": notification_to_dict(n)})
                    self._high_water = max(self._high_water, n.created_at)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Notification relay error: %s", exc)

    def start_relay(self, interval: float = 3.0) -> None:
        if self._relay_task is None or self._relay_task.done():
            self._relay_task = asyncio.create_task(self._relay(interval), name="notification-relay")

    async def stop_relay(self) -> None:
        if self._relay_task is not None:
            self._relay_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._relay_task
            self._relay_task = None


hub = NotificationHub()
