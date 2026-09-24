"""DEVELOPMENT / TEST MOCKS - not real AI.

`DevMockProvider` is only used when AI_PROVIDER=mock is set explicitly. Every
answer it produces is prefixed with "[DEV MOCK]" so it can never be mistaken
for a real model response.

`ScriptedProvider` is used by the test-suite to drive deterministic agent
loops.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from app.services.ai.base import AIProvider, ChatMessage, ProviderResponse, TextCallback, ToolSpec


class DevMockProvider(AIProvider):
    name = "mock"
    model = "dev-mock"
    supports_vision = False

    async def generate(self, *, system: str, messages: list[ChatMessage], tools: list[ToolSpec] | None = None,
                       effort: str | None = None, max_tokens: int | None = None,
                       on_text: TextCallback | None = None) -> ProviderResponse:
        last_user = next((m.text() for m in reversed(messages) if m.role == "user"), "")
        if "User message:" in last_user:  # strip NexusCore's context block
            last_user = last_user.rsplit("User message:", 1)[1]
        if "Respond with JSON only" in system or "Return ONLY JSON" in system:
            return ProviderResponse(text="{}", tool_calls=[], stop_reason="end", model=self.model)
        text = (
            "[DEV MOCK] No real AI model is connected (AI_PROVIDER=mock). "
            f"You said: “{last_user[-300:].strip()}”"
        )
        if on_text:
            for word in text.split(" "):
                await on_text(word + " ")
        return ProviderResponse(text=text, tool_calls=[], stop_reason="end", model=self.model)


class ScriptedProvider(AIProvider):
    """Returns queued responses; each item is a ProviderResponse or a callable
    taking (system, messages, tools) and returning one."""

    name = "scripted"
    model = "scripted-test"
    supports_vision = True

    def __init__(self, script: list[ProviderResponse | Callable[..., ProviderResponse]] | None = None) -> None:
        self.script = list(script or [])
        self.calls: list[dict[str, Any]] = []

    def push(self, item: ProviderResponse | Callable[..., ProviderResponse]) -> None:
        self.script.append(item)

    async def generate(self, *, system: str, messages: list[ChatMessage], tools: list[ToolSpec] | None = None,
                       effort: str | None = None, max_tokens: int | None = None,
                       on_text: TextCallback | None = None) -> ProviderResponse:
        self.calls.append({"system": system, "messages": list(messages), "tools": [t.name for t in tools or []]})
        if not self.script:
            resp = ProviderResponse(text="(scripted: no more responses)", tool_calls=[], stop_reason="end")
        else:
            item = self.script.pop(0)
            resp = item(system=system, messages=messages, tools=tools) if callable(item) else item
        if on_text and resp.text:
            await on_text(resp.text)
        return resp


def json_response(data: Any) -> ProviderResponse:
    return ProviderResponse(text=json.dumps(data), tool_calls=[], stop_reason="end")
