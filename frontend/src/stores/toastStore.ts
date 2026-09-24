import { create } from "zustand";
import { ApiError } from "../services/api";

export interface Toast {
  id: number;
  kind: "info" | "success" | "error" | "reminder";
  title: string;
  body?: string;
  detail?: string;
  timeout?: number;
}

interface ToastState {
  toasts: Toast[];
  push: (toast: Omit<Toast, "id">) => void;
  dismiss: (id: number) => void;
  error: (err: unknown, title?: string) => void;
}

let nextId = 1;

export const useToasts = create<ToastState>((set, get) => ({
  toasts: [],
  push: (toast) => {
    const id = nextId++;
    set((s) => ({ toasts: [...s.toasts.slice(-4), { ...toast, id }] }));
    const timeout = toast.timeout ?? (toast.kind === "error" ? 9000 : toast.kind === "reminder" ? 20000 : 5000);
    if (timeout > 0) window.setTimeout(() => get().dismiss(id), timeout);
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
  error: (err, title) => {
    const e = ApiError.from(err);
    const detail = [e.reason, e.nextStep].filter(Boolean).join(" · ");
    get().push({ kind: "error", title: title ?? e.message, body: title ? e.message : undefined, detail });
  },
}));
