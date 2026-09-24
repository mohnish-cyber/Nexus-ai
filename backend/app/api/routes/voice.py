from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.deps import current_user
from app.config import get_settings
from app.security.auth import CurrentUser
from app.security.rate_limit import rate_limiter
from app.services.voice import stt, tts

router = APIRouter(prefix="/api/voice", tags=["voice"])


@router.get("/status")
async def voice_status(_: CurrentUser = Depends(current_user)) -> dict[str, Any]:
    s = get_settings()
    stt_provider = await stt.get_stt()
    tts_provider = await tts.get_tts()
    return {
        "stt": {"server": stt_provider.name if stt_provider else None, "configured_mode": s.stt_provider},
        "tts": {"server": tts_provider.name if tts_provider else None, "configured_mode": s.tts_provider},
        "wake_word": {"engine": "browser-speech (experimental)",
                      "note": "Porcupine/openWakeWord can replace the browser engine on desktop builds."},
    }


@router.post("/transcribe")
async def transcribe(audio: UploadFile = File(...), language: str | None = Form(default=None),
                     user: CurrentUser = Depends(current_user)) -> dict[str, Any]:
    rate_limiter.check(f"stt:{user.id}", 30)
    data = await audio.read(stt.MAX_AUDIO_BYTES + 1)
    text, provider = await stt.transcribe(data, audio.content_type or "audio/webm", language)
    return {"text": text, "provider": provider}


class SpeakBody(BaseModel):
    text: str = Field(min_length=1, max_length=8000)


@router.post("/speak")
async def speak(body: SpeakBody, user: CurrentUser = Depends(current_user)) -> Response:
    rate_limiter.check(f"tts:{user.id}", 30)
    audio, mime = await tts.synthesize(body.text)
    return Response(content=audio, media_type=mime, headers={"Cache-Control": "no-store"})
