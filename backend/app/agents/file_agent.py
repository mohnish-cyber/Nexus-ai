from __future__ import annotations

import uuid

from app.agents.base import Agent, AgentResult, AgentTask
from app.core.context import RequestContext
from app.services import files as file_service


class FileAgent(Agent):
    name = "file"
    title = "FileAgent"
    purpose = "Reads uploaded PDFs, Word documents, text and code; finds sections, summarises and compares documents."
    allowed_tools = frozenset({"list_files", "search_files", "get_file_outline", "read_file_section"})
    max_steps = 8
    instructions = """
You are FileAgent. You work with the user's uploaded files (listed in the context with their ids).
- Locate information with search_files; use get_file_outline to see sections; read_file_section for full
  sections (e.g. "Unit 3") or whole short documents.
- For large documents never guess: retrieve the relevant parts first.
- Summaries: lead with the key points; mention section/page for important items.
- Comparisons: a compact table or bullet list of similarities and differences.
- Code files: explain structure, purpose, and point out likely bugs with line references.
- Only state what the file actually says. If something is not in the file, say so explicitly.
Cite locations like (File name · Unit 3 · p. 12).
"""

    async def prefer_fallback(self, task: AgentTask, ctx: RequestContext) -> bool:
        # In a multi-step plan FileAgent only retrieves; the next agent explains.
        return task.options.get("mode") == "retrieve"

    async def fallback(self, task: AgentTask, ctx: RequestContext) -> AgentResult | None:
        ids = [a.id for a in ctx.attachments if a.kind != "image"] or None
        if ids is None and task.options.get("file_ids"):
            ids = [uuid.UUID(f) for f in task.options["file_ids"]]
        activity = await ctx.activity(self.title, "Retrieving relevant passages from your files")
        results = await file_service.search(ctx.user.id, task.user_message, ids, top_k=8)
        names = {f.id: f.filename for f in await file_service.list_files(ctx.user.id, limit=500)}
        if not results:
            await ctx.activity(self.title, "No matching passages found", "succeeded", activity_id=activity)
            return AgentResult(agent=self.name, status="succeeded",
                               answer="No passages in the user's files matched this request.",
                               data={"excerpts": 0})
        blocks = []
        for r in results:
            c = r.chunk
            loc = f"{names.get(c.file_id, 'file')}" + (f" · {c.section}" if c.section else "") + (
                f" · p. {c.page}" if c.page else "")
            ctx.add_source(loc, None, "file")
            blocks.append(f"--- Excerpt [{loc}] ---\n{c.text}")
        await ctx.activity(self.title, f"Found {len(results)} relevant passages", "succeeded", activity_id=activity)
        from app.security.prompt_injection import wrap_untrusted

        return AgentResult(agent=self.name, status="succeeded",
                           answer=wrap_untrusted("\n\n".join(blocks), source="user_files", max_chars=40000),
                           data={"excerpts": len(results)})
