"""Observability and audit: agent runs, tool calls, permissions, audit log."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, utcnow


class AgentRun(Base, IdMixin):
    __tablename__ = "agent_runs"
    __table_args__ = (Index("ix_agent_runs_user_started", "user_id", "started_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    request_id: Mapped[str | None] = mapped_column(String(64), index=True)
    agent: Mapped[str] = mapped_column(String(40))
    task: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="running")  # running | succeeded | failed
    summary: Mapped[str | None] = mapped_column(Text)
    error: Mapped[dict[str, Any] | None] = mapped_column(default=None)
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", default=dict)
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(default=None)


class ToolCall(Base, IdMixin):
    __tablename__ = "tool_calls"
    __table_args__ = (Index("ix_tool_calls_user_created", "user_id", "created_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    request_id: Mapped[str | None] = mapped_column(String(64))
    agent: Mapped[str | None] = mapped_column(String(40))
    tool: Mapped[str] = mapped_column(String(60))
    arguments: Mapped[dict[str, Any]] = mapped_column(default=dict)  # secrets redacted
    risk_level: Mapped[str] = mapped_column(String(10))
    # succeeded | failed | denied | cancelled
    status: Mapped[str] = mapped_column(String(16))
    # auto | allow_once | always_allow | denied | expired | policy
    approval: Mapped[str] = mapped_column(String(16), default="auto")
    result_summary: Mapped[str | None] = mapped_column(Text)
    error: Mapped[dict[str, Any] | None] = mapped_column(default=None)
    duration_ms: Mapped[int | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class PermissionGrant(Base, IdMixin):
    """A remembered "Always Allow" decision for a (tool, scope) pair."""

    __tablename__ = "permission_grants"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    tool: Mapped[str] = mapped_column(String(60))
    scope: Mapped[str] = mapped_column(String(500), default="*")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(default=None)
    use_count: Mapped[int] = mapped_column(default=0)


class PermissionRequest(Base, IdMixin):
    __tablename__ = "permission_requests"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    request_id: Mapped[str | None] = mapped_column(String(64))
    tool: Mapped[str] = mapped_column(String(60))
    agent: Mapped[str | None] = mapped_column(String(40))
    risk_level: Mapped[str] = mapped_column(String(10))
    summary: Mapped[str] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(default=dict)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | allowed | denied | expired
    decision: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(default=None)


class AuditLog(Base, IdMixin):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_user_created", "user_id", "created_at"),)

    user_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    event: Mapped[str] = mapped_column(String(60))
    detail: Mapped[dict[str, Any]] = mapped_column(default=dict)
    ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
