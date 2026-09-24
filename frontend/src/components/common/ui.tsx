// Small, consistent UI primitives for the NEXUS command centre.
import clsx from "clsx";
import { AlertTriangle, Loader2, X } from "lucide-react";
import { type ButtonHTMLAttributes, type ReactNode, useEffect, useRef } from "react";
import type { RiskLevel } from "../../types/api";

type Variant = "primary" | "ghost" | "danger" | "subtle";

export function Button({
  variant = "subtle",
  size = "md",
  loading,
  icon,
  className,
  children,
  disabled,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: "sm" | "md";
  loading?: boolean;
  icon?: ReactNode;
}) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-all select-none",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan/60 disabled:opacity-45 disabled:cursor-not-allowed",
        size === "sm" ? "px-2.5 py-1.5 text-xs" : "px-3.5 py-2 text-sm",
        variant === "primary" &&
          "bg-cyan/90 text-void hover:bg-cyan shadow-[0_0_20px_-6px_rgba(56,225,255,0.7)] font-semibold",
        variant === "subtle" && "bg-white/[0.04] text-ink border border-line hover:bg-white/[0.08] hover:border-line-strong",
        variant === "ghost" && "text-muted hover:text-ink hover:bg-white/[0.05]",
        variant === "danger" && "bg-rose/15 text-rose border border-rose/30 hover:bg-rose/25",
        className,
      )}
    >
      {loading ? <Loader2 className="size-4 animate-spin" /> : icon}
      {children}
    </button>
  );
}

export function Panel({
  title,
  icon,
  actions,
  children,
  className,
  bodyClassName,
}: {
  title?: ReactNode;
  icon?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={clsx("glass rounded-2xl flex flex-col min-h-0", className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 px-4 pt-3.5 pb-2">
          <div className="flex items-center gap-2 min-w-0">
            {icon && <span className="text-cyan/80 shrink-0">{icon}</span>}
            <h2 className="hud-label truncate">{title}</h2>
          </div>
          {actions && <div className="flex items-center gap-1.5 shrink-0">{actions}</div>}
        </header>
      )}
      <div className={clsx("px-4 pb-4 min-h-0", bodyClassName)}>{children}</div>
    </section>
  );
}

export function Badge({ tone = "neutral", children, className }: {
  tone?: "neutral" | "cyan" | "ok" | "warn" | "danger" | "violet";
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[0.68rem] font-medium tracking-wide border",
        tone === "neutral" && "bg-white/[0.04] text-muted border-line",
        tone === "cyan" && "bg-cyan/10 text-cyan border-cyan/25",
        tone === "ok" && "bg-ok/10 text-ok border-ok/25",
        tone === "warn" && "bg-amber/10 text-amber border-amber/25",
        tone === "danger" && "bg-rose/10 text-rose border-rose/25",
        tone === "violet" && "bg-violet/10 text-violet border-violet/25",
        className,
      )}
    >
      {children}
    </span>
  );
}

export function RiskBadge({ risk }: { risk: RiskLevel }) {
  const tone = risk === "high" ? "danger" : risk === "medium" ? "warn" : "ok";
  return <Badge tone={tone}>{risk.toUpperCase()} RISK</Badge>;
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-muted text-sm py-6 justify-center">
      <Loader2 className="size-4 animate-spin text-cyan" />
      {label ?? "Loading…"}
    </div>
  );
}

export function EmptyState({ icon, title, children }: { icon?: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center text-center gap-2 py-10 px-4">
      {icon && <div className="text-dim mb-1">{icon}</div>}
      <p className="text-sm text-ink/90 font-medium">{title}</p>
      {children && <div className="text-xs text-muted max-w-sm leading-relaxed">{children}</div>}
    </div>
  );
}

export function ErrorNotice({ title, reason, nextStep, onRetry }: {
  title: string;
  reason?: string | null;
  nextStep?: string | null;
  onRetry?: () => void;
}) {
  return (
    <div className="rounded-xl border border-rose/25 bg-rose/[0.06] p-3.5 text-sm">
      <div className="flex items-start gap-2.5">
        <AlertTriangle className="size-4 text-rose mt-0.5 shrink-0" />
        <div className="space-y-1 min-w-0">
          <p className="text-ink font-medium">{title}</p>
          {reason && <p className="text-muted text-xs">Reason: {reason}</p>}
          {nextStep && <p className="text-muted text-xs">Next step: {nextStep}</p>}
          {onRetry && (
            <Button size="sm" className="mt-1.5" onClick={onRetry}>
              Try again
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

export function Modal({ open, onClose, title, children, footer, tone = "default", dismissible = true }: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  tone?: "default" | "warn" | "danger";
  dismissible?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && dismissible && onClose();
    window.addEventListener("keydown", onKey);
    ref.current?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose, dismissible]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-3 sm:p-6 animate-fade-in">
      <div className="absolute inset-0 bg-void/70 backdrop-blur-sm" onClick={() => dismissible && onClose()} />
      <div
        ref={ref}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        className={clsx(
          "relative glass rounded-2xl w-full max-w-lg max-h-[88vh] flex flex-col animate-rise outline-none",
          tone === "warn" && "border-amber/35 shadow-[0_0_60px_-20px_rgba(255,181,71,0.5)]",
          tone === "danger" && "border-rose/40 shadow-[0_0_60px_-20px_rgba(255,84,112,0.55)]",
        )}
      >
        <header className="flex items-center justify-between px-5 pt-4 pb-2">
          <div className="text-base font-semibold">{title}</div>
          {dismissible && (
            <button onClick={onClose} className="text-muted hover:text-ink p-1 rounded-md" aria-label="Close">
              <X className="size-4" />
            </button>
          )}
        </header>
        <div className="px-5 pb-4 overflow-y-auto scrollbar-thin">{children}</div>
        {footer && <footer className="px-5 py-3.5 border-t border-line flex flex-wrap justify-end gap-2">{footer}</footer>}
      </div>
    </div>
  );
}

export function Field({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-xs font-medium text-muted">{label}</span>
      {children}
      {hint && <span className="block text-[0.7rem] text-dim leading-relaxed">{hint}</span>}
    </label>
  );
}

export const inputClass =
  "w-full rounded-lg bg-deep/80 border border-line px-3 py-2 text-sm text-ink placeholder:text-dim " +
  "focus:outline-none focus:border-cyan/50 focus:ring-2 focus:ring-cyan/15 transition";

export function Toggle({ checked, onChange, label, description, disabled }: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  description?: string;
  disabled?: boolean;
}) {
  return (
    <label className={clsx("flex items-start justify-between gap-4 py-2", disabled && "opacity-50")}>
      <span>
        <span className="block text-sm text-ink">{label}</span>
        {description && <span className="block text-xs text-muted mt-0.5 leading-relaxed">{description}</span>}
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={clsx(
          "relative shrink-0 mt-0.5 h-5 w-9 rounded-full border transition-colors",
          checked ? "bg-cyan/80 border-cyan" : "bg-white/[0.06] border-line-strong",
        )}
      >
        <span
          className={clsx(
            "absolute top-0.5 size-3.5 rounded-full bg-white transition-all",
            checked ? "left-[1.1rem]" : "left-0.5 bg-muted",
          )}
        />
      </button>
    </label>
  );
}

export function StatusDot({ ok, pulse }: { ok: boolean | null; pulse?: boolean }) {
  return (
    <span
      className={clsx(
        "inline-block size-2 rounded-full",
        ok === null ? "bg-dim" : ok ? "bg-ok shadow-[0_0_8px_rgba(52,211,153,0.8)]" : "bg-rose shadow-[0_0_8px_rgba(255,84,112,0.7)]",
        pulse && "animate-pulse",
      )}
    />
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3 mb-5">
      <div>
        <h1 className="text-xl sm:text-2xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="text-sm text-muted mt-1">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
