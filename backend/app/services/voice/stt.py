"""Speech-to-text providers (replaceable).

* openai - Whisper API (needs OPENAI_API_KEY)
* local  - faster-whisper running on this machine (pip install faster-whisper)

When neither is available the frontend falls back to the browser's built-in
speech recognition.
"""

from __future__ import annotations

import abc
import asyncio
import importlib.util
import io
import logging

import httpx

from app.config import get_settings
from app.core.errors import NotConfiguredError, ToolExecutionError
from app.services.secrets import get_secret

logger = logging.getLogger(__name__)

ALLOWED_AUDIO = {"audio/webm", "audio/ogg", "audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp4", "audio/m4a",
                 "audio/aac", "video/webm"}
MAX_AUDIO_BYTES = 20 * 1024 * 1024


class STTProvider(abc.ABC):
    name: str

    @abc.abstractmethod
    async def transcribe(self, audio: bytes, mime: str, language: str | None = None) -> str: ...


class OpenAIWhisperSTT(STTProvider):
    name = "openai-whisper"

    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    async def transcribe(self, audio: bytes, mime: str, language: str | None = None) -> str:
        ext = {"audio/webm": "webm", "video/webm": "webm", "audio/ogg": "ogg", "audio/wav": "wav", "audio/x-wav": "wav",
               "audio/mpeg": "mp3", "audio/mp4": "mp4", "audio/m4a": "m4a", "audio/aac": "aac"}.get(mime, "webm")
        data = {"model": self.model}
        if language:
            data["language"] = language
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    data=data,
                    files={"file": (f"speech.{ext}", audio, mime)},
                )
        except httpx.HTTPError as exc:
            raise ToolExecutionError("Could not reach the speech-to-text service.", code="stt_unreachable",
                                     reason=exc.__class__.__name__) from exc
        if resp.status_code == 401:
            raise ToolExecutionError("The OpenAI API key was rejected.", code="stt_auth_failed",
                                     next_step="Check OPENAI_API_KEY in Settings → API keys.")
        if resp.status_code >= 400:
            raise ToolExecutionError(f"Speech-to-text failed (HTTP {resp.status_code}).", code="stt_failed",
                                     reason=resp.text[:200])
        return (resp.json().get("text") or "").strip()


class LocalWhisperSTT(STTProvider):
    name = "local-whisper"
    _model = None

    def __init__(self, model_size: str) -> None:
        self.model_size = model_size

    def _load(self):
        if LocalWhisperSTT._model is None:
            from faster_whisper import WhisperModel

            LocalWhisperSTT._model = WhisperModel(self.model_size, device="auto", compute_type="int8")
        return LocalWhisperSTT._model

    async def transcribe(self, audio: bytes, mime: str, language: str | None = None) -> str:
        def run() -> str:
            model = self._load()
            segments, _ = model.transcribe(io.BytesIO(audio), language=language, vad_filter=True)
            return " ".join(s.text.strip() for s in segments).strip()

        try:
            return await asyncio.to_thread(run)
        except Exception as exc:
            raise ToolExecutionError("Local speech recognition failed.", code="stt_failed",
                                     reason=f"{exc.__class__.__name__}: {str(exc)[:200]}") from exc


def local_whisper_installed() -> bool:
    return importlib.util.find_spec("faster_whisper") is not None


async def get_stt() -> STTProvider | None:
    settings = get_settings()
    choice = settings.stt_provider
    if choice == "none":
        return None
    if choice in ("auto", "openai"):
        key = await get_secret("OPENAI_API_KEY")
        if key:
            return OpenAIWhisperSTT(key, settings.openai_stt_model)
        if choice == "openai":
            return None
    if choice in ("auto", "local") and local_whisper_installed():
        return LocalWhisperSTT(settings.local_whisper_model)
    return None


async def transcribe(audio: bytes, mime: str, language: str | None = None) -> tuple[str, str]:
    base_mime = (mime or "").split(";")[0].strip().lower()
    if base_mime not in ALLOWED_AUDIO:
        raise ToolExecutionError(f"Unsupported audio format '{base_mime}'.", code="unsupported_audio")
    if len(audio) > MAX_AUDIO_BYTES:
        raise ToolExecutionError("The recording is too long.", code="audio_too_large",
                                 next_step="Keep voice messages under about 5 minutes.")
    provider = await get_stt()
    if provider is None:
        raise NotConfiguredError(
            "Server speech-to-text is not configured.",
            code="stt_not_configured",
            reason="No OpenAI key for Whisper and faster-whisper is not installed.",
            next_step="The app will use your browser's speech recognition instead, or add an OpenAI key.",
        )
    return await provider.transcribe(audio, base_mime, language), provider.name
