import clsx from "clsx";
import { useEffect, useState } from "react";
import { greeting } from "../../lib/format";
import { useSystem } from "../../stores/systemStore";
import type { SystemStatus } from "../../types/api";
import { NexusOrb } from "../orb/NexusOrb";

interface Line {
  label: string;
  state: "ok" | "warn" | "fail";
  text: string;
}

/** Only reports a component as ready when its real startup check passed. */
function linesFrom(status: SystemStatus | null, error: string | null): Line[] {
  if (!status) {
    return [{ label: "Core link", state: "fail", text: error ? "Offline" : "No response" }];
  }
  const c = status.components;
  const ai = c.ai;
  return [
    { label: "Memory", state: c.memory.ready ? "ok" : "fail", text: c.memory.ready ? "Ready" : "Unavailable" },
    { label: "Agents", state: c.agents.ready ? "ok" : "fail", text: c.agents.ready ? `Ready (${c.agents.count})` : "Unavailable" },
    {
      label: "Voice",
      state: "ok",
      text: c.voice.stt_server ? "Ready (server)" : "Ready (browser)",
    },
    { label: "Network", state: c.network.ready ? "ok" : "warn", text: c.network.ready ? "Connected" : "Offline" },
    {
      label: "AI Core",
      state: ai.ready ? "ok" : ai.configured ? "fail" : "warn",
      text: ai.ready ? (ai.mock ? "Dev mock" : `Online · ${ai.model}`) : ai.configured ? "Unreachable" : "Not configured",
    },
    {
      label: "Scheduler",
      state: c.scheduler.ready ? "ok" : "warn",
      text: c.scheduler.ready ? (c.scheduler.mode === "external" ? "External worker" : "Running") : "Stopped",
    },
  ];
}

export function BootSequence({ onDone }: { onDone: () => void }) {
  const status = useSystem((s) => s.status);
  const statusError = useSystem((s) => s.statusError);
  const [shown, setShown] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const lines = linesFrom(status, statusError);

  useEffect(() => {
    void useSystem.getState().loadStatus().finally(() => setLoaded(true));
  }, []);

  useEffect(() => {
    if (!loaded) return;
    if (shown < lines.length) {
      const t = window.setTimeout(() => setShown((n) => n + 1), 260);
      return () => window.clearTimeout(t);
    }
    if (!status) return;
    const t = window.setTimeout(onDone, 1600);
    return () => window.clearTimeout(t);
  }, [loaded, shown, lines.length, onDone, status]);

  const done = loaded && shown >= lines.length;
  const aiReady = status?.components.ai.ready;
  return (
    <div className="fixed inset-0 z-[70] nexus-backdrop flex items-center justify-center p-6 cursor-pointer"
      onClick={() => status && onDone()} role="dialog" aria-label="NEXUS startup">
      <div className="w-full max-w-md flex flex-col items-center text-center">
        <NexusOrb state={!loaded ? "thinking" : status ? "idle" : "error"} size={180} />
        <h1 className="mt-4 text-3xl font-semibold tracking-[0.5em] pl-[0.5em] text-ink">NEXUS</h1>
        <p className="hud-label mt-2">{loaded ? "AI core initialisation" : "Initializing AI Core…"}</p>
        <div className="mt-6 w-full font-mono text-[0.8rem] space-y-1.5 text-left">
          {lines.slice(0, shown).map((l) => (
            <div key={l.label} className="flex items-center gap-2 animate-fade-in">
              <span className="text-muted w-24">{l.label}</span>
              <span className="flex-1 border-b border-dotted border-line-strong translate-y-[-3px]" />
              <span className={clsx(l.state === "ok" ? "text-ok" : l.state === "warn" ? "text-amber" : "text-rose")}>{l.text}</span>
            </div>
          ))}
        </div>
        {done && (
          <p className="mt-7 text-ink/90 animate-rise">
            {status
              ? aiReady
                ? `${greeting()}. NEXUS is online.`
                : `${greeting()}. NEXUS is online in limited mode — connect the AI core in Settings.`
              : "Can't reach the NEXUS backend. Start it with `uvicorn app.main:app` and reload."}
          </p>
        )}
        {status && <p className="mt-4 text-[0.68rem] text-dim">Click anywhere to continue</p>}
        {done && !status && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              setShown(0);
              setLoaded(false);
              void useSystem.getState().loadStatus().finally(() => setLoaded(true));
            }}
            className="mt-5 rounded-lg border border-cyan/40 px-4 py-2 text-sm text-cyan hover:bg-cyan/10"
          >
            Retry connection
          </button>
        )}
      </div>
    </div>
  );
}
