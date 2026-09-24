"""Agent router: dispatches a plan step to its agent, with auditing,
timeouts and structured error handling."""

from __future__ import annotations

import asyncio
import logging

from app.agents.base import AgentResult, AgentTask
from app.agents.registry import get_agent
from app.core.context import RequestContext
from app.core.errors import ErrorInfo, NexusError
from app.database.session import session_scope
from app.models import AgentRun
from app.models.base import utcnow
from app.services.ai.base import AIProvider

logger = logging.getLogger(__name__)


async def dispatch(agent_name: str, task: AgentTask, ctx: RequestContext, provider: AIProvider | None,
                   *, stream: bool) -> AgentResult:
    agent = get_agent(agent_name)
    if agent is None:
        return AgentResult.failure(agent_name, ErrorInfo("unknown_agent", f"No agent named '{agent_name}'."))

    async with session_scope() as db:
        run = AgentRun(user_id=ctx.user.id, conversation_id=ctx.conversation_id, request_id=ctx.request_id,
                       agent=agent.name, task=task.instruction[:4000])
        db.add(run)
        await db.flush()
        run_id = run.id

    previous_run, previous_agent = ctx.agent_run_id, ctx.current_agent
    ctx.agent_run_id, ctx.current_agent = run_id, agent.title
    activity = await ctx.activity(agent.title, "Working on the request", "started", detail=task.instruction[:160])
    try:
        result = await agent.run(task, ctx, provider, stream=stream)
    except asyncio.CancelledError:
        await _finish(run_id, "cancelled", "Stopped by user", None)
        raise
    except NexusError as exc:
        result = AgentResult.failure(agent.name, exc.info)
    except Exception as exc:
        logger.exception("Agent %s crashed", agent.name)
        result = AgentResult.failure(agent.name, ErrorInfo(
            "agent_crashed", f"{agent.title} hit an unexpected error.",
            reason=f"{exc.__class__.__name__}: {str(exc)[:200]}", next_step="Try again; check the backend logs if it persists."))
    finally:
        ctx.agent_run_id, ctx.current_agent = previous_run, previous_agent

    status = "succeeded" if result.status != "failed" else "failed"
    await ctx.activity(agent.title, "Finished" if status == "succeeded" else "Could not complete the request", status,
                       detail=(result.error or {}).get("message") if result.error else None, activity_id=activity)
    await _finish(run_id, status, result.answer[:2000], result.error)
    return result


async def _finish(run_id, status: str, summary: str | None, error: dict | None) -> None:
    try:
        async with session_scope() as db:
            run = await db.get(AgentRun, run_id)
            if run is not None:
                run.status = status
                run.summary = summary
                run.error = error
                run.finished_at = utcnow()
    except Exception as exc:
        logger.error("Could not record agent run %s: %s", run_id, exc)
