"""Memory tools used by MemoryAgent."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import Field

from app.core.context import RequestContext
from app.core.errors import NotFoundError, ValidationFailedError
from app.security.risk import RiskLevel
from app.services import memory_service as ms
from app.tools.base import Assessment, Tool, ToolOutput, ToolParams

Category = Literal["preference", "project", "person", "place", "study", "command", "date", "task", "fact"]


class RememberParams(ToolParams):
    category: Category
    subject: str = Field(min_length=2, max_length=200, description="Short subject, e.g. 'college AI project'")
    value: str = Field(min_length=1, max_length=2000, description="The fact, e.g. 'LinkGuard AI'")
    aliases: list[str] = Field(default_factory=list, max_length=10, description="Other ways the user may refer to it")
    attributes: dict[str, Any] = Field(default_factory=dict, description="Structured extras, e.g. {'path': '/home/me/linkguard'}")
    explicit: bool = Field(default=True, description="True only if the user explicitly asked to remember this")


class RememberTool(Tool):
    name = "remember"
    description = ("Store a durable fact about the user in long-term memory. Only for information the user wants "
                   "remembered (projects, people, places, preferences, dates). Secrets are always rejected.")
    Params = RememberParams
    category = "memory"

    def describe_call(self, params: RememberParams) -> str:
        return f"Remembering {params.subject}"

    async def run(self, params: RememberParams, ctx: RequestContext) -> ToolOutput:
        cand = ms.MemoryCandidate(params.category, params.subject, params.value, params.aliases,
                                  params.attributes, params.explicit)
        decision, row = await ms.save_candidate(ctx.user.id, cand, ctx.preferences)
        if decision.action in ("reject", "skip"):
            raise ValidationFailedError(f"Not stored: {decision.reason}.", code="memory_rejected")
        if decision.action == "store_pending":
            return ToolOutput(
                summary=f"Suggested memory “{params.subject}” (awaiting your approval)",
                content=f"Saved as a PENDING suggestion because {decision.reason}. The user can approve it on the Memory page.",
                data={"memory_id": str(row.id), "status": "pending"},
            )
        return ToolOutput(summary=f"Remembered: {params.subject} → {params.value[:60]}",
                          content=f"Stored memory {row.id}: [{row.category}] {row.subject}: {row.value}",
                          data={"memory_id": str(row.id), "status": "active"})


class RecallParams(ToolParams):
    query: str = Field(min_length=1, max_length=300, description="What to look up, e.g. 'college AI project'")
    category: Category | None = None


class RecallTool(Tool):
    name = "recall"
    description = "Look up long-term memories relevant to a query (e.g. resolve 'my college project' to its name/path)."
    Params = RecallParams
    category = "memory"

    def describe_call(self, params: RecallParams) -> str:
        return f"Recalling “{params.query[:50]}”"

    async def run(self, params: RecallParams, ctx: RequestContext) -> ToolOutput:
        hits = await ms.recall(ctx.user.id, params.query, category=params.category, limit=8, min_score=0.2)
        if not hits:
            return ToolOutput(summary="No matching memories", content="No matching memories.", data={"count": 0})
        return ToolOutput(summary=f"Recalled {len(hits)} memories",
                          content=ms.format_for_context([m for m, _ in hits]),
                          data={"count": len(hits), "ids": [str(m.id) for m, _ in hits]})


class ListMemoriesParams(ToolParams):
    category: Category | None = None


class ListMemoriesTool(Tool):
    name = "list_memories"
    description = "List what NEXUS remembers about the user, optionally filtered by category."
    Params = ListMemoriesParams
    category = "memory"

    def describe_call(self, params) -> str:
        return "Listing your memories"

    async def run(self, params: ListMemoriesParams, ctx: RequestContext) -> ToolOutput:
        rows = await ms.list_memories(ctx.user.id, category=params.category, status="active", limit=200)
        return ToolOutput(summary=f"Listed {len(rows)} memories",
                          content=ms.format_for_context(rows) or "No memories stored.", data={"count": len(rows)})


class ForgetParams(ToolParams):
    memory_id: uuid.UUID | None = None
    query: str | None = Field(default=None, max_length=300, description="Used when the id is unknown")


class ForgetTool(Tool):
    name = "forget"
    description = "Delete a memory (by id, or the best match for a query). Requires the user's confirmation."
    Params = ForgetParams
    risk = RiskLevel.MEDIUM
    category = "memory"

    def assess(self, params: ForgetParams, ctx: RequestContext) -> Assessment:
        target = str(params.memory_id) if params.memory_id else f"memory matching “{params.query}”"
        return Assessment(RiskLevel.MEDIUM, f"Forget {target}", scope="memory",
                          details={"memory_id": str(params.memory_id) if params.memory_id else None,
                                   "query": params.query})

    async def run(self, params: ForgetParams, ctx: RequestContext) -> ToolOutput:
        if params.memory_id:
            row = await ms.get_memory(ctx.user.id, params.memory_id)
        elif params.query:
            hits = await ms.recall(ctx.user.id, params.query, limit=1, touch=False)
            if not hits:
                raise NotFoundError("No memory matches that description.", code="memory_not_found")
            row = hits[0][0]
        else:
            raise ValidationFailedError("Say which memory to forget.", code="invalid_arguments")
        await ms.delete_memory(ctx.user.id, row.id)
        return ToolOutput(summary=f"Forgot “{row.subject}”", content=f"Deleted memory: {row.subject}: {row.value}",
                          data={"memory_id": str(row.id)})
