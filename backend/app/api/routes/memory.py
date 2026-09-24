"""View, add, edit, approve and delete long-term memories."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.deps import current_user
from app.core.errors import ValidationFailedError
from app.security.auth import CurrentUser
from app.services import memory_service as ms
from app.services.preferences import get_preferences

router = APIRouter(prefix="/api/memories", tags=["memory"])

Category = Literal["preference", "project", "person", "place", "study", "command", "date", "task", "fact"]


@router.get("")
async def list_memories(category: Category | None = None, status: Literal["active", "pending"] | None = None,
                        q: str | None = Query(default=None, max_length=100),
                        user: CurrentUser = Depends(current_user)) -> list[dict[str, Any]]:
    return [ms.memory_to_dict(m) for m in await ms.list_memories(user.id, category=category, status=status, query=q)]


class MemoryBody(BaseModel):
    category: Category = "fact"
    subject: str = Field(min_length=2, max_length=200)
    value: str = Field(min_length=1, max_length=4000)
    aliases: list[str] = Field(default_factory=list, max_length=20)
    attributes: dict[str, Any] = Field(default_factory=dict)


@router.post("", status_code=201)
async def create_memory(body: MemoryBody, user: CurrentUser = Depends(current_user)) -> dict[str, Any]:
    cand = ms.MemoryCandidate(body.category, body.subject, body.value, body.aliases, body.attributes, explicit=True)
    decision, row = await ms.save_candidate(user.id, cand, await get_preferences(user.id))
    if row is None:
        raise ValidationFailedError(f"Not stored: {decision.reason}.", code="memory_rejected")
    return ms.memory_to_dict(row)


class MemoryPatch(BaseModel):
    category: Category | None = None
    subject: str | None = Field(default=None, min_length=2, max_length=200)
    value: str | None = Field(default=None, min_length=1, max_length=4000)
    aliases: list[str] | None = Field(default=None, max_length=20)
    attributes: dict[str, Any] | None = None


@router.patch("/{memory_id}")
async def update_memory(memory_id: uuid.UUID, body: MemoryPatch, user: CurrentUser = Depends(current_user)) -> dict[str, Any]:
    row = await ms.update_memory(user.id, memory_id, **body.model_dump(exclude_none=True))
    return ms.memory_to_dict(row)


@router.post("/{memory_id}/approve")
async def approve(memory_id: uuid.UUID, user: CurrentUser = Depends(current_user)) -> dict[str, Any]:
    return ms.memory_to_dict(await ms.update_memory(user.id, memory_id, status="active"))


@router.delete("/{memory_id}", status_code=204)
async def delete_memory(memory_id: uuid.UUID, user: CurrentUser = Depends(current_user)) -> None:
    await ms.delete_memory(user.id, memory_id)


@router.delete("")
async def delete_all(confirm: bool = False, user: CurrentUser = Depends(current_user)) -> dict[str, int]:
    if not confirm:
        raise ValidationFailedError("Deleting all memories needs confirmation.", code="confirmation_required",
                                    next_step="Call again with ?confirm=true.")
    return {"deleted": await ms.delete_all(user.id)}
