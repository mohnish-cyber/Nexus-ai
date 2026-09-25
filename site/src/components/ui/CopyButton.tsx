import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { cn } from "../../lib/cn";

/** Copies `text` to the clipboard and shows a check mark for a moment. */
export function CopyButton({ text, className }: { text: string; className?: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      /* clipboard unavailable (insecure context); ignore */
    }
  }
  return (
    <button
      type="button"
      onClick={copy}
      aria-label={copied ? "Copied" : "Copy to clipboard"}
      className={cn(
        "inline-flex size-8 items-center justify-center rounded-lg text-fg-dim transition-colors hover:bg-white/[0.06] hover:text-fg",
        className,
      )}
    >
      {copied ? <Check className="size-4 text-ok" /> : <Copy className="size-4" />}
    </button>
  );
}
