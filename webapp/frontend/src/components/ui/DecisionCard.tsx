import type { Decision } from "../../lib/types";
import { decisionLabel, num, statusTone } from "../../lib/format";
import { Badge } from "./Badge";
import { AlertTriangle, CheckCircle2, CircleDot, Info, XCircle } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "../../lib/utils";

const ICONS = {
  pass: CheckCircle2,
  fail: XCircle,
  warning: AlertTriangle,
  pending: CircleDot,
  info: Info,
} as const;

export function DecisionCard({
  decision,
  testName,
  className,
  actions,
  why,
  compact = false,
  extra,
  marginUnit = "",
}: {
  decision: Decision | null | undefined;
  testName: string;
  className?: string;
  actions?: ReactNode;
  why?: ReactNode;
  compact?: boolean;
  extra?: ReactNode;
  marginUnit?: string;
}) {
  const tone = statusTone(decision?.status);
  const Icon = ICONS[tone];

  return (
    <div
      className={cn(
        "panel overflow-hidden",
        tone === "pass" && "status-card-pass",
        tone === "fail" && "status-card-fail",
        tone === "warning" && "status-card-warning",
        tone === "pending" && "status-card-pending",
        tone === "info" && "status-card-info",
        className,
      )}
    >
      <div className={cn("p-4", compact && "p-3.5")}>
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-2.5">
            <span className={cn("mt-0.5 shrink-0", `tone-${tone}`)}>
              <Icon size={18} strokeWidth={1.9} aria-hidden />
            </span>
            <div className="min-w-0">
              <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-[var(--text-faint)]">
                {testName}
              </p>
              <p className={cn("mt-0.5 text-[19px] font-semibold leading-tight tracking-[-0.02em]", `tone-${tone}`)}>
                {decisionLabel(decision?.status)}
              </p>
            </div>
          </div>
          {decision?.margin !== null && decision?.margin !== undefined ? (
            <Badge tone={tone}>
              {`marj ${num(decision.margin, 6)}${marginUnit ? ` ${marginUnit}` : ""}`}
            </Badge>
          ) : null}
        </div>

        {decision?.summary ? (
          <p className="mt-2.5 break-words text-[12px] leading-relaxed text-[var(--text-muted)]">
            {decision.summary}
          </p>
        ) : (
          <p className="mt-2.5 text-[12px] leading-relaxed text-[var(--text-faint)]">
            Bu test için henüz değerlendirme yapılmadı. Gerekli alanları doldurup
            “Değerlendir” düğmesini kullanın.
          </p>
        )}

        {decision?.rule ? (
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-2">
            <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-faint)]">
              Kabul kuralı
            </span>
            <span className="font-mono text-[11px] text-[var(--text-soft)]">{decision.rule}</span>
          </div>
        ) : null}

        {extra}

        {why ? <details className="mt-3 text-[11.5px] text-[var(--text-muted)]">
          <summary className="cursor-pointer select-none font-semibold text-[var(--primary)]">
            Neden? Formül ve girdiler
          </summary>
          <div className="mt-2 space-y-1.5 rounded-lg bg-[var(--surface-2)] p-2.5 leading-relaxed">{why}</div>
        </details> : null}

        {actions ? <div className="mt-3 flex flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
    </div>
  );
}
