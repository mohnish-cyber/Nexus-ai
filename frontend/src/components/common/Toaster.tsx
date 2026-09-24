import clsx from "clsx";
import { AlertTriangle, BellRing, CheckCircle2, Info, X } from "lucide-react";
import { useToasts } from "../../stores/toastStore";

export function Toaster() {
  const { toasts, dismiss } = useToasts();
  return (
    <div className="fixed z-[60] bottom-20 lg:bottom-5 right-3 left-3 sm:left-auto sm:w-96 flex flex-col gap-2 pointer-events-none"
      aria-live="polite">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={clsx(
            "glass pointer-events-auto rounded-xl p-3 pr-9 relative animate-rise text-sm",
            t.kind === "error" && "border-rose/35",
            t.kind === "success" && "border-ok/35",
            t.kind === "reminder" && "border-amber/40 shadow-[0_0_30px_-12px_rgba(255,181,71,0.6)]",
          )}
          role={t.kind === "error" ? "alert" : "status"}
        >
          <div className="flex gap-2.5">
            {t.kind === "error" && <AlertTriangle className="size-4 text-rose shrink-0 mt-0.5" />}
            {t.kind === "success" && <CheckCircle2 className="size-4 text-ok shrink-0 mt-0.5" />}
            {t.kind === "info" && <Info className="size-4 text-cyan shrink-0 mt-0.5" />}
            {t.kind === "reminder" && <BellRing className="size-4 text-amber shrink-0 mt-0.5" />}
            <div className="min-w-0">
              <p className="font-medium text-ink">{t.title}</p>
              {t.body && <p className="text-muted mt-0.5 whitespace-pre-line break-words">{t.body}</p>}
              {t.detail && <p className="text-dim text-xs mt-1">{t.detail}</p>}
            </div>
          </div>
          <button
            onClick={() => dismiss(t.id)}
            className="absolute top-2.5 right-2.5 text-dim hover:text-ink"
            aria-label="Dismiss notification"
          >
            <X className="size-3.5" />
          </button>
        </div>
      ))}
    </div>
  );
}
