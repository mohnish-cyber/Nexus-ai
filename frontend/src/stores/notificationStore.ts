import { create } from "zustand";
import { api } from "../services/api";
import type { NexusNotification } from "../types/api";
import { useToasts } from "./toastStore";

interface NotificationState {
  items: NexusNotification[];
  load: () => Promise<void>;
  receive: (n: NexusNotification) => void;
  markAllRead: () => Promise<void>;
}

function browserNotify(n: NexusNotification): void {
  if (typeof Notification === "undefined" || Notification.permission !== "granted") return;
  if (document.visibilityState === "visible") return;
  try {
    new Notification(`NEXUS · ${n.title}`, { body: n.body.slice(0, 240), tag: n.id });
  } catch {
    /* some browsers require a service worker; the in-app toast still shows */
  }
}

export const useNotifications = create<NotificationState>((set, get) => ({
  items: [],
  load: async () => {
    try {
      set({ items: await api.get<NexusNotification[]>("/api/notifications") });
    } catch {
      /* shown elsewhere via connection state */
    }
  },
  receive: (n) => {
    if (get().items.some((x) => x.id === n.id)) return;
    set((s) => ({ items: [n, ...s.items].slice(0, 100) }));
    useToasts.getState().push({
      kind: n.kind === "reminder" ? "reminder" : "info",
      title: n.title,
      body: n.body.length > 280 ? `${n.body.slice(0, 280)}…` : n.body,
    });
    browserNotify(n);
  },
  markAllRead: async () => {
    await api.post("/api/notifications/read", {});
    set((s) => ({ items: s.items.map((n) => ({ ...n, status: "read" as const })) }));
  },
}));
