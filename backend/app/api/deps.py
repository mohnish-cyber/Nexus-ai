"""Shared FastAPI dependencies."""

from __future__ import annotations

from fastapi import Depends, Request

from app.config import get_settings
from app.core.errors import PermissionDeniedError
from app.security.auth import CurrentUser, verify_token
from app.security.rate_limit import rate_limiter


def bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization") or ""
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None
    return None


async def current_user(request: Request) -> CurrentUser:
    user = await verify_token(bearer_token(request))
    rate_limiter.check(f"default:{user.id}", get_settings().rate_limit_default_per_minute)
    return user


async def chat_user(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    rate_limiter.check(f"chat:{user.id}", get_settings().rate_limit_chat_per_minute)
    return user


async def admin_user(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    if not user.is_admin:
        raise PermissionDeniedError("Only an administrator can change this setting.",
                                    next_step="Ask the NEXUS administrator (see NEXUS_ADMIN_EMAILS).")
    return user


async def host_control_user(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    """Settings that grant access to the host machine (workspace folders, custom apps)."""
    settings = get_settings()
    if not settings.computer_control:
        raise PermissionDeniedError(
            "Computer control is disabled on this server, so host folders and apps can't be configured.",
            next_step="Enable COMPUTER_CONTROL_ENABLED only on your personal machine.")
    if settings.auth_mode != "local" and not user.is_admin:
        raise PermissionDeniedError("Only an administrator can grant access to the host machine.")
    return user
