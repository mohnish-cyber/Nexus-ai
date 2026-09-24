from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class StoredFile(Base, IdMixin, TimestampMixin):
    __tablename__ = "files"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(80))
    mime_type: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(12))  # pdf | docx | text | code | image
    size_bytes: Mapped[int] = mapped_column()
    sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(12), default="processing")  # processing | ready | failed
    page_count: Mapped[int | None] = mapped_column(default=None)
    char_count: Mapped[int | None] = mapped_column(default=None)
    error: Mapped[str | None] = mapped_column(Text)
    # {"sections": [{"title": "Unit 3", "page": 12}], "language": "python"}
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", default=dict)


class FileChunk(Base, IdMixin):
    __tablename__ = "file_chunks"
    __table_args__ = (Index("ix_file_chunks_file_idx", "file_id", "idx"),)

    file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    idx: Mapped[int] = mapped_column()
    text: Mapped[str] = mapped_column(Text)
    section: Mapped[str | None] = mapped_column(String(300))
    page: Mapped[int | None] = mapped_column(default=None)
