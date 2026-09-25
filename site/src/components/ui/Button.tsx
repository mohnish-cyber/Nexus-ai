import type { ButtonHTMLAttributes, ReactNode } from "react";
import { cn } from "../../lib/cn";
import { SmartLink } from "./SmartLink";

type Variant = "primary" | "secondary" | "ghost";
type Size = "sm" | "md" | "lg";

const base =
  "group inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full font-medium transition-all duration-200 disabled:pointer-events-none disabled:opacity-50";

const variants: Record<Variant, string> = {
  primary:
    "bg-accent text-white glow-accent hover:bg-accent-strong hover:shadow-[0_0_0_1px_rgb(139_92_246/0.5),0_14px_50px_-10px_rgb(139_92_246/0.75)] active:scale-[0.98]",
  secondary:
    "border border-line-strong bg-white/[0.03] text-fg hover:border-white/25 hover:bg-white/[0.07] active:scale-[0.98]",
  ghost: "text-fg-muted hover:text-fg hover:bg-white/[0.05]",
};

const sizes: Record<Size, string> = {
  sm: "h-9 px-4 text-sm",
  md: "h-11 px-5 text-sm",
  lg: "h-12 px-6 text-[15px]",
};

type CommonProps = { variant?: Variant; size?: Size; className?: string; children: ReactNode };

export function buttonClasses({ variant = "primary", size = "md", className }: Omit<CommonProps, "children">): string {
  return cn(base, variants[variant], sizes[size], className);
}

/** Link styled as a button. Internal paths use the router; external URLs open in a new tab. */
export function ButtonLink({ href, variant, size, className, children }: CommonProps & { href: string }) {
  return (
    <SmartLink href={href} className={buttonClasses({ variant, size, className })}>
      {children}
    </SmartLink>
  );
}

export function Button({
  variant,
  size,
  className,
  children,
  ...rest
}: CommonProps & Omit<ButtonHTMLAttributes<HTMLButtonElement>, "className" | "children">) {
  return (
    <button type="button" className={buttonClasses({ variant, size, className })} {...rest}>
      {children}
    </button>
  );
}
