import clsx from "clsx";
import { Activity, CheckCircle2, CircleX, Loader2 } from "lucide-react";
import { useChat } from "../../stores/chatStore";
import { EmptyState, Panel } from "../common/ui";

/** Live, concise action summaries — never private reasoning. */
export function ActivityPanel({ className, max = 14 }: { className?: string; max?: number }) {
  const activity = useChat((s) => s.activity).slice(0, max);
  return (
    <Panel title="Activity" icon={<Activity className="size-3.5" />} className={className}
      bodyClassName="overflow-y-auto scrollbar-thin flex-1">
      {activity.length === 0 ? (
        <EmptyState title="No activity yet">Agent and tool actions appear here live while NEXUS works.</EmptyState>
      ) : (
        <ol className="relative space-y-2.5 before:absolute before:left-[7px] before:top-1 before:bottom-1 before:w-px before:bg-line">
          {activity.map((a) => (
            <li key={a.id} className="relative pl-6 animate-fade-in">
              <span className="absolute left-0 top-0.5">
                {a.status === "started" ? <Loader2 className="size-3.5 text-cyan animate-spin" /> :
                  a.status === "succeeded" ? <CheckCircle2 className="size-3.5 text-ok" /> :
                  <CircleX className="size-3.5 text-rose" />}
              </span>
              <p className="text-xs leading-snug">
                <span className={clsx("font-medium", a.agent === "NexusCore" ? "text-cyan" : "text-violet")}>{a.agent}</span>
                <span className="text-dim"> → </span>
                <span className="text-ink/85">{a.action}</span>
              </p>
              {a.detail && a.status === "failed" && <p className="text-[0.68rem] text-rose/90 mt-0.5">{a.detail}</p>}
              <p className="text-[0.62rem] text-dim mt-0.5 font-mono">{new Date(a.ts).toLocaleTimeString()}</p>
            </li>
          ))}
        </ol>
      )}
    </Panel>
  );
}
