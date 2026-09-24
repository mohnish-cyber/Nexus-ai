// Connects the WebSocket and keeps shared state fresh while the app is open.
import { useEffect } from "react";
import { api } from "../services/api";
import { socket } from "../services/ws";
import { useChat } from "../stores/chatStore";
import { useNotifications } from "../stores/notificationStore";
import { useSettings } from "../stores/settingsStore";
import { useSystem } from "../stores/systemStore";
import { useVoice } from "../stores/voiceStore";

function deviceFingerprint(): string {
  try {
    let id = localStorage.getItem("nexus.device");
    if (!id) {
      id = `web_${crypto.randomUUID().replace(/-/g, "")}`;
      localStorage.setItem("nexus.device", id);
    }
    return id;
  } catch {
    return "web_ephemeral_session";
  }
}

function deviceName(): string {
  const ua = navigator.userAgent;
  const browser = /Edg\//.test(ua) ? "Edge" : /Chrome\//.test(ua) ? "Chrome" : /Firefox\//.test(ua) ? "Firefox" : /Safari\//.test(ua) ? "Safari" : "Browser";
  const os = /Android/.test(ua) ? "Android" : /iPhone|iPad/.test(ua) ? "iOS" : /Mac OS/.test(ua) ? "macOS" : /Windows/.test(ua) ? "Windows" : /Linux/.test(ua) ? "Linux" : "device";
  return `${browser} on ${os}`;
}

async function heartbeat(): Promise<void> {
  const mobile = /Android|iPhone|iPad/.test(navigator.userAgent);
  await api.post("/api/devices/heartbeat", {
    fingerprint: deviceFingerprint(),
    name: deviceName(),
    kind: mobile ? "phone" : "browser",
    platform: navigator.platform || null,
    capabilities: {
      microphone: !!navigator.mediaDevices?.getUserMedia,
      speech_recognition: "webkitSpeechRecognition" in window || "SpeechRecognition" in window,
      speech_synthesis: "speechSynthesis" in window,
      screen_capture: !!navigator.mediaDevices?.getDisplayMedia,
      notifications: typeof Notification !== "undefined",
    },
  }).catch(() => undefined);
}

export function useBackgroundSync(): void {
  useEffect(() => {
    const offEvent = socket.onEvent((ev) => useChat.getState().handle(ev));
    const offState = socket.onState((s) => {
      useSystem.getState().setConnection(s);
      if (s === "open") void useNotifications.getState().load();
    });
    socket.connect();

    void useSettings.getState().load().then((bundle) => {
      if (!bundle) return;
      if (bundle.preferences.voice.wake_word_enabled) useVoice.getState().setWake(true);
      // Remember the user's real timezone so "tomorrow at 8 AM" means their 8 AM.
      const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
      if (!bundle.preferences.regional.timezone && tz) void useSettings.getState().updateSection("regional", { timezone: tz });
    }).catch(() => undefined);
    void useChat.getState().loadConversations();
    void useNotifications.getState().load();
    void useVoice.getState().loadStatus();
    void useSystem.getState().loadTelemetry();
    void heartbeat();

    const telemetry = window.setInterval(() => {
      if (document.visibilityState === "visible") void useSystem.getState().loadTelemetry();
    }, 5000);
    const status = window.setInterval(() => {
      if (document.visibilityState === "visible") void useSystem.getState().loadStatus();
    }, 60000);
    const beat = window.setInterval(() => void heartbeat(), 5 * 60 * 1000);

    const onKey = (e: KeyboardEvent) => {
      // Ctrl/⌘ + Shift + Space: push-to-talk from anywhere
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.code === "Space") {
        e.preventDefault();
        void useVoice.getState().toggle();
      }
    };
    window.addEventListener("keydown", onKey);

    return () => {
      offEvent();
      offState();
      window.clearInterval(telemetry);
      window.clearInterval(status);
      window.clearInterval(beat);
      window.removeEventListener("keydown", onKey);
    };
  }, []);
}
