import { Square } from "lucide-react";
import type { LiveRequest } from "../../stores/chatStore";
import { useChat } from "../../stores/chatStore";
import { Markdown } from "../common/Markdown";

/** A reply that is still being produced: plan, live status and streamed text. */
export function LiveResponse({ live }: { live: LiveRequest }) {
  const cancel = useChat((s) => s.cancel);
  const text = live.segments.map((s) => s.text).join("");
  return (
    <div className="flex gap-3 animate-fade-in">
      <div className="mt-1 size-7 shrink-0 rounded-full bg-gradient-to-br from-violet to-cyan animate-pulse" aria-hidden />
      <div className="min-w-0 flex-1 space-y-2">
        <div className="rounded-2xl rounded-tl-md px-4 py-3 border border-line bg-panel/60">
          {live.plan.length > 0 && (
            <p className="hud-label mb-2 !text-[0.62rem]">{live.plan.map((s) => s.agent).join(" → ")}</p>
          )}
          {text ? (
            <Markdown text={text + " ▍"} />
          ) : (
            <div className="flex items-center gap-2 text-sm text-muted">
              <span className="relative flex size-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-cyan/70" />
                <span className="relative inline-flex size-2 rounded-full bg-cyan" />
              </span>
              {live.label ?? "Working…"}
            </div>
          )}
        </div>
        <button
          onClick={() => cancel(live.requestId)}
          className="ml-1 inline-flex items-center gap-1.5 text-[0.7rem] text-dim hover:text-rose transition"
        >
          <Square className="size-3" /> Stop
        </button>
      </div>
    </div>
  );
}
