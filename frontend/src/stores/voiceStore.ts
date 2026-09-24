// Voice controller shared by the composer, the orb and the wake word.
import { create } from "zustand";
import { ApiError, api } from "../services/api";
import { MicRecorder, transcribeOnServer } from "../services/voice/recorder";
import { stopSpeaking } from "../services/voice/speech";
import { speechRecognitionCtor, type SpeechRecognitionLike } from "../services/voice/speechTypes";
import { WakeWordListener } from "../services/voice/wakeword";
import { useChat } from "./chatStore";
import { useSettings } from "./settingsStore";
import { useSystem } from "./systemStore";
import { useToasts } from "./toastStore";

interface VoiceStatus {
  stt: { server: string | null };
  tts: { server: string | null };
}

interface VoiceState {
  listening: boolean;
  transcribing: boolean;
  interim: string;
  engine: "server" | "browser" | null;
  serverStt: string | null;
  serverTts: string | null;
  wakeActive: boolean;
  loadStatus: () => Promise<void>;
  start: () => Promise<void>;
  stop: () => Promise<void>;
  cancel: () => void;
  toggle: () => Promise<void>;
  setWake: (on: boolean) => void;
}

let recorder: MicRecorder | null = null;
let recognition: SpeechRecognitionLike | null = null;
let finalText = "";
const wake = new WakeWordListener();

function chooseEngine(serverStt: string | null): "server" | "browser" | null {
  const pref = useSettings.getState().bundle?.preferences.voice.stt_provider ?? "auto";
  const browser = speechRecognitionCtor() !== null;
  if (pref === "server") return serverStt ? "server" : null;
  if (pref === "browser") return browser ? "browser" : null;
  if (serverStt) return "server";
  return browser ? "browser" : null;
}

function submit(text: string): void {
  const clean = text.trim();
  if (!clean) {
    useToasts.getState().push({ kind: "info", title: "I didn't catch that", body: "Try again a little closer to the microphone." });
    useSystem.getState().setOrb("idle");
    return;
  }
  useChat.getState().send(clean, { voice: true });
}

export const useVoice = create<VoiceState>((set, get) => ({
  listening: false,
  transcribing: false,
  interim: "",
  engine: null,
  serverStt: null,
  serverTts: null,
  wakeActive: false,

  loadStatus: async () => {
    try {
      const s = await api.get<VoiceStatus>("/api/voice/status");
      set({ serverStt: s.stt.server, serverTts: s.tts.server });
    } catch {
      set({ serverStt: null, serverTts: null });
    }
  },

  start: async () => {
    if (get().listening || get().transcribing) return;
    stopSpeaking();
    const engine = chooseEngine(get().serverStt);
    if (!engine) {
      useToasts.getState().push({
        kind: "error",
        title: "Voice input isn't available",
        detail: "This browser has no speech recognition and server speech-to-text isn't configured. Use Chrome/Edge, or add an OpenAI key (Whisper) in Settings.",
      });
      return;
    }
    wake.pause();
    const sys = useSystem.getState();
    finalText = "";
    set({ listening: true, interim: "", engine });
    sys.setOrb("listening", "Listening…");
    try {
      if (engine === "server") {
        recorder = new MicRecorder();
        await recorder.start((level) => useSystem.getState().setAudioLevel(level));
      } else {
        const Ctor = speechRecognitionCtor()!;
        recognition = new Ctor();
        recognition.lang = navigator.language || "en-US";
        recognition.interimResults = true;
        recognition.continuous = false;
        recognition.onresult = (ev) => {
          let interim = "";
          for (let i = ev.resultIndex; i < ev.results.length; i++) {
            const r = ev.results[i];
            if (r.isFinal) finalText += r[0].transcript;
            else interim += r[0].transcript;
          }
          set({ interim: (finalText + " " + interim).trim() });
          useSystem.getState().setAudioLevel(0.35 + Math.random() * 0.4);
        };
        recognition.onerror = (ev) => {
          if (ev.error === "not-allowed") {
            useToasts.getState().push({ kind: "error", title: "Microphone permission was denied",
              detail: "Allow microphone access for this site in your browser settings." });
          } else if (ev.error && ev.error !== "no-speech" && ev.error !== "aborted") {
            useToasts.getState().push({ kind: "error", title: "Speech recognition failed", detail: ev.error });
          }
        };
        recognition.onend = () => {
          const text = finalText || get().interim;
          recognition = null;
          set({ listening: false, interim: "" });
          useSystem.getState().setAudioLevel(0);
          wake.resume();
          submit(text);
        };
        recognition.start();
      }
    } catch (err) {
      set({ listening: false });
      sys.setOrb("error", ApiError.from(err).message);
      useToasts.getState().error(err);
      wake.resume();
    }
  },

  stop: async () => {
    if (!get().listening) return;
    if (get().engine === "browser") {
      recognition?.stop(); // onend submits
      return;
    }
    const rec = recorder;
    recorder = null;
    set({ listening: false, transcribing: true });
    useSystem.getState().setAudioLevel(0);
    useSystem.getState().setOrb("thinking", "Transcribing…");
    try {
      const audio = await rec!.stop();
      const text = audio.size > 1000 ? await transcribeOnServer(audio) : "";
      submit(text);
    } catch (err) {
      useSystem.getState().setOrb("error", "Transcription failed");
      useToasts.getState().error(err, "Couldn't transcribe your voice");
    } finally {
      set({ transcribing: false });
      wake.resume();
    }
  },

  cancel: () => {
    recorder?.cancel();
    recorder = null;
    recognition?.abort();
    recognition = null;
    set({ listening: false, transcribing: false, interim: "" });
    useSystem.getState().setAudioLevel(0);
    useSystem.getState().setOrb("idle");
    wake.resume();
  },

  toggle: async () => (get().listening ? get().stop() : get().start()),

  setWake: (on) => {
    if (on && !get().wakeActive) {
      wake.start(
        (rest) => {
          useToasts.getState().push({ kind: "info", title: "Yes?", body: "Listening…", timeout: 2500 });
          if (rest.split(" ").length >= 3) submit(rest);
          else void get().start();
        },
        (msg) => {
          set({ wakeActive: false });
          useToasts.getState().push({ kind: "error", title: "Wake word unavailable", detail: msg });
        },
      );
      set({ wakeActive: true });
    } else if (!on && get().wakeActive) {
      wake.stop();
      set({ wakeActive: false });
    }
  },
}));
