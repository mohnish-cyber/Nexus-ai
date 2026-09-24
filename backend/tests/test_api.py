"""HTTP + WebSocket API tests (runs the real app, including middleware)."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

ORIGIN = {"origin": "http://localhost:5173"}


@pytest.fixture
def client(fresh_env):
    from app.database import session as db_session
    from app.main import create_app

    # The engine created by `fresh_env` belongs to pytest's event loop; the app runs in its own.
    old_engine, old_maker = db_session._engine, db_session._sessionmaker
    db_session._engine = db_session._sessionmaker = None
    with TestClient(create_app(), base_url="http://localhost") as c:
        yield c
    db_session._engine, db_session._sessionmaker = old_engine, old_maker


def _ws_chat(ws, text: str, **extra) -> list[dict]:
    ws.send_text(json.dumps({"type": "chat", "request_id": "r1", "text": text, **extra}))
    events = []
    while True:
        ev = json.loads(ws.receive_text())
        events.append(ev)
        if ev["type"] == "done":
            return events


# --------------------------------------------------------------------------- system


def test_health_status_and_config(client: TestClient) -> None:
    assert client.get("/api/health").json()["status"] == "ok"
    status = client.get("/api/system/status").json()["components"]
    assert status["database"]["ready"] is True
    assert status["ai"]["configured"] is False and status["ai"]["ready"] is False
    assert status["agents"]["count"] == 9
    config = client.get("/api/system/config").json()
    assert config["auth_mode"] == "local" and config["supabase_anon_key"] is None
    telemetry = client.get("/api/system/telemetry").json()
    assert "cpu" in telemetry and "battery" in telemetry


def test_security_headers(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"


def test_foreign_origin_cannot_post(client: TestClient) -> None:
    r = client.post("/api/chat", json={"text": "hi"}, headers={"origin": "https://evil.example"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "origin_not_allowed"


def test_dns_rebinding_host_rejected(client: TestClient) -> None:
    r = client.get("/api/health", headers={"host": "attacker.example"})
    assert r.status_code == 400


def test_errors_have_consistent_shape(client: TestClient) -> None:
    r = client.get("/api/conversations/00000000-0000-0000-0000-000000000000/messages")
    body = r.json()["error"]
    assert r.status_code == 404 and body["code"] == "conversation_not_found" and "message" in body
    r = client.post("/api/tasks", json={"title": ""}, headers=ORIGIN)
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"


# --------------------------------------------------------------------------- chat


def test_rest_chat_and_conversations(client: TestClient) -> None:
    msg = client.post("/api/chat", json={"text": "My college AI project is LinkGuard AI."}, headers=ORIGIN).json()
    assert msg["status"] == "complete" and msg["actions"][0]["tool"] == "remember"
    convs = client.get("/api/conversations").json()
    assert len(convs) == 1 and convs[0]["message_count"] == 2
    msgs = client.get(f"/api/conversations/{convs[0]['id']}/messages").json()
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert client.patch(f"/api/conversations/{convs[0]['id']}", json={"title": "Projects"}, headers=ORIGIN).json()["title"] == "Projects"
    assert client.delete(f"/api/conversations/{convs[0]['id']}", headers=ORIGIN).status_code == 204


def test_websocket_chat_flow(client: TestClient) -> None:
    with client.websocket_connect("/ws", headers=ORIGIN) as ws:
        ws.send_text(json.dumps({"type": "auth", "token": None}))
        assert json.loads(ws.receive_text())["type"] == "ready"
        events = _ws_chat(ws, "Remind me tomorrow at 8 AM to submit my assignment")
        kinds = [e["type"] for e in events]
        assert kinds[0] == "status" and "conversation" in kinds and "plan" in kinds and "activity" in kinds
        message = next(e for e in events if e["type"] == "message")["message"]
        assert message["actions"][0]["tool"] == "create_reminder" and message["actions"][0]["status"] == "succeeded"
        ws.send_text(json.dumps({"type": "ping"}))
        assert json.loads(ws.receive_text())["type"] == "pong"
    automations = client.get("/api/automations").json()
    assert automations[0]["kind"] == "reminder" and automations[0]["status"] == "active"


def test_websocket_permission_round_trip(client: TestClient) -> None:
    client.post("/api/memories", json={"category": "person", "subject": "sister", "value": "Ana"}, headers=ORIGIN)
    with client.websocket_connect("/ws", headers=ORIGIN) as ws:
        ws.send_text(json.dumps({"type": "auth"}))
        json.loads(ws.receive_text())
        ws.send_text(json.dumps({"type": "chat", "request_id": "r2", "text": "Forget my sister"}))
        while True:
            ev = json.loads(ws.receive_text())
            if ev["type"] == "permission_request":
                perm = ev["permission"]
                assert perm["risk"] == "medium" and perm["allow_always"] is True
                ws.send_text(json.dumps({"type": "permission_decision", "permission_id": perm["id"],
                                         "decision": "allow_once"}))
            if ev["type"] == "message":
                assert ev["message"]["actions"][0]["status"] == "succeeded"
            if ev["type"] == "done":
                break
    assert client.get("/api/memories").json() == []


def test_websocket_rejects_foreign_origin(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws", headers={"origin": "https://evil.example"}) as ws:
            ws.receive_text()
    assert exc.value.code == 4403


def test_websocket_requires_auth_message(client: TestClient) -> None:
    with client.websocket_connect("/ws", headers=ORIGIN) as ws:
        ws.send_text(json.dumps({"type": "chat", "text": "hi"}))
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_text()
    assert exc.value.code == 4401


# --------------------------------------------------------------------------- resources


def test_file_upload_and_serving(client: TestClient) -> None:
    from PIL import Image

    from tests.test_memory_and_documents import SYLLABUS, make_pdf

    r = client.post("/api/files", files={"file": ("syllabus.pdf", make_pdf(SYLLABUS), "application/pdf")}, headers=ORIGIN)
    assert r.status_code == 201 and r.json()["status"] == "ready" and r.json()["page_count"] == 4
    assert any("Unit 2" in s for s in r.json()["sections"])
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "blue").save(buf, format="PNG")
    img = client.post("/api/files", files={"file": ("shot.png", buf.getvalue(), "image/png")}, headers=ORIGIN).json()
    content = client.get(f"/api/files/{img['id']}/content")
    assert content.headers["content-type"] == "image/png" and "sandbox" in content.headers["content-security-policy"]
    pdf_content = client.get(f"/api/files/{r.json()['id']}/content")
    assert pdf_content.headers["content-type"] == "application/octet-stream"
    assert "attachment" in pdf_content.headers["content-disposition"]
    bad = client.post("/api/files", files={"file": ("x.exe", b"MZ\x90\x00binary\x00", "application/octet-stream")},
                      headers=ORIGIN)
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "unsupported_file_type"
    assert len(client.get("/api/files").json()) == 2
    assert client.delete(f"/api/files/{img['id']}", headers=ORIGIN).status_code == 204


def test_memory_crud_and_approval(client: TestClient) -> None:
    m = client.post("/api/memories", json={"category": "project", "subject": "thesis", "value": "Graph ML"},
                    headers=ORIGIN).json()
    assert m["status"] == "active"
    pending = client.post("/api/memories", json={"subject": "health", "value": "I take medication for anxiety"},
                          headers=ORIGIN).json()
    assert pending["status"] == "pending"
    assert client.post(f"/api/memories/{pending['id']}/approve", headers=ORIGIN).json()["status"] == "active"
    rejected = client.post("/api/memories", json={"subject": "api key", "value": "sk-ant-api03-abcdefghijklmnop"},
                           headers=ORIGIN)
    assert rejected.status_code == 422
    assert client.patch(f"/api/memories/{m['id']}", json={"value": "Graph neural nets"}, headers=ORIGIN).json()["value"] == "Graph neural nets"
    assert client.delete("/api/memories", headers=ORIGIN).status_code == 422  # needs confirm
    assert client.delete("/api/memories?confirm=true", headers=ORIGIN).json()["deleted"] == 2


def test_tasks_crud(client: TestClient) -> None:
    t = client.post("/api/tasks", json={"title": "Submit assignment", "due": "tomorrow 5pm", "remind": True},
                    headers=ORIGIN).json()
    assert t["due_at"] and t["automation_id"]
    assert client.patch(f"/api/tasks/{t['id']}", json={"status": "done"}, headers=ORIGIN).json()["status"] == "done"
    assert client.get("/api/tasks?view=done").json()[0]["id"] == t["id"]
    assert client.delete(f"/api/tasks/{t['id']}", headers=ORIGIN).status_code == 204


def test_automations_crud_and_run_now(client: TestClient) -> None:
    a = client.post("/api/automations", json={"name": "Stretch", "kind": "reminder", "message": "Stretch!",
                                               "schedule": {"type": "daily", "time": "10:00"}}, headers=ORIGIN).json()
    assert a["trigger_type"] == "cron" and a["next_run_at"]
    paused = client.patch(f"/api/automations/{a['id']}", json={"status": "paused"}, headers=ORIGIN).json()
    assert paused["status"] == "paused"
    run = client.post(f"/api/automations/{a['id']}/run", headers=ORIGIN).json()
    assert run["result"]["condition_met"] is True
    notes = client.get("/api/notifications").json()
    assert notes[0]["body"] == "Stretch!" and notes[0]["status"] == "unread"
    assert client.post("/api/notifications/read", json={}, headers=ORIGIN).json()["updated"] == 1
    assert client.get(f"/api/automations/{a['id']}/runs").json()[0]["status"] == "succeeded"
    assert client.delete(f"/api/automations/{a['id']}", headers=ORIGIN).status_code == 204
    too_often = client.post("/api/automations", json={"name": "spam", "kind": "agent_task", "prompt": "x",
                                                       "schedule": {"type": "cron", "cron": "* * * * *"}}, headers=ORIGIN)
    assert too_often.status_code == 422


def test_settings_and_secrets(client: TestClient, tmp_path: Path) -> None:
    s = client.get("/api/settings").json()
    assert s["can_edit_secrets"] is True and s["preferences"]["permissions"]["confirm_medium_actions"] is True
    assert client.put("/api/settings/workspace", json={"values": {"roots": ["/"]}}, headers=ORIGIN).status_code == 422
    (tmp_path / "proj").mkdir()
    ok = client.put("/api/settings/workspace", json={"values": {"roots": [str(tmp_path / "proj")]}}, headers=ORIGIN)
    assert ok.status_code == 200 and ok.json()["workspace"]["roots"] == [str((tmp_path / "proj").resolve())]
    assert client.put("/api/settings/regional", json={"values": {"timezone": "Mars/Base"}}, headers=ORIGIN).status_code == 422

    key = "sk-ant-api03-SUPERSECRETVALUE1234"
    status = client.put("/api/settings/secrets/ANTHROPIC_API_KEY", json={"value": key}, headers=ORIGIN).json()
    anth = next(x for x in status if x["name"] == "ANTHROPIC_API_KEY")
    assert anth["configured"] and anth["source"] == "stored" and anth["hint"] == "…1234"
    everything = client.get("/api/settings").text
    assert key not in everything and "SUPERSECRET" not in everything
    assert client.put("/api/settings/secrets/NOT_A_SECRET", json={"value": "abcdefghij"}, headers=ORIGIN).status_code == 422
    after = client.delete("/api/settings/secrets/ANTHROPIC_API_KEY", headers=ORIGIN).json()
    assert not next(x for x in after if x["name"] == "ANTHROPIC_API_KEY")["configured"]


def test_agents_activity_devices_export_erase(client: TestClient) -> None:
    agents = client.get("/api/agents").json()
    names = {a["name"] for a in agents}
    assert {"research", "file", "study", "memory", "computer", "coding", "vision", "automation"} <= names
    assert any(a["status"] == "planned" and a["title"] == "EmailAgent" for a in agents)
    client.post("/api/chat", json={"text": "remember that my favourite colour is teal"}, headers=ORIGIN)
    activity = client.get("/api/activity").json()
    assert activity["agent_runs"][0]["agent"] == "memory" and activity["tool_calls"][0]["tool"] == "remember"
    dev = client.post("/api/devices/heartbeat", json={"fingerprint": "browser_abc12345", "name": "Chrome on Linux",
                                                      "capabilities": {"microphone": True}}, headers=ORIGIN).json()
    devices = client.get("/api/devices").json()
    assert devices["host"]["name"] and devices["clients"][0]["id"] == dev["id"]
    export = client.get("/api/settings/export").json()
    assert export["memories"][0]["value"] == "teal" and export["conversations"]
    assert client.post("/api/settings/erase", json={"confirm": "nope"}, headers=ORIGIN).status_code == 422
    assert client.post("/api/settings/erase", json={"confirm": "ERASE"}, headers=ORIGIN).json()["ok"]
    assert client.get("/api/memories").json() == [] and client.get("/api/conversations").json() == []


def test_voice_endpoints_without_providers(client: TestClient) -> None:
    status = client.get("/api/voice/status").json()
    assert status["stt"]["server"] is None and status["tts"]["server"] is None
    r = client.post("/api/voice/transcribe", files={"audio": ("a.webm", b"\x1aE\xdf\xa3....", "audio/webm")},
                    headers=ORIGIN)
    assert r.status_code == 503 and r.json()["error"]["code"] == "stt_not_configured"
    r = client.post("/api/voice/speak", json={"text": "hello"}, headers=ORIGIN)
    assert r.status_code == 503 and r.json()["error"]["code"] == "tts_not_configured"
