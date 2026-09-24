"""Agents, tools, activity feed (observability) and audit history."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.agents.registry import agent_catalog
from app.api.deps import current_user
from app.database.session import session_scope
from app.models import AgentRun, AuditLog, PermissionRequest, ToolCall
from app.security.auth import CurrentUser
from app.tools.registry import all_tools

router = APIRouter(tags=["agents"])


@router.get("/api/agents")
async def agents(_: CurrentUser = Depends(current_user)) -> list[dict[str, Any]]:
    items = agent_catalog()
    for item in items:  # schemas are large; the UI only needs names
        item.pop("input_schema", None)
        item.pop("output_schema", None)
    return items


@router.get("/api/tools")
async def tools(_: CurrentUser = Depends(current_user)) -> list[dict[str, Any]]:
    return [t.public_info() for t in all_tools()]


@router.get("/api/activity")
async def activity(limit: int = Query(default=50, ge=1, le=200), user: CurrentUser = Depends(current_user)) -> dict[str, Any]:
    """Concise history of what agents and tools actually did (no private reasoning)."""
    async with session_scope() as db:
        runs = (await db.execute(select(AgentRun).where(AgentRun.user_id == user.id)
                                 .order_by(AgentRun.started_at.desc()).limit(limit))).scalars().all()
        calls = (await db.execute(select(ToolCall).where(ToolCall.user_id == user.id)
                                  .order_by(ToolCall.created_at.desc()).limit(limit))).scalars().all()
    return {
        "agent_runs": [
            {"id": str(r.id), "agent": r.agent, "status": r.status, "task": r.task[:200], "summary": (r.summary or "")[:300],
             "error": r.error, "started_at": r.started_at.isoformat(),
             "finished_at": r.finished_at.isoformat() if r.finished_at else None,
             "conversation_id": str(r.conversation_id) if r.conversation_id else None}
            for r in runs
        ],
        "tool_calls": [
            {"id": str(c.id), "tool": c.tool, "agent": c.agent, "status": c.status, "risk": c.risk_level,
             "approval": c.approval, "summary": c.result_summary, "error": c.error, "duration_ms": c.duration_ms,
             "created_at": c.created_at.isoformat()}
            for c in calls
        ],
    }


@router.get("/api/audit")
async def audit(limit: int = Query(default=100, ge=1, le=500), user: CurrentUser = Depends(current_user)) -> dict[str, Any]:
    async with session_scope() as db:
        perms = (await db.execute(select(PermissionRequest).where(PermissionRequest.user_id == user.id)
                                  .order_by(PermissionRequest.created_at.desc()).limit(limit))).scalars().all()
        logs = (await db.execute(select(AuditLog).where(AuditLog.user_id == user.id)
                                 .order_by(AuditLog.created_at.desc()).limit(limit))).scalars().all()
    return {
        "permission_requests": [
            {"id": str(p.id), "tool": p.tool, "agent": p.agent, "risk": p.risk_level, "summary": p.summary,
             "reason": p.reason, "status": p.status, "decision": p.decision, "created_at": p.created_at.isoformat(),
             "decided_at": p.decided_at.isoformat() if p.decided_at else None}
            for p in perms
        ],
        "events": [{"id": str(e.id), "event": e.event, "detail": e.detail, "created_at": e.created_at.isoformat()}
                   for e in logs],
    }
