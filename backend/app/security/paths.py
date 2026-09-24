"""Path traversal protection.

Every filesystem path that originates from user input or model output is
resolved (following symlinks) and must end up inside one of the explicitly
authorised roots.
"""

from __future__ import annotations

import os
import re
import unicodedata
from collections.abc import Iterable
from pathlib import Path

from app.core.errors import SecurityViolationError

# Files NEXUS never reads or modifies, even inside an authorised root.
_SENSITIVE_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
    ".netrc",
    ".pgpass",
    "credentials",
    ".git-credentials",
    ".npmrc",
    ".pypirc",
    ".secret_key",
}
_SENSITIVE_DIRS = {".ssh", ".gnupg", ".aws", ".kube", ".docker"}
_SENSITIVE_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".kdbx")


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def is_sensitive_path(path: Path) -> bool:
    name = path.name.lower()
    if name in _SENSITIVE_NAMES or name.startswith(".env."):
        return True
    if name.endswith(_SENSITIVE_SUFFIXES):
        return True
    return any(part.lower() in _SENSITIVE_DIRS for part in path.parts)


def resolve_within(user_path: str | os.PathLike[str], roots: Iterable[Path], *, must_exist: bool = False) -> Path:
    """Resolve `user_path` and ensure it is inside one of `roots`.

    Relative paths are resolved against the first root. Raises
    SecurityViolationError when the path escapes every root or targets a
    sensitive credential file.
    """
    roots = [Path(r).expanduser().resolve() for r in roots]
    if not roots:
        raise SecurityViolationError(
            "No folders are authorised for file access yet.",
            code="no_workspace_roots",
            reason="NEXUS only touches files inside folders you explicitly allow.",
            next_step="Add a folder under Settings → Workspace folders (or WORKSPACE_ROOTS in .env).",
        )
    raw = str(user_path)
    if "\x00" in raw:
        raise SecurityViolationError("Invalid path.", code="invalid_path", reason="Path contains a NUL byte.")
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = roots[0] / candidate
    resolved = candidate.resolve(strict=False)
    if not any(is_within(resolved, root) for root in roots):
        raise SecurityViolationError(
            f"Access to '{raw}' is outside the folders NEXUS is allowed to use.",
            code="path_outside_workspace",
            reason="The path resolves outside every authorised workspace folder.",
            next_step="Add the folder in Settings → Workspace folders if you want NEXUS to access it.",
        )
    if is_sensitive_path(resolved):
        raise SecurityViolationError(
            f"'{resolved.name}' looks like a credential or key file, so NEXUS will not access it.",
            code="sensitive_path",
            reason="Credential files are blocked to protect your secrets.",
        )
    if must_exist and not resolved.exists():
        raise SecurityViolationError(
            f"'{raw}' does not exist.", code="path_not_found", next_step="Check the path and try again."
        )
    return resolved


_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._() \-]+")


def sanitize_filename(name: str, *, max_length: int = 180) -> str:
    """Return a display-safe file name (never used as a storage path)."""
    name = unicodedata.normalize("NFKC", name or "")
    name = name.replace("\\", "/").split("/")[-1]
    name = _SAFE_NAME_RE.sub("_", name).strip(" .")
    if not name:
        name = "file"
    if len(name) > max_length:
        stem, dot, ext = name.rpartition(".")
        if dot and len(ext) <= 10:
            name = stem[: max_length - len(ext) - 1] + "." + ext
        else:
            name = name[:max_length]
    return name
