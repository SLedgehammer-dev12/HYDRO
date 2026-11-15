/** tr-TR sayı, birim ve tarih biçimleme yardımcıları. */
import type { FieldValue } from "./types";

const LOCALE = "tr-TR";
const MINUS = "−";

export type ConfidenceTier = "critical" | "low" | "ok" | "high";

export function confidenceTier(confidence: number | null | undefined): ConfidenceTier {
  const value = typeof confidence === "number" && Number.isFinite(confidence) ? confidence : 0;
  if (value < 0.4) return "critical";
  if (value < 0.6) return "low";
  if (value < 0.85) return "ok";
  return "high";
}

export function formatConfidence(confidence: number | null | undefined): string {
  if (typeof confidence !== "number" || !Number.isFinite(confidence)) return "—";
  return `${Math.round(confidence * 100)}%`;
}

export function formatNumber(value: number, maxFractionDigits = 3): string {
  if (!Number.isFinite(value)) return "—";
  return new Intl.NumberFormat(LOCALE, {
    maximumFractionDigits: Math.max(0, maxFractionDigits),
  }).format(value);
}

const FIELD_DIGITS: Record<string, number> = {
  pipe_od_mm: 2,
  wall_mm: 2,
  length_m: 3,
  test_pressure_bar: 3,
  "air_test.vp": 6,
  "air_test.vpa": 6,
  "air_test.a": 6,
  "pressure_test.a": 6,
  "pressure_test.b": 6,
  "pressure_test.t_initial": 2,
  "pressure_test.t_final": 2,
  "pressure_test.delta_t": 2,
  "pressure_test.pa": 3,
};

export function fieldDigits(key: string, unit: string): number {
  const configured = FIELD_DIGITS[key];
  if (configured !== undefined) return configured;
  if (unit.includes("10^-6") || unit.includes("10⁻⁶")) return 6;
  if (unit === "m³") return 6;
  if (unit === "bar") return 3;
  if (unit === "°C") return 2;
  if (unit === "mm") return 2;
  if (unit === "m") return 3;
  return 4;
}

/** Kanonik birim etiketini okunur biçime çevirir (10^-6/bar → 10⁻⁶/bar). */
export function formatUnit(unit: string | null | undefined): string {
  if (!unit) return "";
  return unit
    .replace(/10\^-6/g, "10⁻⁶")
    .replace(/1e-6/g, "10⁻⁶")
    .replace(/micro/g, "µ");
}

export function formatValue(
  value: FieldValue,
  key = "",
  unit = "",
): string {
  if (value === null || value === undefined) return "—";
  if (key === "date" && typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const parsed = new Date(`${value}T00:00:00`);
    if (!Number.isNaN(parsed.getTime())) {
      return new Intl.DateTimeFormat(LOCALE, { dateStyle: "short" }).format(parsed);
    }
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return "—";
    return formatNumber(value, fieldDigits(key, unit));
  }
  return value;
}

export function formatDelta(delta: number | null, unit = ""): string {
  if (delta === null || delta === undefined || !Number.isFinite(delta)) return "—";
  const digits =
    unit === "bar"
      ? 3
      : unit === "m³"
        ? 6
        : unit === "°C"
          ? 2
          : unit.includes("10^-6")
            ? 6
            : 4;
  const formatted = formatNumber(Math.abs(delta), digits);
  if (delta === 0) return `0${unit ? ` ${formatUnit(unit)}` : ""}`;
  const sign = delta > 0 ? "+" : MINUS;
  return `${sign}${formatted}${unit ? ` ${formatUnit(unit)}` : ""}`;
}

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${formatNumber(kb, 1)} KB`;
  return `${formatNumber(kb / 1024, 2)} MB`;
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat(LOCALE, {
    dateStyle: "short",
    timeStyle: "short",
  }).format(date);
}

export function formatElapsed(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  if (total < 60) return `${total} sn`;
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  return `${minutes} dk ${rest} sn`;
}

export function shortId(id: string | null | undefined): string {
  if (!id) return "—";
  if (id.length <= 12) return id;
  return `${id.slice(0, 8)}…`;
}
