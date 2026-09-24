// WebSocket client with authentication, heartbeats and automatic reconnection.
import type { ServerEvent } from "../types/events";
import { currentToken } from "./api";

export type ConnectionState = "connecting" | "open" | "closed";

type Listener = (event: ServerEvent) => void;
type StateListener = (state: ConnectionState) => void;

function wsUrl(): string {
  const base = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "");
  if (base) return base.replace(/^http/, "ws") + "/ws";
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/ws`;
}

export class NexusSocket {
  private ws: WebSocket | null = null;
  private listeners = new Set<Listener>();
  private stateListeners = new Set<StateListener>();
  private queue: string[] = [];
  private retry = 0;
  private heartbeat: number | null = null;
  private reconnectTimer: number | null = null;
  private stopped = false;
  private ready = false;
  state: ConnectionState = "closed";

  connect(): void {
    this.stopped = false;
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) return;
    this.setState("connecting");
    const ws = new WebSocket(wsUrl());
    this.ws = ws;
    ws.onopen = async () => {
      ws.send(JSON.stringify({ type: "auth", token: await currentToken() }));
    };
    ws.onmessage = (msg) => {
      let event: ServerEvent;
      try {
        event = JSON.parse(msg.data as string) as ServerEvent;
      } catch {
        return;
      }
      if (event.type === "ready") {
        this.ready = true;
        this.retry = 0;
        this.setState("open");
        for (const item of this.queue.splice(0)) ws.send(item);
        this.startHeartbeat();
      }
      for (const l of this.listeners) l(event);
    };
    ws.onclose = (ev) => {
      this.ready = false;
      this.stopHeartbeat();
      this.setState("closed");
      if (this.stopped) return;
      if (ev.code === 4401 || ev.code === 4403) {
        // Auth/origin rejection: retry slowly (e.g. after sign-in).
        this.scheduleReconnect(15000);
        return;
      }
      this.scheduleReconnect(Math.min(15000, 500 * 2 ** this.retry++));
    };
    ws.onerror = () => ws.close();
  }

  private scheduleReconnect(delay: number): void {
    if (this.reconnectTimer) window.clearTimeout(this.reconnectTimer);
    this.reconnectTimer = window.setTimeout(() => this.connect(), delay);
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeat = window.setInterval(() => this.send({ type: "ping" }), 25000);
  }

  private stopHeartbeat(): void {
    if (this.heartbeat) window.clearInterval(this.heartbeat);
    this.heartbeat = null;
  }

  private setState(state: ConnectionState): void {
    this.state = state;
    for (const l of this.stateListeners) l(state);
  }

  send(payload: Record<string, unknown>): void {
    const data = JSON.stringify(payload);
    if (this.ws && this.ready && this.ws.readyState === WebSocket.OPEN) this.ws.send(data);
    else {
      this.queue.push(data);
      this.connect();
    }
  }

  onEvent(fn: Listener): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  onState(fn: StateListener): () => void {
    this.stateListeners.add(fn);
    return () => this.stateListeners.delete(fn);
  }

  close(): void {
    this.stopped = true;
    this.stopHeartbeat();
    if (this.reconnectTimer) window.clearTimeout(this.reconnectTimer);
    this.ws?.close();
  }

  reconnect(): void {
    this.ws?.close();
    this.retry = 0;
    this.connect();
  }
}

export const socket = new NexusSocket();
