import clsx from "clsx";
import {
  AlertTriangle, Ban, CheckCircle2, ChevronDown, CircleX, FileText, Globe, Image as ImageIcon, Mic, ShieldCheck, Volume2,
} from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../../services/api";
import { speak } from "../../services/voice/speech";
import { useSettings } from "../../stores/settingsStore";
import type { ActionRecord, Attachment, ChatMessage } from "../../types/api";
import { Markdown } from "../common/Markdown";

function ActionChip({ action }: { action: ActionRecord }) {
  const icon =
    action.status === "succeeded" ? <CheckCircle2 className="size-3.5 text-ok" /> :
    action.status === "denied" ? <Ban className="size-3.5 text-amber" /> :
    <CircleX className="size-3.5 text-rose" />;
  return (
    <li className="flex items-start gap-2 text-xs">
      <span className="mt-0.5 shrink-0">{icon}</span>
      <span className="min-w-0">
        <span className="text-ink/90">{action.summary}</span>
        <span className="text-dim"> · {action.agent ?? "NexusCore"}</span>
        {action.approval !== "auto" && action.approval !== "policy" && (
          <span className="text-dim"> · {action.approval.replace(/_/g, " ")}</span>
        )}
        {action.error && (
          <span className="block text-muted mt-0.5">
            {action.error.message}
            {action.error.reason ? ` — ${action.error.reason}` : ""}
          </span>
        )}
      </span>
    </li>
  );
}

function AttachmentPreview({ att }: { att: Attachment }) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (att.kind !== "image") return;
    let revoked = false;
    let objectUrl: string | null = null;
    api.fileObjectUrl(att.id).then((u) => {
      objectUrl = u;
      if (!revoked) setUrl(u);
    }).catch(() => undefined);
    return () => {
      revoked = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [att.id, att.kind]);
  if (att.kind === "image" && url) {
    return <img src={url} alt={att.filename} className="max-h-40 rounded-lg border border-line object-contain bg-deep" />;
  }
  return (
    <span className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-deep/70 px-2 py-1 text-xs text-muted">
      {att.kind === "image" ? <ImageIcon className="size-3.5" /> : <FileText className="size-3.5" />}
      {att.filename}
    </span>
  );
}

export function MessageBubble({ message }: { message: ChatMessage }) {
  const [showDetails, setShowDetails] = useState(false);
  const isUser = message.role === "user";
  const actions = message.actions ?? [];
  const sources = message.sources ?? [];
  const plan = message.meta?.plan?.steps ?? [];

  const replay = () => {
    const v = useSettings.getState().bundle?.preferences.voice;
    void speak(message.content, "browser", { voiceName: v?.voice_name, rate: v?.rate, pitch: v?.pitch });
  };

  if (isUser) {
    return (
      <div className="flex justify-end animate-rise">
        <div className="max-w-[85%] space-y-2">
          {message.attachments.length > 0 && (
            <div className="flex flex-wrap justify-end gap-2">
              {message.attachments.map((a) => <AttachmentPreview key={a.id} att={a} />)}
            </div>
          )}
          <div className="rounded-2xl rounded-br-md bg-cyan/12 border border-cyan/20 px-4 py-2.5 text-[0.93rem] whitespace-pre-wrap break-words">
            {message.meta?.voice && <Mic className="inline size-3.5 mr-1.5 -mt-0.5 text-cyan/80" aria-label="Spoken" />}
            {message.content}
          </div>
        </div>
      </div>
    );
  }

  const failed = message.status === "error";
  return (
    <div className="flex gap-3 animate-rise">
      <div className="mt-1 size-7 shrink-0 rounded-full bg-gradient-to-br from-cyan to-violet shadow-[0_0_14px_rgba(56,225,255,0.5)]"
        aria-hidden />
      <div className="min-w-0 flex-1 space-y-2">
        <div className={clsx("rounded-2xl rounded-tl-md px-4 py-3 border",
          failed ? "bg-rose/[0.06] border-rose/25" : "bg-panel/70 border-line")}>
          {failed && <AlertTriangle className="size-4 text-rose mb-1.5" />}
          <Markdown text={message.content || "_(no response)_"} />
        </div>

        {(actions.length > 0 || sources.length > 0 || plan.length > 0) && (
          <div className="px-1">
            <button
              onClick={() => setShowDetails((v) => !v)}
              className="flex items-center gap-1.5 text-[0.7rem] text-dim hover:text-muted transition"
            >
              <ShieldCheck className="size-3.5" />
              {actions.length > 0 && `${actions.filter((a) => a.status === "succeeded").length}/${actions.length} actions verified`}
              {actions.length > 0 && sources.length > 0 && " · "}
              {sources.length > 0 && `${sources.length} source${sources.length > 1 ? "s" : ""}`}
              {actions.length === 0 && sources.length === 0 && "How NEXUS handled this"}
              <ChevronDown className={clsx("size-3 transition", showDetails && "rotate-180")} />
            </button>
            {showDetails && (
              <div className="mt-2 space-y-3 rounded-xl border border-line bg-deep/60 p-3 animate-fade-in">
                {plan.length > 0 && (
                  <div>
                    <p className="hud-label mb-1.5">Route</p>
                    <p className="text-xs text-muted">{plan.map((s) => s.agent).join(" → ")}</p>
                  </div>
                )}
                {actions.length > 0 && (
                  <div>
                    <p className="hud-label mb-1.5">Action ledger</p>
                    <ul className="space-y-1.5">{actions.map((a) => <ActionChip key={a.id} action={a} />)}</ul>
                  </div>
                )}
                {sources.length > 0 && (
                  <div>
                    <p className="hud-label mb-1.5">Sources</p>
                    <ul className="space-y-1">
                      {sources.map((s, i) => (
                        <li key={`${s.title}-${i}`} className="flex items-start gap-2 text-xs">
                          {s.kind === "file" ? <FileText className="size-3.5 text-violet mt-0.5 shrink-0" /> :
                            <Globe className="size-3.5 text-cyan mt-0.5 shrink-0" />}
                          {s.url ? (
                            <a href={s.url} target="_blank" rel="noopener noreferrer nofollow"
                              className="text-cyan/90 hover:underline break-all">{s.title}</a>
                          ) : <span className="text-muted">{s.title}</span>}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
        <div className="px-1 flex gap-3 text-[0.68rem] text-dim">
          <span>{new Date(message.created_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</span>
          <button onClick={replay} className="inline-flex items-center gap-1 hover:text-muted" aria-label="Read aloud">
            <Volume2 className="size-3" /> Read aloud
          </button>
        </div>
      </div>
    </div>
  );
}
