from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin, utcnow


class User(Base, IdMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str | None] = mapped_column(String(320), index=True)
    display_name: Mapped[str | None] = mapped_column(String(120))
    auth_provider: Mapped[str] = mapped_column(String(20), default="local")
    is_admin: Mapped[bool] = mapped_column(default=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(default=None)


class UserPreference(Base, IdMixin):
    __tablename__ = "user_preferences"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_user_preferences_user_key"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(80))
    value: Mapped[dict[str, Any]] = mapped_column(default=dict)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class Device(Base, IdMixin, TimestampMixin):
    __tablename__ = "devices"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20), default="host")  # host | browser | phone
    platform: Mapped[str | None] = mapped_column(String(120))
    fingerprint: Mapped[str | None] = mapped_column(String(128), index=True)
    capabilities: Mapped[dict[str, Any]] = mapped_column(default=dict)
    last_seen_at: Mapped[datetime | None] = mapped_column(default=None)


class AppSecret(Base, IdMixin):
    """Instance-level API keys entered through Settings, encrypted at rest."""

    __tablename__ = "app_secrets"

    name: Mapped[str] = mapped_column(String(80), unique=True)
    ciphertext: Mapped[str] = mapped_column(String(4096))
    hint: Mapped[str] = mapped_column(String(16), default="")
    updated_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
