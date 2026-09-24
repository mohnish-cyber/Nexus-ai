"""Permission broker: decides whether a tool call may run, and asks the user
when it needs approval.

Policy:
* LOW risk    -> runs automatically.
* MEDIUM risk -> asks the user unless (a) the user disabled confirmations for
                 medium-risk actions, or (b) an "Always Allow" grant exists for
                 the same tool + scope.
* HIGH risk   -> always asks. "Always Allow" is never offered.
* Non-interactive contexts (REST calls, background automations) cannot ask,
  so anything needing approval is denied with a clear explanation.

Approval requests are persisted (audit trail) and resolved through an
in-process future, fed either by the WebSocket or the REST decision endpoint.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.database.session import session_scope
from app.models import PermissionGrant, PermissionRequest
from app.models.base import utcnow
from app.security.redaction import redact_value
from app.security.risk import RiskLevel

if TYPE_CHECKING:
    from app.core.context import RequestContext

logger = logging.getLogger(__name__)

APPROVAL_TIMEOUT_SECONDS = 180


class Decision(StrEnum):
    ALLOW_ONCE = "allow_once"
    ALWAYS_ALLOW = "always_allow"
    DENY = "deny"


@dataclass
class ApprovalOutcome:
    allowed: bool
    approval: str  # auto | policy | always_allow | allow_once | denied | expired | non_interactive
    message: str | None = None


@dataclass
class _Pending:
    user_id: uuid.UUID
    request_id: str
    future: asyncio.Future[Decision]


class PermissionBroker:
    def __init__(self) -> None:
        self._pending: dict[uuid.UUID, _Pending] = {}

    # ------------------------------------------------------------------
    async def authorize(
        self,
        ctx: RequestContext,
        *,
        tool: str,
        agent: str | None,
        risk: RiskLevel,
        scope: str,
        summary: str,
        reason: str | None,
        details: dict[str, Any],
        allow_always: bool,
    ) -> ApprovalOutcome:
        if risk == RiskLevel.LOW:
            return ApprovalOutcome(True, "auto")

        if risk == RiskLevel.MEDIUM:
            if not ctx.preferences.get("permissions", {}).get("confirm_medium_actions", True):
                return ApprovalOutcome(True, "policy")
            if await self._has_grant(ctx.user.id, tool, scope):
                return ApprovalOutcome(True, "always_allow")

        if not ctx.interactive:
            return ApprovalOutcome(
                False,
                "non_interactive",
                f"'{summary}' needs your approval, which can only be given in the NEXUS app.",
            )

        allow_always = allow_always and risk == RiskLevel.MEDIUM
        return await self._ask(ctx, tool=tool, agent=agent, risk=risk, scope=scope, summary=summary,
                               reason=reason, details=details, allow_always=allow_always)

    # ------------------------------------------------------------------
    async def _has_grant(self, user_id: uuid.UUID, tool: str, scope: str) -> bool:
        async with session_scope() as db:
            grants = (
                await db.execute(
                    select(PermissionGrant).where(PermissionGrant.user_id == user_id, PermissionGrant.tool == tool)
                )
            ).scalars().all()
            for g in grants:
                if g.scope == "*" or g.scope == scope or (g.scope.endswith("/") and scope.startswith(g.scope)):
                    g.last_used_at = utcnow()
                    g.use_count += 1
                    return True
        return False

    async def _ask(self, ctx: RequestContext, *, tool: str, agent: str | None, risk: RiskLevel, scope: str,
                   summary: str, reason: str | None, details: dict[str, Any], allow_always: bool) -> ApprovalOutcome:
        safe_details = redact_value(details)
        async with session_scope() as db:
            req = PermissionRequest(
                user_id=ctx.user.id,
                request_id=ctx.request_id,
                tool=tool,
                agent=agent,
                risk_level=risk.value,
                summary=summary,
                reason=reason,
                details={**safe_details, "scope": scope, "allow_always": allow_always},
            )
            db.add(req)
            await db.flush()
            perm_id = req.id

        loop = asyncio.get_running_loop()
        future: asyncio.Future[Decision] = loop.create_future()
        self._pending[perm_id] = _Pending(ctx.user.id, ctx.request_id, future)
        expires_at = utcnow() + timedelta(seconds=APPROVAL_TIMEOUT_SECONDS)
        await ctx.emit(
            {
                "type": "permission_request",
                "permission": {
                    "id": str(perm_id),
                    "tool": tool,
                    "agent": agent,
                    "risk": risk.value,
                    "summary": summary,
                    "reason": reason,
                    "details": safe_details,
                    "scope": scope,
                    "allow_always": allow_always,
                    "expires_at": expires_at.isoformat(),
                },
            }
        )
        await ctx.set_state("waiting", "Waiting for your approval")
        status, decision_value = "expired", None
        try:
            decision = await asyncio.wait_for(asyncio.shield(future), timeout=APPROVAL_TIMEOUT_SECONDS)
            decision_value = decision.value
            status = "denied" if decision == Decision.DENY else "allowed"
        except TimeoutError:
            decision = None
        except asyncio.CancelledError:
            decision = None
            status = "denied"
            raise
        finally:
            self._pending.pop(perm_id, None)
            async with session_scope() as db:
                row = await db.get(PermissionRequest, perm_id)
                if row is not None:
                    row.status = status
                    row.decision = decision_value
                    row.decided_at = utcnow()
                if decision == Decision.ALWAYS_ALLOW and allow_always:
                    db.add(PermissionGrant(user_id=ctx.user.id, tool=tool, scope=scope))
            await ctx.emit({"type": "permission_resolved", "permission_id": str(perm_id), "status": status})
            await ctx.set_state("executing", None)

        if decision is None:
            return ApprovalOutcome(False, "expired", f"No response to the approval request for '{summary}'.")
        if decision == Decision.DENY:
            return ApprovalOutcome(False, "denied", f"You declined: {summary}.")
        if decision == Decision.ALWAYS_ALLOW and not allow_always:
            # Client tried to escalate a HIGH-risk approval to "always": treat as once.
            return ApprovalOutcome(True, "allow_once")
        return ApprovalOutcome(True, decision.value)

    # ------------------------------------------------------------------
    def resolve(self, permission_id: uuid.UUID, user_id: uuid.UUID, decision: Decision) -> bool:
        entry = self._pending.get(permission_id)
        if entry is None:
            return False
        if entry.user_id != user_id:
            logger.warning("User %s tried to resolve permission %s owned by another user", user_id, permission_id)
            return False
        if not entry.future.done():
            entry.future.set_result(decision)
        return True

    def cancel_for_request(self, request_id: str) -> None:
        """Deny any approvals still pending for an aborted request."""
        for entry in list(self._pending.values()):
            if entry.request_id == request_id and not entry.future.done():
                entry.future.set_result(Decision.DENY)

    def pending_count(self) -> int:
        return len(self._pending)


permission_broker = PermissionBroker()
