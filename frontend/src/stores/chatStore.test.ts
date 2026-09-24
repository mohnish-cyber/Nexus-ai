import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../services/ws", () => ({ socket: { send: vi.fn(), onEvent: vi.fn(), onState: vi.fn() } }));

import { socket } from "../services/ws";
import type { ChatMessage } from "../types/api";
import { currentMessages, liveForCurrent, useChat } from "./chatStore";

function reply(conversationId: string, requestId: string, content: string): ChatMessage {
  return {
    id: `m-${requestId}`, conversation_id: conversationId, role: "assistant", content, status: "complete",
    request_id: requestId, attachments: [], actions: [], sources: [], meta: {}, created_at: new Date().toISOString(),
  };
}

describe("chat store event stream", () => {
  beforeEach(() => {
    useChat.setState({ conversations: [], currentId: null, messages: {}, live: {}, activity: [], permissions: [], lastReply: null });
    vi.mocked(socket.send).mockClear();
  });

  it("sends, streams, discards interim segments and settles on the final message", () => {
    const rid = useChat.getState().send("How are you?");
    expect(socket.send).toHaveBeenCalledWith(expect.objectContaining({ type: "chat", request_id: rid, text: "How are you?" }));
    expect(currentMessages(useChat.getState())).toHaveLength(1);

    const { handle } = useChat.getState();
    handle({ type: "conversation", request_id: rid, conversation_id: "c1", title: "How are you?" });
    expect(useChat.getState().currentId).toBe("c1");
    expect(useChat.getState().messages.c1).toHaveLength(1); // optimistic message moved from the draft

    handle({ type: "token", request_id: rid, segment: "s1", text: "Let me check…" });
    handle({ type: "segment_discard", request_id: rid, segment: "s1" });
    handle({ type: "token", request_id: rid, segment: "s2", text: "Doing " });
    handle({ type: "token", request_id: rid, segment: "s2", text: "well." });
    const live = liveForCurrent(useChat.getState());
    expect(live[0].segments.map((s) => s.text).join("")).toBe("Doing well.");

    handle({ type: "message", request_id: rid, message: reply("c1", rid, "Doing well.") });
    handle({ type: "done", request_id: rid });
    const state = useChat.getState();
    expect(state.messages.c1.map((m) => m.role)).toEqual(["user", "assistant"]);
    expect(Object.keys(state.live)).toHaveLength(0);
    expect(state.lastReply?.message.content).toBe("Doing well.");
  });

  it("queues permission requests and clears them on decision or completion", () => {
    const { handle } = useChat.getState();
    const perm = {
      id: "p1", tool: "delete_path", agent: "ComputerAgent", risk: "high" as const, summary: "Delete x", reason: null,
      details: {}, scope: "x", allow_always: false, expires_at: new Date(Date.now() + 60000).toISOString(),
    };
    handle({ type: "permission_request", request_id: "r1", permission: perm });
    expect(useChat.getState().permissions).toHaveLength(1);
    useChat.getState().decide("p1", "deny");
    expect(socket.send).toHaveBeenCalledWith({ type: "permission_decision", permission_id: "p1", decision: "deny" });
    expect(useChat.getState().permissions).toHaveLength(0);
    handle({ type: "permission_request", request_id: "r1", permission: { ...perm, id: "p2" } });
    handle({ type: "done", request_id: "r1" });
    expect(useChat.getState().permissions).toHaveLength(0);
  });

  it("updates activity items in place", () => {
    const { handle } = useChat.getState();
    const base = { type: "activity" as const, request_id: "r", id: "a1", agent: "ResearchAgent", action: "Searching", detail: null, ts: "" };
    handle({ ...base, status: "started" });
    handle({ ...base, status: "succeeded", action: "Found 5 results" });
    const activity = useChat.getState().activity;
    expect(activity).toHaveLength(1);
    expect(activity[0]).toMatchObject({ status: "succeeded", action: "Found 5 results" });
  });
});
