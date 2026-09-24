"""Audit log for security-relevant events (settings, secrets, permissions, data deletion)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.database.session import session_scope
from app.models import AuditLog
from app.security.redaction import redact_value

logger = logging.getLogger("nexus.audit")


async def audit_event(user_id: uuid.UUID | None, event: str, detail: dict[str, Any] | None = None,
                      ip: str | None = None) -> None:
    try:
        async with session_scope() as db:
            db.add(AuditLog(user_id=user_id, event=event, detail=redact_value(detail or {}), ip=ip))
        logger.info("audit %s user=%s", event, user_id)
    except Exception as exc:  # never break the request because of auditing
        logger.error("Failed to write audit event %s: %s", event, exc)
