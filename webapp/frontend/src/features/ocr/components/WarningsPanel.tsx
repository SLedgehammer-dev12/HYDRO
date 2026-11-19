import clsx from "clsx";
import { AlertTriangle, CheckCircle2, Info, ShieldAlert } from "lucide-react";
import { fieldLabel } from "../fields";
import { SEVERITY_LABELS, type Severity, type ValidationIssue } from "../types";
import { severityTone, TONE_BADGE_CLASSES } from "./tone";

const SEVERITY_ICON: Record<Severity, typeof Info> = {
  info: Info,
  warning: AlertTriangle,
  critical: ShieldAlert,
};

export interface WarningsPanelProps {
  warnings: string[];
  issues: ValidationIssue[];
  reportWarnings: string[];
}

export default function WarningsPanel({ warnings, issues, reportWarnings }: WarningsPanelProps) {
  const issueMessages = new Set(issues.map((issue) => issue.message));
  const extraWarnings = Array.from(
    new Set([...warnings, ...reportWarnings].filter((message) => !issueMessages.has(message))),
  );

  if (extraWarnings.length === 0 && issues.length === 0) {
    return (
      <div className="px-5 py-10 text-center">
        <span className="mx-auto grid h-10 w-10 place-items-center rounded-full border border-[var(--success-border)] bg-[var(--success-bg)] text-[var(--success)]">
          <CheckCircle2 size={18} aria-hidden="true" />
        </span>
        <p className="mt-3 text-sm font-medium text-[var(--text)]">Uyarı veya doğrulama sorunu yok.</p>
        <p className="mt-1 text-xs text-[var(--text-faint)]">
          Yine de OCR çıktısı resmi kabul değildir; insan onayı zorunludur.
        </p>
      </div>
    );
  }

  return (
    <div className="px-4 py-4">
      <div className="flex flex-wrap items-center gap-2 text-[10px]">
        <span className={clsx("rounded-full border px-2 py-0.5", TONE_BADGE_CLASSES.warning)}>
          {extraWarnings.length} uyarı
        </span>
        <span className={clsx("rounded-full border px-2 py-0.5", TONE_BADGE_CLASSES.info)}>
          {issues.length} doğrulama sorunu
        </span>
      </div>

      {extraWarnings.length > 0 ? (
        <section className="mt-4" aria-labelledby="ocr-warning-list-title">
          <h3
            id="ocr-warning-list-title"
            className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]"
          >
            Uyarılar
          </h3>
          <ul className="mt-2 space-y-2">
            {extraWarnings.map((message, index) => (
              <li
                key={`${message}-${index}`}
                className="flex items-start gap-2 rounded-lg border border-[var(--warning-border)] bg-[var(--warning-bg)] px-3 py-2 text-xs leading-relaxed text-[var(--text-soft)]"
              >
                <AlertTriangle
                  size={14}
                  className="mt-0.5 shrink-0 text-[var(--warning)]"
                  aria-hidden="true"
                />
                <span>{message}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {issues.length > 0 ? (
        <section className="mt-4" aria-labelledby="ocr-issue-list-title">
          <h3
            id="ocr-issue-list-title"
            className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]"
          >
            Doğrulama sorunları
          </h3>
          <ul className="mt-2 space-y-2">
            {issues.map((issue, index) => {
              const tone = severityTone(issue.severity);
              const Icon = SEVERITY_ICON[issue.severity];
              return (
                <li
                  key={`${issue.field}-${issue.code}-${index}`}
                  className="rounded-lg border border-[var(--border)] bg-[var(--surface-3)] px-3 py-2.5"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={clsx(
                        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold",
                        TONE_BADGE_CLASSES[tone],
                      )}
                    >
                      <Icon size={11} aria-hidden="true" />
                      {SEVERITY_LABELS[issue.severity]}
                    </span>
                    <span className="text-xs font-medium text-[var(--text)]">
                      {issue.field ? fieldLabel(issue.field) : "Rapor geneli"}
                    </span>
                    <span className="numeric text-[10px] text-[var(--text-faint)]">{issue.code}</span>
                  </div>
                  <p className="mt-1.5 text-xs leading-relaxed text-[var(--text-soft)]">{issue.message}</p>
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}

      <p className="mt-4 border-t hairline pt-3 text-[10px] leading-relaxed text-[var(--text-faint)]">
        Uyarılar kabul kararını tek başına değiştirmez; kritik uyuşmazlıklar kabul akışını durdurur.
        Nihai değerlendirme şartname ve proje prosedürüyle birlikte yapılır.
      </p>
    </div>
  );
}
