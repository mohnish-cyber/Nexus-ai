"""SSRF protection for every outbound request made on behalf of a user or model.

Rules:
* only http/https, no embedded credentials
* hostnames must resolve exclusively to globally routable addresses
  (blocks localhost, private LANs, link-local cloud metadata, CGNAT, ...)
* redirects are followed manually and every hop is re-validated
* after connecting (when not going through a configured proxy) the actual peer
  address is checked again to defeat DNS rebinding
* responses are size-capped and time-limited
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx

from app.core.errors import SecurityViolationError, ToolExecutionError

logger = logging.getLogger(__name__)

USER_AGENT = "NEXUS-Assistant/0.1 (+personal AI assistant; respects robots)"
_BLOCKED_HOST_SUFFIXES = (".localhost", ".local", ".internal", ".home.arpa", ".lan", ".intranet")
_BLOCKED_HOSTS = {"localhost", "metadata.google.internal", "metadata"}
MAX_REDIRECTS = 5


@dataclass
class FetchResult:
    url: str
    status_code: int
    content_type: str
    content: bytes
    truncated: bool

    @property
    def text(self) -> str:
        charset = "utf-8"
        if "charset=" in self.content_type:
            charset = self.content_type.split("charset=")[-1].split(";")[0].strip() or "utf-8"
        try:
            return self.content.decode(charset, errors="replace")
        except LookupError:
            return self.content.decode("utf-8", errors="replace")


def _is_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return bool(ip.is_global) and not ip.is_multicast


def validate_url_syntax(url: str) -> tuple[str, str, int]:
    """Validate scheme/host/credentials. Returns (scheme, host, port)."""
    if not isinstance(url, str) or len(url) > 2048:
        raise SecurityViolationError("That URL is not valid.", code="invalid_url", reason="URL is missing or too long.")
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise SecurityViolationError(
            f"Only http and https links can be opened (got '{scheme or 'none'}').",
            code="unsafe_url_scheme",
            reason="Other schemes (file:, ftp:, javascript:, ...) can expose local data.",
        )
    if parts.username or parts.password:
        raise SecurityViolationError(
            "URLs with embedded credentials are not allowed.", code="unsafe_url_credentials"
        )
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        raise SecurityViolationError("That URL has no host name.", code="invalid_url")
    if host in _BLOCKED_HOSTS or host.endswith(_BLOCKED_HOST_SUFFIXES):
        raise SecurityViolationError(
            f"'{host}' is a local/internal address, which NEXUS will not fetch.",
            code="ssrf_blocked",
            reason="Requests to internal network addresses are blocked to prevent SSRF attacks.",
        )
    try:
        port = parts.port or (443 if scheme == "https" else 80)
    except ValueError as exc:
        raise SecurityViolationError("That URL has an invalid port.", code="invalid_url") from exc
    # Literal IPs are checked immediately.
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        ip = None
    if ip is not None and not _is_public_ip(ip):
        raise SecurityViolationError(
            f"'{host}' is a private or reserved address, which NEXUS will not fetch.",
            code="ssrf_blocked",
            reason="Requests to internal network addresses are blocked to prevent SSRF attacks.",
        )
    return scheme, host, port


async def resolve_public(host: str, port: int) -> list[str]:
    """Resolve `host` and ensure every address is public."""
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
        return [str(ip)]
    except ValueError:
        pass
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ToolExecutionError(
            f"Could not resolve '{host}'.",
            code="dns_failed",
            reason="The domain does not exist or DNS is unavailable.",
            next_step="Check the address or your network connection.",
        ) from exc
    addrs = sorted({info[4][0] for info in infos})
    for addr in addrs:
        if not _is_public_ip(ipaddress.ip_address(addr.split("%")[0])):
            raise SecurityViolationError(
                f"'{host}' resolves to an internal address ({addr}), so NEXUS will not fetch it.",
                code="ssrf_blocked",
                reason="Requests to internal network addresses are blocked to prevent SSRF attacks.",
            )
    return addrs


async def validate_url(url: str) -> str:
    _, host, port = validate_url_syntax(url)
    await resolve_public(host, port)
    return url


def _proxy_configured() -> bool:
    return any(os.environ.get(k) for k in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY"))


def _check_peer(response: httpx.Response) -> None:
    if _proxy_configured():
        return  # the peer is the proxy; the pre-resolution check already ran
    stream = response.extensions.get("network_stream")
    if stream is None:
        return
    try:
        addr = stream.get_extra_info("server_addr")
    except Exception:  # pragma: no cover - transport specific
        return
    if not addr:
        return
    ip = ipaddress.ip_address(str(addr[0]).split("%")[0])
    if not _is_public_ip(ip):
        raise SecurityViolationError(
            "The site redirected the connection to an internal address; request blocked.",
            code="ssrf_blocked",
            reason="Possible DNS rebinding attack.",
        )


async def safe_fetch(
    url: str,
    *,
    max_bytes: int = 3 * 1024 * 1024,
    timeout: float = 15.0,
    accept: str = "text/html,application/xhtml+xml,application/json,text/plain;q=0.9,*/*;q=0.5",
    client: httpx.AsyncClient | None = None,
) -> FetchResult:
    """GET a public URL with SSRF protection, manual redirects and a size cap."""
    own_client = client is None
    client = client or httpx.AsyncClient(
        timeout=httpx.Timeout(timeout, connect=min(timeout, 8.0)),
        follow_redirects=False,
        headers={"User-Agent": USER_AGENT, "Accept": accept},
    )
    try:
        current = url
        for _hop in range(MAX_REDIRECTS + 1):
            await validate_url(current)
            try:
                async with client.stream("GET", current) as response:
                    _check_peer(response)
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise ToolExecutionError("The site sent an invalid redirect.", code="bad_redirect")
                        current = urljoin(current, location)
                        continue
                    chunks: list[bytes] = []
                    size = 0
                    truncated = False
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > max_bytes:
                            chunks.append(chunk[: max(0, max_bytes - (size - len(chunk)))])
                            truncated = True
                            break
                        chunks.append(chunk)
                    return FetchResult(
                        url=str(response.url),
                        status_code=response.status_code,
                        content_type=response.headers.get("content-type", ""),
                        content=b"".join(chunks),
                        truncated=truncated,
                    )
            except httpx.TimeoutException as exc:
                raise ToolExecutionError(
                    "The website took too long to respond.",
                    code="fetch_timeout",
                    reason=f"No response within {timeout:.0f}s.",
                    next_step="Try again later or use a different source.",
                ) from exc
            except httpx.HTTPError as exc:
                raise ToolExecutionError(
                    "Could not connect to the website.",
                    code="fetch_failed",
                    reason=str(exc)[:200] or exc.__class__.__name__,
                    next_step="Check the address or your network connection.",
                ) from exc
        raise ToolExecutionError("Too many redirects.", code="too_many_redirects")
    finally:
        if own_client:
            await client.aclose()
