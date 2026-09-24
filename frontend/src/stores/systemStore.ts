import { create } from "zustand";
import { api } from "../services/api";
import type { ConnectionState } from "../services/ws";
import type { PublicConfig, SystemStatus, Telemetry } from "../types/api";
import type { OrbState } from "../types/events";

interface SystemState {
  config: PublicConfig | null;
  status: SystemStatus | null;
  statusError: string | null;
  telemetry: Telemetry | null;
  connection: ConnectionState;
  orb: OrbState;
  orbLabel: string | null;
  audioLevel: number; // 0..1, microphone or speech output level
  loadConfig: () => Promise<PublicConfig>;
  loadStatus: () => Promise<SystemStatus | null>;
  loadTelemetry: () => Promise<void>;
  setConnection: (c: ConnectionState) => void;
  setOrb: (state: OrbState, label?: string | null) => void;
  setAudioLevel: (level: number) => void;
}

let resetTimer: number | null = null;

export const useSystem = create<SystemState>((set, get) => ({
  config: null,
  status: null,
  statusError: null,
  telemetry: null,
  connection: "closed",
  orb: "idle",
  orbLabel: null,
  audioLevel: 0,
  loadConfig: async () => {
    const config = await api.get<PublicConfig>("/api/system/config");
    set({ config });
    return config;
  },
  loadStatus: async () => {
    try {
      const status = await api.get<SystemStatus>("/api/system/status");
      set({ status, statusError: null });
      return status;
    } catch (err) {
      set({ statusError: err instanceof Error ? err.message : String(err) });
      return null;
    }
  },
  loadTelemetry: async () => {
    try {
      set({ telemetry: await api.get<Telemetry>("/api/system/telemetry") });
    } catch {
      /* telemetry is optional; keep the last value */
    }
  },
  setConnection: (connection) => set({ connection }),
  setOrb: (orb, label = null) => {
    if (resetTimer) window.clearTimeout(resetTimer);
    set({ orb, orbLabel: label });
    // Transient states settle back to idle.
    if (orb === "completed" || orb === "error") {
      resetTimer = window.setTimeout(() => {
        if (get().orb === orb) set({ orb: "idle", orbLabel: null });
      }, orb === "error" ? 4000 : 1800);
    }
  },
  setAudioLevel: (audioLevel) => set({ audioLevel }),
}));
