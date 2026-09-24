"""Conversation and message persistence (short-term memory)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select

from app.core.errors import NotFoundError
from app.database.session import session_scope
from app.models import Conversation, Message
from app.models.base import utcnow


def conversation_to_dict(c: Conversation, message_count: int | None = None) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "title": c.title,
        "archived": c.archived,
        "created_at": c.created_at.isoformat(),
        "updated_at": c.updated_at.isoformat(),
        "message_count": message_count,
    }


def message_to_dict(m: Message) -> dict[str, Any]:
    return {
        "id": str(m.id),
        "conversation_id": str(m.conversation_id),
        "role": m.role,
        "content": m.content,
        "status": m.status,
        "request_id": m.request_id,
        "attachments": m.attachments or [],
        "actions": m.actions or [],
        "sources": m.sources or [],
        "meta": m.meta or {},
        "created_at": m.created_at.isoformat(),
    }


def make_title(text: str) -> str:
    t = " ".join(text.strip().split())
    return (t[:60] + "…") if len(t) > 60 else (t or "New conversation")


async def get_or_create(user_id: uuid.UUID, conversation_id: uuid.UUID | None, first_text: str) -> Conversation:
    async with session_scope() as db:
        if conversation_id is not None:
            conv = await db.get(Conversation, conversation_id)
            if conv is None or conv.user_id != user_id:
                raise NotFoundError("That conversation was not found.", code="conversation_not_found")
            return conv
        conv = Conversation(user_id=user_id, title=make_title(first_text))
        db.add(conv)
        await db.flush()
        return conv


async def add_message(user_id: uuid.UUID, conversation_id: uuid.UUID, role: str, content: str, *,
                      request_id: str | None = None, status: str = "complete", attachments: list | None = None,
                      actions: list | None = None, sources: list | None = None,
                      meta: dict | None = None) -> Message:
    async with session_scope() as db:
        m = Message(conversation_id=conversation_id, user_id=user_id, role=role, content=content,
                    request_id=request_id, status=status, attachments=attachments or [], actions=actions or [],
                    sources=sources or [], meta=meta or {})
        db.add(m)
        conv = await db.get(Conversation, conversation_id)
        if conv is not None:
            conv.updated_at = utcnow()
        await db.flush()
        return m


async def history(user_id: uuid.UUID, conversation_id: uuid.UUID, limit: int = 12,
                  exclude_request: str | None = None) -> list[dict[str, str]]:
    async with session_scope() as db:
        rows = (await db.execute(
            select(Message).where(Message.user_id == user_id, Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc()).limit(limit + 2)
        )).scalars().all()
    turns = [{"role": m.role, "content": m.content} for m in reversed(rows)
             if m.request_id != exclude_request and m.content and m.status != "error"]
    return turns[-limit:]


async def list_conversations(user_id: uuid.UUID, limit: int = 50, query: str | None = None) -> list[dict[str, Any]]:
    stmt = (select(Conversation, func.count(Message.id))
            .outerjoin(Message, Message.conversation_id == Conversation.id)
            .where(Conversation.user_id == user_id, Conversation.archived.is_(False))
            .group_by(Conversation.id).order_by(Conversation.updated_at.desc()).limit(limit))
    if query:
        stmt = stmt.where(func.lower(Conversation.title).like(f"%{query.lower()}%"))
    async with session_scope() as db:
        rows = (await db.execute(stmt)).all()
    return [conversation_to_dict(c, n) for c, n in rows]


async def get_messages(user_id: uuid.UUID, conversation_id: uuid.UUID, limit: int = 200) -> list[Message]:
    async with session_scope() as db:
        conv = await db.get(Conversation, conversation_id)
        if conv is None or conv.user_id != user_id:
            raise NotFoundError("That conversation was not found.", code="conversation_not_found")
        rows = (await db.execute(
            select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at).limit(limit)
        )).scalars().all()
    return list(rows)


async def rename(user_id: uuid.UUID, conversation_id: uuid.UUID, title: str) -> Conversation:
    async with session_scope() as db:
        conv = await db.get(Conversation, conversation_id)
        if conv is None or conv.user_id != user_id:
            raise NotFoundError("That conversation was not found.", code="conversation_not_found")
        conv.title = title[:200]
        return conv


async def delete_conversation(user_id: uuid.UUID, conversation_id: uuid.UUID) -> None:
    async with session_scope() as db:
        conv = await db.get(Conversation, conversation_id)
        if conv is None or conv.user_id != user_id:
            raise NotFoundError("That conversation was not found.", code="conversation_not_found")
        await db.execute(sql_delete(Message).where(Message.conversation_id == conversation_id))
        await db.delete(conv)
