import type { OcrAnalysisStatus, Severity } from "../types";

export type Tone = "neutral" | "info" | "success" | "warning" | "danger";

export const TONE_BADGE_CLASSES: Record<Tone, string> = {
  neutral: "border-[var(--border)] bg-[var(--surface-3)] text-[var(--text-soft)]",
  info: "border-[var(--info-border)] bg-[var(--info-bg)] text-[var(--primary)]",
  success: "border-[var(--success-border)] bg-[var(--success-bg)] text-[var(--success)]",
  warning: "border-[var(--warning-border)] bg-[var(--warning-bg)] text-[var(--warning)]",
  danger: "border-[var(--danger-border)] bg-[var(--danger-bg)] text-[var(--danger)]",
};

export const TONE_TEXT_CLASSES: Record<Tone, string> = {
  neutral: "text-[var(--text-soft)]",
  info: "text-[var(--primary)]",
  success: "text-[var(--success)]",
  warning: "text-[var(--warning)]",
  danger: "text-[var(--danger)]",
};

export function confidenceTone(confidence: number): Tone {
  if (confidence < 0.4) return "danger";
  if (confidence < 0.6) return "warning";
  if (confidence < 0.85) return "info";
  return "success";
}

export function analysisStatusTone(status: OcrAnalysisStatus): Tone {
  switch (status) {
    case "succeeded":
      return "success";
    case "failed":
      return "danger";
    case "running":
      return "info";
    case "queued":
      return "warning";
    case "cancelled":
    default:
      return "neutral";
  }
}

export function severityTone(severity: Severity): Tone {
  switch (severity) {
    case "critical":
      return "danger";
    case "warning":
      return "warning";
    case "info":
    default:
      return "info";
  }
}
