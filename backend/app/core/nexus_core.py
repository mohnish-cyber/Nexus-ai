"""NexusCore - the central controller.

    input → context (history, memories, files) → intent detection → task plan
          → agent routing (one agent per step, results passed forward)
          → result verification against the action ledger
          → persistence + memory update → response (streamed)

NexusCore is the only component that talks to agents; agents never call each
other directly.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.agents.base import AgentResult, AgentTask
from app.agents.memory_agent import memory_context
from app.agents.registry import get_agent
from app.core import planner as task_planner
from app.core import router
from app.core.context import RequestContext
from app.core.errors import ErrorInfo, NexusError, NotConfiguredError, ValidationFailedError
from app.core.intent import classify
from app.core.memory_update import update_after_turn
from app.core.verifier import verify
from app.services import conversation_service as convs
from app.services import files as file_service
from app.services.ai.base import AIProvider
from app.services.ai.factory import get_provider
from app.services.preferences import get_preferences

logger = logging.getLogger(__name__)

MAX_INPUT_CHARS = 20000
_ACTION_AGENTS = {"computer", "coding", "automation"}
_UNSUPPORTED = {
    "email": "Email isn't connected to NEXUS yet, so I can't read or send messages. It's on the roadmap as "
             "EmailAgent (sending will always require your approval).",
    "calendar": "Calendar access isn't connected to NEXUS yet. It's planned as CalendarAgent. For now I can set "
                "reminders and tasks for you.",
}


@dataclass
class ChatRequest:
    text: str
    conversation_id: uuid.UUID | None = None
    attachment_ids: list[uuid.UUID] = field(default_factory=list)
    voice: bool = False


def _strip_untrusted(text: str) -> str:
    return re.sub(r"</?untrusted_content[^>]*>", "", text).strip()


class NexusCore:
    async def handle(self, ctx: RequestContext, req: ChatRequest) -> dict[str, Any]:
        text = (req.text or "").strip()
        if not text and not req.attachment_ids:
            raise ValidationFailedError("Say or type something first.", code="empty_message")
        if len(text) > MAX_INPUT_CHARS:
            raise ValidationFailedError(f"That message is too long ({len(text)} characters).", code="message_too_long",
                                        next_step=f"Keep it under {MAX_INPUT_CHARS} characters, or upload it as a file.")
        if not text:
            text = "Please analyse the attached file(s)."

        await ctx.set_state("thinking", "Understanding your request")
        if not ctx.preferences:
            ctx.preferences = await get_preferences(ctx.user.id)
        attachments = await self._load_attachments(ctx, req.attachment_ids)
        ctx.attachments = attachments

        conv = await convs.get_or_create(ctx.user.id, req.conversation_id, text)
        ctx.conversation_id = conv.id
        await ctx.emit({"type": "conversation", "conversation_id": str(conv.id), "title": conv.title})
        history = await convs.history(ctx.user.id, conv.id, limit=12)
        await convs.add_message(
            ctx.user.id, conv.id, "user", text, request_id=ctx.request_id,
            attachments=[{"id": str(a.id), "filename": a.filename, "kind": a.kind} for a in attachments],
            meta={"voice": req.voice},
        )

        try:
            return await self._run(ctx, req, text, attachments, history)
        except asyncio.CancelledError:
            await self._save_reply(ctx, "_Stopped._", status="partial", meta={"cancelled": True})
            raise
        except NexusError as exc:
            reply = self._error_text(exc.info)
            msg = await self._save_reply(ctx, reply, status="error", meta={"error": exc.to_dict()})
            await ctx.emit({"type": "message", "message": msg})
            await ctx.set_state("error", exc.message)
            return msg

    # ------------------------------------------------------------------
    async def _run(self, ctx: RequestContext, req: ChatRequest, text: str, attachments: list[Any],
                   history: list[dict[str, str]]) -> dict[str, Any]:
        provider: AIProvider | None = None
        provider_error: ErrorInfo | None = None
        try:
            provider = await get_provider()
        except NotConfiguredError as exc:
            provider_error = exc.info

        intent = classify(text, attachments)
        memories_text, _ = await memory_context(ctx.user.id, text)
        plan = await task_planner.plan(text, intent, provider, history)
        await ctx.emit({"type": "plan", **plan.to_public(), "intent": intent.to_dict()})

        base_context = self._context_block(ctx, memories_text, attachments, req.voice)
        results: list[AgentResult] = []
        image_ids = [str(a.id) for a in attachments if a.kind == "image"]
        streamed = False

        if plan.unsupported:
            answer = _UNSUPPORTED.get(plan.unsupported, "That integration isn't available yet.")
        else:
            for i, step in enumerate(plan.steps):
                is_last = i == len(plan.steps) - 1
                agent = get_agent(step.agent)
                label = f"{agent.title if agent else step.agent}: {step.instruction[:80]}"
                await ctx.set_state("executing" if step.agent in _ACTION_AGENTS else "thinking", label)
                context = base_context + self._previous_results(results)
                instruction = step.instruction
                if is_last and results:
                    instruction += ("\n\nYour reply is the final answer shown to the user: include the relevant "
                                    "results of the earlier steps.")
                task = AgentTask(instruction=instruction, user_message=text, context=context, history=history,
                                 image_file_ids=image_ids, options=step.options, voice=req.voice)
                result = await router.dispatch(step.agent, task, ctx, provider, stream=is_last)
                results.append(result)
                image_ids += [f for f in result.data.get("image_file_ids", []) if f not in image_ids]
                if result.status in ("failed", "needs_input") and not is_last:
                    break  # later steps depend on this one
            answer, streamed = self._compose(results, provider_error)

        answer, problems = verify(answer, ctx.actions)
        declined = bool(results) and (results[-1].error or {}).get("code") in ("not_approved", "approval_required")
        if declined and results[-1].status == "failed":
            # The user said no (or couldn't be asked): that's a normal outcome, not a failure.
            answer = f"Okay — I didn't go ahead. {results[-1].error.get('message', '')}".strip()
            if results[-1].error.get("next_step"):
                answer += f"\n\n{results[-1].error['next_step']}"
        failed = bool(results) and all(r.status == "failed" for r in results) and not declined
        meta = {
            "plan": plan.to_public(),
            "intent": intent.to_dict(),
            "agents": [r.agent for r in results],
            "verification": problems,
            "streamed": streamed,
            "voice": req.voice,
        }
        if failed and results[-1].error:
            meta["error"] = results[-1].error
        msg = await self._save_reply(ctx, answer, status="error" if failed else "complete", meta=meta)
        await ctx.emit({"type": "message", "message": msg})
        await ctx.set_state("error" if failed else "completed", None)

        asyncio.create_task(
            update_after_turn(ctx.user.id, text, ctx.preferences, provider, list(ctx.actions), ctx.emit),
            name=f"memory-update-{ctx.request_id}",
        )
        return msg

    # ------------------------------------------------------------------
    async def _load_attachments(self, ctx: RequestContext, ids: list[uuid.UUID]) -> list[Any]:
        rows = []
        for fid in ids[:10]:
            row = await file_service.get_file(ctx.user.id, fid)
            if row.status == "processing":
                raise ValidationFailedError(f"'{row.filename}' is still being processed.", code="file_processing",
                                            next_step="Wait a moment and send again.")
            if row.status == "failed":
                raise ValidationFailedError(f"'{row.filename}' could not be read.", code="file_failed",
                                            reason=row.error, next_step="Try uploading a different version of the file.")
            rows.append(row)
        return rows

    def _context_block(self, ctx: RequestContext, memories: str, attachments: list[Any], voice: bool) -> str:
        now = ctx.now_local()
        loc = ctx.preferences.get("location") or {}
        profile = ctx.preferences.get("profile") or {}
        lines = [f"Current time: {now:%A %d %B %Y, %H:%M} ({ctx.timezone})"]
        if profile.get("user_name"):
            lines.append(f"User's name: {profile['user_name']}")
        if loc.get("city"):
            lines.append(f"User's saved location: {loc['city']}" + (f", {loc['country']}" if loc.get("country") else ""))
        roots = ctx.workspace_roots
        lines.append("Authorised workspace folders: " + (", ".join(str(r) for r in roots) if roots else "none configured"))
        if memories:
            lines.append("Relevant memories:\n" + memories)
        if attachments:
            lines.append("Files attached to this message:\n" + "\n".join(
                f"- {a.filename} (id {a.id}, {a.kind}" + (f", {a.page_count} pages" if a.page_count else "") + ")"
                for a in attachments))
        if voice:
            lines.append("The user is speaking by voice: reply in 1-3 short spoken sentences, no Markdown.")
        return "\n".join(lines)

    def _previous_results(self, results: list[AgentResult]) -> str:
        if not results:
            return ""
        blocks = []
        for r in results:
            agent = get_agent(r.agent)
            blocks.append(f"### {agent.title if agent else r.agent} ({r.status})\n{r.answer}")
        return "\n\nResults from earlier steps (produced by NEXUS agents):\n" + "\n\n".join(blocks)

    def _compose(self, results: list[AgentResult], provider_error: ErrorInfo | None) -> tuple[str, bool]:
        """The last agent received every earlier result as context, so its answer is the final answer.
        If a step failed, show what earlier steps achieved followed by the failure."""
        if not results:
            return "I wasn't able to work on that.", False
        last = results[-1]
        if len(results) == 1:
            return self._friendly(last), last.streamed
        if last.status != "failed":
            return last.answer, last.streamed
        parts = [self._friendly(r) for r in results[:-1] if r.status == "succeeded"] + [last.answer]
        return "\n\n".join(p for p in parts if p), False

    @staticmethod
    def _friendly(result: AgentResult) -> str:
        if result.agent == "file" and result.data.get("excerpts"):
            return "Most relevant passages from your files:\n\n" + _strip_untrusted(result.answer)[:6000]
        return result.answer

    @staticmethod
    def _error_text(err: ErrorInfo) -> str:
        parts = [err.message]
        if err.reason:
            parts.append(f"**Reason:** {err.reason}")
        if err.next_step:
            parts.append(f"**Next step:** {err.next_step}")
        return "\n\n".join(parts)

    async def _save_reply(self, ctx: RequestContext, content: str, *, status: str, meta: dict[str, Any]) -> dict[str, Any]:
        if ctx.conversation_id is None:
            return {"role": "assistant", "content": content, "status": status}
        m = await convs.add_message(
            ctx.user.id, ctx.conversation_id, "assistant", content, request_id=ctx.request_id, status=status,
            actions=[a.to_public() for a in ctx.actions], sources=ctx.sources, meta=meta,
        )
        return convs.message_to_dict(m)


nexus_core = NexusCore()
