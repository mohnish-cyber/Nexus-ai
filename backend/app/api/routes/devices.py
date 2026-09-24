"""Devices: the host running NEXUS (real telemetry) and client devices that connected."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import current_user
from app.config import get_settings
from app.core.errors import NotFoundError
from app.database.session import session_scope
from app.models import Device
from app.models.base import utcnow
from app.security.auth import CurrentUser
from app.services import telemetry

router = APIRouter(prefix="/api/devices", tags=["devices"])


def device_to_dict(d: Device) -> dict[str, Any]:
    return {"id": str(d.id), "name": d.name, "kind": d.kind, "platform": d.platform, "capabilities": d.capabilities,
            "last_seen_at": d.last_seen_at.isoformat() if d.last_seen_at else None, "created_at": d.created_at.isoformat()}


@router.get("")
async def list_devices(user: CurrentUser = Depends(current_user)) -> dict[str, Any]:
    snap = await asyncio.to_thread(telemetry.snapshot)
    s = get_settings()
    async with session_scope() as db:
        rows = (await db.execute(select(Device).where(Device.user_id == user.id)
                                 .order_by(Device.last_seen_at.desc()))).scalars().all()
    return {
        "host": {
            "name": snap["host"], "os": snap["os"], "display": snap["display"],
            "capabilities": {
                "computer_control": s.computer_control,
                "screenshots": s.computer_control and snap["display"],
                "open_apps": s.computer_control and snap["display"],
                "commands": s.computer_control,
            },
        },
        "clients": [device_to_dict(d) for d in rows],
    }


class HeartbeatBody(BaseModel):
    fingerprint: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=120)
    kind: str = Field(default="browser", pattern=r"^(browser|phone|desktop)$")
    platform: str | None = Field(default=None, max_length=120)
    capabilities: dict[str, bool] = Field(default_factory=dict)


@router.post("/heartbeat")
async def heartbeat(body: HeartbeatBody, request: Request, user: CurrentUser = Depends(current_user)) -> dict[str, Any]:
    caps = {k[:40]: bool(v) for k, v in list(body.capabilities.items())[:20]}
    async with session_scope() as db:
        row = (await db.execute(select(Device).where(Device.user_id == user.id,
                                                     Device.fingerprint == body.fingerprint))).scalar_one_or_none()
        if row is None:
            row = Device(user_id=user.id, fingerprint=body.fingerprint, name=body.name, kind=body.kind,
                         platform=body.platform, capabilities=caps, last_seen_at=utcnow())
            db.add(row)
        else:
            row.name, row.platform, row.capabilities, row.last_seen_at = body.name, body.platform, caps, utcnow()
        await db.flush()
        return device_to_dict(row)


@router.delete("/{device_id}", status_code=204)
async def remove(device_id: uuid.UUID, user: CurrentUser = Depends(current_user)) -> None:
    async with session_scope() as db:
        row = await db.get(Device, device_id)
        if row is None or row.user_id != user.id:
            raise NotFoundError("That device was not found.", code="device_not_found")
        await db.delete(row)
