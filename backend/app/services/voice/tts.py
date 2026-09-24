"""Text-to-speech providers (replaceable).

* browser    - the frontend speaks with the Web Speech API (default, free)
* openai     - OpenAI TTS (needs OPENAI_API_KEY)
* elevenlabs - ElevenLabs (needs ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID)
"""

from __future__ import annotations

import abc
import re

import httpx

from app.config import get_settings
from app.core.errors import NotConfiguredError, ToolExecutionError
from app.services.secrets import get_secret

MAX_TTS_CHARS = 4000


def speakable(text: str) -> str:
    """Strip Markdown so TTS doesn't read symbols aloud."""
    t = re.sub(r"```.*?```", " (code omitted) ", text, flags=re.DOTALL)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"^\s{0,3}#{1,6}\s*", "", t, flags=re.MULTILINE)
    t = re.sub(r"^\s*[-*+]\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"^\s*>\s?", "", t, flags=re.MULTILINE)
    t = re.sub(r"[*_~|]", "", t)
    t = re.sub(r"\n{2,}", ". ", t)
    return re.sub(r"\s+", " ", t).strip()[:MAX_TTS_CHARS]


class TTSProvider(abc.ABC):
    name: str

    @abc.abstractmethod
    async def synthesize(self, text: str, voice: str | None = None) -> tuple[bytes, str]: ...


class OpenAITTS(TTSProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str, voice: str) -> None:
        self.api_key, self.model, self.voice = api_key, model, voice

    async def synthesize(self, text: str, voice: str | None = None) -> tuple[bytes, str]:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post("https://api.openai.com/v1/audio/speech",
                                     headers={"Authorization": f"Bearer {self.api_key}"},
                                     json={"model": self.model, "voice": voice or self.voice, "input": text,
                                           "response_format": "mp3"})
        if resp.status_code >= 400:
            raise ToolExecutionError(f"Voice synthesis failed (HTTP {resp.status_code}).", code="tts_failed",
                                     reason=resp.text[:200])
        return resp.content, "audio/mpeg"


class ElevenLabsTTS(TTSProvider):
    name = "elevenlabs"

    def __init__(self, api_key: str, voice_id: str) -> None:
        self.api_key, self.voice_id = api_key, voice_id

    async def synthesize(self, text: str, voice: str | None = None) -> tuple[bytes, str]:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"https://api.elevenlabs.io/v1/text-to-speech/{voice or self.voice_id}",
                                     headers={"xi-api-key": self.api_key, "Accept": "audio/mpeg"},
                                     json={"text": text, "model_id": "eleven_multilingual_v2"})
        if resp.status_code >= 400:
            raise ToolExecutionError(f"Voice synthesis failed (HTTP {resp.status_code}).", code="tts_failed",
                                     reason=resp.text[:200])
        return resp.content, "audio/mpeg"


async def get_tts() -> TTSProvider | None:
    settings = get_settings()
    if settings.tts_provider == "openai":
        key = await get_secret("OPENAI_API_KEY")
        return OpenAITTS(key, settings.openai_tts_model, settings.openai_tts_voice) if key else None
    if settings.tts_provider == "elevenlabs":
        key = await get_secret("ELEVENLABS_API_KEY")
        if key and settings.elevenlabs_voice_id:
            return ElevenLabsTTS(key, settings.elevenlabs_voice_id)
    return None


async def synthesize(text: str) -> tuple[bytes, str]:
    provider = await get_tts()
    if provider is None:
        raise NotConfiguredError("Server voice is not configured; the browser voice is used instead.",
                                 code="tts_not_configured",
                                 next_step="Set TTS_PROVIDER=openai or elevenlabs with the matching API key.")
    clean = speakable(text)
    if not clean:
        raise ToolExecutionError("There is nothing to say.", code="tts_empty")
    return await provider.synthesize(clean)
