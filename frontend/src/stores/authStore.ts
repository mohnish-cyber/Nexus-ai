// Authentication: nothing to do in local mode; Supabase Auth in multi-user mode.
import type { Session, SupabaseClient } from "@supabase/supabase-js";
import { create } from "zustand";
import { setTokenProvider } from "../services/api";
import type { PublicConfig } from "../types/api";

interface AuthState {
  mode: "local" | "supabase" | null;
  session: Session | null;
  ready: boolean;
  client: SupabaseClient | null;
  init: (config: PublicConfig) => Promise<void>;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string) => Promise<string>;
  magicLink: (email: string) => Promise<void>;
  signOut: () => Promise<void>;
}

export const useAuth = create<AuthState>((set, get) => ({
  mode: null,
  session: null,
  ready: false,
  client: null,
  init: async (config) => {
    if (config.auth_mode === "local") {
      setTokenProvider(async () => null);
      set({ mode: "local", ready: true });
      return;
    }
    if (!config.supabase_url || !config.supabase_anon_key) {
      set({ mode: "supabase", ready: true });
      return;
    }
    // Loaded only in multi-user mode to keep the local bundle small.
    const { createClient } = await import("@supabase/supabase-js");
    const client = createClient(config.supabase_url, config.supabase_anon_key, {
      auth: { persistSession: true, autoRefreshToken: true },
    });
    const { data } = await client.auth.getSession();
    setTokenProvider(async () => (await client.auth.getSession()).data.session?.access_token ?? null);
    client.auth.onAuthStateChange((_event, session) => set({ session }));
    set({ mode: "supabase", client, session: data.session, ready: true });
  },
  signIn: async (email, password) => {
    const client = get().client;
    if (!client) throw new Error("Supabase is not configured on the server.");
    const { error } = await client.auth.signInWithPassword({ email, password });
    if (error) throw error;
  },
  signUp: async (email, password) => {
    const client = get().client;
    if (!client) throw new Error("Supabase is not configured on the server.");
    const { data, error } = await client.auth.signUp({ email, password });
    if (error) throw error;
    return data.session ? "Account created." : "Check your email to confirm your account.";
  },
  magicLink: async (email) => {
    const client = get().client;
    if (!client) throw new Error("Supabase is not configured on the server.");
    const { error } = await client.auth.signInWithOtp({ email, options: { emailRedirectTo: window.location.origin } });
    if (error) throw error;
  },
  signOut: async () => {
    await get().client?.auth.signOut();
    set({ session: null });
  },
}));
