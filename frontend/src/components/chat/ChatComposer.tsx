import clsx from "clsx";
import { ArrowUp, FileText, Image as ImageIcon, Loader2, Mic, MicOff, MonitorUp, Paperclip, X } from "lucide-react";
import { type KeyboardEvent, useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../services/api";
import { useChat } from "../../stores/chatStore";
import { useToasts } from "../../stores/toastStore";
import { useVoice } from "../../stores/voiceStore";
import type { Attachment, FileInfo } from "../../types/api";
import { captureScreenFrame, screenCaptureSupported } from "../../lib/screen";

interface PendingFile {
  key: string;
  name: string;
  status: "uploading" | "ready" | "failed";
  info?: FileInfo;
  error?: string;
}

export function ChatComposer({ autoFocus, placeholder, initialAttachments }: {
  autoFocus?: boolean;
  placeholder?: string;
  initialAttachments?: FileInfo[];
}) {
  const send = useChat((s) => s.send);
  const { listening, transcribing, interim, toggle } = useVoice();
  const [text, setText] = useState("");
  const [files, setFiles] = useState<PendingFile[]>(() =>
    (initialAttachments ?? []).map((f) => ({ key: f.id, name: f.filename, status: "ready" as const, info: f })),
  );
  const [dragging, setDragging] = useState(false);
  const [capturing, setCapturing] = useState(false);
  const areaRef = useRef<HTMLTextAreaElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const el = areaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  }, [text]);

  const upload = useCallback(async (list: File[]) => {
    for (const file of list) {
      const key = `${file.name}-${crypto.randomUUID()}`;
      setFiles((f) => [...f, { key, name: file.name, status: "uploading" }]);
      const form = new FormData();
      form.append("file", file);
      try {
        const info = await api.upload<FileInfo>("/api/files", form);
        setFiles((f) => f.map((x) => (x.key === key
          ? { ...x, status: info.status === "failed" ? "failed" : "ready", info, error: info.error ?? undefined } : x)));
        if (info.status === "failed") useToasts.getState().push({ kind: "error", title: `${file.name} couldn't be read`, detail: info.error ?? undefined });
      } catch (err) {
        setFiles((f) => f.map((x) => (x.key === key ? { ...x, status: "failed", error: (err as Error).message } : x)));
        useToasts.getState().error(err, `Upload failed: ${file.name}`);
      }
    }
  }, []);

  const captureScreen = async () => {
    setCapturing(true);
    try {
      const shot = await captureScreenFrame();
      await upload([shot]);
      if (!text.trim()) setText("What's wrong on my screen?");
    } catch (err) {
      if (!(err instanceof DOMException && err.name === "NotAllowedError")) useToasts.getState().error(err, "Screen capture failed");
    } finally {
      setCapturing(false);
    }
  };

  const ready = files.filter((f) => f.status === "ready" && f.info);
  const uploading = files.some((f) => f.status === "uploading");
  const canSend = (text.trim().length > 0 || ready.length > 0) && !uploading;

  const submit = () => {
    if (!canSend) return;
    const attachments: Attachment[] = ready.map((f) => ({ id: f.info!.id, filename: f.info!.filename, kind: f.info!.kind }));
    send(text.trim(), { attachments });
    setText("");
    setFiles([]);
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div
      className={clsx("glass rounded-2xl p-2 transition", dragging && "border-cyan/60 glow-ring")}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        void upload(Array.from(e.dataTransfer.files));
      }}
    >
      {files.length > 0 && (
        <div className="flex flex-wrap gap-1.5 px-1.5 pt-1 pb-2">
          {files.map((f) => (
            <span key={f.key} className={clsx(
              "inline-flex items-center gap-1.5 rounded-lg border px-2 py-1 text-xs max-w-[14rem]",
              f.status === "failed" ? "border-rose/40 text-rose" : "border-line text-muted bg-deep/60",
            )} title={f.error}>
              {f.status === "uploading" ? <Loader2 className="size-3 animate-spin" /> :
                f.info?.kind === "image" ? <ImageIcon className="size-3" /> : <FileText className="size-3" />}
              <span className="truncate">{f.name}</span>
              <button onClick={() => setFiles((x) => x.filter((y) => y.key !== f.key))} aria-label={`Remove ${f.name}`}
                className="hover:text-ink">
                <X className="size-3" />
              </button>
            </span>
          ))}
        </div>
      )}
      {(listening || transcribing) && (
        <div className="px-3 pt-1 pb-2 text-sm text-mint flex items-center gap-2">
          <span className="relative flex size-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-mint/70" />
            <span className="relative inline-flex size-2 rounded-full bg-mint" />
          </span>
          {transcribing ? "Transcribing…" : interim || "Listening… tap the mic again when you're done."}
        </div>
      )}
      <div className="flex items-end gap-1.5">
        <input ref={fileInput} type="file" multiple hidden
          accept=".pdf,.docx,.txt,.md,.csv,.json,.py,.js,.ts,.tsx,.jsx,.java,.c,.cpp,.cs,.go,.rs,.rb,.php,.html,.css,.sql,.sh,.yaml,.yml,.png,.jpg,.jpeg,.gif,.webp"
          onChange={(e) => {
            void upload(Array.from(e.target.files ?? []));
            e.target.value = "";
          }} />
        <button onClick={() => fileInput.current?.click()} className="p-2.5 rounded-xl text-muted hover:text-ink hover:bg-white/[0.05]"
          aria-label="Attach files" title="Attach files (PDF, DOCX, text, code, images)">
          <Paperclip className="size-[1.1rem]" />
        </button>
        {screenCaptureSupported() && (
          <button onClick={captureScreen} disabled={capturing}
            className="p-2.5 rounded-xl text-muted hover:text-ink hover:bg-white/[0.05] disabled:opacity-40 hidden sm:block"
            aria-label="Capture screen" title="Capture screen — one screenshot, with your browser's permission">
            {capturing ? <Loader2 className="size-[1.1rem] animate-spin" /> : <MonitorUp className="size-[1.1rem]" />}
          </button>
        )}
        <textarea
          ref={areaRef}
          value={text}
          autoFocus={autoFocus}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKey}
          rows={1}
          maxLength={20000}
          placeholder={placeholder ?? "Ask NEXUS anything…"}
          aria-label="Message NEXUS"
          className="flex-1 resize-none bg-transparent px-2 py-2.5 text-[0.95rem] text-ink placeholder:text-dim focus:outline-none scrollbar-thin"
        />
        <button
          onClick={() => void toggle()}
          disabled={transcribing}
          className={clsx(
            "p-2.5 rounded-xl transition",
            listening ? "bg-mint/20 text-mint shadow-[0_0_18px_-4px_rgba(52,245,197,0.8)]" : "text-muted hover:text-ink hover:bg-white/[0.05]",
          )}
          aria-label={listening ? "Stop listening" : "Speak to NEXUS"}
          title={listening ? "Stop and send" : "Push to talk"}
        >
          {listening ? <MicOff className="size-[1.1rem]" /> : <Mic className="size-[1.1rem]" />}
        </button>
        <button
          onClick={submit}
          disabled={!canSend}
          className="p-2.5 rounded-xl bg-cyan text-void disabled:bg-white/[0.06] disabled:text-dim transition shadow-[0_0_16px_-4px_rgba(56,225,255,0.8)] disabled:shadow-none"
          aria-label="Send"
        >
          <ArrowUp className="size-[1.1rem]" />
        </button>
      </div>
    </div>
  );
}
