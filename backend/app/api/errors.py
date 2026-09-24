"""Exception → JSON error mapping. Every error has code/message/reason/next_step."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import NexusError

logger = logging.getLogger(__name__)


def _body(code: str, message: str, reason: str | None = None, next_step: str | None = None) -> dict:
    return {"error": {"code": code, "message": message, "reason": reason, "next_step": next_step}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(NexusError)
    async def nexus_error(_: Request, exc: NexusError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"error": exc.to_dict()})

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(p) for p in first.get("loc", []) if p not in ("body", "query", "path"))
        return JSONResponse(status_code=422, content=_body(
            "invalid_request", f"Invalid value for '{field or 'request'}': {first.get('msg', 'invalid')}",
            next_step="Check the input and try again."))

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        messages = {404: "Not found.", 405: "Method not allowed.", 413: "The request is too large."}
        return JSONResponse(status_code=exc.status_code,
                            content=_body(f"http_{exc.status_code}", messages.get(exc.status_code, str(exc.detail))))

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error: %s", exc)
        return JSONResponse(status_code=500, content=_body(
            "internal_error", "NEXUS hit an unexpected error.", reason=exc.__class__.__name__,
            next_step="Try again. If it keeps happening, check the backend logs."))
