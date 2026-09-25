import type { ReactNode } from "react";
import { cn } from "../../lib/cn";

type Props = {
  eyebrow?: string;
  title: ReactNode;
  subtitle?: ReactNode;
  align?: "center" | "left";
  className?: string;
  /** Heading level; sections on a page use h2 by default. */
  as?: "h1" | "h2";
};

/** Eyebrow + title + subtitle block used at the top of every section. */
export function SectionHeading({ eyebrow, title, subtitle, align = "center", className, as: Tag = "h2" }: Props) {
  return (
    <div
      data-reveal
      className={cn("flex flex-col gap-4", align === "center" ? "mx-auto max-w-2xl items-center text-center" : "max-w-2xl", className)}
    >
      {eyebrow && (
        <span className="font-mono text-xs font-medium tracking-[0.18em] text-accent-soft uppercase">{eyebrow}</span>
      )}
      <Tag className="text-gradient text-3xl leading-[1.1] font-semibold tracking-tight text-balance sm:text-4xl md:text-[44px]">
        {title}
      </Tag>
      {subtitle && <p className="text-base leading-relaxed text-pretty text-fg-muted sm:text-lg">{subtitle}</p>}
    </div>
  );
}
