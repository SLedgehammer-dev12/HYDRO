import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "../../lib/utils";

export function SectionCard({
  title,
  description,
  icon: Icon,
  action,
  children,
  className,
  bodyClassName,
  tone,
  id,
}: {
  title: ReactNode;
  description?: ReactNode;
  icon?: LucideIcon;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  tone?: "default" | "pass" | "fail" | "warning" | "pending" | "info";
  id?: string;
}) {
  return (
    <section
      id={id}
      className={cn(
        "panel",
        tone === "pass" && "status-card-pass",
        tone === "fail" && "status-card-fail",
        tone === "warning" && "status-card-warning",
        tone === "pending" && "status-card-pending",
        tone === "info" && "status-card-info",
        className,
      )}
    >
      <header className="panel-head">
        <div className="flex min-w-0 items-start gap-2.5">
          {Icon ? (
            <span className="mt-0.5 grid size-10 shrink-0 place-items-center rounded-xl border border-[color-mix(in_srgb,var(--primary)_35%,var(--border-strong))] bg-[var(--primary-soft)] text-[var(--primary)]">
              <Icon size={19} strokeWidth={2} aria-hidden />
            </span>
          ) : null}
          <div className="min-w-0">
            <h2 className="text-[18px] font-bold leading-snug tracking-[-0.015em] text-[var(--text)] sm:text-[19.5px]">{title}</h2>
            {description ? (
              <p className="mt-1 text-[13px] leading-relaxed text-[var(--text-muted)]">
                {description}
              </p>
            ) : null}
          </div>
        </div>
        {action ? <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">{action}</div> : null}
      </header>
      <div className={cn("panel-body", bodyClassName)}>{children}</div>
    </section>
  );
}

export function KpiCard({
  label,
  value,
  unit,
  hint,
  icon: Icon,
  tone = "default",
  footer,
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  hint?: ReactNode;
  icon?: LucideIcon;
  tone?: "default" | "pass" | "fail" | "warning" | "info";
  footer?: ReactNode;
}) {
  return (
    <div
      className={cn(
        "kpi",
        tone === "pass" && "status-card-pass",
        tone === "fail" && "status-card-fail",
        tone === "warning" && "status-card-warning",
        tone === "info" && "status-card-info",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="kpi-label">{label}</span>
        {Icon ? <Icon size={15} className="text-[var(--text-faint)]" aria-hidden /> : null}
      </div>
      <div className="mt-2 flex items-baseline gap-1.5">
        <span className="kpi-value">{value}</span>
        {unit ? <span className="text-[11px] font-medium text-[var(--text-faint)]">{unit}</span> : null}
      </div>
      {hint ? <div className="mt-1.5 text-[11px] leading-snug text-[var(--text-muted)]">{hint}</div> : null}
      {footer ? <div className="mt-2">{footer}</div> : null}
    </div>
  );
}

export function ResultTile({
  label,
  value,
  unit,
  hint,
  tone,
  icon,
}: {
  label: ReactNode;
  value: ReactNode;
  unit?: string;
  hint?: ReactNode;
  tone?: "pass" | "fail" | "warning" | "info";
  icon?: ReactNode;
}) {
  return (
    <div
      className={cn(
        "result-tile",
        tone === "pass" && "status-card-pass",
        tone === "fail" && "status-card-fail",
        tone === "warning" && "status-card-warning",
        tone === "info" && "status-card-info",
      )}
    >
      <div className="result-label">
        {icon}
        {label}
      </div>
      <div className={cn("result-value", tone && `tone-${tone}`)}>
        {value}
        {unit ? <span className="result-unit">{unit}</span> : null}
      </div>
      {hint ? <div className="mt-1 text-[10.5px] leading-snug text-[var(--text-faint)]">{hint}</div> : null}
    </div>
  );
}
