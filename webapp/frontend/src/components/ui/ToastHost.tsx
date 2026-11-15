import { useEffect } from "react";
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from "lucide-react";
import { useAppStore } from "../../store/useAppStore";
import type { ToastItem } from "../../lib/types";
import { cn } from "../../lib/utils";

const TONE = {
  success: { icon: CheckCircle2, className: "tone-pass", ms: 3500 },
  error: { icon: XCircle, className: "tone-fail", ms: 8000 },
  warning: { icon: AlertTriangle, className: "tone-warning", ms: 6000 },
  info: { icon: Info, className: "tone-info", ms: 3500 },
} as const;

function ToastRow({ toast }: { toast: ToastItem }) {
  const dismiss = useAppStore((state) => state.dismissToast);
  const tone = TONE[toast.tone];
  const Icon = tone.icon;

  useEffect(() => {
    const timer = window.setTimeout(() => dismiss(toast.id), tone.ms);
    return () => window.clearTimeout(timer);
  }, [toast.id, tone.ms, dismiss]);

  return (
    <div className="toast no-print" role="status" aria-live="polite">
      <Icon size={16} className={cn("mt-0.5 shrink-0", tone.className)} aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="text-[12.5px] font-semibold text-[var(--text)]">{toast.title}</p>
        {toast.description ? (
          <p className="mt-0.5 text-[11px] leading-relaxed text-[var(--text-muted)]">{toast.description}</p>
        ) : null}
      </div>
      <button
        type="button"
        className="shrink-0 text-[var(--text-faint)] hover:text-[var(--text)]"
        aria-label="Bildirimi kapat"
        onClick={() => dismiss(toast.id)}
      >
        <X size={14} />
      </button>
    </div>
  );
}

export function ToastHost() {
  const toasts = useAppStore((state) => state.toasts);
  if (toasts.length === 0) return null;
  return (
    <div className="no-print pointer-events-none fixed bottom-4 right-4 z-[80] flex flex-col items-end gap-2">
      {toasts.map((toast) => (
        <div key={toast.id} className="pointer-events-auto">
          <ToastRow toast={toast} />
        </div>
      ))}
    </div>
  );
}
