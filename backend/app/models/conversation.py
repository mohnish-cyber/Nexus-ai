from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class Conversation(Base, IdMixin, TimestampMixin):
    __tablename__ = "conversations"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200), default="New conversation")
    archived: Mapped[bool] = mapped_column(default=False)
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", default=dict)


class Message(Base, IdMixin, TimestampMixin):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_conversation_created", "conversation_id", "created_at"),)

    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user | assistant
    content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="complete")  # complete | error | partial
    request_id: Mapped[str | None] = mapped_column(String(64), index=True)
    attachments: Mapped[list[Any]] = mapped_column(default=list)
    # Verified action ledger: what NEXUS actually executed for this reply.
    actions: Mapped[list[Any]] = mapped_column(default=list)
    sources: Mapped[list[Any]] = mapped_column(default=list)
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", default=dict)
