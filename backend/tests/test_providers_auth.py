"""AI provider mapping (no network) and Supabase JWT authentication."""

from __future__ import annotations

import time
import uuid
from types import SimpleNamespace

import jwt
import pytest

from app.core.errors import AuthenticationError
from app.services.ai.anthropic_provider import AnthropicProvider, _to_api_messages
from app.services.ai.base import ChatMessage, ImagePart, TextPart, ToolCallRequest, ToolResultPart


def test_message_conversion_for_claude() -> None:
    raw = [{"type": "thinking", "thinking": "", "signature": "sig"}, {"type": "tool_use", "id": "t1", "name": "recall",
                                                                       "input": {"query": "x"}}]
    msgs = [
        ChatMessage.user("hi"),
        ChatMessage(role="assistant", content="", tool_calls=[ToolCallRequest("t1", "recall", {"query": "x"})],
                    provider_raw=raw),
        ChatMessage(role="user", content=[ToolResultPart("t1", "result", False), TextPart("go on")]),
        ChatMessage(role="user", content=[ImagePart("image/png", "AAAA"), TextPart("what is this?")]),
    ]
    api = _to_api_messages(msgs)
    assert api[0] == {"role": "user", "content": "hi"}
    assert api[1]["content"] is raw  # thinking + tool_use blocks replayed verbatim inside the tool loop
    assert api[2]["content"][0] == {"type": "tool_result", "tool_use_id": "t1", "content": "result", "is_error": False}
    assert api[3]["content"][0]["source"] == {"type": "base64", "media_type": "image/png", "data": "AAAA"}


def _final(stop: str, blocks: list) -> SimpleNamespace:
    return SimpleNamespace(stop_reason=stop, content=blocks, model="claude-opus-5", stop_details=None,
                           usage=SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=0))


def test_parse_tool_use_refusal_and_truncation() -> None:
    p = AnthropicProvider("sk-ant-test-key", "claude-opus-5")
    tool = SimpleNamespace(type="tool_use", id="t1", name="get_weather", input={"location": "Pune"})
    text = SimpleNamespace(type="text", text="Checking.")
    r = p._parse(_final("tool_use", [text, tool]))
    assert r.stop_reason == "tool_use" and r.tool_calls[0].arguments == {"location": "Pune"}
    # A tool call cut off by max_tokens must never be executed.
    assert p._parse(_final("max_tokens", [tool])).tool_calls == []
    refusal = p._parse(_final("refusal", []))
    assert refusal.stop_reason == "refusal" and refusal.tool_calls == []


def test_model_capabilities() -> None:
    assert AnthropicProvider("k" * 10, "claude-opus-5").refusal_fallback is True
    assert AnthropicProvider("k" * 10, "claude-haiku-4-5").refusal_fallback is False


# --------------------------------------------------------------------------- Supabase auth

SECRET = "super-secret-jwt-signing-key-for-tests-0123456789"


@pytest.fixture
def supabase_mode(monkeypatch: pytest.MonkeyPatch):
    from app.config import get_settings

    monkeypatch.setenv("AUTH_MODE", "supabase")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
    monkeypatch.setenv("NEXUS_ADMIN_EMAILS", "boss@example.com")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _token(**overrides) -> str:
    claims = {"sub": str(uuid.uuid4()), "email": "user@example.com", "aud": "authenticated",
              "exp": int(time.time()) + 3600, "role": "authenticated"}
    claims.update(overrides)
    return jwt.encode(claims, SECRET, algorithm="HS256")


async def test_supabase_token_verification(supabase_mode) -> None:
    from app.security.auth import verify_token

    user = await verify_token(_token())
    assert user.auth_mode == "supabase" and user.email == "user@example.com" and not user.is_admin
    admin = await verify_token(_token(email="boss@example.com"))
    assert admin.is_admin
    for bad in (None, _token(exp=int(time.time()) - 10), _token(aud="anon"),
                jwt.encode({"sub": str(uuid.uuid4()), "aud": "authenticated", "exp": int(time.time()) + 60}, "wrong-key-" * 4,
                           algorithm="HS256"), "not-a-jwt"):
        with pytest.raises(AuthenticationError):
            await verify_token(bad)


async def test_supabase_mode_disables_computer_control(supabase_mode) -> None:
    from app.config import get_settings

    assert get_settings().computer_control is False
