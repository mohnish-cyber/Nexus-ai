// Server → client WebSocket events (see backend/app/api/routes/chat.py).
import type { ApiErrorBody, ChatMessage, Memory, NexusNotification, PermissionRequest } from "./api";

export type OrbState = "idle" | "listening" | "thinking" | "speaking" | "executing" | "waiting" | "completed" | "error";

export type ServerEvent =
  | { type: "ready"; user: { id: string; email: string | null; auth_mode: string } }
  | { type: "pong" }
  | { type: "status"; request_id?: string; state: string; label: string | null }
  | { type: "conversation"; request_id: string; conversation_id: string; title: string }
  | { type: "plan"; request_id: string; steps: { agent: string; instruction: string }[]; source: string }
  | {
      type: "activity";
      request_id: string;
      id: string;
      agent: string;
      action: string;
      status: "started" | "succeeded" | "failed";
      detail: string | null;
      ts: string;
    }
  | { type: "token"; request_id: string; segment: string; text: string }
  | { type: "segment_discard"; request_id: string; segment: string }
  | { type: "permission_request"; request_id: string; permission: PermissionRequest }
  | { type: "permission_resolved"; request_id: string; permission_id: string; status: string }
  | { type: "message"; request_id: string; message: ChatMessage }
  | { type: "memory_update"; request_id: string; memories: Memory[] }
  | { type: "notification"; notification: NexusNotification }
  | { type: "error"; request_id?: string; error: ApiErrorBody }
  | { type: "done"; request_id: string };

export interface ActivityItem {
  id: string;
  requestId: string;
  agent: string;
  action: string;
  status: "started" | "succeeded" | "failed";
  detail: string | null;
  ts: string;
}
