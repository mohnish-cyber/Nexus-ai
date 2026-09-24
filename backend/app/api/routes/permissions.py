from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import current_user
from app.core.errors import NotFoundError
from app.database.session import session_scope
from app.models import PermissionGrant, PermissionRequest
from app.security.auth import CurrentUser
from app.security.permissions import Decision, permission_broker
from app.services.audit import audit_event

router = APIRouter(prefix="/api/permissions", tags=["permissions"])


@router.get("/pending")
async def pending(user: CurrentUser = Depends(current_user)) -> list[dict[str, Any]]:
    async with session_scope() as db:
        rows = (await db.execute(select(PermissionRequest).where(
            PermissionRequest.user_id == user.id, PermissionRequest.status == "pending"
        ).order_by(PermissionRequest.created_at.desc()).limit(20))).scalars().all()
    return [{"id": str(r.id), "tool": r.tool, "agent": r.agent, "risk": r.risk_level, "summary": r.summary,
             "reason": r.reason, "details": r.details, "allow_always": bool((r.details or {}).get("allow_always")),
             "created_at": r.created_at.isoformat()} for r in rows]


class DecisionBody(BaseModel):
    decision: Decision


@router.post("/{permission_id}/decision")
async def decide(permission_id: uuid.UUID, body: DecisionBody, user: CurrentUser = Depends(current_user)) -> dict[str, Any]:
    ok = permission_broker.resolve(permission_id, user.id, body.decision)
    if not ok:
        raise NotFoundError("That approval request is no longer pending.", code="permission_not_pending")
    return {"ok": True}


@router.get("/grants")
async def grants(user: CurrentUser = Depends(current_user)) -> list[dict[str, Any]]:
    async with session_scope() as db:
        rows = (await db.execute(select(PermissionGrant).where(PermissionGrant.user_id == user.id)
                                 .order_by(PermissionGrant.created_at.desc()))).scalars().all()
    return [{"id": str(g.id), "tool": g.tool, "scope": g.scope, "use_count": g.use_count,
             "created_at": g.created_at.isoformat(),
             "last_used_at": g.last_used_at.isoformat() if g.last_used_at else None} for g in rows]


@router.delete("/grants/{grant_id}", status_code=204)
async def revoke(grant_id: uuid.UUID, user: CurrentUser = Depends(current_user)) -> None:
    async with session_scope() as db:
        g = await db.get(PermissionGrant, grant_id)
        if g is None or g.user_id != user.id:
            raise NotFoundError("That permission was not found.", code="grant_not_found")
        await db.delete(g)
    await audit_event(user.id, "permission_revoked", {"grant_id": str(grant_id)})
