"""HTTP hardening: security headers and cross-site request protection."""

from __future__ import annotations

from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import get_settings

_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

APP_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; "
    "media-src 'self' blob:; connect-src 'self' ws: wss: https://*.supabase.co wss://*.supabase.co; "
    "font-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-site")
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
            response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'; sandbox")
        elif response.headers.get("content-type", "").startswith("text/html"):
            # The built web app (served by FastAPI in production).
            response.headers.setdefault("Content-Security-Policy", APP_CSP)
        return response


def origin_allowed(origin: str | None, host: str | None) -> bool:
    """True for same-origin requests, configured frontend origins, and non-browser clients (no Origin)."""
    if not origin:
        return True
    if origin == "null":
        return False
    if origin in get_settings().cors_origin_list:
        return True
    parts = urlsplit(origin)
    return bool(host) and parts.netloc.lower() == host.lower()


class OriginGuardMiddleware(BaseHTTPMiddleware):
    """Rejects state-changing requests from foreign web origins.

    CORS only stops a malicious page from *reading* responses; simple
    cross-site POSTs (e.g. multipart uploads) would still execute. Since NEXUS
    can act on the local machine, we refuse them outright.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method in _UNSAFE_METHODS:
            origin = request.headers.get("origin")
            if not origin_allowed(origin, request.headers.get("host")):
                return JSONResponse(
                    status_code=403,
                    content={"error": {"code": "origin_not_allowed",
                                       "message": "Requests from this website are not allowed.",
                                       "reason": f"Origin {origin} is not in CORS_ORIGINS.",
                                       "next_step": "Add the origin to CORS_ORIGINS if it is your NEXUS frontend."}},
                )
        return await call_next(request)
