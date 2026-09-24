from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.deps import current_user
from app.security.auth import CurrentUser
from app.services import conversation_service as convs

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("")
async def list_conversations(q: str | None = Query(default=None, max_length=100),
                             user: CurrentUser = Depends(current_user)) -> list[dict[str, Any]]:
    return await convs.list_conversations(user.id, query=q)


@router.get("/{conversation_id}/messages")
async def messages(conversation_id: uuid.UUID, user: CurrentUser = Depends(current_user)) -> list[dict[str, Any]]:
    return [convs.message_to_dict(m) for m in await convs.get_messages(user.id, conversation_id)]


class RenameBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)


@router.patch("/{conversation_id}")
async def rename(conversation_id: uuid.UUID, body: RenameBody, user: CurrentUser = Depends(current_user)) -> dict[str, Any]:
    return convs.conversation_to_dict(await convs.rename(user.id, conversation_id, body.title))


@router.delete("/{conversation_id}", status_code=204)
async def delete(conversation_id: uuid.UUID, user: CurrentUser = Depends(current_user)) -> None:
    await convs.delete_conversation(user.id, conversation_id)
