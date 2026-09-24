from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import current_user
from app.security.auth import CurrentUser
from app.services import notifications as notes

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("")
async def list_notifications(status: Literal["unread", "read"] | None = None,
                             user: CurrentUser = Depends(current_user)) -> list[dict[str, Any]]:
    return [notes.notification_to_dict(n) for n in await notes.list_notifications(user.id, status)]


class ReadBody(BaseModel):
    ids: list[uuid.UUID] | None = Field(default=None, max_length=200)


@router.post("/read")
async def mark_read(body: ReadBody, user: CurrentUser = Depends(current_user)) -> dict[str, int]:
    return {"updated": await notes.mark_read(user.id, body.ids)}
