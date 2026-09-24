"""Test fixtures: every test gets a fresh data directory and SQLite database."""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import pytest

os.environ.setdefault("NEXUS_ENV", "test")
os.environ["SCHEDULER_MODE"] = "disabled"
os.environ["AI_PROVIDER"] = "anthropic"
for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "TAVILY_API_KEY", "BRAVE_SEARCH_API_KEY", "DATABASE_URL",
            "WORKSPACE_ROOTS", "AUTH_MODE"):
    os.environ.pop(key, None)


@pytest.fixture(autouse=True)
async def fresh_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Path]:
    from app.config import Settings, get_settings
    from app.database import session as db_session
    from app.security import auth
    from app.security.rate_limit import rate_limiter
    from app.services import secrets
    from app.services.ai import factory

    data_dir = tmp_path / "data"
    monkeypatch.setenv("NEXUS_DATA_DIR", str(data_dir))
    # Run the suite against PostgreSQL with NEXUS_TEST_DATABASE_URL=postgresql+asyncpg://...
    test_db = os.environ.get("NEXUS_TEST_DATABASE_URL")
    if test_db:
        monkeypatch.setenv("DATABASE_URL", test_db)
    monkeypatch.setenv("NEXUS_SECRET_KEY", "test-secret-key-for-nexus-tests-only")
    # Never pick up the developer's real .env during tests.
    monkeypatch.setitem(Settings.model_config, "env_file", ())
    get_settings.cache_clear()
    await db_session.dispose_engine()
    auth.forget_known_users()
    rate_limiter.reset()
    secrets.invalidate_cache()
    factory.set_provider_override(None)
    factory._cache.clear()
    factory._health_cache.clear()
    await db_session.init_db()
    if test_db:
        from sqlalchemy import text

        from app.models import Base

        async with db_session.get_engine().begin() as conn:
            names = ", ".join(t.name for t in Base.metadata.sorted_tables)
            await conn.execute(text(f"TRUNCATE {names} CASCADE"))
    yield data_dir
    factory.set_provider_override(None)
    await db_session.dispose_engine()
    get_settings.cache_clear()


@pytest.fixture
async def user():
    from app.security.auth import verify_token

    return await verify_token(None)


@pytest.fixture
def events() -> list[dict[str, Any]]:
    return []


@pytest.fixture
def make_ctx(user, events) -> Callable[..., Any]:
    from app.core.context import RequestContext

    def _make(interactive: bool = True, approver: str | None = None, preferences: dict | None = None) -> RequestContext:
        async def emit(event: dict[str, Any]) -> None:
            events.append(event)
            if approver and event.get("type") == "permission_request":
                from app.security.permissions import Decision, permission_broker

                pid = uuid.UUID(event["permission"]["id"])

                async def decide() -> None:
                    await asyncio.sleep(0)
                    permission_broker.resolve(pid, user.id, Decision(approver))

                asyncio.get_running_loop().create_task(decide())

        import copy

        from app.services.preferences import DEFAULT_PREFERENCES

        prefs = copy.deepcopy(DEFAULT_PREFERENCES)
        for section, values in (preferences or {}).items():
            prefs[section].update(values)
        return RequestContext(user=user, emit_fn=emit, interactive=interactive, preferences=prefs)

    return _make


@pytest.fixture
def scripted():
    from app.services.ai import factory
    from app.services.ai.mock_provider import ScriptedProvider

    provider = ScriptedProvider()
    factory.set_provider_override(provider)
    return provider


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "projects"
    (root / "demo").mkdir(parents=True)
    (root / "demo" / "app.py").write_text("def add(a, b):\n    return a - b\n")
    (root / "demo" / "test_app.py").write_text(
        "from app import add\n\ndef test_add():\n    assert add(2, 3) == 5\n")
    (root / "demo" / ".env").write_text("SECRET=1\n")
    return root
