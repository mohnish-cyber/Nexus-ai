"""Per-request execution context shared by NexusCore, agents and tools."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.core.errors import ErrorInfo
from app.models.base import utcnow
from app.security.auth import CurrentUser

logger = logging.getLogger(__name__)

EmitFn = Callable[[dict[str, Any]], Awaitable[None]]


async def _discard(_event: dict[str, Any]) -> None:
    return None


@dataclass
class ActionRecord:
    """One tool execution, as it actually happened. This is the ground truth
    the verifier uses - NEXUS never reports an action that is not here."""

    id: str
    tool: str
    agent: str | None
    summary: str
    status: str  # succeeded | failed | denied | cancelled
    risk: str
    approval: str
    error: ErrorInfo | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tool": self.tool,
            "agent": self.agent,
            "summary": self.summary,
            "status": self.status,
            "risk": self.risk,
            "approval": self.approval,
            "error": self.error.to_dict() if self.error else None,
            "data": self.data,
        }


@dataclass
class RequestContext:
    user: CurrentUser
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    conversation_id: uuid.UUID | None = None
    emit_fn: EmitFn = _discard
    # False for REST calls and background jobs: nothing can be approved.
    interactive: bool = False
    preferences: dict[str, Any] = field(default_factory=dict)
    attachments: list[Any] = field(default_factory=list)  # StoredFile rows
    actions: list[ActionRecord] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    agent_run_id: uuid.UUID | None = None
    current_agent: str | None = None
    origin: str = "chat"  # chat | automation | api

    # ------------------------------------------------------------------
    async def emit(self, event: dict[str, Any]) -> None:
        event.setdefault("request_id", self.request_id)
        try:
            await self.emit_fn(event)
        except Exception as exc:  # the client may have disconnected
            logger.debug("emit failed: %s", exc)

    async def set_state(self, state: str, label: str | None) -> None:
        await self.emit({"type": "status", "state": state, "label": label})

    async def activity(self, agent: str, action: str, status: str = "started", detail: str | None = None,
                       activity_id: str | None = None) -> str:
        activity_id = activity_id or uuid.uuid4().hex[:12]
        await self.emit(
            {
                "type": "activity",
                "id": activity_id,
                "agent": agent,
                "action": action,
                "status": status,
                "detail": detail,
                "ts": utcnow().isoformat(),
            }
        )
        return activity_id

    def add_source(self, title: str, url: str | None = None, kind: str = "web", snippet: str | None = None) -> None:
        key = url or title
        if any((s.get("url") or s.get("title")) == key for s in self.sources):
            return
        self.sources.append({"title": title[:200], "url": url, "kind": kind, "snippet": (snippet or "")[:300]})

    @property
    def cancelled(self) -> bool:
        return self.cancel_event.is_set()

    # ------------------------------------------------------------------
    @property
    def timezone(self) -> str:
        from app.services.preferences import resolve_timezone

        return resolve_timezone(self.preferences)

    def now_local(self) -> datetime:
        try:
            return utcnow().astimezone(ZoneInfo(self.timezone))
        except Exception:
            return utcnow()

    @property
    def workspace_roots(self) -> list:
        from app.services.preferences import workspace_roots

        return workspace_roots(self.preferences)
