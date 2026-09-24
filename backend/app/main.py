"""NEXUS API entry point.

    uvicorn app.main:app --host 127.0.0.1 --port 8000

Serves the REST API under /api, the WebSocket at /ws, and - when the frontend
has been built (frontend/dist) - the web app itself.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import __version__
from app.api.errors import install_error_handlers
from app.api.middleware import OriginGuardMiddleware, SecurityHeadersMiddleware
from app.api.routes import (
    agents,
    automations,
    chat,
    conversations,
    devices,
    files,
    memory,
    notifications,
    permissions,
    settings,
    system,
    tasks,
    voice,
)
from app.config import REPO_ROOT, get_settings
from app.database.session import dispose_engine, init_db
from app.logging_config import configure_logging
from app.security.auth import ensure_user_row, local_user
from app.services.notifications import hub
from app.services.scheduler import get_scheduler

logger = logging.getLogger("nexus")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    s = get_settings()
    configure_logging(s.log_level)
    s.ensure_dirs()
    if s.is_production and s.nexus_secret_key is None:
        raise RuntimeError("NEXUS_SECRET_KEY must be set in production.")
    s.secret_key()  # generate/persist the dev key early
    await init_db()
    if s.auth_mode == "local":
        await ensure_user_row(local_user())
    hub.start_relay()
    scheduler = None
    if s.scheduler_mode == "embedded" and not s.is_test:
        scheduler = get_scheduler(s.scheduler_poll_seconds)
        scheduler.start()
    logger.info("NEXUS %s online (auth=%s, db=%s, scheduler=%s, computer_control=%s)", __version__, s.auth_mode,
                "sqlite" if "sqlite" in s.resolved_database_url else "postgres", s.scheduler_mode, s.computer_control)
    try:
        yield
    finally:
        if scheduler is not None:
            await scheduler.stop()
        await hub.stop_relay()
        await dispose_engine()


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="NEXUS API",
        version=__version__,
        description="Personal AI Operating System",
        lifespan=lifespan,
        docs_url="/api/docs" if not s.is_production else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if not s.is_production else None,
    )
    # Order: outermost first
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(OriginGuardMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
        max_age=600,
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=s.allowed_host_list or ["localhost"])
    install_error_handlers(app)

    for module in (system, chat, conversations, memory, files, tasks, automations, agents, permissions, settings,
                   voice, notifications, devices):
        app.include_router(module.router)

    dist = REPO_ROOT / "frontend" / "dist"
    if (dist / "index.html").exists():
        _mount_frontend(app, dist)
    return app


def _mount_frontend(app: FastAPI, dist: Path) -> None:
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
    index = dist / "index.html"

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        if path.startswith(("api/", "ws")):
            raise StarletteHTTPException(status_code=404)
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(dist.resolve()):
            return FileResponse(candidate)
        return FileResponse(index)


app = create_app()
