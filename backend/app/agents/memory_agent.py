from __future__ import annotations

import re
import uuid

from app.agents.base import Agent, AgentResult, AgentTask
from app.core.context import RequestContext
from app.models import Memory
from app.services import memory_service as ms
from app.tools.executor import execute_tool

_LIST_RE = re.compile(r"\b(what do you (know|remember)( about me)?|list (my |all )?memor(y|ies)|show (my )?memor(y|ies))\b",
                      re.IGNORECASE)
_FORGET_RE = re.compile(r"^\s*(?:please\s+)?forget\s+(?:about\s+|that\s+)?(?P<what>.+?)\s*[.!]?$", re.IGNORECASE)
_WHAT_IS_MY_RE = re.compile(r"\b(?:what|who|where|which|when)(?:'s| is| are| was)\s+my\s+(?P<what>[\w\s'-]{2,80}?)\s*\??$",
                            re.IGNORECASE)
_STRUCTURED = re.compile(r"^\s*(?:(?:please\s+)?(?:remember|note|save)\s+(?:that\s+)?)?(?:my\s+.+\s+(?:is|are)\s+|i live in |call me |my name is |(?:[A-Za-z]:\\|~?/)\S+\s+(?:folder\s+)?(?:contains|has|holds))",
                         re.IGNORECASE)


class MemoryAgent(Agent):
    name = "memory"
    title = "MemoryAgent"
    purpose = "Remembers useful facts (projects, people, places, preferences, dates) and recalls them when needed."
    allowed_tools = frozenset({"remember", "recall", "list_memories", "forget"})
    requires_ai = False
    max_steps = 4
    instructions = """
You are MemoryAgent. Store and retrieve the user's long-term memories.
- When the user asks you to remember something, call `remember` once per distinct fact with a precise
  category, a short subject the user is likely to use later (e.g. "college AI project"), the value, useful
  aliases, and attributes such as {"path": ...} for folders.
- Never store passwords, keys, card or ID numbers - politely refuse instead.
- To answer questions about the user, use `recall` and answer only from what is stored.
- Deleting (forget) requires the user's confirmation, which NEXUS asks for automatically.
Confirm briefly what was stored, or say it is awaiting approval if the tool says so.
"""

    async def prefer_fallback(self, task: AgentTask, ctx: RequestContext) -> bool:
        text = task.user_message.strip()
        return bool(_STRUCTURED.match(text) or _LIST_RE.search(text) or _FORGET_RE.match(text)
                    or _WHAT_IS_MY_RE.search(text))

    async def fallback(self, task: AgentTask, ctx: RequestContext) -> AgentResult | None:
        text = task.user_message.strip()
        allowed = set(self.allowed_tools)
        if _LIST_RE.search(text):
            rows = await ms.list_memories(ctx.user.id, status="active", limit=50)
            if not rows:
                return AgentResult(agent=self.name, status="succeeded", answer="I don't have any memories stored yet.")
            lines = [f"- **{m.subject}**: {m.value}" for m in rows[:30]]
            return AgentResult(agent=self.name, status="succeeded",
                               answer="Here's what I remember:\n" + "\n".join(lines))
        fm = _FORGET_RE.match(text)
        if fm:
            ex = await execute_tool(ctx, "forget", {"query": fm.group("what")}, agent=self.title, allowed_tools=allowed)
            if ex.ok and ex.output:
                return AgentResult(agent=self.name, status="succeeded", answer=f"Done — {ex.output.summary[0].lower()}{ex.output.summary[1:]}.")
            return AgentResult.failure(self.name, ex.error) if ex.error else None
        wm = _WHAT_IS_MY_RE.search(text)
        if wm and not _STRUCTURED.match(text):
            hits = await ms.recall(ctx.user.id, wm.group("what"), limit=3)
            if not hits:
                return AgentResult(agent=self.name, status="succeeded",
                                   answer=f"I don't have anything stored about your {wm.group('what').strip()}.")
            m = hits[0][0]
            extra = f" (folder: `{m.attributes['path']}`)" if (m.attributes or {}).get("path") else ""
            return AgentResult(agent=self.name, status="succeeded", answer=f"Your {m.subject} is **{m.value}**{extra}.",
                               data={"memory_id": str(m.id)})
        candidate = ms.extract_explicit(text)
        if candidate is None:
            return None
        ex = await execute_tool(ctx, "remember", {
            "category": candidate.category, "subject": candidate.subject, "value": candidate.value,
            "aliases": candidate.aliases, "attributes": candidate.attributes, "explicit": True,
        }, agent=self.title, allowed_tools=allowed)
        if not ex.ok:
            return AgentResult.failure(self.name, ex.error) if ex.error else None
        if ex.output and ex.output.data.get("status") == "pending":
            return AgentResult(agent=self.name, status="succeeded",
                               answer=f"I've noted “{candidate.subject}”, but because it's personal it's waiting for "
                                      "your approval on the Memory page before I use it.")
        return AgentResult(agent=self.name, status="succeeded",
                           answer=f"Got it. I'll remember that your {candidate.subject} is **{candidate.value}**."
                           if not candidate.subject.startswith("folder for")
                           else f"Got it. I'll remember that `{candidate.value}` contains your {candidate.aliases[0]}.")


async def memory_context(user_id: uuid.UUID, text: str, limit: int = 6) -> tuple[str, list[Memory]]:
    """Relevant memories for the per-request context (used by NexusCore)."""
    hits = await ms.recall(user_id, text, limit=limit, min_score=0.34)
    rows = [m for m, _ in hits]
    return ms.format_for_context(rows), rows
