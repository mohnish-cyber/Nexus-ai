import { cn } from "../../lib/cn";

/** NEXUS mark (orb with an orbit ring) plus optional wordmark. */
export function Logo({ className, withWordmark = true }: { className?: string; withWordmark?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <svg viewBox="0 0 64 64" className="size-7" aria-hidden>
        <defs>
          <radialGradient id="nexus-logo-g" cx="50%" cy="42%" r="58%">
            <stop offset="0" stopColor="#f5f3ff" />
            <stop offset=".35" stopColor="#c4b5fd" />
            <stop offset=".7" stopColor="#7c3aed" />
            <stop offset="1" stopColor="#1e1033" />
          </radialGradient>
        </defs>
        <circle cx="32" cy="32" r="17" fill="url(#nexus-logo-g)" />
        <ellipse
          cx="32"
          cy="32"
          rx="27"
          ry="9"
          fill="none"
          stroke="#38e1ff"
          strokeOpacity=".7"
          strokeWidth="2"
          transform="rotate(-24 32 32)"
        />
      </svg>
      {withWordmark && <span className="text-[15px] font-semibold tracking-[0.2em] text-fg">NEXUS</span>}
    </span>
  );
}
