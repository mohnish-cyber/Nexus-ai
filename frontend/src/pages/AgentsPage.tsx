import clsx from "clsx";
import { Bot, CheckCircle2, CircleX, History, Lock, ShieldCheck, Wrench } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Badge, EmptyState, ErrorNotice, PageHeader, Panel, RiskBadge, Spinner } from "../components/common/ui";
import { timeAgo } from "../lib/format";
import { ApiError, api } from "../services/api";
import { useChat } from "../stores/chatStore";
import type { ActivityFeed, AgentInfo, AuditFeed } from "../types/api";

export default function AgentsPage() {
  const [agents, setAgents] = useState<AgentInfo[] | null>(null);
  const [activity, setActivity] = useState<ActivityFeed | null>(null);
  const [audit, setAudit] = useState<AuditFeed | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [tab, setTab] = useState<"runs" | "tools" | "approvals">("tools");
  const lastReply = useChat((s) => s.lastReply?.at);

  const load = useCallback(async () => {
    try {
      const [a, act, au] = await Promise.all([
        api.get<AgentInfo[]>("/api/agents"), api.get<ActivityFeed>("/api/activity?limit=60"), api.get<AuditFeed>("/api/audit?limit=60"),
      ]);
      setAgents(a);
      setActivity(act);
      setAudit(au);
      setError(null);
    } catch (err) {
      setError(ApiError.from(err));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, lastReply]);

  const available = agents?.filter((a) => a.status === "available") ?? [];
  const planned = agents?.filter((a) => a.status === "planned") ?? [];

  return (
    <div className="p-4 sm:p-6 max-w-6xl mx-auto">
      <PageHeader title="Agents" subtitle="Specialists that NexusCore delegates to. Each has a fixed set of tools and a permission ceiling." />
      {error && <ErrorNotice title={error.message} reason={error.reason} nextStep={error.nextStep} onRetry={load} />}
      {agents === null && !error ? <Spinner /> : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 mb-6">
            {available.map((a) => (
              <div key={a.name} className="glass rounded-2xl p-4 flex flex-col">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="size-8 rounded-lg bg-gradient-to-br from-cyan/25 to-violet/25 border border-line flex items-center justify-center">
                      <Bot className="size-4 text-cyan" />
                    </span>
                    <p className="font-medium">{a.title}</p>
                  </div>
                  <Badge tone="ok">available</Badge>
                </div>
                <p className="text-xs text-muted mt-2 leading-relaxed">{a.purpose}</p>
                <div className="mt-3 flex flex-wrap gap-1">
                  {a.tools.map((t) => (
                    <span key={t.name} title={t.description}
                      className={clsx("text-[0.64rem] font-mono rounded px-1.5 py-0.5 border",
                        t.risk === "high" ? "border-rose/30 text-rose/90" : t.risk === "medium" ? "border-amber/30 text-amber/90" : "border-line text-muted")}>
                      {t.name}
                    </span>
                  ))}
                  {a.tools.length === 0 && <span className="text-[0.68rem] text-dim">Uses the AI model directly (vision)</span>}
                </div>
                <div className="mt-auto pt-3 flex items-center gap-2 text-[0.68rem] text-dim">
                  {a.permission_level && <RiskBadge risk={a.permission_level} />}
                  {a.requires_ai ? <span>needs AI core</span> : <span>works without AI for common requests</span>}
                </div>
              </div>
            ))}
          </div>

          {planned.length > 0 && (
            <Panel title="Planned agents" icon={<Lock className="size-3.5" />} className="mb-6">
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {planned.map((a) => (
                  <div key={a.name} className="rounded-xl border border-line border-dashed p-3 opacity-80">
                    <div className="flex items-center justify-between">
                      <p className="text-sm text-ink/90">{a.title}</p>
                      <Badge>planned</Badge>
                    </div>
                    <p className="text-xs text-dim mt-1">{a.purpose}</p>
                  </div>
                ))}
              </div>
            </Panel>
          )}

          <Panel title="Activity history" icon={<History className="size-3.5" />}
            actions={
              <div className="flex gap-1">
                {(["tools", "runs", "approvals"] as const).map((t) => (
                  <button key={t} onClick={() => setTab(t)}
                    className={clsx("text-xs px-2.5 py-1 rounded-lg", tab === t ? "bg-cyan/15 text-cyan" : "text-muted hover:text-ink")}>
                    {t === "tools" ? "Tool calls" : t === "runs" ? "Agent runs" : "Approvals"}
                  </button>
                ))}
              </div>
            }>
            {tab === "tools" && (activity?.tool_calls.length ? (
              <ul className="divide-y divide-line text-sm">
                {activity.tool_calls.map((c) => (
                  <li key={c.id} className="py-2.5 flex items-start gap-3">
                    {c.status === "succeeded" ? <CheckCircle2 className="size-4 text-ok mt-0.5" /> : <CircleX className="size-4 text-rose mt-0.5" />}
                    <div className="flex-1 min-w-0">
                      <p className="text-ink/90">{c.summary ?? c.tool}</p>
                      <p className="text-[0.68rem] text-dim">
                        <span className="font-mono">{c.tool}</span> · {c.agent ?? "NexusCore"} · {c.risk} risk · {c.approval.replace(/_/g, " ")}
                        {c.duration_ms != null && ` · ${c.duration_ms} ms`} · {timeAgo(c.created_at)}
                      </p>
                      {c.error && <p className="text-xs text-rose/90 mt-0.5">{c.error.message}</p>}
                    </div>
                  </li>
                ))}
              </ul>
            ) : <EmptyState icon={<Wrench className="size-5" />} title="No tool calls yet" />)}
            {tab === "runs" && (activity?.agent_runs.length ? (
              <ul className="divide-y divide-line text-sm">
                {activity.agent_runs.map((r) => (
                  <li key={r.id} className="py-2.5">
                    <div className="flex items-center gap-2">
                      <Badge tone={r.status === "succeeded" ? "ok" : r.status === "failed" ? "danger" : "cyan"}>{r.status}</Badge>
                      <span className="text-ink/90 font-medium">{r.agent}</span>
                      <span className="text-[0.68rem] text-dim ml-auto">{timeAgo(r.started_at)}</span>
                    </div>
                    <p className="text-xs text-muted mt-1 line-clamp-2">{r.task}</p>
                  </li>
                ))}
              </ul>
            ) : <EmptyState icon={<Bot className="size-5" />} title="No agent runs yet" />)}
            {tab === "approvals" && (audit?.permission_requests.length ? (
              <ul className="divide-y divide-line text-sm">
                {audit.permission_requests.map((p) => (
                  <li key={p.id} className="py-2.5 flex items-start gap-3">
                    <ShieldCheck className={clsx("size-4 mt-0.5", p.status === "allowed" ? "text-ok" : "text-amber")} />
                    <div className="flex-1 min-w-0">
                      <p className="text-ink/90">{p.summary}</p>
                      <p className="text-[0.68rem] text-dim">
                        {p.risk} risk · {p.status}{p.decision ? ` (${p.decision.replace(/_/g, " ")})` : ""} · {timeAgo(p.created_at)}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            ) : <EmptyState icon={<ShieldCheck className="size-5" />} title="No approval requests yet" />)}
          </Panel>
        </>
      )}
    </div>
  );
}
