"""Chat: WebSocket (streaming, interactive approvals) and REST (one-shot)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, ValidationError

from app.api.deps import chat_user
from app.api.middleware import origin_allowed
from app.config import get_settings
from app.core.context import RequestContext
from app.core.errors import ErrorInfo, NexusError
from app.core.nexus_core import ChatRequest, nexus_core
from app.security.auth import CurrentUser, verify_token
from app.security.permissions import Decision, permission_broker
from app.security.rate_limit import rate_limiter
from app.services.notifications import hub
from app.services.preferences import get_preferences

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])

MAX_CONCURRENT_REQUESTS = 3


class ChatBody(BaseModel):
    text: str = Field(default="", max_length=20000)
    conversation_id: uuid.UUID | None = None
    attachments: list[uuid.UUID] = Field(default_factory=list, max_length=10)
    voice: bool = False


@router.post("/api/chat")
async def chat_rest(body: ChatBody, user: CurrentUser = Depends(chat_user)) -> dict[str, Any]:
    """Non-streaming chat. Actions needing approval are declined (use the app/WebSocket to approve)."""
    ctx = RequestContext(user=user, interactive=False, origin="api", preferences=await get_preferences(user.id))
    return await nexus_core.handle(ctx, ChatRequest(body.text, body.conversation_id, body.attachments, body.voice))


class _Connection:
    def __init__(self, ws: WebSocket, user: CurrentUser) -> None:
        self.ws = ws
        self.user = user
        self.lock = asyncio.Lock()
        self.running: dict[str, tuple[asyncio.Task[None], RequestContext]] = {}
        self.closed = False

    async def send(self, event: dict[str, Any]) -> None:
        if self.closed:
            return
        async with self.lock:
            try:
                await self.ws.send_text(json.dumps(event, default=str))
            except Exception:
                self.closed = True

    async def run_chat(self, request_id: str, body: ChatBody) -> None:
        ctx = RequestContext(user=self.user, request_id=request_id, emit_fn=self.send, interactive=True,
                             preferences=await get_preferences(self.user.id))
        task = asyncio.current_task()
        assert task is not None
        self.running[request_id] = (task, ctx)
        try:
            await nexus_core.handle(ctx, ChatRequest(body.text, body.conversation_id, body.attachments, body.voice))
        except asyncio.CancelledError:
            await self.send({"type": "status", "request_id": request_id, "state": "idle", "label": "Stopped"})
        except NexusError as exc:
            await self.send({"type": "error", "request_id": request_id, "error": exc.to_dict()})
            await self.send({"type": "status", "request_id": request_id, "state": "error", "label": exc.message})
        except Exception as exc:
            logger.exception("Chat request %s failed", request_id)
            err = ErrorInfo("internal_error", "NEXUS hit an unexpected error while answering.",
                            reason=exc.__class__.__name__, next_step="Try again. Check the backend logs if it repeats.")
            await self.send({"type": "error", "request_id": request_id, "error": err.to_dict()})
            await self.send({"type": "status", "request_id": request_id, "state": "error", "label": err.message})
        finally:
            self.running.pop(request_id, None)
            await self.send({"type": "done", "request_id": request_id})

    def cancel(self, request_id: str) -> bool:
        entry = self.running.get(request_id)
        if entry is None:
            return False
        task, ctx = entry
        ctx.cancel_event.set()
        permission_broker.cancel_for_request(request_id)
        task.cancel()
        return True


@router.websocket("/ws")
async def chat_ws(websocket: WebSocket) -> None:
    settings = get_settings()
    if not origin_allowed(websocket.headers.get("origin"), websocket.headers.get("host")):
        # Browsers always send Origin; a foreign one means another website is trying to connect.
        await websocket.close(code=4403)
        return
    await websocket.accept()
    try:
        first = json.loads(await asyncio.wait_for(websocket.receive_text(), timeout=15))
        if first.get("type") != "auth":
            raise ValueError("first message must be auth")
        user = await verify_token(first.get("token"))
    except (TimeoutError, ValueError, json.JSONDecodeError, WebSocketDisconnect):
        with contextlib.suppress(Exception):
            await websocket.close(code=4401)
        return
    except NexusError as exc:
        with contextlib.suppress(Exception):
            await websocket.send_text(json.dumps({"type": "error", "error": exc.to_dict()}))
            await websocket.close(code=4401)
        return

    conn = _Connection(websocket, user)
    queue = hub.subscribe(user.id)

    async def forward_notifications() -> None:
        while True:
            event = await queue.get()
            await conn.send(event)

    forwarder = asyncio.create_task(forward_notifications())
    await conn.send({"type": "ready", "user": {"id": str(user.id), "email": user.email, "auth_mode": user.auth_mode}})
    try:
        while True:
            raw = await websocket.receive_text()
            if len(raw) > 100_000:
                await conn.send({"type": "error", "error": {"code": "message_too_large", "message": "Message too large."}})
                continue
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await conn.send({"type": "error", "error": {"code": "invalid_json", "message": "Invalid message."}})
                continue
            kind = msg.get("type")
            if kind == "ping":
                await conn.send({"type": "pong"})
            elif kind == "chat":
                request_id = str(msg.get("request_id") or uuid.uuid4().hex)[:64]
                try:
                    rate_limiter.check(f"chat:{user.id}", settings.rate_limit_chat_per_minute)
                    body = ChatBody.model_validate(msg)
                    if len(conn.running) >= MAX_CONCURRENT_REQUESTS:
                        raise NexusError("NEXUS is already working on several requests.", code="too_many_requests",
                                         next_step="Wait for one to finish, or stop it.")
                except ValidationError as exc:
                    err = {"code": "invalid_request", "message": exc.errors()[0].get("msg", "Invalid request")}
                    await conn.send({"type": "error", "request_id": request_id, "error": err})
                    await conn.send({"type": "done", "request_id": request_id})
                    continue
                except NexusError as exc:
                    await conn.send({"type": "error", "request_id": request_id, "error": exc.to_dict()})
                    await conn.send({"type": "done", "request_id": request_id})
                    continue
                asyncio.create_task(conn.run_chat(request_id, body), name=f"chat-{request_id}")
            elif kind == "permission_decision":
                try:
                    ok = permission_broker.resolve(uuid.UUID(str(msg.get("permission_id"))), user.id,
                                                   Decision(str(msg.get("decision"))))
                except ValueError:
                    ok = False
                if not ok:
                    await conn.send({"type": "error", "error": {"code": "permission_not_pending",
                                                                "message": "That approval request is no longer pending."}})
            elif kind == "cancel":
                conn.cancel(str(msg.get("request_id", "")))
            else:
                await conn.send({"type": "error", "error": {"code": "unknown_message", "message": f"Unknown type {kind!r}."}})
    except WebSocketDisconnect:
        pass
    finally:
        conn.closed = True
        forwarder.cancel()
        hub.unsubscribe(user.id, queue)
        # Nobody can approve anything any more: deny pending approvals, let work finish and be saved.
        for request_id in list(conn.running):
            permission_broker.cancel_for_request(request_id)
