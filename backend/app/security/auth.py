"""Authentication.

Two modes:

* local    - a single-user personal install. There is exactly one user. The
             API only binds to localhost and rejects foreign Host/Origin
             headers (protection against CSRF and DNS rebinding).
* supabase - multi-user. Every request carries a Supabase access token (JWT),
             verified with the project's JWT secret (HS256) or its JWKS
             (asymmetric signing keys).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from functools import lru_cache

import jwt
from sqlalchemy import select

from app.config import get_settings
from app.core.errors import AuthenticationError
from app.database.session import session_scope
from app.models import User
from app.models.base import utcnow

logger = logging.getLogger(__name__)

LOCAL_USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
_known_users: set[uuid.UUID] = set()


@dataclass(frozen=True)
class CurrentUser:
    id: uuid.UUID
    email: str | None
    is_admin: bool
    auth_mode: str
    display_name: str | None = None


def local_user() -> CurrentUser:
    return CurrentUser(id=LOCAL_USER_ID, email=None, is_admin=True, auth_mode="local", display_name="You")


async def ensure_user_row(user: CurrentUser) -> None:
    if user.id in _known_users:
        return
    async with session_scope() as db:
        row = await db.get(User, user.id)
        if row is None:
            db.add(
                User(
                    id=user.id,
                    email=user.email,
                    display_name=user.display_name,
                    auth_provider=user.auth_mode,
                    is_admin=user.is_admin,
                    last_seen_at=utcnow(),
                )
            )
        else:
            row.last_seen_at = utcnow()
            if user.email and row.email != user.email:
                row.email = user.email
            row.is_admin = user.is_admin
    _known_users.add(user.id)


def forget_known_users() -> None:
    _known_users.clear()


@lru_cache(maxsize=1)
def _jwks_client(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(url, cache_keys=True, lifespan=3600)


def _decode_supabase(token: str) -> dict:
    settings = get_settings()
    options = {"require": ["exp", "sub"]}
    if settings.supabase_jwt_secret is not None:
        return jwt.decode(
            token,
            settings.supabase_jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            audience=settings.supabase_jwt_audience,
            options=options,
        )
    if not settings.supabase_url:
        raise AuthenticationError(
            "Supabase authentication is not configured on the server.",
            code="auth_not_configured",
            next_step="Set SUPABASE_URL (and optionally SUPABASE_JWT_SECRET) in the backend .env.",
        )
    client = _jwks_client(settings.supabase_url.rstrip("/") + "/auth/v1/.well-known/jwks.json")
    key = client.get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        key.key,
        algorithms=["RS256", "ES256"],
        audience=settings.supabase_jwt_audience,
        options=options,
    )


async def verify_token(token: str | None) -> CurrentUser:
    settings = get_settings()
    if settings.auth_mode == "local":
        user = local_user()
        await ensure_user_row(user)
        return user
    if not token:
        raise AuthenticationError("Please sign in to use NEXUS.", next_step="Sign in and try again.")
    try:
        claims = await asyncio.to_thread(_decode_supabase, token)
    except AuthenticationError:
        raise
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Your session has expired.", code="token_expired", next_step="Sign in again.") from exc
    except (jwt.PyJWTError, ValueError) as exc:
        logger.info("Rejected access token: %s", exc.__class__.__name__)
        raise AuthenticationError("Your session is invalid.", code="invalid_token", next_step="Sign in again.") from exc
    try:
        user_id = uuid.UUID(str(claims["sub"]))
    except ValueError as exc:
        raise AuthenticationError("Your session is invalid.", code="invalid_token") from exc
    email = (claims.get("email") or "").lower() or None
    user = CurrentUser(
        id=user_id,
        email=email,
        is_admin=bool(email and email in settings.admin_email_list),
        auth_mode="supabase",
        display_name=(claims.get("user_metadata") or {}).get("full_name"),
    )
    await ensure_user_row(user)
    return user


async def load_user(user_id: uuid.UUID) -> CurrentUser | None:
    """Load a user for background jobs (scheduler)."""
    async with session_scope() as db:
        row = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if row is None:
            return None
        return CurrentUser(
            id=row.id, email=row.email, is_admin=row.is_admin, auth_mode=row.auth_provider, display_name=row.display_name
        )
