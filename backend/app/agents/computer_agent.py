from __future__ import annotations

import re

from app.agents.base import Agent, AgentResult, AgentTask
from app.core.context import RequestContext
from app.core.errors import NexusError
from app.security.risk import RiskLevel
from app.services import memory_service as ms
from app.tools.computer import find_app
from app.tools.executor import execute_tool

_OPEN_RE = re.compile(r"^\s*(?:hey\s+nexus[,!.]?\s*)?(?:please\s+)?(?:open|launch|start|run)\s+(?:up\s+)?(?:the\s+)?(?P<target>.+?)\s*(?:for me)?[.!]?$",
                      re.IGNORECASE)
_SCREEN_RE = re.compile(r"\b(screenshot|screen ?shot|capture (my|the) screen)\b", re.IGNORECASE)


class ComputerAgent(Agent):
    name = "computer"
    title = "ComputerAgent"
    purpose = "Opens apps, folders, files and web pages, runs approved dev commands, and takes screenshots with permission."
    allowed_tools = frozenset({"open_application", "open_path", "open_url", "run_command", "take_screenshot",
                               "list_applications", "get_system_status", "recall", "delete_path"})
    permission_level = RiskLevel.HIGH
    requires_ai = False
    max_steps = 6
    instructions = """
You are ComputerAgent, controlling the user's computer through approved tools only.
- Resolve references like "my college project" using the memories in the context (or `recall`), then act on
  the stored name/path. If a project has no known path, ask the user for it.
- To open a project for coding, use open_application with app "vscode" and the project path.
- Only run commands from the approved list via run_command; explain what a command does before risky ones.
- Screenshots and deletions always require the user's approval - NEXUS asks automatically.
- After acting, report exactly what happened based on the tool result. If a tool failed, give the error,
  the likely reason and a safe next step.
"""

    async def prefer_fallback(self, task: AgentTask, ctx: RequestContext) -> bool:
        if task.options.get("mode") == "screenshot":
            return True
        m = _OPEN_RE.match(task.user_message)
        if not m:
            return False
        target = m.group("target")
        if re.match(r"my\b", target, re.IGNORECASE):
            hits = await ms.recall(ctx.user.id, target, limit=1, touch=False)
            return bool(hits and (hits[0][0].attributes or {}).get("path"))
        try:
            find_app(target, ctx.preferences)
            return True
        except NexusError:
            return False

    async def fallback(self, task: AgentTask, ctx: RequestContext) -> AgentResult | None:
        allowed = set(self.allowed_tools)
        if task.options.get("mode") == "screenshot" or _SCREEN_RE.search(task.user_message):
            ex = await execute_tool(ctx, "take_screenshot", {}, agent=self.title, allowed_tools=allowed,
                                    reason="Needed to see what is on your screen.")
            if not ex.ok:
                return AgentResult.failure(self.name, ex.error) if ex.error else None
            return AgentResult(agent=self.name, status="succeeded", answer="Screenshot captured.",
                               data={"image_file_ids": [ex.output.data["file_id"]]} if ex.output else {})
        m = _OPEN_RE.match(task.user_message)
        if not m:
            return None
        target = m.group("target").strip()
        # "my college project" -> resolve via memory
        if re.search(r"\bmy\b", target, re.IGNORECASE):
            hits = await ms.recall(ctx.user.id, target, limit=1)
            if hits:
                mem = hits[0][0]
                path = (mem.attributes or {}).get("path")
                if not path:
                    return AgentResult(agent=self.name, status="needs_input",
                                       answer=f"Your {mem.subject} is **{mem.value}**, but I don't know where it is on "
                                              "disk. Tell me its folder path so I can save it with the project.")
                ex = await execute_tool(ctx, "open_application", {"app": "vscode", "path": path}, agent=self.title,
                                        allowed_tools=allowed)
                if not ex.ok:
                    ex = await execute_tool(ctx, "open_path", {"path": path}, agent=self.title, allowed_tools=allowed)
                if ex.ok and ex.output:
                    return AgentResult(agent=self.name, status="succeeded",
                                       answer=f"Opening **{mem.value}** — {ex.output.summary[0].lower()}{ex.output.summary[1:]}.")
                return AgentResult.failure(self.name, ex.error) if ex.error else None
            return AgentResult(agent=self.name, status="needs_input",
                               answer=f"I don't know which {target.replace('my ', '')} you mean yet. "
                                      "Tell me its name and folder, e.g. “My college AI project is LinkGuard AI at ~/projects/linkguard”.")
        path = None
        pm = re.search(r"\b(?:in|with|at)\s+(?P<path>(?:[A-Za-z]:\\|~?/)\S+)", target)
        if pm:
            path = pm.group("path")
            target = target[: pm.start()].strip()
        ex = await execute_tool(ctx, "open_application", {"app": target, "path": path}, agent=self.title,
                                allowed_tools=allowed)
        if ex.ok and ex.output:
            return AgentResult(agent=self.name, status="succeeded", answer=f"{ex.output.summary}.")
        return AgentResult.failure(self.name, ex.error) if ex.error else None
