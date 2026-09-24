"""Tasks, reminders, automations and notifications."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin, utcnow


class Task(Base, IdMixin, TimestampMixin):
    __tablename__ = "tasks"
    __table_args__ = (Index("ix_tasks_user_status_due", "user_id", "status", "due_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(300))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="open")  # open | done | cancelled
    priority: Mapped[str] = mapped_column(String(10), default="normal")  # low | normal | high
    due_at: Mapped[datetime | None] = mapped_column(default=None)
    completed_at: Mapped[datetime | None] = mapped_column(default=None)
    # Reminder automation created for this task, if any.
    automation_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    source: Mapped[str] = mapped_column(String(16), default="user")  # user | assistant


class Automation(Base, IdMixin, TimestampMixin):
    """A persisted scheduled job executed by the background scheduler."""

    __tablename__ = "automations"
    __table_args__ = (Index("ix_automations_due", "status", "next_run_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    # reminder | agent_task | price_watch | weather_check
    kind: Mapped[str] = mapped_column(String(24))
    # once | interval | cron
    trigger_type: Mapped[str] = mapped_column(String(12))
    # {"run_at": iso} | {"seconds": int} | {"cron": "0 8 * * *"}
    schedule: Mapped[dict[str, Any]] = mapped_column(default=dict)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    config: Mapped[dict[str, Any]] = mapped_column(default=dict)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | paused | completed | failed
    next_run_at: Mapped[datetime | None] = mapped_column(default=None)
    last_run_at: Mapped[datetime | None] = mapped_column(default=None)
    last_result: Mapped[dict[str, Any]] = mapped_column(default=dict)
    run_count: Mapped[int] = mapped_column(default=0)
    failure_count: Mapped[int] = mapped_column(default=0)
    # Lease used so only one scheduler instance executes a job at a time.
    locked_until: Mapped[datetime | None] = mapped_column(default=None)
    locked_by: Mapped[str | None] = mapped_column(String(64), default=None)


class AutomationRun(Base, IdMixin):
    __tablename__ = "automation_runs"

    automation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("automations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="running")  # running | succeeded | failed
    condition_met: Mapped[bool | None] = mapped_column(default=None)
    result: Mapped[dict[str, Any]] = mapped_column(default=dict)
    error: Mapped[dict[str, Any] | None] = mapped_column(default=None)
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(default=None)


class Notification(Base, IdMixin):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_status", "user_id", "status", "created_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(20), default="system")  # reminder | automation | system
    status: Mapped[str] = mapped_column(String(10), default="unread")  # unread | read
    automation_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    data: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    read_at: Mapped[datetime | None] = mapped_column(default=None)
