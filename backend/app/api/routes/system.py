"""Health, startup self-checks, public config and host telemetry."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
from fastapi import APIRouter, Depends

from app import __version__
from app.agents.registry import all_agents
from app.api.deps import current_user
from app.config import get_settings
from app.database.session import check_db
from app.security.auth import CurrentUser
from app.services import telemetry
from app.services.ai.factory import provider_status
from app.services.voice.stt import get_stt
from app.services.voice.tts import get_tts
from app.tools.registry import all_tools
from app.tools.web import configured_search_provider

router = APIRouter(tags=["system"])

_net_cache: tuple[float, dict[str, Any]] | None = None


async def network_status() -> dict[str, Any]:
    global _net_cache
    if _net_cache and time.monotonic() - _net_cache[0] < 60:
        return _net_cache[1]
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            await client.head("https://api.anthropic.com/")
        result = {"connected": True, "latency_ms": int((time.monotonic() - started) * 1000)}
    except httpx.HTTPError as exc:
        result = {"connected": False, "error": exc.__class__.__name__}
    _net_cache = (time.monotonic(), result)
    return result


@router.get("/api/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "version": __version__}


@router.get("/api/system/config")
async def public_config() -> dict[str, Any]:
    s = get_settings()
    return {
        "version": __version__,
        "auth_mode": s.auth_mode,
        "supabase_url": s.supabase_url if s.auth_mode == "supabase" else None,
        "supabase_anon_key": s.supabase_anon_key if s.auth_mode == "supabase" else None,
        "computer_control": s.computer_control,
        "max_upload_mb": s.max_upload_mb,
    }


@router.get("/api/system/status")
async def system_status() -> dict[str, Any]:
    """Real startup self-checks. A component is only 'ready' if its check passed."""
    from app.services import scheduler as sched_module

    s = get_settings()
    db_ok, ai, net, stt, tts, search = await asyncio.gather(
        check_db(), provider_status(), network_status(), get_stt(), get_tts(), configured_search_provider()
    )
    sched = sched_module.scheduler
    agents = all_agents()
    return {
        "version": __version__,
        "components": {
            "database": {"ready": db_ok, "detail": "SQLite" if "sqlite" in s.resolved_database_url else "PostgreSQL"},
            "memory": {"ready": db_ok, "detail": "Structured memory store"},
            "ai": ai,
            "agents": {"ready": bool(agents), "count": len(agents), "tools": len(all_tools())},
            "voice": {
                "ready": True,
                "stt_server": stt.name if stt else None,
                "tts_server": tts.name if tts else None,
                "detail": "Server speech" if (stt or tts) else "Browser speech (server voice not configured)",
            },
            "network": {"ready": net.get("connected", False), **net},
            "search": {"ready": search is not None, "provider": search[0] if search else None},
            "scheduler": {
                "ready": s.scheduler_mode == "external" or bool(sched and sched.running),
                "mode": s.scheduler_mode,
                "last_tick_at": sched.last_tick_at.isoformat() if sched and sched.last_tick_at else None,
            },
            "computer_control": {"ready": s.computer_control, "display": telemetry.has_display()},
        },
        "auth_mode": s.auth_mode,
    }


@router.get("/api/system/telemetry")
async def host_telemetry(_: CurrentUser = Depends(current_user)) -> dict[str, Any]:
    return await asyncio.to_thread(telemetry.snapshot)
