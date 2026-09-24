import clsx from "clsx";
import { Bell, BellOff, Ear, LogOut, Menu, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { timeAgo } from "../../lib/format";
import { useAuth } from "../../stores/authStore";
import { useNotifications } from "../../stores/notificationStore";
import { useSystem } from "../../stores/systemStore";
import { useVoice } from "../../stores/voiceStore";
import { ORB_STATE_TEXT } from "../orb/NexusOrb";
import { NAV } from "./nav";

function Clock() {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const t = window.setInterval(() => setNow(new Date()), 15000);
    return () => window.clearInterval(t);
  }, []);
  return (
    <span className="font-mono text-xs text-muted hidden sm:inline">
      {now.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" })} ·{" "}
      {now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
    </span>
  );
}

function NotificationsMenu() {
  const { items, markAllRead } = useNotifications();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const unread = items.filter((n) => n.status === "unread").length;

  useEffect(() => {
    const onClick = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const requestBrowserPermission = () => {
    if (typeof Notification !== "undefined" && Notification.permission === "default") void Notification.requestPermission();
  };

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => {
          setOpen((v) => !v);
          requestBrowserPermission();
        }}
        className="relative p-2 rounded-lg text-muted hover:text-ink hover:bg-white/[0.05]"
        aria-label={`Notifications (${unread} unread)`}
      >
        <Bell className="size-[1.1rem]" />
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-4 h-4 px-1 rounded-full bg-amber text-void text-[0.6rem] font-bold flex items-center justify-center">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 mt-2 w-[min(22rem,calc(100vw-1.5rem))] glass rounded-xl shadow-2xl z-40 animate-rise">
          <div className="flex items-center justify-between px-4 py-3 border-b border-line">
            <p className="text-sm font-medium">Notifications</p>
            {unread > 0 && (
              <button onClick={() => void markAllRead()} className="text-xs text-cyan hover:underline">Mark all read</button>
            )}
          </div>
          <ul className="max-h-96 overflow-y-auto scrollbar-thin divide-y divide-line">
            {items.length === 0 && (
              <li className="px-4 py-8 text-center text-xs text-dim flex flex-col items-center gap-2">
                <BellOff className="size-5" /> Reminders and automation results will appear here.
              </li>
            )}
            {items.slice(0, 30).map((n) => (
              <li key={n.id} className={clsx("px-4 py-3", n.status === "unread" && "bg-cyan/[0.04]")}>
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm text-ink font-medium">{n.title}</p>
                  <span className="text-[0.62rem] text-dim shrink-0">{timeAgo(n.created_at)}</span>
                </div>
                <p className="text-xs text-muted mt-0.5 whitespace-pre-line line-clamp-4">{n.body}</p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function TopBar() {
  const orb = useSystem((s) => s.orb);
  const orbLabel = useSystem((s) => s.orbLabel);
  const connection = useSystem((s) => s.connection);
  const wakeActive = useVoice((s) => s.wakeActive);
  const { mode, session, signOut } = useAuth();
  const [menu, setMenu] = useState(false);
  const location = useLocation();

  useEffect(() => setMenu(false), [location.pathname]);

  return (
    <>
      <header className="h-14 lg:h-16 shrink-0 flex items-center gap-3 px-3 sm:px-5 border-b border-line bg-deep/40 backdrop-blur-md">
        <button className="lg:hidden p-2 -ml-1 text-muted" onClick={() => setMenu(true)} aria-label="Open menu">
          <Menu className="size-5" />
        </button>
        <div className="flex items-center gap-2 min-w-0">
          <span className={clsx("size-2 rounded-full shrink-0",
            orb === "error" ? "bg-rose" : orb === "idle" ? "bg-ok" : orb === "waiting" ? "bg-amber" : "bg-cyan animate-pulse")} />
          <span className="text-xs sm:text-sm text-ink/90 truncate">{orbLabel ?? ORB_STATE_TEXT[orb]}</span>
        </div>
        <div className="ml-auto flex items-center gap-1 sm:gap-3">
          {wakeActive && (
            <span className="hidden sm:inline-flex items-center gap-1 text-[0.68rem] text-mint border border-mint/30 rounded-md px-1.5 py-0.5"
              title="Listening for “Hey Nexus”">
              <Ear className="size-3" /> Wake word
            </span>
          )}
          <span className={clsx("hidden sm:inline-flex items-center gap-1.5 text-[0.68rem] font-mono",
            connection === "open" ? "text-ok" : "text-amber")}>
            <span className={clsx("size-1.5 rounded-full", connection === "open" ? "bg-ok" : "bg-amber animate-pulse")} />
            {connection === "open" ? "LINKED" : connection === "connecting" ? "LINKING" : "OFFLINE"}
          </span>
          <Clock />
          <NotificationsMenu />
          {mode === "supabase" && session && (
            <button onClick={() => void signOut()} className="p-2 rounded-lg text-muted hover:text-ink" aria-label="Sign out"
              title={session.user.email ?? "Sign out"}>
              <LogOut className="size-4" />
            </button>
          )}
        </div>
      </header>

      {menu && (
        <div className="lg:hidden fixed inset-0 z-50 animate-fade-in">
          <div className="absolute inset-0 bg-void/80 backdrop-blur-sm" onClick={() => setMenu(false)} />
          <nav className="absolute left-0 top-0 bottom-0 w-72 bg-deep border-r border-line p-4 space-y-1 animate-rise" aria-label="Main">
            <div className="flex items-center justify-between mb-4">
              <p className="font-semibold tracking-[0.3em] text-sm">NEXUS</p>
              <button onClick={() => setMenu(false)} className="p-1.5 text-muted" aria-label="Close menu"><X className="size-5" /></button>
            </div>
            {NAV.map(({ to, label, icon: Icon }) => (
              <NavLink key={to} to={to} end={to === "/"}
                className={({ isActive }) => clsx("flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm",
                  isActive ? "bg-cyan/10 text-ink" : "text-muted")}>
                <Icon className="size-4" /> {label}
              </NavLink>
            ))}
          </nav>
        </div>
      )}
    </>
  );
}
