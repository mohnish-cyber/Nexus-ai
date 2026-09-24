import { CalendarClock, CheckCircle2, Circle, ListChecks } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { dateTime } from "../../lib/format";
import { api } from "../../services/api";
import { useChat } from "../../stores/chatStore";
import { useToasts } from "../../stores/toastStore";
import type { Automation, Task } from "../../types/api";
import { EmptyState, Panel } from "../common/ui";

export function TodayPanel({ className }: { className?: string }) {
  const [tasks, setTasks] = useState<Task[] | null>(null);
  const [autos, setAutos] = useState<Automation[] | null>(null);
  const lastReply = useChat((s) => s.lastReply?.at);

  const load = useCallback(async () => {
    try {
      const [t, a] = await Promise.all([api.get<Task[]>("/api/tasks?view=today"), api.get<Automation[]>("/api/automations")]);
      setTasks(t);
      setAutos(a.filter((x) => x.status === "active" && x.next_run_at)
        .sort((x, y) => (x.next_run_at! < y.next_run_at! ? -1 : 1)).slice(0, 4));
    } catch {
      setTasks([]);
      setAutos([]);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, lastReply]);

  const complete = async (t: Task) => {
    try {
      await api.patch(`/api/tasks/${t.id}`, { status: "done" });
      setTasks((list) => list?.filter((x) => x.id !== t.id) ?? null);
    } catch (err) {
      useToasts.getState().error(err, "Couldn't complete the task");
    }
  };

  return (
    <Panel title="Today" icon={<ListChecks className="size-3.5" />} className={className}
      actions={<Link to="/tasks" className="text-[0.68rem] text-cyan/80 hover:text-cyan">All tasks</Link>}>
      {tasks === null ? (
        <p className="text-xs text-dim py-2">Loading…</p>
      ) : tasks.length === 0 ? (
        <EmptyState icon={<CheckCircle2 className="size-5" />} title="Nothing due today">
          Try “Remind me tomorrow at 8 AM to submit my assignment”.
        </EmptyState>
      ) : (
        <ul className="space-y-1.5">
          {tasks.map((t) => (
            <li key={t.id} className="flex items-start gap-2 text-sm group">
              <button onClick={() => void complete(t)} className="mt-0.5 text-dim hover:text-ok" aria-label={`Complete ${t.title}`}>
                <Circle className="size-4" />
              </button>
              <div className="min-w-0">
                <p className="text-ink/90 leading-snug">{t.title}</p>
                {t.due_at && <p className="text-[0.68rem] text-dim">{dateTime(t.due_at)}</p>}
              </div>
            </li>
          ))}
        </ul>
      )}
      {autos && autos.length > 0 && (
        <div className="mt-4 pt-3 border-t border-line">
          <p className="hud-label mb-2 flex items-center gap-1.5"><CalendarClock className="size-3" /> Scheduled</p>
          <ul className="space-y-1.5">
            {autos.map((a) => (
              <li key={a.id} className="text-xs flex justify-between gap-2">
                <span className="text-muted truncate">{a.name.replace(/^Reminder: /, "⏰ ")}</span>
                <span className="text-dim shrink-0 font-mono">{dateTime(a.next_run_at)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Panel>
  );
}
