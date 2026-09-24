"""Permission broker and tool executor gating."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.database.session import session_scope
from app.models import PermissionGrant, ToolCall
from app.security import permissions
from app.security.risk import RiskLevel
from app.tools.executor import execute_tool


async def _authorize(ctx, risk: RiskLevel, allow_always: bool = True, scope: str = "scope-a"):
    return await permissions.permission_broker.authorize(
        ctx, tool="forget", agent="Test", risk=risk, scope=scope, summary="Do the thing", reason="test",
        details={"x": 1}, allow_always=allow_always)


async def test_low_risk_runs_automatically(make_ctx) -> None:
    outcome = await _authorize(make_ctx(interactive=False), RiskLevel.LOW)
    assert outcome.allowed and outcome.approval == "auto"


async def test_medium_risk_denied_without_interactive_channel(make_ctx) -> None:
    outcome = await _authorize(make_ctx(interactive=False), RiskLevel.MEDIUM)
    assert not outcome.allowed and outcome.approval == "non_interactive"


async def test_medium_allowed_once_does_not_persist(make_ctx, events) -> None:
    ctx = make_ctx(approver="allow_once")
    outcome = await _authorize(ctx, RiskLevel.MEDIUM)
    assert outcome.allowed and outcome.approval == "allow_once"
    assert any(e["type"] == "permission_request" and e["permission"]["allow_always"] for e in events)
    async with session_scope() as db:
        assert (await db.execute(select(PermissionGrant))).scalars().all() == []


async def test_always_allow_creates_scoped_grant(make_ctx) -> None:
    outcome = await _authorize(make_ctx(approver="always_allow"), RiskLevel.MEDIUM)
    assert outcome.allowed and outcome.approval == "always_allow"
    # Same tool + scope: no prompt, even non-interactively.
    again = await _authorize(make_ctx(interactive=False), RiskLevel.MEDIUM)
    assert again.allowed and again.approval == "always_allow"
    # Different scope: still needs approval.
    other = await _authorize(make_ctx(interactive=False), RiskLevel.MEDIUM, scope="scope-b")
    assert not other.allowed


async def test_high_risk_never_always_allowed(make_ctx, events) -> None:
    outcome = await _authorize(make_ctx(approver="always_allow"), RiskLevel.HIGH)
    assert outcome.allowed and outcome.approval == "allow_once"
    request = next(e for e in events if e["type"] == "permission_request")
    assert request["permission"]["allow_always"] is False
    async with session_scope() as db:
        assert (await db.execute(select(PermissionGrant))).scalars().all() == []
    # And the next HIGH request still asks.
    denied = await _authorize(make_ctx(interactive=False), RiskLevel.HIGH)
    assert not denied.allowed


async def test_deny(make_ctx) -> None:
    outcome = await _authorize(make_ctx(approver="deny"), RiskLevel.HIGH)
    assert not outcome.allowed and outcome.approval == "denied"


async def test_timeout_expires(make_ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(permissions, "APPROVAL_TIMEOUT_SECONDS", 0.05)
    outcome = await _authorize(make_ctx(), RiskLevel.MEDIUM)
    assert not outcome.allowed and outcome.approval == "expired"


async def test_other_user_cannot_resolve(make_ctx, events) -> None:
    import asyncio
    import uuid

    ctx = make_ctx()
    task = asyncio.create_task(_authorize(ctx, RiskLevel.HIGH))
    for _ in range(50):
        await asyncio.sleep(0.01)
        if any(e["type"] == "permission_request" for e in events):
            break
    pid = uuid.UUID(next(e for e in events if e["type"] == "permission_request")["permission"]["id"])
    assert permissions.permission_broker.resolve(pid, uuid.uuid4(), permissions.Decision.ALLOW_ONCE) is False
    assert permissions.permission_broker.resolve(pid, ctx.user.id, permissions.Decision.DENY) is True
    assert not (await task).allowed


async def test_user_can_disable_medium_confirmations(make_ctx) -> None:
    ctx = make_ctx(interactive=False, preferences={"permissions": {"confirm_medium_actions": False}})
    assert (await _authorize(ctx, RiskLevel.MEDIUM)).allowed
    assert not (await _authorize(ctx, RiskLevel.HIGH)).allowed  # HIGH always asks


async def test_executor_validates_arguments(make_ctx) -> None:
    ctx = make_ctx()
    ex = await execute_tool(ctx, "create_reminder", {"message": "x"}, agent="Test")
    assert not ex.ok and ex.error.code == "invalid_arguments"
    ex = await execute_tool(ctx, "create_reminder", {"message": "x", "when": "tomorrow", "evil": 1}, agent="Test")
    assert not ex.ok and ex.error.code == "invalid_arguments"


async def test_executor_enforces_agent_allowlist(make_ctx) -> None:
    ex = await execute_tool(make_ctx(), "delete_path", {"path": "/tmp/x"}, agent="Test",
                            allowed_tools={"recall"})
    assert not ex.ok and ex.error.code == "unknown_tool"


async def test_executor_audits_and_records_denial(make_ctx) -> None:
    ctx = make_ctx(interactive=False)
    ex = await execute_tool(ctx, "forget", {"query": "anything"}, agent="Test")
    assert not ex.ok and ex.record.status == "denied"
    assert "NOT performed" in ex.model_content()
    async with session_scope() as db:
        calls = (await db.execute(select(ToolCall))).scalars().all()
    assert calls and calls[0].status == "denied" and calls[0].approval == "non_interactive"
