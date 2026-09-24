import clsx from "clsx";
import { AlarmClock, CloudRain, Newspaper, Pause, Play, Plus, Tag, Trash2, Workflow, Zap } from "lucide-react";
import { type FormEvent, type ReactNode, useCallback, useEffect, useState } from "react";
import { Badge, Button, EmptyState, ErrorNotice, Field, Modal, PageHeader, Panel, Spinner, inputClass } from "../components/common/ui";
import { dateTime, timeAgo } from "../lib/format";
import { ApiError, api } from "../services/api";
import { useChat } from "../stores/chatStore";
import { useToasts } from "../stores/toastStore";
import type { Automation, AutomationKind } from "../types/api";

const KINDS: { id: AutomationKind; label: string; icon: ReactNode; hint: string }[] = [
  { id: "reminder", label: "Reminder", icon: <AlarmClock className="size-4" />, hint: "A notification on a schedule." },
  { id: "agent_task", label: "Agent task", icon: <Newspaper className="size-4" />, hint: "NEXUS runs a prompt, e.g. a daily AI news digest." },
  { id: "price_watch", label: "Price watch", icon: <Tag className="size-4" />, hint: "Checks a product page and alerts on a price threshold." },
  { id: "weather_check", label: "Rain alert", icon: <CloudRain className="size-4" />, hint: "Alerts you when rain is expected." },
];

const kindMeta = (k: AutomationKind) => KINDS.find((x) => x.id === k)!;

type ScheduleType = "daily" | "weekly" | "every_hours" | "once";

export default function AutomationsPage() {
  const [items, setItems] = useState<Automation[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [form, setForm] = useState({
    kind: "agent_task" as AutomationKind,
    name: "",
    scheduleType: "daily" as ScheduleType,
    time: "08:00",
    weekday: "monday",
    hours: 24,
    at: "",
    message: "",
    prompt: "Give me the five most important AI news stories from the last 24 hours, with sources.",
    url: "",
    threshold: "",
    direction: "below",
    location: "",
    dayOffset: 0,
  });
  const lastReply = useChat((s) => s.lastReply?.at);

  const load = useCallback(async () => {
    try {
      setItems(await api.get<Automation[]>("/api/automations"));
      setError(null);
    } catch (err) {
      setError(ApiError.from(err));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, lastReply]);

  const act = async (a: Automation, action: "pause" | "resume" | "run" | "delete") => {
    setBusy(a.id);
    try {
      if (action === "delete") {
        if (!window.confirm(`Delete “${a.name}”?`)) return;
        await api.del(`/api/automations/${a.id}`);
      } else if (action === "run") {
        const res = await api.post<{ result: { summary?: string } }>(`/api/automations/${a.id}/run`);
        useToasts.getState().push({ kind: "success", title: `Ran “${a.name}”`, body: res.result.summary });
      } else {
        await api.patch(`/api/automations/${a.id}`, { status: action === "pause" ? "paused" : "active" });
      }
      await load();
    } catch (err) {
      useToasts.getState().error(err, `Couldn't ${action} the automation`);
      await load();
    } finally {
      setBusy(null);
    }
  };

  const create = async (e: FormEvent) => {
    e.preventDefault();
    const schedule =
      form.scheduleType === "daily" ? { type: "daily", time: form.time } :
      form.scheduleType === "weekly" ? { type: "weekly", time: form.time, weekday: form.weekday } :
      form.scheduleType === "every_hours" ? { type: "every_hours", hours: Number(form.hours) } :
      { type: "once", at: form.at };
    const fallbackName =
      form.kind === "agent_task" ? form.prompt.slice(0, 60) :
      form.kind === "reminder" ? `Reminder: ${form.message.slice(0, 60)}` :
      form.kind === "price_watch" ? `Price watch: ${(() => { try { return new URL(form.url).hostname; } catch { return "product"; } })()}` :
      `Rain alert${form.location ? ` · ${form.location}` : ""}`;
    const body: Record<string, unknown> = { name: form.name.trim() || fallbackName, kind: form.kind, schedule };
    if (form.kind === "reminder") body.message = form.message;
    if (form.kind === "agent_task") body.prompt = form.prompt;
    if (form.kind === "price_watch") {
      body.price_watch = { url: form.url, threshold: Number(form.threshold), direction: form.direction };
    }
    if (form.kind === "weather_check") {
      body.location = form.location || null;
      body.day_offset = Number(form.dayOffset);
      body.message = form.message || null;
    }
    try {
      await api.post("/api/automations", body);
      setCreating(false);
      useToasts.getState().push({ kind: "success", title: "Automation created" });
      await load();
    } catch (err) {
      useToasts.getState().error(err, "Couldn't create the automation");
    }
  };

  const set = (patch: Partial<typeof form>) => setForm((f) => ({ ...f, ...patch }));

  return (
    <div className="p-4 sm:p-6 max-w-5xl mx-auto">
      <PageHeader
        title="Automations"
        subtitle="Background jobs that run on schedule — even while this page is closed — and notify you."
        actions={<Button variant="primary" size="sm" icon={<Plus className="size-3.5" />} onClick={() => setCreating(true)}>New automation</Button>}
      />
      <Panel title="Scheduled" icon={<Workflow className="size-3.5" />}>
        {error ? <ErrorNotice title={error.message} reason={error.reason} nextStep={error.nextStep} onRetry={load} /> :
          items === null ? <Spinner /> : items.length === 0 ? (
            <EmptyState icon={<Workflow className="size-6" />} title="No automations yet">
              Create one here or ask NEXUS: “Every morning give me five important AI news stories” or
              “Check this laptop's price daily and alert me below ₹55,000”.
            </EmptyState>
          ) : (
            <ul className="divide-y divide-line">
              {items.map((a) => {
                const meta = kindMeta(a.kind);
                const err = a.last_result?.error;
                return (
                  <li key={a.id} className="py-3.5 flex flex-wrap sm:flex-nowrap items-start gap-3">
                    <span className="mt-0.5 text-cyan">{meta.icon}</span>
                    <div className="flex-1 min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="text-sm text-ink font-medium">{a.name}</p>
                        <Badge tone={a.status === "active" ? "ok" : a.status === "failed" ? "danger" : a.status === "paused" ? "warn" : "neutral"}>
                          {a.status}
                        </Badge>
                        <Badge>{meta.label}</Badge>
                      </div>
                      <p className="text-xs text-muted mt-1">
                        {a.schedule_text} · next: {a.next_run_at ? dateTime(a.next_run_at) : "—"}
                        {a.last_run_at && ` · last ran ${timeAgo(a.last_run_at)}`}
                        {a.run_count > 0 && ` · ${a.run_count} runs`}
                      </p>
                      {a.last_result?.summary && !err && <p className="text-xs text-dim mt-1 line-clamp-2">{a.last_result.summary}</p>}
                      {err && <p className="text-xs text-rose/90 mt-1">Last error: {err.message}{err.reason ? ` — ${err.reason}` : ""}</p>}
                    </div>
                    <div className="flex gap-1 shrink-0">
                      <Button size="sm" loading={busy === a.id} icon={<Zap className="size-3.5" />}
                        onClick={() => void act(a, "run")} title="Run now">Run</Button>
                      {(a.status === "active" || a.status === "paused" || a.status === "failed") && (
                        <Button size="sm" variant="ghost" onClick={() => void act(a, a.status === "active" ? "pause" : "resume")}
                          icon={a.status === "active" ? <Pause className="size-3.5" /> : <Play className="size-3.5" />}>
                          {a.status === "active" ? "Pause" : "Resume"}
                        </Button>
                      )}
                      <button onClick={() => void act(a, "delete")} className="p-1.5 text-dim hover:text-rose" aria-label={`Delete ${a.name}`}>
                        <Trash2 className="size-4" />
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
      </Panel>

      <Modal open={creating} onClose={() => setCreating(false)} title="New automation"
        footer={<><Button variant="ghost" onClick={() => setCreating(false)}>Cancel</Button>
          <Button variant="primary" type="submit" form="automation-form">Create</Button></>}>
        <form id="automation-form" onSubmit={create} className="space-y-3.5">
          <div className="grid grid-cols-2 gap-2">
            {KINDS.map((k) => (
              <button type="button" key={k.id} onClick={() => set({ kind: k.id })}
                className={clsx("text-left rounded-xl border p-2.5 transition",
                  form.kind === k.id ? "border-cyan/50 bg-cyan/10" : "border-line hover:border-line-strong")}>
                <span className="flex items-center gap-2 text-sm text-ink">{k.icon}{k.label}</span>
                <span className="block text-[0.68rem] text-dim mt-1">{k.hint}</span>
              </button>
            ))}
          </div>
          <Field label="Name">
            <input className={inputClass} value={form.name} maxLength={200} placeholder={kindMeta(form.kind).label}
              onChange={(e) => set({ name: e.target.value })} />
          </Field>
          {form.kind === "reminder" && (
            <Field label="Message">
              <input className={inputClass} required value={form.message} onChange={(e) => set({ message: e.target.value })}
                placeholder="Stretch and drink water" />
            </Field>
          )}
          {form.kind === "agent_task" && (
            <Field label="What should NEXUS do each time?" hint="Runs without you present, so actions that need approval are skipped.">
              <textarea className={clsx(inputClass, "min-h-20")} required value={form.prompt} maxLength={2000}
                onChange={(e) => set({ prompt: e.target.value })} />
            </Field>
          )}
          {form.kind === "price_watch" && (
            <>
              <Field label="Product page URL" hint="Some shops block automated checks; errors are shown on this page.">
                <input className={inputClass} required type="url" value={form.url} onChange={(e) => set({ url: e.target.value })}
                  placeholder="https://…" />
              </Field>
              <div className="grid grid-cols-2 gap-2">
                <Field label="Alert when price is">
                  <select className={inputClass} value={form.direction} onChange={(e) => set({ direction: e.target.value })}>
                    <option value="below">below</option>
                    <option value="above">above</option>
                  </select>
                </Field>
                <Field label="Threshold">
                  <input className={inputClass} required type="number" min={0} step="any" value={form.threshold}
                    onChange={(e) => set({ threshold: e.target.value })} placeholder="55000" />
                </Field>
              </div>
            </>
          )}
          {form.kind === "weather_check" && (
            <div className="grid grid-cols-2 gap-2">
              <Field label="Location" hint="Blank = your saved location">
                <input className={inputClass} value={form.location} onChange={(e) => set({ location: e.target.value })} placeholder="Pune" />
              </Field>
              <Field label="Check for">
                <select className={inputClass} value={form.dayOffset} onChange={(e) => set({ dayOffset: Number(e.target.value) })}>
                  <option value={0}>the same day</option>
                  <option value={1}>the next day</option>
                </select>
              </Field>
            </div>
          )}
          <div className="grid grid-cols-2 gap-2">
            <Field label="Schedule">
              <select className={inputClass} value={form.scheduleType} onChange={(e) => set({ scheduleType: e.target.value as ScheduleType })}>
                <option value="daily">Every day</option>
                <option value="weekly">Every week</option>
                <option value="every_hours">Every N hours</option>
                <option value="once">Once</option>
              </select>
            </Field>
            {(form.scheduleType === "daily" || form.scheduleType === "weekly") && (
              <Field label="At">
                <input className={inputClass} type="time" required value={form.time} onChange={(e) => set({ time: e.target.value })} />
              </Field>
            )}
            {form.scheduleType === "every_hours" && (
              <Field label="Hours">
                <input className={inputClass} type="number" min={1} max={168} value={form.hours} onChange={(e) => set({ hours: Number(e.target.value) })} />
              </Field>
            )}
            {form.scheduleType === "once" && (
              <Field label="When">
                <input className={inputClass} required value={form.at} onChange={(e) => set({ at: e.target.value })} placeholder="tomorrow 9am" />
              </Field>
            )}
          </div>
          {form.scheduleType === "weekly" && (
            <Field label="Weekday">
              <select className={inputClass} value={form.weekday} onChange={(e) => set({ weekday: e.target.value })}>
                {["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"].map((d) => (
                  <option key={d} value={d}>{d[0].toUpperCase() + d.slice(1)}</option>
                ))}
              </select>
            </Field>
          )}
        </form>
      </Modal>
    </div>
  );
}
