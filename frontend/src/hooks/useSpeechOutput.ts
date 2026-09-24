// Speaks NEXUS's replies when the request came from voice, or when auto-speak is on.
import { useEffect, useRef } from "react";
import { speak } from "../services/voice/speech";
import { useChat } from "../stores/chatStore";
import { useSettings } from "../stores/settingsStore";
import { useSystem } from "../stores/systemStore";
import { useVoice } from "../stores/voiceStore";

export function useSpeechOutput(): void {
  const lastReply = useChat((s) => s.lastReply);
  const seen = useRef<number>(0);

  useEffect(() => {
    if (!lastReply || lastReply.at === seen.current) return;
    seen.current = lastReply.at;
    const prefs = useSettings.getState().bundle?.preferences.voice;
    if (!lastReply.voice && !prefs?.auto_speak) return;
    const sys = useSystem.getState();
    const provider = prefs?.tts_provider === "server" && useVoice.getState().serverTts ? "server" : "browser";
    sys.setOrb("speaking", "Speaking…");
    speak(lastReply.message.content, provider, {
      voiceName: prefs?.voice_name,
      rate: prefs?.rate,
      pitch: prefs?.pitch,
      onLevel: (l) => useSystem.getState().setAudioLevel(l),
    })
      .catch(() => undefined)
      .finally(() => {
        if (useSystem.getState().orb === "speaking") useSystem.getState().setOrb("idle");
        useSystem.getState().setAudioLevel(0);
      });
  }, [lastReply]);
}
