"""Command execution allowlist.

NEXUS never runs a shell and never executes arbitrary strings. A requested
command is tokenised, matched against an explicit allowlist of development
commands, assigned a risk level, and executed with `create_subprocess_exec`
(no shell), inside an authorised workspace folder, with a sanitised
environment, a timeout and an output cap.
"""

from __future__ import annotations

import asyncio
import os
import re
import shlex
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.core.errors import SecurityViolationError, ToolExecutionError
from app.security.risk import RiskLevel

_META_RE = re.compile(r"[;&|`$<>\n\r]|\$\(")
_SCRIPT_RE = re.compile(r"^[A-Za-z0-9:_\-.]{1,64}$")
_SAFE_FLAG_RE = re.compile(r"^--?[A-Za-z0-9][A-Za-z0-9_\-]*(=[A-Za-z0-9_\-./:,]*)?$")
_SAFE_ARG_RE = re.compile(r"^[A-Za-z0-9_\-./:,@=+\[\]]{1,200}$")

# Environment variables that must never leak into child processes.
_SECRET_ENV_MARKERS = ("KEY", "SECRET", "TOKEN", "PASSWORD", "PASSWD", "CREDENTIAL", "DATABASE_URL")


@dataclass(frozen=True)
class CommandRule:
    program: str
    description: str
    risk: RiskLevel
    matcher: Callable[[list[str]], bool]


@dataclass
class ValidatedCommand:
    argv: list[str]
    display: str
    risk: RiskLevel
    description: str


def _args_safe(args: list[str]) -> bool:
    return all(_SAFE_FLAG_RE.match(a) or _SAFE_ARG_RE.match(a) for a in args)


def _npm_like(args: list[str]) -> bool:
    if not args:
        return False
    if args[0] == "test" and _args_safe(args[1:]):
        return True
    if args[0] == "run" and len(args) >= 2 and _SCRIPT_RE.match(args[1]) and _args_safe(args[2:]):
        return True
    return args == ["start"] or args == ["run"]


def _npm_install(args: list[str]) -> bool:
    return args in (["install"], ["ci"], ["i"])


def _git_readonly(args: list[str]) -> bool:
    return bool(args) and args[0] in {"status", "diff", "log", "branch", "show", "remote"} and _args_safe(args[1:])


def _pytest(args: list[str]) -> bool:
    return _args_safe(args)


def _python(args: list[str]) -> bool:
    if args[:2] == ["-m", "pytest"]:
        return _args_safe(args[2:])
    if args[:2] in (["-m", "unittest"], ["-m", "mypy"], ["-m", "ruff"]):
        return _args_safe(args[2:])
    # python path/to/script.py [args]  (script must be inside the workspace)
    return bool(args) and args[0].endswith(".py") and _args_safe(args)


def _node(args: list[str]) -> bool:
    return bool(args) and args[0].endswith((".js", ".mjs", ".cjs")) and _args_safe(args)


def _cargo_go(args: list[str]) -> bool:
    return bool(args) and args[0] in {"test", "build", "run", "check", "vet"} and _args_safe(args[1:])


def _make(args: list[str]) -> bool:
    return len(args) <= 2 and all(_SCRIPT_RE.match(a) for a in args)


def _tsc_eslint(args: list[str]) -> bool:
    return _args_safe(args)


RULES: list[CommandRule] = [
    CommandRule("npm", "Run an npm project script", RiskLevel.MEDIUM, _npm_like),
    CommandRule("pnpm", "Run a pnpm project script", RiskLevel.MEDIUM, _npm_like),
    CommandRule("yarn", "Run a yarn project script", RiskLevel.MEDIUM, lambda a: _npm_like(a) or (len(a) == 1 and bool(_SCRIPT_RE.match(a[0])))),
    CommandRule("npm", "Install project dependencies", RiskLevel.HIGH, _npm_install),
    CommandRule("pnpm", "Install project dependencies", RiskLevel.HIGH, _npm_install),
    CommandRule("git", "Read git repository state", RiskLevel.LOW, _git_readonly),
    CommandRule("pytest", "Run Python tests", RiskLevel.MEDIUM, _pytest),
    CommandRule("python", "Run Python in the project", RiskLevel.MEDIUM, _python),
    CommandRule("python3", "Run Python in the project", RiskLevel.MEDIUM, _python),
    CommandRule("node", "Run a Node.js script in the project", RiskLevel.MEDIUM, _node),
    CommandRule("cargo", "Build or test a Rust project", RiskLevel.MEDIUM, _cargo_go),
    CommandRule("go", "Build or test a Go project", RiskLevel.MEDIUM, _cargo_go),
    CommandRule("make", "Run a make target", RiskLevel.MEDIUM, _make),
    CommandRule("npx", "Run a project-local tool (tsc/eslint/vitest)", RiskLevel.MEDIUM,
                lambda a: bool(a) and a[0] in {"tsc", "eslint", "vitest", "jest", "prettier"} and _args_safe(a[1:])),
]


def allowed_command_summaries() -> list[dict[str, str]]:
    return [{"program": r.program, "description": r.description, "risk": r.risk.value} for r in RULES]


def validate_command(command: str | list[str]) -> ValidatedCommand:
    """Tokenise and validate a command against the allowlist."""
    if isinstance(command, str):
        if len(command) > 500:
            raise SecurityViolationError("That command is too long.", code="command_rejected")
        if _META_RE.search(command):
            raise SecurityViolationError(
                "Shell operators (;, &&, |, >, $(), backticks) are not allowed.",
                code="command_rejected",
                reason="NEXUS runs single allowlisted commands without a shell to prevent command injection.",
                next_step="Ask for one command at a time.",
            )
        try:
            argv = shlex.split(command, posix=True)
        except ValueError as exc:
            raise SecurityViolationError("Could not parse that command.", code="command_rejected") from exc
    else:
        argv = list(command)
        if any(_META_RE.search(a) for a in argv):
            raise SecurityViolationError("Shell operators are not allowed.", code="command_rejected")
    if not argv:
        raise SecurityViolationError("No command given.", code="command_rejected")
    program = Path(argv[0]).name.lower()
    if program.endswith((".exe", ".cmd", ".bat")):
        program = program.rsplit(".", 1)[0]
    args = argv[1:]
    for rule in RULES:
        if rule.program == program and rule.matcher(args):
            return ValidatedCommand(
                argv=[program, *args], display=shlex.join([program, *args]), risk=rule.risk, description=rule.description
            )
    raise SecurityViolationError(
        f"'{shlex.join(argv)[:120]}' is not on the approved command list.",
        code="command_not_allowed",
        reason="Only known development commands (tests, builds, project scripts, read-only git) may run.",
        next_step="Run it yourself in a terminal, or ask for an approved alternative such as 'npm test'.",
    )


def check_path_args(cmd: ValidatedCommand, cwd: Path, roots: list[Path]) -> None:
    """Ensure every path-like argument stays inside the authorised roots."""
    from app.security.paths import resolve_within

    for arg in cmd.argv[1:]:
        if arg.startswith("-"):
            if "=" in arg:
                arg = arg.split("=", 1)[1]
            else:
                continue
        if "/" in arg or "\\" in arg or arg.startswith(".") or re.search(r"\.(py|js|mjs|cjs|ts)$", arg):
            candidate = arg if Path(arg).is_absolute() else str(cwd / arg)
            resolve_within(candidate, roots)


def sanitized_env() -> dict[str, str]:
    env = {}
    for k, v in os.environ.items():
        upper = k.upper()
        if any(marker in upper for marker in _SECRET_ENV_MARKERS):
            continue
        env[k] = v
    env["NEXUS_CHILD_PROCESS"] = "1"
    return env


@dataclass
class CommandOutput:
    exit_code: int
    output: str
    truncated: bool
    timed_out: bool


async def run_validated(cmd: ValidatedCommand, cwd: Path, *, timeout: float = 180.0, max_chars: int = 20000) -> CommandOutput:
    executable = shutil.which(cmd.argv[0])
    if cmd.argv[0] in ("python", "python3") and executable is None:
        executable = sys.executable
    if executable is None:
        raise ToolExecutionError(
            f"'{cmd.argv[0]}' is not installed or not on PATH.",
            code="executable_not_found",
            reason=f"The executable '{cmd.argv[0]}' could not be found.",
            next_step=f"Install {cmd.argv[0]} or add it to your PATH, then try again.",
        )
    proc = await asyncio.create_subprocess_exec(
        executable,
        *cmd.argv[1:],
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        stdin=asyncio.subprocess.DEVNULL,
        env=sanitized_env(),
    )
    timed_out = False
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        timed_out = True
        proc.kill()
        stdout, _ = await proc.communicate()
    text = (stdout or b"").decode("utf-8", errors="replace")
    truncated = len(text) > max_chars
    if truncated:
        # Keep the tail: errors and test summaries are usually at the end.
        text = "…[output truncated]…\n" + text[-max_chars:]
    return CommandOutput(exit_code=proc.returncode if proc.returncode is not None else -1, output=text,
                         truncated=truncated, timed_out=timed_out)
