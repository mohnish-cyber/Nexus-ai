import { ShieldAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { useChat } from "../../stores/chatStore";
import { Button, Modal, RiskBadge } from "../common/ui";

/** "NEXUS wants to: …" — shown for every medium/high-risk action. */
export function PermissionDialog() {
  const permissions = useChat((s) => s.permissions);
  const decide = useChat((s) => s.decide);
  const current = permissions[0];
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    if (!current) return;
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, [current]);

  if (!current) return null;
  const remaining = Math.max(0, Math.round((new Date(current.expires_at).getTime() - now) / 1000));
  const details = { ...current.details };
  const diff = typeof details.diff === "string" ? (details.diff as string) : null;
  delete details.diff;
  const target = (details.path ?? details.command ?? details.app ?? details.url) as string | undefined;

  return (
    <Modal
      open
      dismissible={false}
      onClose={() => decide(current.id, "deny")}
      tone={current.risk === "high" ? "danger" : "warn"}
      title={
        <span className="flex items-center gap-2">
          <ShieldAlert className={current.risk === "high" ? "size-5 text-rose" : "size-5 text-amber"} />
          NEXUS wants to:
        </span>
      }
      footer={
        <>
          <Button variant="ghost" onClick={() => decide(current.id, "deny")}>Cancel</Button>
          {current.allow_always && (
            <Button onClick={() => decide(current.id, "always_allow")}>Always allow</Button>
          )}
          <Button variant={current.risk === "high" ? "danger" : "primary"} onClick={() => decide(current.id, "allow_once")} autoFocus>
            Allow once
          </Button>
        </>
      }
    >
      <div className="space-y-3.5 text-sm">
        <div className="flex items-start justify-between gap-3">
          <p className="text-base text-ink font-medium leading-snug">{current.summary}</p>
          <RiskBadge risk={current.risk} />
        </div>
        {target && (
          <div>
            <p className="hud-label mb-1">Target</p>
            <code className="block rounded-lg bg-deep border border-line px-3 py-2 text-xs break-all font-mono">{target}</code>
          </div>
        )}
        {current.reason && (
          <div>
            <p className="hud-label mb-1">Reason</p>
            <p className="text-muted">{current.reason}</p>
          </div>
        )}
        {diff && (
          <div>
            <p className="hud-label mb-1">Changes</p>
            <pre className="max-h-64 overflow-auto scrollbar-thin rounded-lg bg-deep border border-line p-3 text-[0.72rem] leading-relaxed font-mono">
              {diff.split("\n").map((line, i) => (
                <div key={i} className={line.startsWith("+") && !line.startsWith("+++") ? "text-ok" :
                  line.startsWith("-") && !line.startsWith("---") ? "text-rose" : "text-muted"}>{line || " "}</div>
              ))}
            </pre>
          </div>
        )}
        <p className="text-xs text-dim">
          Requested by {current.agent ?? "NexusCore"} · {current.tool.replace(/_/g, " ")} · expires in {remaining}s
          {current.risk === "high" && " · high-risk actions always need your explicit approval"}
          {permissions.length > 1 && ` · ${permissions.length - 1} more waiting`}
        </p>
      </div>
    </Modal>
  );
}
