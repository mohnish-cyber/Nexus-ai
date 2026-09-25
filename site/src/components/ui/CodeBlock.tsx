import { cn } from "../../lib/cn";
import { CopyButton } from "./CopyButton";

/** Terminal-style code block with an optional title bar and a copy button. */
export function CodeBlock({ code, title, className }: { code: string; title?: string; className?: string }) {
  return (
    <div className={cn("card-border overflow-hidden rounded-xl", className)}>
      <div className="flex items-center justify-between border-b border-line px-4 py-2">
        <div className="flex items-center gap-2">
          <span className="flex gap-1.5" aria-hidden>
            <span className="size-2.5 rounded-full bg-white/10" />
            <span className="size-2.5 rounded-full bg-white/10" />
            <span className="size-2.5 rounded-full bg-white/10" />
          </span>
          {title && <span className="ml-2 font-mono text-xs text-fg-dim">{title}</span>}
        </div>
        <CopyButton text={code} />
      </div>
      <pre className="overflow-x-auto p-4 font-mono text-[13px] leading-relaxed text-fg-muted">
        <code>{code}</code>
      </pre>
    </div>
  );
}
