import type { ReactNode } from "react";
import { AlertTriangle, CheckCircle2, CircleDot, Info, XCircle } from "lucide-react";
import type { CoefficientState, DecisionStatus } from "../../lib/types";
import { decisionLabel, formatCoefficientState, statusTone } from "../../lib/format";
import { cn } from "../../lib/utils";

export type Tone = "pass" | "fail" | "warning" | "pending" | "info" | "neutral";

const BADGE_CLASS: Record<Tone, string> = {
  pass: "badge badge-pass",
  fail: "badge badge-fail",
  warning: "badge badge-warning",
  pending: "badge badge-pending",
  info: "badge badge-info",
  neutral: "badge badge-neutral",
};

const TONE_ICON: Record<Tone, ReactNode> = {
  pass: <CheckCircle2 size={12} aria-hidden />,
  fail: <XCircle size={12} aria-hidden />,
  warning: <AlertTriangle size={12} aria-hidden />,
  pending: <CircleDot size={12} aria-hidden />,
  info: <Info size={12} aria-hidden />,
  neutral: null,
};

export function Badge({
  tone = "neutral",
  children,
  icon,
  className,
}: {
  tone?: Tone;
  children: ReactNode;
  icon?: ReactNode;
  className?: string;
}) {
  return (
    <span className={cn(BADGE_CLASS[tone], className)}>
      {icon ?? TONE_ICON[tone]}
      {children}
    </span>
  );
}

export function StatusBadge({
  status,
  className,
  dotOnly = false,
}: {
  status: DecisionStatus | null | undefined;
  className?: string;
  dotOnly?: boolean;
}) {
  const tone = statusTone(status);
  if (dotOnly) {
    return (
      <span className={cn(`tone-${tone}`, "inline-flex items-center gap-1.5 text-xs font-semibold", className)}>
        <span className="status-dot" />
        {decisionLabel(status)}
      </span>
    );
  }
  return (
    <Badge tone={tone} className={className}>
      {decisionLabel(status)}
    </Badge>
  );
}

export function CoefficientBadge({
  state,
  className,
}: {
  state: CoefficientState | string | null | undefined;
  className?: string;
}) {
  const tone: Tone =
    state === "computed" || state === "reference"
      ? "pass"
      : state === "manual"
        ? "info"
        : state === "stale"
          ? "warning"
          : "pending";
  return (
    <span
      className={cn(
        "badge",
        tone === "pass" && "badge-pass",
        tone === "info" && "badge-info",
        tone === "warning" && "badge-warning",
        tone === "pending" && "badge-pending",
        className,
      )}
    >
      {formatCoefficientState(state)}
    </span>
  );
}

export function StatusDot({ tone, label }: { tone: Tone; label: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-[11px] font-semibold", `tone-${tone}`)}>
      <span className="status-dot" aria-hidden />
      {label}
    </span>
  );
}
