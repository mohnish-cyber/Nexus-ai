"""Settings: preferences, write-only API keys, workspace folders, apps, data export/erase."""

from __future__ import annotations

import shutil
import sys
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from app.api.deps import admin_user, current_user, host_control_user
from app.config import get_settings
from app.core.errors import ValidationFailedError
from app.database.session import session_scope
from app.models import (
    AgentRun,
    Automation,
    AutomationRun,
    Conversation,
    Device,
    FileChunk,
    Memory,
    Message,
    Notification,
    PermissionGrant,
    PermissionRequest,
    StoredFile,
    Task,
    ToolCall,
    UserPreference,
)
from app.security.auth import CurrentUser
from app.security.commands import allowed_command_summaries
from app.services import files as file_service
from app.services import memory_service as ms
from app.services import secrets as secret_store
from app.services.ai.factory import provider_status
from app.services.audit import audit_event
from app.services.preferences import DEFAULT_PREFERENCES, get_preferences, update_preferences, workspace_roots
from app.tools.computer import list_apps

router = APIRouter(prefix="/api/settings", tags=["settings"])

_FORBIDDEN_ROOTS = {Path("/"), Path("/etc"), Path("/usr"), Path("/bin"), Path("/sbin"), Path("/var"), Path("/boot"),
                    Path("/System"), Path("/Library"), Path("C:/"), Path("C:/Windows"), Path("C:/Program Files")}


@router.get("")
async def get_all(user: CurrentUser = Depends(current_user)) -> dict[str, Any]:
    s = get_settings()
    prefs = await get_preferences(user.id)
    return {
        "preferences": prefs,
        "secrets": await secret_store.secret_status(),
        "ai": {**(await provider_status()), "effort": s.ai_effort_default, "refusal_fallback": s.anthropic_refusal_fallback},
        "workspace_roots": [str(p) for p in workspace_roots(prefs)],
        "env_workspace_roots": [str(p) for p in s.workspace_root_list],
        "computer_control": s.computer_control,
        "can_edit_secrets": user.is_admin,
        "can_edit_host": s.computer_control and (s.auth_mode == "local" or user.is_admin),
        "allowed_commands": allowed_command_summaries(),
        "auth_mode": s.auth_mode,
    }


class SectionBody(BaseModel):
    values: dict[str, Any]


@router.put("/{section}")
async def update_section(section: str, body: SectionBody, request: Request,
                         user: CurrentUser = Depends(current_user)) -> dict[str, Any]:
    if section not in DEFAULT_PREFERENCES:
        raise ValidationFailedError(f"Unknown settings section '{section}'.", code="unknown_section")
    if section in ("workspace", "apps"):
        await host_control_user(user)
    values = _validate_section(section, body.values)
    prefs = await update_preferences(user.id, section, values)
    await audit_event(user.id, "settings_updated", {"section": section, "keys": sorted(values)},
                      ip=request.client.host if request.client else None)
    return prefs


def _validate_section(section: str, values: dict[str, Any]) -> dict[str, Any]:
    if section == "workspace":
        roots = []
        for raw in values.get("roots", [])[:20]:
            p = Path(str(raw)).expanduser().resolve()
            if not p.is_dir():
                raise ValidationFailedError(f"'{raw}' is not an existing folder.", code="invalid_workspace_root")
            if p in _FORBIDDEN_ROOTS or p == Path.home() or len(p.parts) <= 1:
                raise ValidationFailedError(f"'{p}' is too broad to authorise.", code="workspace_root_too_broad",
                                            next_step="Choose a specific projects folder instead.")
            roots.append(str(p))
        return {"roots": roots}
    if section == "apps":
        custom = []
        for app in values.get("custom", [])[:30]:
            app_id = str(app.get("id") or app.get("name") or "").strip().lower().replace(" ", "_")[:40]
            cmd = app.get("command")
            if isinstance(cmd, str):
                cmd = [cmd]
            if not app_id or not isinstance(cmd, list) or not cmd or not all(isinstance(c, str) for c in cmd):
                raise ValidationFailedError("Each app needs a name and an executable.", code="invalid_app")
            exe = cmd[0]
            if not (Path(exe).is_absolute() and Path(exe).exists()) and not shutil.which(exe):
                raise ValidationFailedError(f"Executable '{exe}' was not found.", code="executable_not_found",
                                            next_step="Use the full path to the program.")
            if any(ch in " ".join(cmd) for ch in ";|&`$<>"):
                raise ValidationFailedError("Shell operators are not allowed in app commands.", code="invalid_app")
            custom.append({"id": app_id, "name": str(app.get("name") or app_id)[:60], "command": cmd[:5],
                           "accepts_path": bool(app.get("accepts_path"))})
        return {"custom": custom}
    if section == "voice":
        out = dict(values)
        for key, lo, hi in (("rate", 0.5, 2.0), ("pitch", 0.5, 2.0)):
            if key in out:
                out[key] = min(hi, max(lo, float(out[key])))
        return out
    if section == "regional" and values.get("timezone"):
        from zoneinfo import ZoneInfo

        try:
            ZoneInfo(values["timezone"])
        except Exception as exc:
            raise ValidationFailedError(f"Unknown timezone '{values['timezone']}'.", code="invalid_timezone") from exc
    return values


# --- API keys (write-only) --------------------------------------------------

class SecretBody(BaseModel):
    value: str = Field(min_length=8, max_length=4000)


@router.put("/secrets/{name}")
async def set_secret(name: str, body: SecretBody, request: Request, user: CurrentUser = Depends(admin_user)) -> list[dict[str, Any]]:
    await secret_store.set_secret(name, body.value, user.id)
    await audit_event(user.id, "secret_updated", {"name": name}, ip=request.client.host if request.client else None)
    return await secret_store.secret_status()


@router.delete("/secrets/{name}")
async def delete_secret(name: str, request: Request, user: CurrentUser = Depends(admin_user)) -> list[dict[str, Any]]:
    await secret_store.delete_secret(name)
    await audit_event(user.id, "secret_deleted", {"name": name}, ip=request.client.host if request.client else None)
    return await secret_store.secret_status()


@router.post("/test-ai")
async def test_ai(_: CurrentUser = Depends(current_user)) -> dict[str, Any]:
    return await provider_status(force=True)


@router.get("/apps")
async def apps(user: CurrentUser = Depends(current_user)) -> dict[str, Any]:
    return {"platform": sys.platform, "apps": list_apps(await get_preferences(user.id))}


# --- Data ownership -------------------------------------------------------------

@router.get("/export")
async def export_data(user: CurrentUser = Depends(current_user)) -> dict[str, Any]:
    from app.services import conversation_service as convs
    from app.services import tasks_service
    from app.services.automation_service import automation_to_dict, list_automations

    conversations = []
    for c in await convs.list_conversations(user.id, limit=1000):
        msgs = await convs.get_messages(user.id, uuid.UUID(c["id"]), limit=5000)
        conversations.append({**c, "messages": [convs.message_to_dict(m) for m in msgs]})
    await audit_event(user.id, "data_exported", {})
    return {
        "preferences": await get_preferences(user.id),
        "memories": [ms.memory_to_dict(m) for m in await ms.list_memories(user.id, limit=100000)],
        "tasks": [tasks_service.task_to_dict(t) for t in await tasks_service.list_tasks(user.id, view="all", limit=100000)],
        "automations": [automation_to_dict(a) for a in await list_automations(user.id)],
        "conversations": conversations,
        "files": [{"id": str(f.id), "filename": f.filename, "kind": f.kind} for f in await file_service.list_files(user.id, 10000)],
    }


class EraseBody(BaseModel):
    confirm: str


@router.post("/erase")
async def erase_all(body: EraseBody, request: Request, user: CurrentUser = Depends(current_user)) -> dict[str, Any]:
    """Delete every piece of the user's data. Requires typing ERASE."""
    if body.confirm != "ERASE":
        raise ValidationFailedError("Type ERASE to confirm deleting all your data.", code="confirmation_required")
    for f in await file_service.list_files(user.id, limit=100000):
        await file_service.delete_file(user.id, f.id)
    async with session_scope() as db:
        conv_ids = select(Conversation.id).where(Conversation.user_id == user.id)
        auto_ids = select(Automation.id).where(Automation.user_id == user.id)
        await db.execute(delete(Message).where(Message.conversation_id.in_(conv_ids)))
        await db.execute(delete(AutomationRun).where(AutomationRun.automation_id.in_(auto_ids)))
        for model in (Conversation, Memory, Task, Automation, Notification, AgentRun, ToolCall, PermissionGrant,
                      PermissionRequest, UserPreference, Device, FileChunk, StoredFile):
            await db.execute(delete(model).where(model.user_id == user.id))
    await audit_event(user.id, "data_erased", {}, ip=request.client.host if request.client else None)
    return {"ok": True}
