import { create } from "zustand";
import { api } from "../services/api";
import type { Preferences, SecretStatus, SettingsBundle } from "../types/api";

interface SettingsState {
  bundle: SettingsBundle | null;
  loading: boolean;
  load: () => Promise<SettingsBundle | null>;
  updateSection: <K extends keyof Preferences>(section: K, values: Partial<Preferences[K]>) => Promise<void>;
  setSecret: (name: string, value: string) => Promise<void>;
  deleteSecret: (name: string) => Promise<void>;
}

export const useSettings = create<SettingsState>((set, get) => ({
  bundle: null,
  loading: false,
  load: async () => {
    set({ loading: true });
    try {
      const bundle = await api.get<SettingsBundle>("/api/settings");
      set({ bundle });
      return bundle;
    } finally {
      set({ loading: false });
    }
  },
  updateSection: async (section, values) => {
    const preferences = await api.put<Preferences>(`/api/settings/${section}`, { values });
    const bundle = get().bundle;
    if (bundle) set({ bundle: { ...bundle, preferences } });
    if (section === "workspace") await get().load();
  },
  setSecret: async (name, value) => {
    const secrets = await api.put<SecretStatus[]>(`/api/settings/secrets/${name}`, { value });
    const bundle = get().bundle;
    if (bundle) set({ bundle: { ...bundle, secrets } });
    await get().load();
  },
  deleteSecret: async (name) => {
    const secrets = await api.del<SecretStatus[]>(`/api/settings/secrets/${name}`);
    const bundle = get().bundle;
    if (bundle) set({ bundle: { ...bundle, secrets } });
    await get().load();
  },
}));
