from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin

MEMORY_CATEGORIES = (
    "preference",
    "project",
    "person",
    "place",
    "study",
    "command",
    "date",
    "task",
    "fact",
)


class Memory(Base, IdMixin, TimestampMixin):
    """A structured long-term memory (kept separate from chat history)."""

    __tablename__ = "memories"
    __table_args__ = (Index("ix_memories_user_category", "user_id", "category"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(20), default="fact")
    # Short subject, e.g. "college AI project"
    subject: Mapped[str] = mapped_column(String(200))
    # The remembered value, e.g. "LinkGuard AI"
    value: Mapped[str] = mapped_column(Text)
    aliases: Mapped[list[Any]] = mapped_column(default=list)
    attributes: Mapped[dict[str, Any]] = mapped_column(default=dict)  # e.g. {"path": "..."}
    source: Mapped[str] = mapped_column(String(16), default="explicit")  # explicit | inferred
    # active: used for recall. pending: awaiting user approval.
    status: Mapped[str] = mapped_column(String(16), default="active")
    sensitivity: Mapped[str] = mapped_column(String(16), default="normal")  # normal | personal
    confidence: Mapped[float] = mapped_column(default=1.0)
    use_count: Mapped[int] = mapped_column(default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(default=None)
    expires_at: Mapped[datetime | None] = mapped_column(default=None)
