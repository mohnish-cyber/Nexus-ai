// Text-to-speech: browser voices by default, server voices (OpenAI/ElevenLabs) when configured.
import { api } from "../api";

export function speakable(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, " (code omitted) ")
    .replace(/`([^`]*)`/g, "$1")
    .replace(/!\[[^\]]*\]\([^)]*\)/g, "")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/^\s{0,3}#{1,6}\s*/gm, "")
    .replace(/^\s*[-*+]\s+/gm, "")
    .replace(/^\s*>\s?/gm, "")
    .replace(/\|/g, " ")
    .replace(/[*_~]/g, "")
    .replace(/⚠️/g, "")
    .replace(/\n{2,}/g, ". ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 4000);
}

export interface SpeakOptions {
  voiceName?: string | null;
  rate?: number;
  pitch?: number;
  onLevel?: (level: number) => void;
}

let currentAudio: HTMLAudioElement | null = null;
let pulseTimer = 0;

export function browserVoices(): SpeechSynthesisVoice[] {
  return typeof speechSynthesis === "undefined" ? [] : speechSynthesis.getVoices();
}

export function stopSpeaking(): void {
  if (typeof speechSynthesis !== "undefined") speechSynthesis.cancel();
  currentAudio?.pause();
  currentAudio = null;
  window.clearInterval(pulseTimer);
}

function speakBrowser(text: string, opts: SpeakOptions): Promise<void> {
  return new Promise((resolve, reject) => {
    if (typeof speechSynthesis === "undefined") {
      reject(new Error("This browser has no speech synthesis."));
      return;
    }
    speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(text);
    const voice = browserVoices().find((v) => v.name === opts.voiceName)
      ?? browserVoices().find((v) => /en[-_](GB|US|IN)/i.test(v.lang) && /natural|neural|google|samantha|daniel/i.test(v.name))
      ?? null;
    if (voice) utter.voice = voice;
    utter.rate = opts.rate ?? 1;
    utter.pitch = opts.pitch ?? 1;
    // Speech synthesis exposes no audio samples; word boundaries drive a gentle pulse instead.
    utter.onboundary = () => opts.onLevel?.(0.55 + Math.random() * 0.35);
    pulseTimer = window.setInterval(() => opts.onLevel?.(0.15 + Math.random() * 0.2), 140);
    utter.onend = () => {
      window.clearInterval(pulseTimer);
      opts.onLevel?.(0);
      resolve();
    };
    utter.onerror = (e) => {
      window.clearInterval(pulseTimer);
      opts.onLevel?.(0);
      if (e.error === "interrupted" || e.error === "canceled") resolve();
      else reject(new Error(`Speech failed: ${e.error}`));
    };
    speechSynthesis.speak(utter);
  });
}

async function speakServer(text: string, opts: SpeakOptions): Promise<void> {
  const blob = await api.blob("/api/voice/speak", { text });
  const url = URL.createObjectURL(blob);
  const audio = new Audio(url);
  currentAudio = audio;
  let ctx: AudioContext | null = null;
  try {
    ctx = new AudioContext();
    const src = ctx.createMediaElementSource(audio);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    src.connect(analyser);
    analyser.connect(ctx.destination);
    const data = new Uint8Array(analyser.frequencyBinCount);
    const tick = () => {
      if (audio.paused || audio.ended) return;
      analyser.getByteFrequencyData(data);
      opts.onLevel?.(Math.min(1, data.reduce((a, b) => a + b, 0) / data.length / 90));
      requestAnimationFrame(tick);
    };
    audio.onplay = () => tick();
  } catch {
    /* the analyser only drives the orb animation */
  }
  const cleanup = () => {
    opts.onLevel?.(0);
    URL.revokeObjectURL(url);
    void ctx?.close().catch(() => undefined);
  };
  await new Promise<void>((resolve, reject) => {
    audio.onended = () => {
      cleanup();
      resolve();
    };
    audio.onerror = () => {
      cleanup();
      reject(new Error("Audio playback failed."));
    };
    audio.play().catch((err) => {
      cleanup();
      reject(err);
    });
  });
}

export async function speak(text: string, provider: "browser" | "server", opts: SpeakOptions = {}): Promise<void> {
  const clean = speakable(text);
  if (!clean) return;
  stopSpeaking();
  if (provider === "server") {
    try {
      await speakServer(clean, opts);
      return;
    } catch {
      /* fall back to the browser voice */
    }
  }
  await speakBrowser(clean, opts);
}
