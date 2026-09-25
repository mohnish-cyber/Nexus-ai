import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "../../lib/cn";

/** Rounded surface with a hairline border. `interactive` adds a hover lift and border brighten. */
export function Card({
  className,
  interactive,
  children,
  ...rest
}: HTMLAttributes<HTMLDivElement> & { interactive?: boolean; children: ReactNode }) {
  return (
    <div
      className={cn(
        "card-border rounded-2xl",
        interactive && "transition-all duration-300 hover:-translate-y-0.5 hover:border-white/15",
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  );
}
