"""Provider-neutral types for talking to LLMs.

NexusCore and the agents only ever use these types, so swapping the model
provider never requires touching agent code.
"""

from __future__ import annotations

import abc
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

TextCallback = Callable[[str], Awaitable[None]]


@dataclass
class TextPart:
    text: str
    type: Literal["text"] = "text"


@dataclass
class ImagePart:
    media_type: str
    data_b64: str
    type: Literal["image"] = "image"


@dataclass
class ToolResultPart:
    tool_call_id: str
    content: str
    is_error: bool = False
    type: Literal["tool_result"] = "tool_result"


Part = TextPart | ImagePart | ToolResultPart


@dataclass
class ToolCallRequest:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ChatMessage:
    role: Literal["user", "assistant"]
    content: str | list[Part]
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    # Provider-native assistant content (e.g. Anthropic content blocks incl.
    # thinking blocks). Replayed verbatim inside a tool-use loop.
    provider_raw: Any = None

    @staticmethod
    def user(text: str) -> ChatMessage:
        return ChatMessage(role="user", content=text)

    @staticmethod
    def assistant(text: str) -> ChatMessage:
        return ChatMessage(role="assistant", content=text)

    def text(self) -> str:
        if isinstance(self.content, str):
            return self.content
        return "\n".join(p.text for p in self.content if isinstance(p, TextPart))


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


StopReason = Literal["end", "tool_use", "max_tokens", "refusal", "other"]


@dataclass
class ProviderResponse:
    text: str
    tool_calls: list[ToolCallRequest]
    stop_reason: StopReason
    provider_raw: Any = None
    model: str | None = None
    usage: dict[str, int] = field(default_factory=dict)
    refusal_category: str | None = None

    def as_message(self) -> ChatMessage:
        return ChatMessage(role="assistant", content=self.text, tool_calls=self.tool_calls,
                           provider_raw=self.provider_raw)


class AIProvider(abc.ABC):
    """Interface every model provider implements."""

    name: str = "base"
    model: str = ""
    supports_vision: bool = False
    supports_tools: bool = True

    @abc.abstractmethod
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
        """Run one model turn. When `on_text` is given, text deltas are
        streamed to it as they are generated."""

    async def health(self) -> tuple[bool, str | None]:
        """Cheap connectivity/credential check (no tokens spent)."""
        return True, None

    def describe(self) -> dict[str, Any]:
        return {"provider": self.name, "model": self.model, "vision": self.supports_vision,
                "tools": self.supports_tools}
