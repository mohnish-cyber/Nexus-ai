"""Controlled interaction with the local computer.

Only applications from an explicit catalog (plus apps the user registered in
Settings) can be launched; only paths inside authorised folders (or the
standard user folders) can be opened; executables are never "opened";
terminal commands go through the allowlist in `app/security/commands.py`.
"""

from __future__ import annotations

import asyncio
import io
import os
import platform
import re
import shutil
import sys
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import Field

from app.config import get_settings
from app.core.context import RequestContext
from app.core.errors import NexusError, NotFoundError, SecurityViolationError, ToolExecutionError
from app.security.commands import check_path_args, run_validated, validate_command
from app.security.paths import is_sensitive_path, is_within, resolve_within
from app.security.risk import RiskLevel
from app.security.url_guard import validate_url_syntax
from app.services import telemetry
from app.tools.base import Assessment, NoParams, Tool, ToolOutput, ToolParams

PLATFORM = sys.platform  # linux | darwin | win32

# app id -> metadata + launch candidates per platform (tried in order)
APP_CATALOG: dict[str, dict[str, Any]] = {
    "vscode": {
        "name": "VS Code", "aliases": ["vs code", "vscode", "visual studio code", "code editor"], "accepts_path": True,
        "linux": [["code"], ["codium"]], "darwin": [["open", "-a", "Visual Studio Code"], ["code"]], "win32": [["code"]],
    },
    "browser": {"name": "Web browser", "aliases": ["browser", "web browser", "internet"], "special": "browser"},
    "chrome": {
        "name": "Google Chrome", "aliases": ["chrome", "google chrome", "chromium"],
        "linux": [["google-chrome"], ["google-chrome-stable"], ["chromium"], ["chromium-browser"]],
        "darwin": [["open", "-a", "Google Chrome"]], "win32": [["chrome"]],
    },
    "firefox": {"name": "Firefox", "aliases": ["firefox", "mozilla"], "linux": [["firefox"]],
                "darwin": [["open", "-a", "Firefox"]], "win32": [["firefox"]]},
    "terminal": {
        "name": "Terminal", "aliases": ["terminal", "command prompt", "shell", "console"], "accepts_path": True,
        "linux": [["x-terminal-emulator"], ["gnome-terminal"], ["konsole"], ["xfce4-terminal"]],
        "darwin": [["open", "-a", "Terminal"]], "win32": [["wt"], ["cmd", "/c", "start", "cmd"]],
    },
    "file_manager": {
        "name": "File manager", "aliases": ["file manager", "files", "explorer", "finder", "file explorer"],
        "accepts_path": True, "linux": [["xdg-open"]], "darwin": [["open"]], "win32": [["explorer"]],
        "default_arg": "~",
    },
    "calculator": {"name": "Calculator", "aliases": ["calculator", "calc"],
                   "linux": [["gnome-calculator"], ["kcalc"], ["galculator"]], "darwin": [["open", "-a", "Calculator"]],
                   "win32": [["calc"]]},
    "text_editor": {"name": "Text editor", "aliases": ["text editor", "notepad", "gedit", "textedit"], "accepts_path": True,
                    "linux": [["gnome-text-editor"], ["gedit"], ["kate"], ["mousepad"]],
                    "darwin": [["open", "-a", "TextEdit"]], "win32": [["notepad"]]},
    "spotify": {"name": "Spotify", "aliases": ["spotify", "music"], "linux": [["spotify"]],
                "darwin": [["open", "-a", "Spotify"]], "win32": [["spotify"]]},
    "slack": {"name": "Slack", "aliases": ["slack"], "linux": [["slack"]], "darwin": [["open", "-a", "Slack"]],
              "win32": [["slack"]]},
    "discord": {"name": "Discord", "aliases": ["discord"], "linux": [["discord"]], "darwin": [["open", "-a", "Discord"]],
                "win32": [["discord"]]},
}

_EXECUTABLE_EXT = {".exe", ".bat", ".cmd", ".com", ".msi", ".ps1", ".vbs", ".js", ".jar", ".sh", ".bash", ".command",
                   ".app", ".desktop", ".appimage", ".scr", ".pif", ".lnk", ".py", ".run", ".bin", ".deb", ".rpm"}
_STANDARD_FOLDERS = ("Desktop", "Documents", "Downloads", "Pictures", "Music", "Videos", "Projects")


def _require_computer_control() -> None:
    if not get_settings().computer_control:
        raise SecurityViolationError(
            "Computer control is disabled on this server.",
            code="computer_control_disabled",
            reason="It is off by default in multi-user mode so remote users can't control the host machine.",
            next_step="Set COMPUTER_CONTROL_ENABLED=true only on your personal machine.",
        )


def _require_display() -> None:
    if not telemetry.has_display():
        raise ToolExecutionError(
            "No graphical display is available on the machine running NEXUS.",
            code="no_display",
            reason="The NEXUS backend is running headless (e.g. in a server or container), so it cannot open windows.",
            next_step="Run the NEXUS backend on your desktop computer to control apps.",
        )


def custom_apps(prefs: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out = {}
    for app in (prefs.get("apps") or {}).get("custom", []):
        app_id = str(app.get("id", "")).strip().lower()
        cmd = app.get("command")
        if app_id and isinstance(cmd, list) and cmd:
            out[app_id] = {"name": app.get("name") or app_id, "aliases": [app.get("name", app_id).lower()],
                           PLATFORM: [cmd], "accepts_path": bool(app.get("accepts_path")), "custom": True}
    return out


def find_app(query: str, prefs: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    q = query.strip().lower().removesuffix(".exe")
    catalog = {**APP_CATALOG, **custom_apps(prefs)}
    if q in catalog:
        return q, catalog[q]
    for app_id, meta in catalog.items():
        if q == meta["name"].lower() or q in meta.get("aliases", []):
            return app_id, meta
    if not re.search(r"\b(folder|directory|file|project|document|repo)\b", q):
        best: tuple[int, str] | None = None
        for app_id, meta in catalog.items():
            for alias in meta.get("aliases", []):
                if re.search(rf"\b{re.escape(alias)}\b", q) and (best is None or len(alias) > best[0]):
                    best = (len(alias), app_id)
        if best is not None:
            return best[1], catalog[best[1]]
    raise NotFoundError(
        f"'{query}' is not in NEXUS's list of approved applications.",
        code="app_not_allowed",
        reason="Only known applications (or ones you add in Settings → Applications) can be launched.",
        next_step="Add it under Settings → Applications, or open it yourself.",
    )


def resolve_launch(meta: dict[str, Any]) -> list[str] | None:
    for candidate in meta.get(PLATFORM, []):
        exe = candidate[0]
        if exe in ("open", "cmd") and PLATFORM in ("darwin", "win32"):
            return list(candidate)
        if Path(exe).is_absolute() and Path(exe).exists():
            return list(candidate)
        if shutil.which(exe):
            return list(candidate)
    return None


async def _spawn(argv: list[str], label: str) -> None:
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE, start_new_session=True,
        )
    except FileNotFoundError as exc:
        raise ToolExecutionError(
            f"{label} could not be opened because the executable was not found.",
            code="executable_not_found",
            reason=f"'{argv[0]}' is not installed or not on PATH.",
            next_step=f"Install {label} or add its location in Settings → Applications.",
        ) from exc
    except OSError as exc:
        raise ToolExecutionError(f"{label} could not be started.", code="launch_failed", reason=str(exc)[:200]) from exc
    try:
        # Launchers usually return quickly; a long-running GUI app keeps running.
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=2.5)
    except TimeoutError:
        return  # still running = launched
    if proc.returncode not in (0, None):
        msg = (stderr or b"").decode("utf-8", "replace").strip()[:300]
        raise ToolExecutionError(f"{label} failed to start (exit code {proc.returncode}).", code="launch_failed",
                                 reason=msg or None, next_step="Check that the application is installed correctly.")


def _classify_path(path: Path, ctx: RequestContext) -> RiskLevel:
    if any(is_within(path, r) for r in ctx.workspace_roots):
        return RiskLevel.LOW
    home = Path.home()
    if any(is_within(path, home / f) for f in _STANDARD_FOLDERS):
        return RiskLevel.LOW
    return RiskLevel.MEDIUM


def _check_openable(path: Path) -> None:
    if is_sensitive_path(path):
        raise SecurityViolationError(f"'{path.name}' looks like a credential file; NEXUS will not open it.",
                                     code="sensitive_path")
    if path.is_file() and (path.suffix.lower() in _EXECUTABLE_EXT or (os.name != "nt" and os.access(path, os.X_OK))):
        raise SecurityViolationError(
            f"'{path.name}' is a program or script. Opening it would run it, so NEXUS won't do that.",
            code="executable_blocked",
            next_step="Run it yourself if you trust it.",
        )


def _expand(p: str) -> Path:
    return Path(os.path.expandvars(p)).expanduser().resolve()


# ---------------------------------------------------------------------------


class OpenAppParams(ToolParams):
    app: str = Field(min_length=1, max_length=80, description="Application name, e.g. 'VS Code', 'Chrome', 'terminal'")
    path: str | None = Field(default=None, max_length=1000, description="Optional folder/file to open with the app")


class OpenApplicationTool(Tool):
    name = "open_application"
    description = ("Launch an approved desktop application (VS Code, browser, terminal, file manager, calculator, "
                   "text editor, Spotify, Slack, Discord, or user-added apps), optionally opening a folder/file in it.")
    Params = OpenAppParams
    category = "computer"
    timeout_seconds = 20

    async def available(self, ctx: RequestContext) -> tuple[bool, str | None]:
        if not get_settings().computer_control:
            return False, "Computer control is disabled on this server."
        return True, None

    def assess(self, params: OpenAppParams, ctx: RequestContext) -> Assessment:
        app_id, meta = find_app(params.app, ctx.preferences)
        risk = RiskLevel.LOW
        details: dict[str, Any] = {"app": meta["name"]}
        if params.path:
            path = _expand(params.path)
            _check_openable(path)
            risk = _classify_path(path, ctx)
            details["path"] = str(path)
        where = f" in {details['path']}" if params.path else ""
        return Assessment(risk, f"Open {meta['name']}{where}", scope=f"{app_id}:{details.get('path', '')}", details=details)

    async def run(self, params: OpenAppParams, ctx: RequestContext) -> ToolOutput:
        _require_computer_control()
        _require_display()
        app_id, meta = find_app(params.app, ctx.preferences)
        path = _expand(params.path) if params.path else None
        if path is not None and not path.exists():
            raise NotFoundError(f"'{path}' does not exist.", code="path_not_found")
        if meta.get("special") == "browser":
            ok = await asyncio.to_thread(webbrowser.open, "about:blank" if path is None else path.as_uri())
            if not ok:
                raise ToolExecutionError("No web browser could be opened.", code="launch_failed",
                                         next_step="Set a default browser on your system.")
            return ToolOutput(summary="Opened the web browser", content="The default web browser was opened.")
        argv = resolve_launch(meta)
        if argv is None:
            raise ToolExecutionError(
                f"{meta['name']} could not be opened because the executable was not found.",
                code="executable_not_found",
                reason=f"None of {[c[0] for c in meta.get(PLATFORM, [])] or ['(no launcher for this OS)']} is installed or on PATH.",
                next_step=f"Install {meta['name']}, or register its executable in Settings → Applications.",
            )
        if path is not None and meta.get("accepts_path"):
            argv.append(str(path))
        elif meta.get("default_arg") and path is None:
            argv.append(str(_expand(meta["default_arg"])))
        await _spawn(argv, meta["name"])
        where = f" with {path}" if path else ""
        return ToolOutput(summary=f"Opened {meta['name']}{where}", content=f"Launched {meta['name']}{where}.",
                          data={"app": app_id, "path": str(path) if path else None})


class OpenPathParams(ToolParams):
    path: str = Field(min_length=1, max_length=1000)


class OpenPathTool(Tool):
    name = "open_path"
    description = "Open a folder (file manager) or a document with its default application. Programs are never run."
    Params = OpenPathParams
    category = "computer"
    timeout_seconds = 20

    async def available(self, ctx: RequestContext) -> tuple[bool, str | None]:
        if not get_settings().computer_control:
            return False, "Computer control is disabled on this server."
        return True, None

    def assess(self, params: OpenPathParams, ctx: RequestContext) -> Assessment:
        path = _expand(params.path)
        _check_openable(path)
        return Assessment(_classify_path(path, ctx), f"Open {path}", scope=str(path.parent) + "/",
                          details={"path": str(path)})

    async def run(self, params: OpenPathParams, ctx: RequestContext) -> ToolOutput:
        _require_computer_control()
        _require_display()
        path = _expand(params.path)
        if not path.exists():
            raise NotFoundError(f"'{path}' does not exist.", code="path_not_found", next_step="Check the path.")
        _check_openable(path)
        if PLATFORM == "win32":
            await asyncio.to_thread(os.startfile, str(path))  # type: ignore[attr-defined]
        else:
            opener = "open" if PLATFORM == "darwin" else "xdg-open"
            if not shutil.which(opener):
                raise ToolExecutionError(f"'{opener}' is not available to open files.", code="executable_not_found")
            await _spawn([opener, str(path)], "The file manager")
        return ToolOutput(summary=f"Opened {path.name or path}", content=f"Opened {path}.", data={"path": str(path)})


class OpenUrlParams(ToolParams):
    url: str = Field(max_length=2048)


class OpenUrlTool(Tool):
    name = "open_url"
    description = "Open a web page in the user's default browser."
    Params = OpenUrlParams
    category = "computer"

    async def available(self, ctx: RequestContext) -> tuple[bool, str | None]:
        if not get_settings().computer_control:
            return False, "Computer control is disabled on this server."
        return True, None

    def assess(self, params: OpenUrlParams, ctx: RequestContext) -> Assessment:
        validate_url_syntax(params.url)
        return Assessment(RiskLevel.LOW, f"Open {params.url[:80]} in the browser")

    async def run(self, params: OpenUrlParams, ctx: RequestContext) -> ToolOutput:
        _require_computer_control()
        _require_display()
        validate_url_syntax(params.url)
        ok = await asyncio.to_thread(webbrowser.open, params.url)
        if not ok:
            raise ToolExecutionError("No web browser could be opened.", code="launch_failed")
        return ToolOutput(summary=f"Opened {params.url[:70]}", content=f"Opened {params.url} in the browser.",
                          data={"url": params.url})


class RunCommandParams(ToolParams):
    command: str = Field(min_length=1, max_length=500, description="One allowlisted command, e.g. 'npm test'")
    cwd: str | None = Field(default=None, max_length=1000,
                            description="Working directory inside an authorised workspace folder")
    timeout_seconds: int = Field(default=180, ge=5, le=900)


class RunCommandTool(Tool):
    name = "run_command"
    description = ("Run ONE allowlisted development command (npm/pnpm/yarn scripts, pytest, python/node scripts, "
                   "cargo/go build & test, make, read-only git) in an authorised project folder. No shell "
                   "operators. Returns exit code and output.")
    Params = RunCommandParams
    category = "computer"
    timeout_seconds = 960

    async def available(self, ctx: RequestContext) -> tuple[bool, str | None]:
        if not get_settings().computer_control:
            return False, "Command execution is disabled on this server."
        return True, None

    def _cwd(self, params: RunCommandParams, ctx: RequestContext) -> Path:
        roots = ctx.workspace_roots
        target = params.cwd or (str(roots[0]) if roots else ".")
        cwd = resolve_within(target, roots, must_exist=True)
        if not cwd.is_dir():
            raise SecurityViolationError(f"'{cwd}' is not a folder.", code="invalid_cwd")
        return cwd

    def assess(self, params: RunCommandParams, ctx: RequestContext) -> Assessment:
        cmd = validate_command(params.command)
        cwd = self._cwd(params, ctx)
        check_path_args(cmd, cwd, ctx.workspace_roots)
        return Assessment(cmd.risk, f"Run `{cmd.display}` in {cwd.name}", scope=f"{cmd.argv[0]} {cmd.argv[1] if len(cmd.argv) > 1 else ''}@{cwd}",
                          details={"command": cmd.display, "cwd": str(cwd), "purpose": cmd.description})

    async def run(self, params: RunCommandParams, ctx: RequestContext) -> ToolOutput:
        _require_computer_control()
        cmd = validate_command(params.command)
        cwd = self._cwd(params, ctx)
        check_path_args(cmd, cwd, ctx.workspace_roots)
        result = await run_validated(cmd, cwd, timeout=params.timeout_seconds)
        status = "timed out" if result.timed_out else f"exit code {result.exit_code}"
        from app.security.prompt_injection import wrap_untrusted

        return ToolOutput(
            summary=f"`{cmd.display}` finished ({status})",
            content=f"Command: {cmd.display}\nWorking directory: {cwd}\nResult: {status}\n\n"
                    + wrap_untrusted(result.output or "(no output)", source="command_output", max_chars=21000),
            data={"command": cmd.display, "exit_code": result.exit_code, "timed_out": result.timed_out},
        )


class ScreenshotTool(Tool):
    name = "take_screenshot"
    description = ("Capture ONE screenshot of the host computer's screen (requires the user's approval every time). "
                   "Returns a file id that can be analysed by vision.")
    Params = NoParams
    risk = RiskLevel.MEDIUM
    allow_always = False
    category = "computer"

    async def available(self, ctx: RequestContext) -> tuple[bool, str | None]:
        if not get_settings().computer_control:
            return False, "Computer control is disabled on this server."
        try:
            import mss  # noqa: F401
        except ImportError:
            return False, "Screenshot support is not installed (pip install mss)."
        if not telemetry.has_display():
            return False, "The NEXUS backend has no display to capture (running headless)."
        return True, None

    def assess(self, params: NoParams, ctx: RequestContext) -> Assessment:
        return Assessment(RiskLevel.MEDIUM, "Take one screenshot of your screen", scope="screen",
                          details={"note": "A single image is captured and stored privately in your Files."})

    async def run(self, params: NoParams, ctx: RequestContext) -> ToolOutput:
        _require_computer_control()

        def _grab() -> bytes:
            import mss
            import mss.tools
            from PIL import Image

            with mss.mss() as sct:
                shot = sct.grab(sct.monitors[1])
                img = Image.frombytes("RGB", shot.size, shot.rgb)
            img.thumbnail((1920, 1920))
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            return buf.getvalue()

        try:
            data = await asyncio.to_thread(_grab)
        except Exception as exc:
            raise ToolExecutionError("The screenshot could not be captured.", code="screenshot_failed",
                                     reason=str(exc)[:200]) from exc
        from app.services import files as file_service

        name = f"screenshot-{datetime.now():%Y%m%d-%H%M%S}.png"
        row = await file_service.store_upload(ctx.user.id, name, data)
        return ToolOutput(summary="Captured a screenshot", content=f"Screenshot saved as file id {row.id} ({name}).",
                          data={"file_id": str(row.id), "filename": name})


class DeletePathParams(ToolParams):
    path: str = Field(min_length=1, max_length=1000)


class DeletePathTool(Tool):
    name = "delete_path"
    description = ("Delete a file or folder inside an authorised workspace folder. HIGH RISK: always requires "
                   "explicit confirmation. Items are moved to NEXUS's trash so they can be recovered.")
    Params = DeletePathParams
    risk = RiskLevel.HIGH
    allow_always = False
    category = "computer"

    async def available(self, ctx: RequestContext) -> tuple[bool, str | None]:
        if not get_settings().computer_control:
            return False, "Computer control is disabled on this server."
        return True, None

    def assess(self, params: DeletePathParams, ctx: RequestContext) -> Assessment:
        path = resolve_within(params.path, ctx.workspace_roots, must_exist=True)
        if any(path == r for r in ctx.workspace_roots):
            raise SecurityViolationError("NEXUS won't delete an entire workspace folder.", code="delete_root_blocked")
        kind = "folder" if path.is_dir() else "file"
        return Assessment(RiskLevel.HIGH, f"Delete {kind} {path}", scope=str(path), details={"path": str(path), "type": kind})

    async def run(self, params: DeletePathParams, ctx: RequestContext) -> ToolOutput:
        _require_computer_control()
        path = resolve_within(params.path, ctx.workspace_roots, must_exist=True)
        trash = get_settings().nexus_data_dir / "trash" / datetime.now().strftime("%Y%m%d-%H%M%S")
        trash.mkdir(parents=True, exist_ok=True)
        dest = trash / path.name
        try:
            await asyncio.to_thread(shutil.move, str(path), str(dest))
        except OSError as exc:
            raise ToolExecutionError(f"Could not delete {path.name}.", code="delete_failed", reason=str(exc)[:200]) from exc
        if path.exists():
            raise ToolExecutionError(f"{path.name} still exists after deletion.", code="delete_unverified")
        return ToolOutput(summary=f"Deleted {path.name} (moved to NEXUS trash)",
                          content=f"Moved {path} to {dest}. It can be restored from there.",
                          data={"path": str(path), "trash": str(dest)})


class ListApplicationsTool(Tool):
    name = "list_applications"
    description = "List applications NEXUS is allowed to open on this computer and whether each is installed."
    Params = NoParams
    category = "computer"

    def describe_call(self, params) -> str:
        return "Checking available applications"

    async def run(self, params: NoParams, ctx: RequestContext) -> ToolOutput:
        apps = list_apps(ctx.preferences)
        lines = [f"- {a['name']} ({a['id']}): {'installed' if a['installed'] else 'not found'}" for a in apps]
        return ToolOutput(summary=f"{sum(a['installed'] for a in apps)} apps available", content="\n".join(lines),
                          data={"count": len(apps)})


def list_apps(prefs: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for app_id, meta in {**APP_CATALOG, **custom_apps(prefs)}.items():
        installed = meta.get("special") == "browser" or resolve_launch(meta) is not None
        out.append({"id": app_id, "name": meta["name"], "installed": installed, "custom": bool(meta.get("custom")),
                    "accepts_path": bool(meta.get("accepts_path"))})
    return out


class SystemStatusTool(Tool):
    name = "get_system_status"
    description = "Get real CPU, memory, disk, battery and network status of the computer running NEXUS."
    Params = NoParams
    category = "computer"

    def describe_call(self, params) -> str:
        return "Reading system status"

    async def run(self, params: NoParams, ctx: RequestContext) -> ToolOutput:
        snap = await asyncio.to_thread(telemetry.snapshot)
        import json

        return ToolOutput(summary="Read system status", content=json.dumps(snap, indent=1),
                          data={"host": snap["host"]})


def platform_name() -> str:
    return platform.system()


__all__ = [
    "DeletePathTool", "ListApplicationsTool", "OpenApplicationTool", "OpenPathTool", "OpenUrlTool", "RunCommandTool",
    "ScreenshotTool", "SystemStatusTool", "NexusError", "list_apps",
]
