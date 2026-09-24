"""Builds the configured AIProvider.

Providers are cached per (provider, model, key) so API keys entered through
Settings take effect immediately without restarting the server.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any

from app.config import get_settings
from app.core.errors import NotConfiguredError
from app.services.ai.anthropic_provider import AnthropicProvider
from app.services.ai.base import AIProvider
from app.services.ai.mock_provider import DevMockProvider
from app.services.ai.openai_compatible import OpenAICompatibleProvider
from app.services.secrets import get_secret

_cache: dict[str, AIProvider] = {}
_override: AIProvider | None = None
_health_cache: dict[str, tuple[float, bool, str | None]] = {}


def set_provider_override(provider: AIProvider | None) -> None:
    """Used by tests to inject a scripted provider."""
    global _override
    _override = provider


def _key(*parts: str | None) -> str:
    return hashlib.sha256("|".join(p or "" for p in parts).encode()).hexdigest()


async def get_provider() -> AIProvider:
    if _override is not None:
        return _override
    settings = get_settings()
    if settings.ai_provider == "mock":
        return _cache.setdefault("mock", DevMockProvider())

    if settings.ai_provider == "openai_compatible":
        base = settings.openai_compat_base_url
        model = settings.openai_compat_model
        if not base or not model:
            raise NotConfiguredError(
                "The OpenAI-compatible AI provider is not configured.",
                code="ai_not_configured",
                reason="OPENAI_COMPAT_BASE_URL and OPENAI_COMPAT_MODEL must both be set.",
                next_step="Set them in .env (e.g. http://localhost:11434/v1 and llama3.1 for Ollama).",
            )
        api_key = await get_secret("OPENAI_COMPAT_API_KEY")
        k = _key("oai", base, model, api_key)
        if k not in _cache:
            _cache[k] = OpenAICompatibleProvider(base, model, api_key, max_tokens=min(settings.ai_max_output_tokens, 8192))
        return _cache[k]

    api_key = await get_secret("ANTHROPIC_API_KEY")
    if not api_key:
        raise NotConfiguredError(
            "NEXUS's AI core is not connected yet.",
            code="ai_not_configured",
            reason="No Anthropic API key is configured.",
            next_step="Add your key in Settings → API keys, or set ANTHROPIC_API_KEY in .env.",
        )
    k = _key("anthropic", settings.ai_model, api_key, settings.ai_effort_default)
    if k not in _cache:
        _cache[k] = AnthropicProvider(
            api_key,
            settings.ai_model,
            default_effort=settings.ai_effort_default,
            max_tokens=settings.ai_max_output_tokens,
            refusal_fallback=settings.anthropic_refusal_fallback,
        )
    return _cache[k]


async def provider_status(force: bool = False) -> dict[str, Any]:
    """Configured? Reachable? Used for the startup sequence and Settings."""
    settings = get_settings()
    try:
        provider = await get_provider()
    except NotConfiguredError as exc:
        return {"configured": False, "ready": False, "provider": settings.ai_provider, "model": None,
                "error": exc.to_dict()}
    k = f"{provider.name}:{provider.model}:{id(provider)}"
    cached = _health_cache.get(k)
    if cached and not force and time.monotonic() - cached[0] < 300:
        ok, err = cached[1], cached[2]
    else:
        ok, err = await provider.health()
        _health_cache[k] = (time.monotonic(), ok, err)
    return {
        "configured": True,
        "ready": ok,
        "provider": provider.name,
        "model": provider.model,
        "vision": provider.supports_vision,
        "mock": provider.name in ("mock", "scripted"),
        "error": None if ok else {"code": "ai_unreachable", "message": err or "AI provider unreachable"},
    }
