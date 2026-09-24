"""Run the NEXUS API server: `python -m app` (uses NEXUS_HOST / NEXUS_PORT)."""

from __future__ import annotations

import ipaddress
import sys

import uvicorn

from app.config import get_settings


def _is_loopback(host: str) -> bool:
    if host in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def main() -> None:
    s = get_settings()
    if s.auth_mode == "local" and not _is_loopback(s.nexus_host):
        sys.exit(
            f"Refusing to listen on {s.nexus_host} in AUTH_MODE=local: anyone on the network could use NEXUS "
            "without signing in. Use AUTH_MODE=supabase (with HTTPS) for network access, or NEXUS_HOST=127.0.0.1."
        )
    uvicorn.run("app.main:app", host=s.nexus_host, port=s.nexus_port, proxy_headers=True,
                reload=not s.is_production and "--reload" in sys.argv)


if __name__ == "__main__":
    main()
