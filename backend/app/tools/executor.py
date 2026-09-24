"""Executes tool calls safely.

validate args -> check availability -> assess risk -> ask permission ->
run with timeout -> audit (tool_calls table) -> record in the action ledger.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.core.context import ActionRecord, RequestContext
from app.core.errors import ErrorInfo, NexusError
from app.database.session import session_scope
from app.models import ToolCall
from app.security.permissions import permission_broker
from app.security.redaction import redact_value
from app.tools.base import Tool, ToolOutput
from app.tools.registry import get_tool

logger = logging.getLogger(__name__)


@dataclass
class ToolExecution:
    ok: bool
    tool: str
    output: ToolOutput | None
    error: ErrorInfo | None
    record: ActionRecord

    def model_content(self) -> str:
        """Text returned to the model as the tool result."""
        if self.ok and self.output is not None:
            return self.output.content
        err = self.error or ErrorInfo("tool_failed", "The tool failed.")
        parts = [f"ERROR ({err.code}): {err.message}"]
        if err.reason:
            parts.append(f"Reason: {err.reason}")
        if err.next_step:
            parts.append(f"Suggested next step: {err.next_step}")
        if self.record.status == "denied":
            parts.append("The action was NOT performed. Do not claim it was.")
        return "\n".join(parts)


async def _audit(ctx: RequestContext, *, tool: str, agent: str | None, args: dict[str, Any], risk: str,
                 status: str, approval: str, summary: str | None, error: ErrorInfo | None, duration_ms: int) -> None:
    try:
        async with session_scope() as db:
            db.add(
                ToolCall(
                    user_id=ctx.user.id,
                    agent_run_id=ctx.agent_run_id,
                    request_id=ctx.request_id,
                    agent=agent,
                    tool=tool,
                    arguments=redact_value(args),
                    risk_level=risk,
                    status=status,
                    approval=approval,
                    result_summary=(summary or "")[:1000],
                    error=error.to_dict() if error else None,
                    duration_ms=duration_ms,
                )
            )
    except Exception as exc:  # auditing must never break the request
        logger.error("Failed to write tool audit record: %s", exc)


async def execute_tool(
    ctx: RequestContext,
    name: str,
    raw_args: dict[str, Any],
    *,
    agent: str | None,
    allowed_tools: set[str] | None = None,
    reason: str | None = None,
) -> ToolExecution:
    started = time.monotonic()
    record_id = uuid.uuid4().hex[:12]

    def _fail(error: ErrorInfo, status: str = "failed", risk: str = "low", approval: str = "auto",
              summary: str | None = None) -> ToolExecution:
        rec = ActionRecord(id=record_id, tool=name, agent=agent, summary=summary or name.replace("_", " "),
                           status=status, risk=risk, approval=approval, error=error)
        ctx.actions.append(rec)
        return ToolExecution(False, name, None, error, rec)

    tool: Tool | None = get_tool(name)
    if tool is None or (allowed_tools is not None and name not in allowed_tools):
        return _fail(ErrorInfo("unknown_tool", f"Tool '{name}' is not available to this agent."))

    if isinstance(raw_args, dict) and "__invalid_json__" in raw_args:
        return _fail(ErrorInfo("invalid_arguments", "The tool arguments were not valid JSON."))
    try:
        params = tool.Params.model_validate(raw_args or {})
    except ValidationError as exc:
        msg = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()[:5])
        return _fail(ErrorInfo("invalid_arguments", f"Invalid arguments for {name}: {msg}",
                               next_step="Fix the arguments and call the tool again."))

    available, why = await tool.available(ctx)
    if not available:
        err = ErrorInfo("tool_unavailable", f"{name.replace('_', ' ').capitalize()} is not available.", reason=why,
                        next_step="Configure it in Settings, or continue without it.")
        await _audit(ctx, tool=name, agent=agent, args=params.model_dump(), risk=tool.risk.value, status="failed",
                     approval="auto", summary=None, error=err, duration_ms=0)
        return _fail(err)

    try:
        assessment = tool.assess(params, ctx)
    except NexusError as exc:
        err = exc.info
        await _audit(ctx, tool=name, agent=agent, args=params.model_dump(), risk=tool.risk.value, status="denied",
                     approval="policy", summary=None, error=err, duration_ms=0)
        return _fail(err, status="denied", approval="policy")

    outcome = await permission_broker.authorize(
        ctx,
        tool=name,
        agent=agent,
        risk=assessment.risk,
        scope=assessment.scope,
        summary=assessment.summary,
        reason=reason,
        details=assessment.details or params.model_dump(),
        allow_always=tool.allow_always,
    )
    if not outcome.allowed:
        err = ErrorInfo(
            "not_approved" if outcome.approval != "non_interactive" else "approval_required",
            outcome.message or f"'{assessment.summary}' was not approved.",
            next_step=None if outcome.approval == "denied" else "Ask again from the NEXUS app to approve it.",
        )
        await _audit(ctx, tool=name, agent=agent, args=params.model_dump(), risk=assessment.risk.value,
                     status="denied", approval=outcome.approval, summary=assessment.summary, error=err,
                     duration_ms=0)
        return _fail(err, status="denied", risk=assessment.risk.value, approval=outcome.approval,
                     summary=assessment.summary)

    activity = await ctx.activity(agent or "NexusCore", assessment.summary, "started")
    status, output, error = "succeeded", None, None
    try:
        output = await asyncio.wait_for(tool.run(params, ctx), timeout=tool.timeout_seconds)
    except TimeoutError:
        status = "failed"
        error = ErrorInfo("tool_timeout", f"{assessment.summary} took too long and was stopped.",
                          reason=f"No result within {int(tool.timeout_seconds)}s.", next_step="Try again later.")
    except NexusError as exc:
        status, error = "failed", exc.info
    except Exception as exc:
        logger.exception("Tool %s crashed", name)
        status = "failed"
        error = ErrorInfo("tool_crashed", f"{assessment.summary} failed unexpectedly.",
                          reason=f"{exc.__class__.__name__}: {str(exc)[:200]}",
                          next_step="Try again; if it keeps failing, check the backend logs.")
    duration_ms = int((time.monotonic() - started) * 1000)

    summary = output.summary if output else assessment.summary
    await ctx.activity(agent or "NexusCore", summary, status, detail=error.message if error else None,
                       activity_id=activity)
    await _audit(ctx, tool=name, agent=agent, args=params.model_dump(), risk=assessment.risk.value, status=status,
                 approval=outcome.approval, summary=summary, error=error, duration_ms=duration_ms)
    record = ActionRecord(
        id=record_id,
        tool=name,
        agent=agent,
        summary=summary,
        status=status,
        risk=assessment.risk.value,
        approval=outcome.approval,
        error=error,
        data=(output.data if output else {}),
    )
    ctx.actions.append(record)
    return ToolExecution(status == "succeeded", name, output, error, record)
