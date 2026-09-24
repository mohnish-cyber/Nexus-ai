"""Project/code tools used by CodingAgent. All paths are confined to the
authorised workspace folders; writes need approval and keep a backup."""

from __future__ import annotations

import asyncio
import difflib
import fnmatch
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

from pydantic import Field

from app.config import get_settings
from app.core.context import RequestContext
from app.core.errors import NotFoundError, SecurityViolationError, ToolExecutionError, ValidationFailedError
from app.security.paths import is_sensitive_path, resolve_within
from app.security.prompt_injection import wrap_untrusted
from app.security.risk import RiskLevel
from app.tools.base import Assessment, Tool, ToolOutput, ToolParams

_IGNORED_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next", ".cache",
                 ".mypy_cache", ".pytest_cache", "target", ".idea", ".vscode", "coverage", ".turbo"}
MAX_READ_BYTES = 400_000
MAX_WRITE_BYTES = 1_000_000


def _roots(ctx: RequestContext) -> list[Path]:
    return ctx.workspace_roots


def _rel(path: Path, ctx: RequestContext) -> str:
    for r in _roots(ctx):
        try:
            return str(path.relative_to(r)) or "."
        except ValueError:
            continue
    return str(path)


def _is_binary(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            return b"\x00" in fh.read(4096)
    except OSError:
        return True


class ListDirParams(ToolParams):
    path: str = Field(default=".", max_length=1000, description="Folder inside a workspace (relative or absolute)")
    depth: int = Field(default=2, ge=1, le=5)


class ListDirectoryTool(Tool):
    name = "list_directory"
    description = "Show the file tree of a project folder (ignores node_modules, .git, build output...)."
    Params = ListDirParams
    category = "code"

    def describe_call(self, params: ListDirParams) -> str:
        return f"Inspecting {params.path}"

    async def run(self, params: ListDirParams, ctx: RequestContext) -> ToolOutput:
        root = resolve_within(params.path, _roots(ctx), must_exist=True)
        if not root.is_dir():
            raise ValidationFailedError(f"'{params.path}' is not a folder.", code="not_a_directory")

        def walk() -> list[str]:
            lines: list[str] = []
            base_depth = len(root.parts)
            for dirpath, dirnames, filenames in os.walk(root):
                d = Path(dirpath)
                depth = len(d.parts) - base_depth
                dirnames[:] = sorted(n for n in dirnames if n not in _IGNORED_DIRS and not n.startswith("."))
                if depth >= params.depth:
                    dirnames[:] = []
                indent = "  " * depth
                if depth > 0:
                    lines.append(f"{indent[:-2]}{d.name}/")
                for f in sorted(filenames)[:200]:
                    if not is_sensitive_path(d / f):
                        lines.append(f"{indent}{f}")
                if len(lines) > 800:
                    lines.append("… (truncated)")
                    break
            return lines

        lines = await asyncio.to_thread(walk)
        return ToolOutput(summary=f"Listed {_rel(root, ctx)}", content=f"{root}\n" + "\n".join(lines),
                          data={"path": str(root), "entries": len(lines)})


class ReadFileParams(ToolParams):
    path: str = Field(max_length=1000)
    start_line: int = Field(default=1, ge=1)
    end_line: int | None = Field(default=None, ge=1)


class ReadTextFileTool(Tool):
    name = "read_text_file"
    description = "Read a text/source file in an authorised workspace folder, with line numbers."
    Params = ReadFileParams
    category = "code"

    def describe_call(self, params: ReadFileParams) -> str:
        return f"Reading {Path(params.path).name}"

    async def run(self, params: ReadFileParams, ctx: RequestContext) -> ToolOutput:
        path = resolve_within(params.path, _roots(ctx), must_exist=True)
        if not path.is_file():
            raise ValidationFailedError(f"'{params.path}' is not a file.", code="not_a_file")
        if path.stat().st_size > MAX_READ_BYTES * 5 or _is_binary(path):
            raise ValidationFailedError(f"'{path.name}' is binary or too large to read.", code="file_unreadable")
        text = await asyncio.to_thread(path.read_text, encoding="utf-8", errors="replace")
        lines = text.splitlines()
        end = min(params.end_line or len(lines), len(lines), params.start_line + 1500)
        numbered = "\n".join(f"{i:5d}| {lines[i - 1]}" for i in range(params.start_line, end + 1))
        more = f"\n… {len(lines) - end} more lines" if end < len(lines) else ""
        return ToolOutput(summary=f"Read {_rel(path, ctx)}",
                          content=wrap_untrusted(f"{path} (lines {params.start_line}-{end} of {len(lines)})\n{numbered}{more}",
                                                 source=str(path), max_chars=120000),
                          data={"path": str(path), "lines": len(lines)})


class SearchCodeParams(ToolParams):
    query: str = Field(min_length=1, max_length=200, description="Text or regular expression to find")
    path: str = Field(default=".", max_length=1000)
    glob: str | None = Field(default=None, max_length=100, description="e.g. '*.py'")
    regex: bool = False
    max_results: int = Field(default=50, ge=1, le=200)


class SearchCodeTool(Tool):
    name = "search_code"
    description = "Search for text (or a regex) across files in a project folder. Returns file:line matches."
    Params = SearchCodeParams
    category = "code"

    def describe_call(self, params: SearchCodeParams) -> str:
        return f"Searching code for “{params.query[:40]}”"

    async def run(self, params: SearchCodeParams, ctx: RequestContext) -> ToolOutput:
        root = resolve_within(params.path, _roots(ctx), must_exist=True)
        try:
            pattern = re.compile(params.query if params.regex else re.escape(params.query), re.IGNORECASE)
        except re.error as exc:
            raise ValidationFailedError(f"Invalid regular expression: {exc}", code="invalid_regex") from exc

        def scan() -> list[str]:
            hits: list[str] = []
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [n for n in dirnames if n not in _IGNORED_DIRS and not n.startswith(".")]
                for f in filenames:
                    if params.glob and not fnmatch.fnmatch(f, params.glob):
                        continue
                    p = Path(dirpath) / f
                    if is_sensitive_path(p):
                        continue
                    try:
                        if p.stat().st_size > MAX_READ_BYTES or _is_binary(p):
                            continue
                        with p.open(encoding="utf-8", errors="replace") as fh:
                            for i, line in enumerate(fh, 1):
                                if pattern.search(line):
                                    hits.append(f"{p.relative_to(root)}:{i}: {line.strip()[:200]}")
                                    if len(hits) >= params.max_results:
                                        return hits
                    except OSError:
                        continue
            return hits

        hits = await asyncio.to_thread(scan)
        return ToolOutput(summary=f"{len(hits)} matches for “{params.query[:40]}”",
                          content=wrap_untrusted("\n".join(hits) or "No matches.", source=str(root)),
                          data={"matches": len(hits)})


def _diff(old: str, new: str, name: str) -> str:
    diff = difflib.unified_diff(old.splitlines(), new.splitlines(), fromfile=f"a/{name}", tofile=f"b/{name}",
                                lineterm="", n=2)
    text = "\n".join(diff)
    return text if len(text) < 12000 else text[:12000] + "\n… (diff truncated)"


def _backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    backups = get_settings().nexus_data_dir / "backups" / datetime.now().strftime("%Y%m%d")
    backups.mkdir(parents=True, exist_ok=True)
    dest = backups / f"{datetime.now():%H%M%S}-{path.name}"
    shutil.copy2(path, dest)
    return dest


class WriteFileParams(ToolParams):
    path: str = Field(max_length=1000)
    content: str = Field(max_length=MAX_WRITE_BYTES)


class WriteFileTool(Tool):
    name = "write_file"
    description = ("Create or overwrite a text file inside an authorised workspace folder. Requires approval; the "
                   "user sees the diff. Prefer edit_file for small changes to existing files.")
    Params = WriteFileParams
    risk = RiskLevel.MEDIUM
    category = "code"

    def assess(self, params: WriteFileParams, ctx: RequestContext) -> Assessment:
        path = resolve_within(params.path, _roots(ctx))
        old = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
        verb = "Overwrite" if path.exists() else "Create"
        return Assessment(RiskLevel.MEDIUM, f"{verb} {_rel(path, ctx)}", scope=str(path.parent) + "/",
                          details={"path": str(path), "diff": _diff(old, params.content, path.name)})

    async def run(self, params: WriteFileParams, ctx: RequestContext) -> ToolOutput:
        path = resolve_within(params.path, _roots(ctx))
        if path.exists() and not path.is_file():
            raise ValidationFailedError(f"'{path}' is a folder.", code="not_a_file")
        backup = await asyncio.to_thread(_backup, path)
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_text, params.content, encoding="utf-8")
        if path.read_text(encoding="utf-8") != params.content:
            raise ToolExecutionError(f"Verification failed: {path.name} does not contain the new content.",
                                     code="write_unverified")
        return ToolOutput(summary=f"Wrote {_rel(path, ctx)}",
                          content=f"Wrote {len(params.content)} characters to {path}." + (f" Backup: {backup}" if backup else ""),
                          data={"path": str(path), "backup": str(backup) if backup else None})


class EditFileParams(ToolParams):
    path: str = Field(max_length=1000)
    old_text: str = Field(min_length=1, max_length=200000, description="Exact existing text to replace (must be unique)")
    new_text: str = Field(max_length=200000)


class EditFileTool(Tool):
    name = "edit_file"
    description = ("Replace one exact, unique snippet in an existing file (minimal, targeted edit). Requires "
                   "approval; the user sees the diff; a backup is kept.")
    Params = EditFileParams
    risk = RiskLevel.MEDIUM
    category = "code"

    def _apply(self, params: EditFileParams, ctx: RequestContext) -> tuple[Path, str, str]:
        path = resolve_within(params.path, _roots(ctx), must_exist=True)
        if not path.is_file():
            raise ValidationFailedError(f"'{path}' is not a file.", code="not_a_file")
        old = path.read_text(encoding="utf-8", errors="replace")
        count = old.count(params.old_text)
        if count == 0:
            raise NotFoundError(f"The text to replace was not found in {path.name}.", code="edit_no_match",
                                next_step="Read the file again and copy the exact text.")
        if count > 1:
            raise ValidationFailedError(f"The text to replace appears {count} times in {path.name}.",
                                        code="edit_ambiguous", next_step="Include more surrounding lines.")
        return path, old, old.replace(params.old_text, params.new_text, 1)

    def assess(self, params: EditFileParams, ctx: RequestContext) -> Assessment:
        path, old, new = self._apply(params, ctx)
        return Assessment(RiskLevel.MEDIUM, f"Edit {_rel(path, ctx)}", scope=str(path.parent) + "/",
                          details={"path": str(path), "diff": _diff(old, new, path.name)})

    async def run(self, params: EditFileParams, ctx: RequestContext) -> ToolOutput:
        path, old, new = self._apply(params, ctx)
        backup = await asyncio.to_thread(_backup, path)
        await asyncio.to_thread(path.write_text, new, encoding="utf-8")
        if path.read_text(encoding="utf-8") != new:
            raise ToolExecutionError(f"Verification failed after editing {path.name}.", code="write_unverified")
        return ToolOutput(summary=f"Edited {_rel(path, ctx)}",
                          content=f"Applied edit to {path}.\n{_diff(old, new, path.name)}",
                          data={"path": str(path), "backup": str(backup) if backup else None})


def ensure_roots(ctx: RequestContext) -> None:
    if not _roots(ctx):
        raise SecurityViolationError(
            "No project folders are authorised yet.",
            code="no_workspace_roots",
            next_step="Add your projects folder in Settings → Workspace folders.",
        )
