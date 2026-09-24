import clsx from "clsx";
import { BatteryCharging, BatteryMedium, Cpu, Gauge, HardDrive, MemoryStick, Wifi } from "lucide-react";
import type { ReactNode } from "react";
import { duration } from "../../lib/format";
import { useSystem } from "../../stores/systemStore";
import { Panel } from "../common/ui";

function Meter({ icon, label, value, pct, unavailable }: {
  icon: ReactNode;
  label: string;
  value: string;
  pct?: number;
  unavailable?: boolean;
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-xs">
        <span className="flex items-center gap-1.5 text-muted">{icon}{label}</span>
        <span className={clsx("font-mono", unavailable ? "text-dim" : "text-ink")}>{value}</span>
      </div>
      <div className="h-1 rounded-full bg-white/[0.06] overflow-hidden">
        {pct !== undefined && !unavailable && (
          <div
            className={clsx("h-full rounded-full transition-all duration-700",
              pct > 85 ? "bg-rose" : pct > 65 ? "bg-amber" : "bg-cyan")}
            style={{ width: `${Math.max(2, Math.min(100, pct))}%` }}
          />
        )}
      </div>
    </div>
  );
}

/** Real host telemetry from the backend. Metrics the host can't report show as unavailable. */
export function TelemetryPanel({ className }: { className?: string }) {
  const t = useSystem((s) => s.telemetry);
  const connection = useSystem((s) => s.connection);
  const activeTasks = ["thinking", "executing", "waiting"].includes(useSystem((s) => s.orb));
  const na = "Unavailable";
  return (
    <Panel title={t ? `System · ${t.host}` : "System"} icon={<Gauge className="size-3.5" />} className={className}>
      {!t ? (
        <p className="text-xs text-dim py-3">Telemetry not available yet.</p>
      ) : (
        <div className="space-y-3">
          <Meter icon={<Cpu className="size-3.5" />} label="CPU" value={t.cpu ? `${t.cpu.percent.toFixed(0)}%` : na}
            pct={t.cpu?.percent} unavailable={!t.cpu} />
          <Meter icon={<MemoryStick className="size-3.5" />} label="Memory"
            value={t.memory ? `${t.memory.used_gb.toFixed(1)} / ${t.memory.total_gb.toFixed(0)} GB` : na}
            pct={t.memory?.percent} unavailable={!t.memory} />
          <Meter icon={<HardDrive className="size-3.5" />} label="Disk"
            value={t.disk ? `${t.disk.free_gb.toFixed(0)} GB free` : na} pct={t.disk?.percent} unavailable={!t.disk} />
          <Meter
            icon={t.battery?.plugged_in ? <BatteryCharging className="size-3.5" /> : <BatteryMedium className="size-3.5" />}
            label="Battery"
            value={t.battery ? `${t.battery.percent}%${t.battery.plugged_in ? " · charging" : ""}` : "No battery reported"}
            pct={t.battery ? 100 - t.battery.percent : undefined}
            unavailable={!t.battery}
          />
          <div className="grid grid-cols-2 gap-2 pt-1 text-[0.7rem]">
            <div className="rounded-lg bg-white/[0.03] border border-line px-2.5 py-2">
              <p className="text-dim flex items-center gap-1"><Wifi className="size-3" /> Network</p>
              <p className="font-mono text-ink mt-0.5">
                {t.network?.rate ? `↓${t.network.rate.down_kbps.toFixed(0)} ↑${t.network.rate.up_kbps.toFixed(0)} KB/s` :
                  t.network ? `${t.network.interfaces_up} link(s) up` : na}
              </p>
            </div>
            <div className="rounded-lg bg-white/[0.03] border border-line px-2.5 py-2">
              <p className="text-dim">Uptime · Link</p>
              <p className="font-mono text-ink mt-0.5">
                {duration(t.uptime_seconds)} · <span className={connection === "open" ? "text-ok" : "text-rose"}>
                  {connection === "open" ? "live" : connection}</span>
              </p>
            </div>
          </div>
          <p className="text-[0.65rem] text-dim">{t.os}{activeTasks ? " · NEXUS is working" : ""}</p>
        </div>
      )}
    </Panel>
  );
}
