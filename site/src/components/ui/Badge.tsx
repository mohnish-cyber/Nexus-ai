import type { ReactNode } from "react";
import { cn } from "../../lib/cn";

/** Small pill label. `dot` adds a pulsing accent dot on the left. */
export function Badge({ children, dot, className }: { children: ReactNode; dot?: boolean; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-full border border-line-strong bg-white/[0.03] px-3 py-1 text-xs font-medium text-fg-muted backdrop-blur",
        className,
      )}
    >
      {dot && (
        <span className="relative flex size-1.5">
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-accent opacity-60" />
          <span className="relative inline-flex size-1.5 rounded-full bg-accent-soft" />
        </span>
      )}
      {children}
    </span>
  );
}
