import type { ReactNode } from "react";
import { cn } from "../../lib/cn";

/** Centered page column: 16px gutters on phones, max 1200px wide. */
export function Container({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cn("mx-auto w-full max-w-[1200px] px-4 sm:px-6 lg:px-8", className)}>{children}</div>;
}
