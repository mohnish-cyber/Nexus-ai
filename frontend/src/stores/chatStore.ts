// Conversation state driven by the WebSocket event stream.
import { create } from "zustand";
import { api } from "../services/api";
import { socket } from "../services/ws";
import type { Attachment, ChatMessage, Conversation, PermissionRequest } from "../types/api";
import type { ActivityItem, ServerEvent } from "../types/events";
import { useNotifications } from "./notificationStore";
import { useSystem } from "./systemStore";
import { useToasts } from "./toastStore";

const NEW = "__new__";

export interface LiveRequest {
  requestId: string;
  conversationKey: string;
  segments: { id: string; text: string }[];
  plan: { agent: string; instruction: string }[];
  label: string | null;
  voice: boolean;
  startedAt: number;
}

interface SendOptions {
  attachments?: Attachment[];
  voice?: boolean;
}

interface ChatState {
  conversations: Conversation[];
  currentId: string | null;
  messages: Record<string, ChatMessage[]>;
  live: Record<string, LiveRequest>;
  activity: ActivityItem[];
  permissions: PermissionRequest[];
  lastReply: { message: ChatMessage; voice: boolean; at: number } | null;
  memorySuggestions: number;
  loadConversations: () => Promise<void>;
  openConversation: (id: string) => Promise<void>;
  newConversation: () => void;
  send: (text: string, opts?: SendOptions) => string;
  cancel: (requestId: string) => void;
  decide: (permissionId: string, decision: "allow_once" | "always_allow" | "deny") => void;
  rename: (id: string, title: string) => Promise<void>;
  remove: (id: string) => Promise<void>;
  handle: (event: ServerEvent) => void;
}

function keyOf(state: ChatState): string {
  return state.currentId ?? NEW;
}

function uid(): string {
  return crypto.randomUUID().replace(/-/g, "");
}

export const useChat = create<ChatState>((set, get) => ({
  conversations: [],
  currentId: null,
  messages: {},
  live: {},
  activity: [],
  permissions: [],
  lastReply: null,
  memorySuggestions: 0,

  loadConversations: async () => {
    try {
      set({ conversations: await api.get<Conversation[]>("/api/conversations") });
    } catch (err) {
      useToasts.getState().error(err, "Couldn't load conversations");
    }
  },

  openConversation: async (id) => {
    set({ currentId: id });
    try {
      const msgs = await api.get<ChatMessage[]>(`/api/conversations/${id}/messages`);
      set((s) => ({ messages: { ...s.messages, [id]: msgs } }));
    } catch (err) {
      useToasts.getState().error(err, "Couldn't open that conversation");
    }
  },

  newConversation: () => set((s) => ({ currentId: null, messages: { ...s.messages, [NEW]: [] } })),

  send: (text, opts = {}) => {
    const requestId = uid();
    const state = get();
    const key = keyOf(state);
    const optimistic: ChatMessage = {
      id: `local-${requestId}`,
      conversation_id: state.currentId ?? "",
      role: "user",
      content: text,
      status: "complete",
      request_id: requestId,
      attachments: opts.attachments ?? [],
      actions: [],
      sources: [],
      meta: { voice: opts.voice },
      created_at: new Date().toISOString(),
    };
    set((s) => ({
      messages: { ...s.messages, [key]: [...(s.messages[key] ?? []), optimistic] },
      live: {
        ...s.live,
        [requestId]: {
          requestId,
          conversationKey: key,
          segments: [],
          plan: [],
          label: "Understanding your request",
          voice: !!opts.voice,
          startedAt: Date.now(),
        },
      },
    }));
    useSystem.getState().setOrb("thinking", "Thinking…");
    socket.send({
      type: "chat",
      request_id: requestId,
      text,
      conversation_id: state.currentId,
      attachments: (opts.attachments ?? []).map((a) => a.id),
      voice: !!opts.voice,
    });
    return requestId;
  },

  cancel: (requestId) => socket.send({ type: "cancel", request_id: requestId }),

  decide: (permissionId, decision) => {
    socket.send({ type: "permission_decision", permission_id: permissionId, decision });
    set((s) => ({ permissions: s.permissions.filter((p) => p.id !== permissionId) }));
  },

  rename: async (id, title) => {
    await api.patch(`/api/conversations/${id}`, { title });
    set((s) => ({ conversations: s.conversations.map((c) => (c.id === id ? { ...c, title } : c)) }));
  },

  remove: async (id) => {
    await api.del(`/api/conversations/${id}`);
    set((s) => {
      const messages = { ...s.messages };
      delete messages[id];
      return {
        conversations: s.conversations.filter((c) => c.id !== id),
        messages,
        currentId: s.currentId === id ? null : s.currentId,
      };
    });
  },

  handle: (event) => {
    const sys = useSystem.getState();
    switch (event.type) {
      case "status": {
        const map: Record<string, Parameters<typeof sys.setOrb>[0]> = {
          thinking: "thinking",
          executing: "executing",
          waiting: "waiting",
          completed: "completed",
          error: "error",
          idle: "idle",
        };
        const orb = map[event.state];
        if (orb && sys.orb !== "listening") sys.setOrb(orb, event.label);
        if (event.request_id && event.label) {
          const rid = event.request_id;
          set((s) => (s.live[rid] ? { live: { ...s.live, [rid]: { ...s.live[rid], label: event.label } } } : {}));
        }
        break;
      }
      case "conversation": {
        const live = get().live[event.request_id];
        set((s) => {
          const messages = { ...s.messages };
          if (live && live.conversationKey === NEW) {
            messages[event.conversation_id] = [...(messages[event.conversation_id] ?? []), ...(messages[NEW] ?? [])];
            delete messages[NEW];
          }
          const exists = s.conversations.some((c) => c.id === event.conversation_id);
          const now = new Date().toISOString();
          return {
            messages,
            currentId: live && live.conversationKey === NEW && s.currentId === null ? event.conversation_id : s.currentId,
            live: live ? { ...s.live, [event.request_id]: { ...live, conversationKey: event.conversation_id } } : s.live,
            conversations: exists
              ? s.conversations.map((c) => (c.id === event.conversation_id ? { ...c, updated_at: now } : c))
              : [{ id: event.conversation_id, title: event.title, archived: false, created_at: now, updated_at: now,
                   message_count: 1 }, ...s.conversations],
          };
        });
        break;
      }
      case "plan":
        set((s) => {
          const live = s.live[event.request_id];
          return live ? { live: { ...s.live, [event.request_id]: { ...live, plan: event.steps } } } : {};
        });
        break;
      case "activity":
        set((s) => {
          const item: ActivityItem = {
            id: event.id, requestId: event.request_id, agent: event.agent, action: event.action,
            status: event.status, detail: event.detail, ts: event.ts,
          };
          const idx = s.activity.findIndex((a) => a.id === event.id);
          const activity = idx >= 0
            ? s.activity.map((a, i) => (i === idx ? item : a))
            : [item, ...s.activity].slice(0, 120);
          return { activity };
        });
        break;
      case "token":
        set((s) => {
          const live = s.live[event.request_id];
          if (!live) return {};
          const segments = [...live.segments];
          const seg = segments.find((x) => x.id === event.segment);
          if (seg) seg.text += event.text;
          else segments.push({ id: event.segment, text: event.text });
          return { live: { ...s.live, [event.request_id]: { ...live, segments } } };
        });
        if (sys.orb !== "speaking" && sys.orb !== "listening") sys.setOrb("thinking", "Responding…");
        break;
      case "segment_discard":
        set((s) => {
          const live = s.live[event.request_id];
          if (!live) return {};
          return {
            live: { ...s.live, [event.request_id]: { ...live, segments: live.segments.filter((x) => x.id !== event.segment) } },
          };
        });
        break;
      case "permission_request":
        set((s) => ({ permissions: [...s.permissions, { ...event.permission, request_id: event.request_id }] }));
        break;
      case "permission_resolved":
        set((s) => ({ permissions: s.permissions.filter((p) => p.id !== event.permission_id) }));
        break;
      case "message": {
        const live = get().live[event.request_id];
        const msg = event.message;
        const key = msg.conversation_id || live?.conversationKey || keyOf(get());
        set((s) => ({
          messages: { ...s.messages, [key]: [...(s.messages[key] ?? []).filter((m) => m.id !== msg.id), msg] },
          lastReply: { message: msg, voice: !!live?.voice, at: Date.now() },
        }));
        break;
      }
      case "memory_update":
        set((s) => ({ memorySuggestions: s.memorySuggestions + event.memories.filter((m) => m.status === "pending").length }));
        if (event.memories.some((m) => m.status === "pending")) {
          useToasts.getState().push({
            kind: "info",
            title: "Memory suggestion",
            body: `NEXUS noticed something worth remembering (“${event.memories[0].subject}”). Approve it on the Memory page.`,
          });
        }
        break;
      case "notification":
        useNotifications.getState().receive(event.notification);
        break;
      case "error":
        useToasts.getState().push({
          kind: "error",
          title: event.error.message,
          detail: [event.error.reason, event.error.next_step].filter(Boolean).join(" · ") || undefined,
        });
        break;
      case "done":
        set((s) => {
          const live = { ...s.live };
          delete live[event.request_id];
          return { live, permissions: s.permissions.filter((p) => p.request_id !== event.request_id) };
        });
        break;
      default:
        break;
    }
  },
}));

export function currentMessages(state: ChatState): ChatMessage[] {
  return state.messages[keyOf(state)] ?? [];
}

export function liveForCurrent(state: ChatState): LiveRequest[] {
  const key = keyOf(state);
  return Object.values(state.live).filter((l) => l.conversationKey === key);
}
