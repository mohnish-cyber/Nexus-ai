import clsx from "clsx";
import { NavLink } from "react-router-dom";
import { useChat } from "../../stores/chatStore";
import { useSystem } from "../../stores/systemStore";
import { NexusOrb } from "../orb/NexusOrb";
import { NAV } from "./nav";

export function Sidebar() {
  const orb = useSystem((s) => s.orb);
  const level = useSystem((s) => s.audioLevel);
  const suggestions = useChat((s) => s.memorySuggestions);
  const version = useSystem((s) => s.config?.version);
  return (
    <aside className="hidden lg:flex w-60 shrink-0 flex-col border-r border-line bg-deep/60 backdrop-blur-md">
      <div className="flex items-center gap-2.5 px-5 h-16">
        <NexusOrb state={orb} level={level} size={34} ariaLabel="NEXUS status" />
        <div>
          <p className="font-semibold tracking-[0.3em] text-sm">NEXUS</p>
          <p className="text-[0.6rem] text-dim font-mono tracking-wider">PERSONAL AI OS</p>
        </div>
      </div>
      <nav className="flex-1 px-3 py-2 space-y-0.5 overflow-y-auto scrollbar-thin" aria-label="Main">
        {NAV.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              clsx(
                "group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition relative",
                isActive ? "bg-cyan/10 text-ink" : "text-muted hover:text-ink hover:bg-white/[0.04]",
              )
            }
          >
            {({ isActive }) => (
              <>
                {isActive && <span className="absolute left-0 top-2 bottom-2 w-0.5 rounded-full bg-cyan shadow-[0_0_10px_rgba(56,225,255,0.9)]" />}
                <Icon className={clsx("size-4", isActive ? "text-cyan" : "text-dim group-hover:text-muted")} />
                {label}
                {to === "/memory" && suggestions > 0 && (
                  <span className="ml-auto text-[0.62rem] rounded-full bg-amber/20 text-amber px-1.5">{suggestions}</span>
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>
      <div className="px-5 py-4 text-[0.62rem] text-dim font-mono">v{version ?? "…"} · local-first</div>
    </aside>
  );
}
