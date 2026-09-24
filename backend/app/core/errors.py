"""Structured, user-facing errors.

Every error NEXUS surfaces follows the same shape so the UI can always show:
what happened, the likely reason, and a safe next step - instead of a vague
"Something went wrong".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ErrorInfo:
    code: str
    message: str
    reason: str | None = None
    next_step: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "reason": self.reason,
            "next_step": self.next_step,
        }


class NexusError(Exception):
    """Base class for expected, explainable failures."""

    status_code: int = 400
    default_code: str = "nexus_error"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        reason: str | None = None,
        next_step: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.info = ErrorInfo(
            code=code or self.default_code,
            message=message,
            reason=reason,
            next_step=next_step,
        )
        if status_code is not None:
            self.status_code = status_code

    @property
    def message(self) -> str:
        return self.info.message

    def to_dict(self) -> dict[str, Any]:
        return self.info.to_dict()


class NotConfiguredError(NexusError):
    status_code = 503
    default_code = "not_configured"


class PermissionDeniedError(NexusError):
    status_code = 403
    default_code = "permission_denied"


class ValidationFailedError(NexusError):
    status_code = 422
    default_code = "validation_failed"


class NotFoundError(NexusError):
    status_code = 404
    default_code = "not_found"


class SecurityViolationError(NexusError):
    status_code = 400
    default_code = "security_violation"


class RateLimitedError(NexusError):
    status_code = 429
    default_code = "rate_limited"


class ToolExecutionError(NexusError):
    status_code = 502
    default_code = "tool_failed"


class AIProviderError(NexusError):
    status_code = 502
    default_code = "ai_provider_error"


class AuthenticationError(NexusError):
    status_code = 401
    default_code = "unauthenticated"
