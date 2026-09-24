"""Real host telemetry via psutil. Only reports what is actually readable -
unavailable metrics are returned as null, never invented."""

from __future__ import annotations

import contextlib
import os
import platform
import socket
import time
from typing import Any

import psutil

_last_net: tuple[float, int, int] | None = None


def has_display() -> bool:
    if os.name == "nt" or platform.system() == "Darwin":
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def snapshot() -> dict[str, Any]:
    global _last_net
    data: dict[str, Any] = {
        "host": socket.gethostname(),
        "os": f"{platform.system()} {platform.release()}",
        "platform": platform.system().lower(),
        "python": platform.python_version(),
        "cpu": None,
        "memory": None,
        "disk": None,
        "battery": None,
        "network": None,
        "uptime_seconds": None,
        "display": has_display(),
    }
    with contextlib.suppress(Exception):
        data["cpu"] = {
            "percent": psutil.cpu_percent(interval=None),
            "cores": psutil.cpu_count(logical=True),
            "load_avg": list(os.getloadavg()) if hasattr(os, "getloadavg") else None,
        }
    with contextlib.suppress(Exception):
        vm = psutil.virtual_memory()
        data["memory"] = {"percent": vm.percent, "used_gb": round(vm.used / 1e9, 2), "total_gb": round(vm.total / 1e9, 2)}
    with contextlib.suppress(Exception):
        du = psutil.disk_usage(os.path.expanduser("~"))
        data["disk"] = {"percent": du.percent, "free_gb": round(du.free / 1e9, 1), "total_gb": round(du.total / 1e9, 1)}
    with contextlib.suppress(Exception):
        batt = psutil.sensors_battery()
        if batt is not None:
            data["battery"] = {"percent": round(batt.percent), "plugged_in": batt.power_plugged,
                               "secs_left": batt.secsleft if batt.secsleft and batt.secsleft > 0 else None}
    with contextlib.suppress(Exception):
        io = psutil.net_io_counters()
        now = time.monotonic()
        rate = None
        if _last_net is not None and now > _last_net[0]:
            dt = now - _last_net[0]
            rate = {"down_kbps": round((io.bytes_recv - _last_net[1]) / dt / 1024, 1),
                    "up_kbps": round((io.bytes_sent - _last_net[2]) / dt / 1024, 1)}
        _last_net = (now, io.bytes_recv, io.bytes_sent)
        stats = psutil.net_if_stats()
        up = [name for name, s in stats.items() if s.isup and not name.startswith(("lo", "docker", "veth"))]
        data["network"] = {"interfaces_up": len(up), "rate": rate}
    with contextlib.suppress(Exception):
        data["uptime_seconds"] = int(time.time() - psutil.boot_time())
    return data
