"""OpenAI-compatible chat-completions provider.

Lets NEXUS run against local/self-hosted models (Ollama, LM Studio, vLLM) or
any service exposing the `/v1/chat/completions` API.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.core.errors import AIProviderError
from app.services.ai.base import (
    AIProvider,
    ChatMessage,
    ImagePart,
    ProviderResponse,
    TextCallback,
    TextPart,
    ToolCallRequest,
    ToolResultPart,
    ToolSpec,
)

logger = logging.getLogger(__name__)


def _to_api_messages(system: str, messages: list[ChatMessage]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for m in messages:
        if m.role == "assistant":
            msg: dict[str, Any] = {"role": "assistant", "content": m.text() or None}
            if m.tool_calls:
                msg["tool_calls"] = [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)}}
                    for tc in m.tool_calls
                ]
            out.append(msg)
            continue
        if isinstance(m.content, str):
            out.append({"role": "user", "content": m.content})
            continue
        parts: list[dict[str, Any]] = []
        for p in m.content:
            if isinstance(p, ToolResultPart):
                out.append({"role": "tool", "tool_call_id": p.tool_call_id,
                            "content": ("ERROR: " if p.is_error else "") + p.content})
            elif isinstance(p, TextPart):
                parts.append({"type": "text", "text": p.text})
            elif isinstance(p, ImagePart):
                parts.append({"type": "image_url", "image_url": {"url": f"data:{p.media_type};base64,{p.data_b64}"}})
        if parts:
            out.append({"role": "user", "content": parts})
    return out


class OpenAICompatibleProvider(AIProvider):
    name = "openai_compatible"
    supports_vision = True  # depends on the model; errors are reported clearly

    def __init__(self, base_url: str, model: str, api_key: str | None = None, max_tokens: int = 4096) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.AsyncClient(base_url=self.base_url, headers=headers, timeout=180.0)

    async def generate(
        self,
        *,
        system: str,
        messages: list[ChatMessage],
        tools: list[ToolSpec] | None = None,
        effort: str | None = None,
        max_tokens: int | None = None,
        on_text: TextCallback | None = None,
    ) -> ProviderResponse:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": _to_api_messages(system, messages),
            "max_tokens": max_tokens or self.max_tokens,
            "stream": True,
        }
        if tools:
            body["tools"] = [
                {"type": "function",
                 "function": {"name": t.name, "description": t.description, "parameters": t.input_schema}}
                for t in tools
            ]
        text_parts: list[str] = []
        calls: dict[int, dict[str, Any]] = {}
        finish = None
        try:
            async with self._client.stream("POST", "/chat/completions", json=body) as resp:
                if resp.status_code >= 400:
                    detail = (await resp.aread()).decode("utf-8", "replace")[:300]
                    raise AIProviderError(
                        f"The AI endpoint returned HTTP {resp.status_code}.",
                        code="ai_server_error" if resp.status_code >= 500 else "ai_bad_request",
                        reason=detail,
                        next_step="Check OPENAI_COMPAT_BASE_URL, the model name and the API key.",
                    )
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    for choice in chunk.get("choices", []):
                        delta = choice.get("delta") or {}
                        if delta.get("content"):
                            text_parts.append(delta["content"])
                            if on_text:
                                await on_text(delta["content"])
                        for tc in delta.get("tool_calls") or []:
                            slot = calls.setdefault(tc.get("index", 0), {"id": None, "name": "", "args": ""})
                            if tc.get("id"):
                                slot["id"] = tc["id"]
                            fn = tc.get("function") or {}
                            slot["name"] += fn.get("name") or ""
                            slot["args"] += fn.get("arguments") or ""
                        finish = choice.get("finish_reason") or finish
        except httpx.ConnectError as exc:
            raise AIProviderError(
                f"Could not connect to the AI endpoint at {self.base_url}.",
                code="ai_connection_failed",
                next_step="Make sure the model server (e.g. Ollama) is running.",
            ) from exc
        except httpx.TimeoutException as exc:
            raise AIProviderError("The AI endpoint timed out.", code="ai_timeout",
                                  next_step="Try again or use a smaller model.") from exc

        tool_calls: list[ToolCallRequest] = []
        for i, slot in sorted(calls.items()):
            try:
                args = json.loads(slot["args"] or "{}")
            except json.JSONDecodeError:
                args = {"__invalid_json__": slot["args"][:500]}
            tool_calls.append(ToolCallRequest(id=slot["id"] or f"call_{i}", name=slot["name"], arguments=args))
        stop = "tool_use" if tool_calls else ("max_tokens" if finish == "length" else "end")
        if stop == "max_tokens":
            tool_calls = []
        return ProviderResponse(text="".join(text_parts), tool_calls=tool_calls, stop_reason=stop, model=self.model)

    async def health(self) -> tuple[bool, str | None]:
        try:
            resp = await self._client.get("/models", timeout=5.0)
            return resp.status_code < 400, None if resp.status_code < 400 else f"HTTP {resp.status_code}"
        except httpx.HTTPError as exc:
            return False, f"Cannot reach {self.base_url}: {exc.__class__.__name__}"
