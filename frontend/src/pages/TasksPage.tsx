import clsx from "clsx";
import { CheckCircle2, Circle, Flag, ListChecks, Plus, Trash2 } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useState } from "react";
import { Badge, Button, EmptyState, ErrorNotice, Field, PageHeader, Panel, Spinner, inputClass } from "../components/common/ui";
import { dateTime } from "../lib/format";
import { ApiError, api } from "../services/api";
import { useChat } from "../stores/chatStore";
import { useToasts } from "../stores/toastStore";
import type { Task } from "../types/api";

const VIEWS = [
  { id: "today", label: "Today" },
  { id: "upcoming", label: "Upcoming" },
  { id: "overdue", label: "Overdue" },
  { id: "open", label: "All open" },
  { id: "done", label: "Done" },
] as const;

export default function TasksPage() {
  const [view, setView] = useState<(typeof VIEWS)[number]["id"]>("open");
  const [tasks, setTasks] = useState<Task[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [form, setForm] = useState({ title: "", due: "", priority: "normal", remind: true });
  const [saving, setSaving] = useState(false);
  const lastReply = useChat((s) => s.lastReply?.at);

  const load = useCallback(async () => {
    try {
      setTasks(await api.get<Task[]>(`/api/tasks?view=${view}`));
      setError(null);
    } catch (err) {
      setError(ApiError.from(err));
    }
  }, [view]);

  useEffect(() => {
    void load();
  }, [load, lastReply]);

  const create = async (e: FormEvent) => {
    e.preventDefault();
    if (!form.title.trim()) return;
    setSaving(true);
    try {
      await api.post("/api/tasks", { title: form.title.trim(), due: form.due.trim() || null, priority: form.priority,
        remind: form.remind && !!form.due.trim() });
      setForm({ title: "", due: "", priority: "normal", remind: true });
      useToasts.getState().push({ kind: "success", title: "Task added" });
      await load();
    } catch (err) {
      useToasts.getState().error(err, "Couldn't add the task");
    } finally {
      setSaving(false);
    }
  };

  const toggle = async (t: Task) => {
    try {
      await api.patch(`/api/tasks/${t.id}`, { status: t.status === "done" ? "open" : "done" });
      await load();
    } catch (err) {
      useToasts.getState().error(err);
    }
  };

  const del = async (t: Task) => {
    try {
      await api.del(`/api/tasks/${t.id}`);
      setTasks((x) => x?.filter((y) => y.id !== t.id) ?? null);
    } catch (err) {
      useToasts.getState().error(err);
    }
  };

  return (
    <div className="p-4 sm:p-6 max-w-5xl mx-auto">
      <PageHeader title="Tasks" subtitle="Your to-dos and reminders. NEXUS can manage these for you by voice or chat." />
      <div className="grid gap-4 lg:grid-cols-[1fr_20rem]">
        <Panel title="Tasks" icon={<ListChecks className="size-3.5" />}
          actions={
            <div className="flex gap-1 flex-wrap">
              {VIEWS.map((v) => (
                <button key={v.id} onClick={() => setView(v.id)}
                  className={clsx("text-xs px-2.5 py-1 rounded-lg", view === v.id ? "bg-cyan/15 text-cyan" : "text-muted hover:text-ink")}>
                  {v.label}
                </button>
              ))}
            </div>
          }>
          {error ? <ErrorNotice title={error.message} reason={error.reason} nextStep={error.nextStep} onRetry={load} /> :
            tasks === null ? <Spinner /> : tasks.length === 0 ? (
              <EmptyState icon={<CheckCircle2 className="size-6" />} title={`No ${VIEWS.find((v) => v.id === view)?.label.toLowerCase()} tasks`}>
                Add one here, or tell NEXUS: “Add a task to renew my passport next Friday”.
              </EmptyState>
            ) : (
              <ul className="divide-y divide-line">
                {tasks.map((t) => (
                  <li key={t.id} className="flex items-start gap-3 py-3 group">
                    <button onClick={() => void toggle(t)} className={clsx("mt-0.5", t.status === "done" ? "text-ok" : "text-dim hover:text-ok")}
                      aria-label={t.status === "done" ? "Mark as open" : "Mark as done"}>
                      {t.status === "done" ? <CheckCircle2 className="size-[1.1rem]" /> : <Circle className="size-[1.1rem]" />}
                    </button>
                    <div className="flex-1 min-w-0">
                      <p className={clsx("text-sm", t.status === "done" ? "text-dim line-through" : "text-ink")}>{t.title}</p>
                      <div className="flex flex-wrap items-center gap-2 mt-1">
                        {t.due_at && <span className={clsx("text-[0.7rem]",
                          t.status === "open" && new Date(t.due_at) < new Date() ? "text-rose" : "text-muted")}>{dateTime(t.due_at)}</span>}
                        {t.priority !== "normal" && <Badge tone={t.priority === "high" ? "danger" : "neutral"}><Flag className="size-3" />{t.priority}</Badge>}
                        {t.automation_id && <Badge tone="cyan">reminder</Badge>}
                        {t.source === "assistant" && <Badge tone="violet">by NEXUS</Badge>}
                      </div>
                    </div>
                    <button onClick={() => void del(t)} className="opacity-0 group-hover:opacity-100 focus:opacity-100 p-1 text-dim hover:text-rose"
                      aria-label={`Delete ${t.title}`}><Trash2 className="size-4" /></button>
                  </li>
                ))}
              </ul>
            )}
        </Panel>

        <Panel title="New task" icon={<Plus className="size-3.5" />}>
          <form onSubmit={create} className="space-y-3">
            <Field label="Title">
              <input className={inputClass} value={form.title} maxLength={300} required
                onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Submit assignment" />
            </Field>
            <Field label="Due" hint="Natural language works: “tomorrow 5pm”, “next Monday”, “in 2 hours”.">
              <input className={inputClass} value={form.due} maxLength={100}
                onChange={(e) => setForm({ ...form, due: e.target.value })} placeholder="tomorrow at 5pm" />
            </Field>
            <Field label="Priority">
              <select className={inputClass} value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
                <option value="low">Low</option>
                <option value="normal">Normal</option>
                <option value="high">High</option>
              </select>
            </Field>
            <label className="flex items-center gap-2 text-sm text-muted">
              <input type="checkbox" checked={form.remind} onChange={(e) => setForm({ ...form, remind: e.target.checked })}
                className="accent-cyan" />
              Remind me at the due time
            </label>
            <Button variant="primary" type="submit" loading={saving} className="w-full">Add task</Button>
          </form>
        </Panel>
      </div>
    </div>
  );
}
