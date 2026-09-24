"""End-to-end NexusCore behaviour: intent → plan → agents → tools → verification."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.core.intent import Intent, classify
from app.core.nexus_core import ChatRequest, nexus_core
from app.core.planner import plan as make_plan
from app.services import files as file_service
from app.services import memory_service as ms
from app.services.ai.base import ProviderResponse, ToolCallRequest
from app.services.ai.mock_provider import json_response


class _File:
    def __init__(self, kind: str) -> None:
        self.kind = kind


@pytest.mark.parametrize("text,expected", [
    ("Hey Nexus, how are you?", {Intent.CONVERSATION}),
    ("Open my AI project.", {Intent.COMPUTER}),
    ("Find gaming laptops below ₹60,000.", {Intent.RESEARCH}),
    ("There is an error on my screen. Help me fix it.", {Intent.SCREEN}),
    ("My college AI project is LinkGuard AI.", {Intent.MEMORY_STORE}),
    ("Remind me tomorrow to submit my assignment.", {Intent.REMINDER}),
    ("Every morning give me five important AI news stories.", {Intent.AUTOMATION}),
    ("Check this laptop's price daily and alert me below ₹55,000.", {Intent.AUTOMATION}),
    ("Run my project and tell me why it is failing.", {Intent.CODING}),
    ("What tasks do I have today?", {Intent.TASKS}),
    ("Open VS Code and start my project.", {Intent.COMPUTER}),
    ("Check tomorrow's weather and remind me to take an umbrella if rain is expected.", {Intent.WEATHER, Intent.REMINDER}),
])
def test_intents(text: str, expected: set[Intent]) -> None:
    result = classify(text)
    assert (set(result.strong) or {result.primary}) == expected


async def test_templates_for_multi_step_requests() -> None:
    p = await make_plan("Read this PDF and explain Unit 3.", classify("Read this PDF and explain Unit 3.", [_File("pdf")]), None)
    assert [s.agent for s in p.steps] == ["file", "study"] and p.steps[0].options["mode"] == "retrieve"
    p = await make_plan("What is wrong on my screen?", classify("What is wrong on my screen?"), None)
    assert [s.agent for s in p.steps] == ["computer", "vision"]
    text = "Check tomorrow's weather and remind me to take an umbrella if rain is expected."
    p = await make_plan(text, classify(text), None)
    assert [s.agent for s in p.steps] == ["research", "automation"]


async def test_model_planner_used_for_ambiguous_requests(scripted) -> None:
    scripted.push(json_response({"steps": [{"agent": "research", "instruction": "Find the release date"},
                                           {"agent": "automation", "instruction": "Create a reminder for it"}]}))
    text = "search when the next iPhone launches and add a task to buy it"
    p = await make_plan(text, classify(text), scripted)
    assert p.source == "model" and [s.agent for s in p.steps] == ["research", "automation"]


async def test_invalid_model_plan_falls_back(scripted) -> None:
    scripted.push(ProviderResponse(text="not json at all", tool_calls=[], stop_reason="end"))
    text = "search when the next iPhone launches and add a task to buy it"
    p = await make_plan(text, classify(text), scripted)
    assert p.source == "fallback" and p.steps


# --------------------------------------------------------------------------- without AI


async def test_deterministic_paths_work_without_ai(make_ctx, user) -> None:
    msg = await nexus_core.handle(make_ctx(), ChatRequest("My college AI project is LinkGuard AI."))
    assert msg["status"] == "complete" and "LinkGuard AI" in msg["content"]
    assert [a["tool"] for a in msg["actions"]] == ["remember"]

    msg = await nexus_core.handle(make_ctx(), ChatRequest("Remind me tomorrow at 8 AM to submit my assignment"))
    assert msg["actions"][0]["tool"] == "create_reminder" and msg["actions"][0]["status"] == "succeeded"
    assert "8:00 AM" in msg["content"]

    msg = await nexus_core.handle(make_ctx(), ChatRequest("How are you today?"))
    assert msg["status"] == "error" and "Settings" in msg["content"]


async def test_conversation_history_persists(make_ctx) -> None:
    from app.services import conversation_service as convs

    first = await nexus_core.handle(make_ctx(), ChatRequest("remember that my favourite editor is Neovim"))
    conv_id = first["conversation_id"]
    import uuid

    await nexus_core.handle(make_ctx(), ChatRequest("what is my favourite editor?", uuid.UUID(conv_id)))
    msgs = await convs.get_messages(first and (await _user_id()), uuid.UUID(conv_id))
    assert [m.role for m in msgs] == ["user", "assistant", "user", "assistant"]
    assert "Neovim" in msgs[-1].content


async def _user_id():
    from app.security.auth import LOCAL_USER_ID

    return LOCAL_USER_ID


# --------------------------------------------------------------------------- with a (scripted) model


async def test_conversation_streams_tokens(make_ctx, events, scripted) -> None:
    scripted.push(ProviderResponse(text="Doing well, ready to help.", tool_calls=[], stop_reason="end"))
    msg = await nexus_core.handle(make_ctx(), ChatRequest("How are you today?"))
    assert msg["content"] == "Doing well, ready to help."
    kinds = [e["type"] for e in events]
    assert "token" in kinds and kinds.index("plan") < kinds.index("message")
    assert any(e["type"] == "status" and e["state"] == "completed" for e in events)


@respx.mock
async def test_research_agent_tool_loop_with_weather(make_ctx, events, scripted) -> None:
    respx.get("https://geocoding-api.open-meteo.com/v1/search").mock(return_value=httpx.Response(200, json={
        "results": [{"name": "Pune", "latitude": 18.5, "longitude": 73.8, "country": "India", "admin1": "Maharashtra"}]}))
    respx.get("https://api.open-meteo.com/v1/forecast").mock(return_value=httpx.Response(200, json={
        "timezone": "Asia/Kolkata", "current": {"temperature_2m": 27, "weather_code": 61},
        "daily": {"time": ["2026-09-24", "2026-09-25"], "weather_code": [3, 63], "temperature_2m_max": [30, 28],
                  "temperature_2m_min": [22, 21], "precipitation_probability_max": [10, 85],
                  "precipitation_sum": [0, 12.5], "wind_speed_10m_max": [10, 20]}}))
    # Weather + reminder: research step (deterministic weather) → automation step (model decides).
    scripted.push(ProviderResponse(text="", tool_calls=[ToolCallRequest(
        "t1", "create_reminder", {"message": "Take an umbrella - rain expected", "when": "tomorrow 7:30 am"})],
        stop_reason="tool_use"))
    scripted.push(ProviderResponse(text="Rain is likely tomorrow in Pune (85%). I'll remind you at 7:30 AM to take an umbrella.",
                                   tool_calls=[], stop_reason="end"))
    ctx = make_ctx(preferences={"location": {"city": "Pune"}})
    msg = await nexus_core.handle(ctx, ChatRequest(
        "Check tomorrow's weather and remind me to take an umbrella if rain is expected."))
    tools = [(a["tool"], a["status"]) for a in msg["actions"]]
    assert tools == [("get_weather", "succeeded"), ("create_reminder", "succeeded")]
    assert "Verification" not in msg["content"]
    # The automation agent saw the weather result from the research step.
    automation_call = scripted.calls[0]
    assert "rain expected" in automation_call["messages"][-1].text().lower()


async def test_verifier_flags_unbacked_claims(make_ctx, scripted) -> None:
    scripted.push(ProviderResponse(text="Sure! I've set a reminder for 5 PM.", tool_calls=[], stop_reason="end"))
    msg = await nexus_core.handle(make_ctx(), ChatRequest("hmm, can you help me not forget the call later"))
    assert "Verification" in msg["content"] and msg["meta"]["verification"]


async def test_tool_failure_is_reported_honestly(make_ctx, scripted) -> None:
    # Search is not configured: the tool fails and the model must be told.
    scripted.push(ProviderResponse(text="", tool_calls=[ToolCallRequest("t1", "web_search", {"query": "AI news"})],
                                   stop_reason="tool_use"))

    def answer(system, messages, tools):
        result = messages[-1].content[0]
        assert result.is_error and "not configured" in result.content.lower() or "not available" in result.content.lower()
        return ProviderResponse(text="Web search isn't configured yet, so I can't fetch live news.", tool_calls=[],
                                stop_reason="end")

    scripted.push(answer)
    msg = await nexus_core.handle(make_ctx(), ChatRequest("Search the latest AI news."))
    assert msg["actions"][0]["status"] == "failed"
    assert "isn't configured" in msg["content"]


async def test_forget_requires_approval(make_ctx, events, user) -> None:
    await ms.save_candidate(user.id, ms.MemoryCandidate("person", "sister", "Ana"))
    msg = await nexus_core.handle(make_ctx(approver="deny"), ChatRequest("Forget my sister"))
    assert any(e["type"] == "permission_request" for e in events)
    assert msg["actions"][0]["tool"] == "forget" and msg["actions"][0]["status"] == "denied"
    assert len(await ms.list_memories(user.id)) == 1
    await nexus_core.handle(make_ctx(approver="allow_once"), ChatRequest("Forget my sister"))
    assert await ms.list_memories(user.id) == []


async def test_high_risk_delete_via_model_needs_approval(make_ctx, events, scripted, workspace) -> None:
    target = workspace / "demo" / "test_app.py"
    scripted.push(ProviderResponse(text="", tool_calls=[ToolCallRequest("t1", "delete_path", {"path": str(target)})],
                                   stop_reason="tool_use"))
    scripted.push(ProviderResponse(text="You declined, so the file was kept.", tool_calls=[], stop_reason="end"))
    ctx = make_ctx(approver="deny", preferences={"workspace": {"roots": [str(workspace)]}})
    msg = await nexus_core.handle(ctx, ChatRequest("Delete the file demo/test_app.py"))
    request = next(e for e in events if e["type"] == "permission_request")["permission"]
    assert request["risk"] == "high" and request["allow_always"] is False
    assert msg["actions"][0]["status"] == "denied" and target.exists()

    events.clear()
    scripted.push(ProviderResponse(text="", tool_calls=[ToolCallRequest("t2", "delete_path", {"path": str(target)})],
                                   stop_reason="tool_use"))
    scripted.push(ProviderResponse(text="I've deleted the file demo/test_app.py (moved to NEXUS trash).",
                                   tool_calls=[], stop_reason="end"))
    ctx = make_ctx(approver="allow_once", preferences={"workspace": {"roots": [str(workspace)]}})
    msg = await nexus_core.handle(ctx, ChatRequest("Delete the file demo/test_app.py"))
    assert msg["actions"][0]["status"] == "succeeded" and not target.exists()
    assert "Verification" not in msg["content"]


async def test_file_to_study_chain(make_ctx, scripted, user) -> None:
    from tests.test_memory_and_documents import SYLLABUS, make_pdf

    row = await file_service.store_upload(user.id, "networks.pdf", make_pdf(SYLLABUS))

    def study(system, messages, tools):
        context = messages[-1].text()
        assert "Dijkstra" in context and "Firewalls" not in context  # only Unit 3 was retrieved
        return ProviderResponse(text="**From your document**\nUnit 3 covers routing (Dijkstra, OSPF).",
                                tool_calls=[], stop_reason="end")

    scripted.push(study)
    msg = await nexus_core.handle(make_ctx(), ChatRequest("Read this PDF and explain Unit 3.", attachment_ids=[row.id]))
    assert msg["meta"]["agents"] == ["file", "study"] and "routing" in msg["content"]
    assert any("UNIT III" in (s["title"] or "") for s in msg["sources"])


async def test_screen_request_fails_gracefully_when_headless(make_ctx, scripted) -> None:
    msg = await nexus_core.handle(make_ctx(), ChatRequest("There is an error on my screen. Help me fix it."))
    assert msg["status"] == "error"
    assert msg["actions"][0]["tool"] == "take_screenshot" and msg["actions"][0]["status"] == "failed"
    assert "Capture screen" in msg["content"] or "screen" in msg["content"].lower()


async def test_vision_agent_receives_image(make_ctx, scripted, user) -> None:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (10, 10), "white").save(buf, format="PNG")
    row = await file_service.store_upload(user.id, "error.png", buf.getvalue())

    def see(system, messages, tools):
        parts = messages[-1].content
        assert any(getattr(p, "type", "") == "image" for p in parts)
        return ProviderResponse(text="**What I see**: a blank dialog.", tool_calls=[], stop_reason="end")

    scripted.push(see)
    msg = await nexus_core.handle(make_ctx(), ChatRequest("Analyse this screenshot.", attachment_ids=[row.id]))
    assert msg["meta"]["agents"] == ["vision"] and "blank dialog" in msg["content"]


async def test_refusal_is_handled(make_ctx, scripted) -> None:
    scripted.push(ProviderResponse(text="", tool_calls=[], stop_reason="refusal"))
    msg = await nexus_core.handle(make_ctx(), ChatRequest("Tell me something."))
    assert "can't help" in msg["content"]


async def test_email_is_honestly_unsupported(make_ctx) -> None:
    msg = await nexus_core.handle(make_ctx(), ChatRequest("check my email"))
    assert "isn't connected" in msg["content"] and msg["actions"] == []
