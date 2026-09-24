"""User preferences with typed defaults.

Stored as one JSON row per top-level section in `user_preferences`.
"""

from __future__ import annotations

import copy
import logging
import uuid
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.config import get_settings
from app.database.session import session_scope
from app.models import UserPreference

logger = logging.getLogger(__name__)

DEFAULT_PREFERENCES: dict[str, dict[str, Any]] = {
    "profile": {"user_name": None, "response_style": "concise"},
    "voice": {
        "auto_speak": False,
        "stt_provider": "auto",  # auto | server | browser
        "tts_provider": "browser",  # browser | server
        "voice_name": None,
        "rate": 1.0,
        "pitch": 1.0,
        "wake_word_enabled": False,
    },
    "permissions": {"confirm_medium_actions": True},
    "memory": {"auto_remember": True, "require_approval_for_inferred": True},
    "location": {"city": None, "latitude": None, "longitude": None, "country": None},
    "regional": {"timezone": None, "units": "metric"},
    "workspace": {"roots": []},
    "apps": {"custom": []},
}

SECTION_SCHEMAS: dict[str, set[str]] = {k: set(v) for k, v in DEFAULT_PREFERENCES.items()}


def _system_timezone() -> str:
    settings = get_settings()
    if settings.default_timezone:
        return settings.default_timezone
    try:
        from tzlocal import get_localzone_name

        return get_localzone_name() or "UTC"
    except Exception:
        return "UTC"


def resolve_timezone(prefs: dict[str, Any]) -> str:
    tz = (prefs.get("regional") or {}).get("timezone") or _system_timezone()
    try:
        ZoneInfo(tz)
        return tz
    except Exception:
        return "UTC"


def workspace_roots(prefs: dict[str, Any]) -> list[Path]:
    roots = list(get_settings().workspace_root_list)
    for r in (prefs.get("workspace") or {}).get("roots", []):
        try:
            p = Path(r).expanduser().resolve()
            if p not in roots:
                roots.append(p)
        except (OSError, RuntimeError, TypeError) as exc:
            logger.warning("Ignoring invalid workspace root %r: %s", r, exc)
    return roots


async def get_preferences(user_id: uuid.UUID) -> dict[str, Any]:
    prefs = copy.deepcopy(DEFAULT_PREFERENCES)
    async with session_scope() as db:
        rows = (await db.execute(select(UserPreference).where(UserPreference.user_id == user_id))).scalars().all()
    for row in rows:
        if row.key in prefs and isinstance(row.value, dict):
            prefs[row.key].update({k: v for k, v in row.value.items() if k in SECTION_SCHEMAS[row.key]})
    return prefs


async def update_preferences(user_id: uuid.UUID, section: str, values: dict[str, Any]) -> dict[str, Any]:
    if section not in DEFAULT_PREFERENCES:
        raise KeyError(section)
    clean = {k: v for k, v in values.items() if k in SECTION_SCHEMAS[section]}
    async with session_scope() as db:
        row = (
            await db.execute(
                select(UserPreference).where(UserPreference.user_id == user_id, UserPreference.key == section)
            )
        ).scalar_one_or_none()
        if row is None:
            row = UserPreference(user_id=user_id, key=section, value=clean)
            db.add(row)
        else:
            merged = dict(row.value or {})
            merged.update(clean)
            row.value = merged
    return await get_preferences(user_id)
