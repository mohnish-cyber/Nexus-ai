// Experimental "Hey Nexus" wake phrase using the browser's speech recognition.
// Opt-in only. The architecture allows swapping in Porcupine / openWakeWord in a
// desktop build; this engine needs a Chromium-based browser and an internet connection.
import { speechRecognitionCtor, type SpeechRecognitionLike } from "./speechTypes";

const WAKE_RE = /\b(hey|hi|okay|ok)[,\s]+(nexus|nexxus|next us|nexis)\b/i;

export class WakeWordListener {
  private rec: SpeechRecognitionLike | null = null;
  private active = false;
  private paused = false;

  static supported(): boolean {
    return speechRecognitionCtor() !== null;
  }

  start(onWake: (rest: string) => void, onError: (msg: string) => void): void {
    const Ctor = speechRecognitionCtor();
    if (!Ctor) {
      onError("Wake word needs a browser with speech recognition (Chrome or Edge).");
      return;
    }
    this.active = true;
    const rec = new Ctor();
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = navigator.language || "en-US";
    rec.onresult = (ev) => {
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        const transcript = ev.results[i][0].transcript;
        const m = WAKE_RE.exec(transcript);
        if (m && ev.results[i].isFinal) {
          const rest = transcript.slice(m.index + m[0].length).replace(/^[\s,.!]+/, "");
          onWake(rest);
        }
      }
    };
    rec.onerror = (ev) => {
      if (ev.error === "not-allowed" || ev.error === "service-not-allowed") {
        this.active = false;
        onError("Microphone permission is needed for the wake word.");
      }
    };
    rec.onend = () => {
      if (this.active && !this.paused) {
        window.setTimeout(() => {
          try {
            rec.start();
          } catch {
            /* already started */
          }
        }, 300);
      }
    };
    this.rec = rec;
    try {
      rec.start();
    } catch {
      /* already started */
    }
  }

  pause(): void {
    this.paused = true;
    this.rec?.abort();
  }

  resume(): void {
    if (!this.active) return;
    this.paused = false;
    try {
      this.rec?.start();
    } catch {
      /* already running */
    }
  }

  stop(): void {
    this.active = false;
    this.rec?.abort();
    this.rec = null;
  }
}
