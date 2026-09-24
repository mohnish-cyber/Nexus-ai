"""Secret resolution.

Order of precedence for every API key:
1. Environment variable / .env file (read-only from the UI)
2. Encrypted value stored through Settings (`app_secrets` table)

Secret values are never returned by the API - only whether they are set,
where they come from, and a short hint (last 4 characters).
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from sqlalchemy import delete, select

from app.config import get_settings
from app.core.errors import ValidationFailedError
from app.database.session import session_scope
from app.models import AppSecret
from app.security.crypto import decrypt, encrypt, hint_for

MANAGED_SECRETS: dict[str, dict[str, str]] = {
    "ANTHROPIC_API_KEY": {"label": "Anthropic API key", "used_for": "AI reasoning (Claude)"},
    "OPENAI_COMPAT_API_KEY": {"label": "OpenAI-compatible API key", "used_for": "Alternative AI provider"},
    "OPENAI_API_KEY": {"label": "OpenAI API key", "used_for": "Server speech-to-text (Whisper) and voice"},
    "TAVILY_API_KEY": {"label": "Tavily API key", "used_for": "Web search"},
    "BRAVE_SEARCH_API_KEY": {"label": "Brave Search API key", "used_for": "Web search"},
    "ELEVENLABS_API_KEY": {"label": "ElevenLabs API key", "used_for": "Premium voice (TTS)"},
}

_CACHE_TTL = 30.0
_cache: dict[str, str | None] = {}
_cache_at: float = 0.0


def _env_value(name: str) -> str | None:
    settings = get_settings()
    value = getattr(settings, name.lower(), None)
    if value is None:
        return None
    if hasattr(value, "get_secret_value"):
        value = value.get_secret_value()
    return value or None


async def _load_cache() -> None:
    global _cache, _cache_at
    async with session_scope() as db:
        rows = (await db.execute(select(AppSecret))).scalars().all()
    _cache = {row.name: decrypt(row.ciphertext) for row in rows}
    _cache_at = time.monotonic()


def invalidate_cache() -> None:
    global _cache_at
    _cache_at = 0.0


async def get_secret(name: str) -> str | None:
    env = _env_value(name)
    if env:
        return env
    if time.monotonic() - _cache_at > _CACHE_TTL:
        try:
            await _load_cache()
        except Exception:
            return None
    return _cache.get(name)


async def set_secret(name: str, value: str, user_id: uuid.UUID | None) -> None:
    if name not in MANAGED_SECRETS:
        raise ValidationFailedError(f"'{name}' is not a configurable secret.", code="unknown_secret")
    value = (value or "").strip()
    if len(value) < 8 or len(value) > 4000 or any(c.isspace() for c in value):
        raise ValidationFailedError("That key doesn't look valid.", code="invalid_secret",
                                    next_step="Paste the full key without spaces.")
    async with session_scope() as db:
        row = (await db.execute(select(AppSecret).where(AppSecret.name == name))).scalar_one_or_none()
        if row is None:
            db.add(AppSecret(name=name, ciphertext=encrypt(value), hint=hint_for(value), updated_by=user_id))
        else:
            row.ciphertext = encrypt(value)
            row.hint = hint_for(value)
            row.updated_by = user_id
    invalidate_cache()


async def delete_secret(name: str) -> None:
    async with session_scope() as db:
        await db.execute(delete(AppSecret).where(AppSecret.name == name))
    invalidate_cache()


async def secret_status() -> list[dict[str, Any]]:
    async with session_scope() as db:
        rows = {r.name: r for r in (await db.execute(select(AppSecret))).scalars().all()}
    out = []
    for name, meta in MANAGED_SECRETS.items():
        env = _env_value(name)
        row = rows.get(name)
        if env:
            source, hint = "environment", hint_for(env)
        elif row is not None:
            source, hint = "stored", row.hint
        else:
            source, hint = None, None
        out.append({"name": name, **meta, "configured": source is not None, "source": source, "hint": hint})
    return out
