import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { AlertTriangle, Inbox, RefreshCw, WifiOff } from "lucide-react";
import { Button } from "./Button";
import { cn } from "../../lib/utils";

export function EmptyState({
  title,
  description,
  icon: Icon = Inbox,
  action,
  className,
}: {
  title: string;
  description?: ReactNode;
  icon?: LucideIcon;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center gap-3 px-4 py-10 text-center", className)}>
      <span className="grid size-11 place-items-center rounded-xl border border-[var(--border)] bg-[var(--surface-3)] text-[var(--text-faint)]">
        <Icon size={20} aria-hidden />
      </span>
      <div>
        <p className="text-sm font-semibold text-[var(--text-soft)]">{title}</p>
        {description ? (
          <p className="mx-auto mt-1 max-w-sm text-xs leading-relaxed text-[var(--text-faint)]">{description}</p>
        ) : null}
      </div>
      {action}
    </div>
  );
}

export function ErrorState({
  title = "Veri yüklenemedi",
  message,
  requestId,
  onRetry,
  className,
}: {
  title?: string;
  message: ReactNode;
  requestId?: string;
  onRetry?: () => void;
  className?: string;
}) {
  return (
    <div className={cn("rounded-xl border border-[var(--danger-border)] bg-[var(--danger-bg)] p-4", className)}>
      <div className="flex items-start gap-2.5">
        <AlertTriangle size={16} className="mt-0.5 shrink-0 text-[var(--danger)]" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="text-[13px] font-semibold text-[var(--danger)]">{title}</p>
          <p className="mt-1 text-[11.5px] leading-relaxed text-[var(--text-muted)]">{message}</p>
          {requestId ? (
            <p className="mt-1.5 font-mono text-[10.5px] text-[var(--text-faint)]">request_id: {requestId}</p>
          ) : null}
          {onRetry ? (
            <Button size="sm" variant="default" icon={<RefreshCw size={12} />} onClick={onRetry} className="mt-2.5">
              Tekrar dene
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export function OfflineNotice({ children }: { children?: ReactNode }) {
  return (
    <div className="flex items-start gap-2.5 rounded-xl border border-[var(--warning-border)] bg-[var(--warning-bg)] px-3.5 py-2.5">
      <WifiOff size={14} className="mt-0.5 shrink-0 text-[var(--warning)]" aria-hidden />
      <p className="text-[11.5px] leading-relaxed text-[var(--text-muted)]">
        {children ?? "Backend bağlı değil. Girdiler yerelde korunuyor, hesaplar demo motoruyla üretiliyor."}
      </p>
    </div>
  );
}

export function InlineNotice({
  tone = "info",
  title,
  children,
  icon: Icon,
}: {
  tone?: "info" | "warning" | "danger" | "success";
  title?: ReactNode;
  children?: ReactNode;
  icon?: LucideIcon;
}) {
  return (
    <div
      className={cn(
        "flex items-start gap-2.5 rounded-xl border px-3.5 py-2.5",
        tone === "info" && "border-[var(--info-border)] bg-[var(--info-bg)]",
        tone === "warning" && "border-[var(--warning-border)] bg-[var(--warning-bg)]",
        tone === "danger" && "border-[var(--danger-border)] bg-[var(--danger-bg)]",
        tone === "success" && "border-[var(--success-border)] bg-[var(--success-bg)]",
      )}
      role={tone === "danger" ? "alert" : undefined}
    >
      {Icon ? <Icon size={14} className={cn("mt-0.5 shrink-0", `tone-${tone === "success" ? "pass" : tone}`)} aria-hidden /> : null}
      <div className="min-w-0 text-[11.5px] leading-relaxed text-[var(--text-muted)]">
        {title ? <p className="mb-0.5 font-semibold text-[var(--text-soft)]">{title}</p> : null}
        {children}
      </div>
    </div>
  );
}

export function SkeletonLine({ className }: { className?: string }) {
  return <div className={cn("skeleton h-3.5 w-full", className)} />;
}

export function SkeletonCards({ count = 4 }: { count?: number }) {
  return (
    <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
      {Array.from({ length: count }).map((_, index) => (
        <div key={index} className="kpi space-y-3">
          <SkeletonLine className="w-1/2" />
          <SkeletonLine className="h-6 w-2/3" />
          <SkeletonLine className="w-3/4" />
        </div>
      ))}
    </div>
  );
}
