from __future__ import annotations

import re

from app.agents.base import Agent, AgentResult, AgentTask
from app.core.context import RequestContext
from app.core.errors import NexusError
from app.services.timeparse import parse_when
from app.tools.executor import execute_tool

# "remind me tomorrow at 8 AM to submit my assignment"
_REMIND_WHEN_FIRST = re.compile(
    r"^\s*(?:hey\s+nexus[,!.]?\s*)?(?:please\s+)?remind me\s+(?P<when>(?:tomorrow|today|tonight|in\s+\d+|at\s+\d|on\s+\w+|next\s+\w+|this\s+\w+)[^,]*?)\s+(?:to|about|that)\s+(?P<what>.+?)\s*[.!]?$",
    re.IGNORECASE,
)
# "remind me to submit my assignment tomorrow at 8 AM"
_REMIND_WHAT_FIRST = re.compile(
    r"^\s*(?:hey\s+nexus[,!.]?\s*)?(?:please\s+)?remind me\s+(?:to|about|that)\s+(?P<what>.+?)\s+(?P<when>(?:tomorrow|today|tonight|in\s+\d+|at\s+\d|on\s+\w+|next\s+\w+|this\s+\w+).*?)\s*[.!]?$",
    re.IGNORECASE,
)
_TASKS_QUERY = re.compile(r"\b(what|which|show|list)\b.*\b(tasks?|to-?dos?)\b", re.IGNORECASE)
_CONDITIONAL = re.compile(r"\b(if|unless|when|only)\b", re.IGNORECASE)


def parse_reminder(text: str) -> tuple[str, str] | None:
    if _CONDITIONAL.search(text) and not re.search(r"\bwhen\s+\d", text):
        return None
    for pattern in (_REMIND_WHEN_FIRST, _REMIND_WHAT_FIRST):
        m = pattern.match(text)
        if m:
            what = m.group("what").strip()
            what = re.sub(r"^\s*(?:to|about)\s+", "", what)
            return what, m.group("when").strip()
    return None


class AutomationAgent(Agent):
    name = "automation"
    title = "AutomationAgent"
    purpose = "Manages tasks, reminders and recurring automations (news digests, price alerts, weather alerts)."
    allowed_tools = frozenset({"create_reminder", "create_task", "list_tasks", "complete_task", "create_automation",
                               "list_automations", "cancel_automation", "get_weather"})
    requires_ai = False
    max_steps = 6
    instructions = """
You are AutomationAgent. You manage the user's tasks, reminders and background automations.
- One-off reminders → create_reminder (natural-language time in the user's timezone is fine).
- To-dos → create_task (with due/remind when given). "What tasks do I have today?" → list_tasks view=today.
- Recurring work → create_automation: agent_task for digests (e.g. "every morning give me five important AI
  news stories" → daily at 08:00 unless a time is given), price_watch for price alerts (needs a product URL -
  ask for it if missing), weather_check for recurring rain alerts.
- Conditional one-off requests (e.g. "remind me to take an umbrella if rain is expected tomorrow"): use the
  weather result in the context (or get_weather); if the condition is met, create the reminder for a
  sensible time (morning of that day, ~07:30) and say why; if not met, create nothing and say so.
- Always confirm with the exact scheduled time returned by the tool. Never say something is scheduled unless
  the tool succeeded.
"""

    async def prefer_fallback(self, task: AgentTask, ctx: RequestContext) -> bool:
        if task.context and "Results from earlier steps" in task.context:
            return False
        text = task.user_message
        if _TASKS_QUERY.search(text) and "today" in text.lower():
            return True
        parsed = parse_reminder(text)
        if parsed is None:
            return False
        try:
            parse_when(parsed[1], ctx.timezone)
            return True
        except NexusError:
            return False

    async def fallback(self, task: AgentTask, ctx: RequestContext) -> AgentResult | None:
        text = task.user_message
        allowed = set(self.allowed_tools)
        if _TASKS_QUERY.search(text):
            view = "today" if "today" in text.lower() else "open"
            ex = await execute_tool(ctx, "list_tasks", {"view": view}, agent=self.title, allowed_tools=allowed)
            if not ex.ok:
                return AgentResult.failure(self.name, ex.error) if ex.error else None
            body = ex.output.content if ex.output else ""
            if body.startswith("No "):
                return AgentResult(agent=self.name, status="succeeded",
                                   answer="You have no tasks due today." if view == "today" else "You have no open tasks.")
            lines = [re.sub(r" · id [0-9a-f-]+$", "", line).replace("- [open] ", "- ") for line in body.splitlines()]
            return AgentResult(agent=self.name, status="succeeded",
                               answer=("Here's what's on your list for today:\n" if view == "today" else "Your open tasks:\n")
                               + "\n".join(lines))
        parsed = parse_reminder(text)
        if parsed is None:
            return None
        what, when = parsed
        what = re.sub(r"\bmy\b", "your", what, flags=re.IGNORECASE)
        ex = await execute_tool(ctx, "create_reminder", {"message": what, "when": when}, agent=self.title,
                                allowed_tools=allowed)
        if not ex.ok:
            return AgentResult.failure(self.name, ex.error) if ex.error else None
        human = ex.output.data.get("when") if ex.output else when
        return AgentResult(agent=self.name, status="succeeded", answer=f"Done. I'll remind you {human} to {what}.",
                           data=ex.output.data if ex.output else {})
