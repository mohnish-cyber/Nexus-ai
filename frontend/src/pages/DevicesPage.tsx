import { Laptop, Monitor, Smartphone, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Badge, EmptyState, ErrorNotice, PageHeader, Panel, Spinner } from "../components/common/ui";
import { TelemetryPanel } from "../components/system/TelemetryPanel";
import { timeAgo, titleCase } from "../lib/format";
import { ApiError, api } from "../services/api";
import { useToasts } from "../stores/toastStore";
import type { DevicesResponse } from "../types/api";

export default function DevicesPage() {
  const [data, setData] = useState<DevicesResponse | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const self = (() => {
    try {
      return localStorage.getItem("nexus.device");
    } catch {
      return null;
    }
  })();

  const load = useCallback(async () => {
    try {
      setData(await api.get<DevicesResponse>("/api/devices"));
      setError(null);
    } catch (err) {
      setError(ApiError.from(err));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const remove = async (id: string) => {
    try {
      await api.del(`/api/devices/${id}`);
      await load();
    } catch (err) {
      useToasts.getState().error(err);
    }
  };

  return (
    <div className="p-4 sm:p-6 max-w-5xl mx-auto">
      <PageHeader title="Devices" subtitle="The computer running NEXUS and the devices you've used to reach it." />
      {error && <ErrorNotice title={error.message} reason={error.reason} nextStep={error.nextStep} onRetry={load} />}
      {!data && !error ? <Spinner /> : data && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Panel title="Host computer" icon={<Monitor className="size-3.5" />}>
            <p className="text-lg font-medium">{data.host.name}</p>
            <p className="text-xs text-muted">{data.host.os}</p>
            <ul className="mt-4 space-y-2 text-sm">
              {Object.entries(data.host.capabilities).map(([k, v]) => (
                <li key={k} className="flex items-center justify-between">
                  <span className="text-muted">{titleCase(k)}</span>
                  <Badge tone={v ? "ok" : "neutral"}>{v ? "available" : "unavailable"}</Badge>
                </li>
              ))}
            </ul>
            {!data.host.display && (
              <p className="text-xs text-dim mt-3">
                No display detected — the backend is running headless, so it can't open apps or take screenshots. Browser
                screen capture in the chat still works.
              </p>
            )}
          </Panel>
          <TelemetryPanel />
          <Panel title="Connected clients" className="lg:col-span-2">
            {data.clients.length === 0 ? (
              <EmptyState title="No client devices recorded yet" />
            ) : (
              <ul className="divide-y divide-line">
                {data.clients.map((d) => (
                  <li key={d.id} className="py-3 flex items-start gap-3">
                    {d.kind === "phone" ? <Smartphone className="size-5 text-violet" /> : <Laptop className="size-5 text-cyan" />}
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-ink flex items-center gap-2">
                        {d.name}
                        {self && d.name && d.id && <Badge tone="cyan">{d.last_seen_at && Date.now() - new Date(d.last_seen_at).getTime() < 6 * 60000 ? "online" : "seen"}</Badge>}
                      </p>
                      <p className="text-[0.7rem] text-dim">
                        {d.platform ?? "unknown platform"} · last seen {timeAgo(d.last_seen_at)} ·{" "}
                        {Object.entries(d.capabilities).filter(([, v]) => v).map(([k]) => titleCase(k)).join(", ") || "no capabilities"}
                      </p>
                    </div>
                    <button onClick={() => void remove(d.id)} className="p-1.5 text-dim hover:text-rose" aria-label={`Forget ${d.name}`}>
                      <Trash2 className="size-4" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <p className="text-[0.7rem] text-dim mt-3">
              A phone companion app is on the roadmap. Today, open NEXUS in your phone's browser on the same network (see README).
            </p>
          </Panel>
        </div>
      )}
    </div>
  );
}
