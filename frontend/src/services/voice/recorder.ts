// Microphone capture (push-to-talk) with a live input level for the orb.
import { ApiError, api } from "../api";

export class MicRecorder {
  private stream: MediaStream | null = null;
  private recorder: MediaRecorder | null = null;
  private chunks: Blob[] = [];
  private ctx: AudioContext | null = null;
  private raf = 0;
  private mime = "";

  async start(onLevel: (level: number) => void): Promise<void> {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new ApiError({ code: "mic_unsupported", message: "This browser can't access the microphone.",
        next_step: "Use a recent Chrome, Edge, Firefox or Safari over http://localhost or https." }, 0);
    }
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    } catch (err) {
      const denied = err instanceof DOMException && (err.name === "NotAllowedError" || err.name === "SecurityError");
      throw new ApiError({
        code: denied ? "mic_denied" : "mic_unavailable",
        message: denied ? "Microphone permission was denied." : "No microphone is available.",
        next_step: denied ? "Allow microphone access for this site in your browser settings." : "Connect a microphone and try again.",
      }, 0);
    }
    this.chunks = [];
    const preferred = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];
    this.mime = preferred.find((m) => typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(m)) ?? "";
    this.recorder = new MediaRecorder(this.stream, this.mime ? { mimeType: this.mime } : undefined);
    this.recorder.ondataavailable = (e) => e.data.size && this.chunks.push(e.data);
    this.recorder.start(250);
    this.meter(this.stream, onLevel);
  }

  private meter(stream: MediaStream, onLevel: (level: number) => void): void {
    try {
      this.ctx = new AudioContext();
      const src = this.ctx.createMediaStreamSource(stream);
      const analyser = this.ctx.createAnalyser();
      analyser.fftSize = 512;
      src.connect(analyser);
      const data = new Uint8Array(analyser.fftSize);
      const loop = () => {
        analyser.getByteTimeDomainData(data);
        let sum = 0;
        for (const v of data) sum += ((v - 128) / 128) ** 2;
        onLevel(Math.min(1, Math.sqrt(sum / data.length) * 4));
        this.raf = requestAnimationFrame(loop);
      };
      loop();
    } catch {
      /* level metering is cosmetic */
    }
  }

  async stop(): Promise<Blob> {
    cancelAnimationFrame(this.raf);
    const rec = this.recorder;
    const done = new Promise<void>((resolve) => {
      if (!rec || rec.state === "inactive") return resolve();
      rec.onstop = () => resolve();
      rec.stop();
    });
    await done;
    this.stream?.getTracks().forEach((t) => t.stop());
    await this.ctx?.close().catch(() => undefined);
    this.stream = null;
    this.recorder = null;
    return new Blob(this.chunks, { type: (this.mime || "audio/webm").split(";")[0] });
  }

  cancel(): void {
    cancelAnimationFrame(this.raf);
    try {
      this.recorder?.stop();
    } catch {
      /* already stopped */
    }
    this.stream?.getTracks().forEach((t) => t.stop());
    void this.ctx?.close().catch(() => undefined);
  }
}

export async function transcribeOnServer(audio: Blob): Promise<string> {
  const form = new FormData();
  form.append("audio", audio, `speech.${audio.type.includes("ogg") ? "ogg" : audio.type.includes("mp4") ? "mp4" : "webm"}`);
  const res = await api.upload<{ text: string }>("/api/voice/transcribe", form);
  return res.text;
}
