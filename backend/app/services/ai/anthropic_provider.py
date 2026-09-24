"""Claude via the official Anthropic Python SDK."""

from __future__ import annotations

import logging
from typing import Any

import anthropic

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

# Models that take adaptive thinking + effort. Everything else (e.g. Haiku 4.5)
# gets neither.
_ADAPTIVE_PREFIXES = (
    "claude-fable-5",
    "claude-mythos-5",
    "claude-opus-5",
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-opus-4-6",
    "claude-sonnet-5",
    "claude-sonnet-4-6",
)
# Models for which the server-side refusal fallback ("default" routing) applies.
_FALLBACK_MODELS = ("claude-opus-5", "claude-fable-5-1", "claude-fable-5", "claude-opus-5-5")
FALLBACK_BETA = "server-side-fallback-2026-07-01"


def _supports_adaptive(model: str) -> bool:
    return model.startswith(_ADAPTIVE_PREFIXES)


def _to_api_messages(messages: list[ChatMessage]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        if m.role == "assistant":
            if m.provider_raw is not None:
                out.append({"role": "assistant", "content": m.provider_raw})
                continue
            blocks: list[dict[str, Any]] = []
            text = m.text()
            if text:
                blocks.append({"type": "text", "text": text})
            for tc in m.tool_calls:
                blocks.append({"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.arguments})
            out.append({"role": "assistant", "content": blocks or [{"type": "text", "text": "…"}]})
            continue
        if isinstance(m.content, str):
            out.append({"role": "user", "content": m.content})
            continue
        blocks = []
        for p in m.content:
            if isinstance(p, TextPart):
                blocks.append({"type": "text", "text": p.text})
            elif isinstance(p, ImagePart):
                blocks.append({"type": "image",
                               "source": {"type": "base64", "media_type": p.media_type, "data": p.data_b64}})
            elif isinstance(p, ToolResultPart):
                blocks.append({"type": "tool_result", "tool_use_id": p.tool_call_id, "content": p.content,
                               "is_error": p.is_error})
        out.append({"role": "user", "content": blocks})
    return out


class AnthropicProvider(AIProvider):
    name = "anthropic"
    supports_vision = True

    def __init__(self, api_key: str, model: str, *, default_effort: str = "medium", max_tokens: int = 16000,
                 refusal_fallback: bool = True) -> None:
        self.model = model
        self.default_effort = default_effort
        self.max_tokens = max_tokens
        self.refusal_fallback = refusal_fallback and model.startswith(_FALLBACK_MODELS)
        self._client = anthropic.AsyncAnthropic(api_key=api_key, max_retries=2, timeout=180.0)

    # ------------------------------------------------------------------
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
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens or self.max_tokens,
            # Frozen system prompt first so it can be served from the prompt cache.
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": _to_api_messages(messages),
        }
        if tools:
            kwargs["tools"] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.input_schema,
                    # Stream large tool inputs as they're generated; inputs are
                    # validated against the tool's schema before execution.
                    "eager_input_streaming": True,
                }
                for t in tools
            ]
        if _supports_adaptive(self.model):
            kwargs["thinking"] = {"type": "adaptive"}
            kwargs["output_config"] = {"effort": effort or self.default_effort}

        try:
            if self.refusal_fallback:
                stream_cm = self._client.beta.messages.stream(betas=[FALLBACK_BETA], fallbacks="default", **kwargs)
            else:
                stream_cm = self._client.messages.stream(**kwargs)
            async with stream_cm as stream:
                async for event in stream:
                    if (
                        on_text is not None
                        and event.type == "content_block_delta"
                        and getattr(event.delta, "type", None) == "text_delta"
                    ):
                        await on_text(event.delta.text)
                final = await stream.get_final_message()
        except ValueError as exc:
            # Tool input JSON the SDK could not parse at all.
            raise AIProviderError(
                "The model produced an unreadable tool request.",
                code="ai_invalid_tool_json",
                reason=str(exc)[:200],
                next_step="Try again; if it persists, rephrase the request.",
            ) from exc
        except anthropic.AuthenticationError as exc:
            raise AIProviderError(
                "The Anthropic API key was rejected.",
                code="ai_auth_failed",
                reason="The key is invalid or has been revoked.",
                next_step="Update the key in Settings → API keys (or ANTHROPIC_API_KEY in .env).",
                status_code=401,
            ) from exc
        except anthropic.PermissionDeniedError as exc:
            raise AIProviderError(
                f"The API key does not have access to model '{self.model}'.",
                code="ai_permission_denied",
                next_step="Choose a model your account can use (AI_MODEL in .env).",
            ) from exc
        except anthropic.NotFoundError as exc:
            raise AIProviderError(
                f"Model '{self.model}' was not found.",
                code="ai_model_not_found",
                next_step="Set AI_MODEL to a valid model id, e.g. claude-opus-5.",
            ) from exc
        except anthropic.RateLimitError as exc:
            raise AIProviderError(
                "The AI provider is rate limiting requests.",
                code="ai_rate_limited",
                reason="Too many requests or tokens per minute for this API key.",
                next_step="Wait a minute and try again.",
                status_code=429,
            ) from exc
        except anthropic.BadRequestError as exc:
            raise AIProviderError(
                "The AI provider rejected the request.",
                code="ai_bad_request",
                reason=getattr(exc, "message", str(exc))[:300],
                next_step="Try rephrasing, or start a new conversation if the history is very long.",
            ) from exc
        except anthropic.APIStatusError as exc:
            overloaded = exc.status_code in (529, 503)
            raise AIProviderError(
                "The AI provider is temporarily overloaded." if overloaded else f"The AI provider returned an error ({exc.status_code}).",
                code="ai_unavailable" if overloaded else "ai_server_error",
                next_step="Try again in a moment.",
            ) from exc
        except anthropic.APIConnectionError as exc:
            raise AIProviderError(
                "Could not reach the Anthropic API.",
                code="ai_connection_failed",
                reason="Network error or firewall blocking api.anthropic.com.",
                next_step="Check your internet connection and try again.",
            ) from exc

        return self._parse(final)

    def _parse(self, final: Any) -> ProviderResponse:
        stop = final.stop_reason
        text_parts: list[str] = []
        tool_calls: list[ToolCallRequest] = []
        for block in final.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                args = block.input if isinstance(block.input, dict) else {}
                tool_calls.append(ToolCallRequest(id=block.id, name=block.name, arguments=args))
        usage = {}
        if getattr(final, "usage", None) is not None:
            usage = {
                "input_tokens": getattr(final.usage, "input_tokens", 0) or 0,
                "output_tokens": getattr(final.usage, "output_tokens", 0) or 0,
                "cache_read_input_tokens": getattr(final.usage, "cache_read_input_tokens", 0) or 0,
            }
        if stop == "refusal":
            details = getattr(final, "stop_details", None)
            return ProviderResponse(
                text="".join(text_parts), tool_calls=[], stop_reason="refusal", provider_raw=final.content,
                model=getattr(final, "model", self.model), usage=usage,
                refusal_category=getattr(details, "category", None) if details else None,
            )
        mapped = {"end_turn": "end", "tool_use": "tool_use", "max_tokens": "max_tokens",
                  "stop_sequence": "end"}.get(stop or "", "other")
        if mapped == "max_tokens":
            # A truncated tool input must never be executed.
            tool_calls = []
        return ProviderResponse(
            text="".join(text_parts),
            tool_calls=tool_calls if mapped == "tool_use" else [],
            stop_reason=mapped,  # type: ignore[arg-type]
            provider_raw=final.content,
            model=getattr(final, "model", self.model),
            usage=usage,
        )

    async def health(self) -> tuple[bool, str | None]:
        try:
            await self._client.with_options(timeout=10.0, max_retries=0).models.retrieve(self.model)
            return True, None
        except anthropic.AuthenticationError:
            return False, "API key rejected"
        except anthropic.NotFoundError:
            return False, f"Model '{self.model}' not found"
        except anthropic.APIConnectionError:
            return False, "Cannot reach api.anthropic.com"
        except anthropic.APIStatusError as exc:
            return False, f"API error {exc.status_code}"
