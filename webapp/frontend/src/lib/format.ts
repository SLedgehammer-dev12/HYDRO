import type { DecisionStatus } from "./types";

const LOCALE = "tr-TR";
const DASH = "—";

export function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

/** tr-TR sayı biçimi. Geçersiz değerlerde "—" döner. */
export function num(value: number | null | undefined, digits = 2): string {
  if (!isFiniteNumber(value)) return DASH;
  return new Intl.NumberFormat(LOCALE, {
    minimumFractionDigits: 0,
    maximumFractionDigits: digits,
  }).format(value);
}

/** Sabit ondalıklı gösterim (ör. katsayılar 6 hane). */
export function fixed(value: number | null | undefined, digits = 3): string {
  if (!isFiniteNumber(value)) return DASH;
  return new Intl.NumberFormat(LOCALE, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

/** Değer + birim; birim ayrı biçimlendirilir. */
export function qty(value: number | null | undefined, unit: string, digits = 2): string {
  const formatted = num(value, digits);
  return formatted === DASH ? DASH : `${formatted} ${unit}`;
}

export const fmt = {
  bar: (v: number | null | undefined, digits = 3) => qty(v, "bar", digits),
  m3: (v: number | null | undefined, digits = 6) => qty(v, "m³", digits),
  m3Short: (v: number | null | undefined, digits = 2) => qty(v, "m³", digits),
  m: (v: number | null | undefined, digits = 2) => qty(v, "m", digits),
  km: (v: number | null | undefined, digits = 3) => qty(v, "km", digits),
  mm: (v: number | null | undefined, digits = 2) => qty(v, "mm", digits),
  mpa: (v: number | null | undefined, digits = 1) => qty(v, "MPa", digits),
  c: (v: number | null | undefined, digits = 2) => qty(v, "°C", digits),
  ms: (v: number | null | undefined, digits = 3) => qty(v, "m/s", digits),
  kmh: (v: number | null | undefined, digits = 2) => qty(v, "km/sa", digits),
  a: (v: number | null | undefined, digits = 6) => qty(v, "10⁻⁶/bar", digits),
  b: (v: number | null | undefined, digits = 6) => qty(v, "10⁻⁶/°C", digits),
  ratio: (v: number | null | undefined, digits = 6) => num(v, digits),
  percent: (v: number | null | undefined, digits = 2) => {
    if (!isFiniteNumber(v)) return DASH;
    return `${num(v * 100, digits)}%`;
  },
  percentValue: (v: number | null | undefined, digits = 2) => {
    if (!isFiniteNumber(v)) return DASH;
    return `${num(v, digits)}%`;
  },
  bytes: (bytes: number | null | undefined) => {
    if (!isFiniteNumber(bytes)) return DASH;
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${num(bytes / 1024, 1)} KB`;
    return `${num(bytes / (1024 * 1024), 2)} MB`;
  },
};

/** Girdi alanları için gruplamasız, ondalık virgüllü metin. */
export function formatInput(value: number | null | undefined, digits = 6): string {
  if (!isFiniteNumber(value)) return "";
  return new Intl.NumberFormat(LOCALE, {
    useGrouping: false,
    maximumFractionDigits: digits,
  }).format(value);
}

/**
 * Hem "1.234,56" hem "1234.56" hem de "1234,56" biçimlerini güvenle çözer.
 * Boş metin => null, çözülemeyen metin => NaN.
 */
export function parseNumber(raw: string): number | null {
  const text = raw.replace(/\u00a0/g, " ").trim();
  if (text === "") return null;
  if (/^[+-]?$/.test(text)) return null;

  const cleaned = text.replace(/\s/g, "").replace(/[^\d.,+-]/g, "");
  if (cleaned === "") return null;

  const lastComma = cleaned.lastIndexOf(",");
  const lastDot = cleaned.lastIndexOf(".");

  let normalized: string;
  if (lastComma >= 0 && lastDot >= 0) {
    // Son görülen ayırıcı ondalık ayırıcıdır.
    if (lastComma > lastDot) {
      normalized = cleaned.replace(/\./g, "").replace(",", ".");
    } else {
      normalized = cleaned.replace(/,/g, "");
    }
  } else if (lastComma >= 0) {
    normalized =
      cleaned.indexOf(",") === lastComma
        ? cleaned.replace(",", ".")
        : cleaned.replace(/,/g, "");
  } else if (lastDot >= 0) {
    // Birden fazla nokta binlik ayırıcıdır; tek nokta ondalıktır.
    normalized = cleaned.indexOf(".") === lastDot ? cleaned : cleaned.replace(/\./g, "");
  } else {
    normalized = cleaned;
  }

  const value = Number(normalized);
  return Number.isFinite(value) ? value : NaN;
}

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return DASH;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return DASH;
  return new Intl.DateTimeFormat(LOCALE, {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function timeOnly(iso: string | null | undefined): string {
  if (!iso) return DASH;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return DASH;
  return new Intl.DateTimeFormat(LOCALE, {
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function dateOnly(iso: string | null | undefined): string {
  if (!iso) return DASH;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return DASH;
  return new Intl.DateTimeFormat(LOCALE, {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(date);
}

export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return DASH;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return DASH;
  const diff = Date.now() - date.getTime();
  const minutes = Math.round(diff / 60_000);
  if (minutes < 1) return "az önce";
  if (minutes < 60) return `${minutes} dk önce`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} saat önce`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days} gün önce`;
  return dateOnly(iso);
}

/** ISO tarih, `<input type="date">` biçimi. */
export function isoDate(value: Date = new Date()): string {
  return value.toISOString().slice(0, 10);
}

export function nowIso(): string {
  return new Date().toISOString();
}

export function statusTone(
  status: DecisionStatus | "BILGI" | "UYGUN" | "LIMIT ASILDI" | null | undefined,
): "pass" | "fail" | "warning" | "pending" | "info" {
  switch (status) {
    case "BASARILI":
    case "UYGUN":
      return "pass";
    case "BASARISIZ":
    case "LIMIT ASILDI":
      return "fail";
    case "KATSAYI GUNCELLENMELI":
    case "DOGRULANAMADI":
      return "warning";
    case "BILGI":
      return "info";
    case "BEKLIYOR":
    case null:
    case undefined:
    default:
      return "pending";
  }
}

export const DECISION_LABELS: Record<DecisionStatus, string> = {
  BEKLIYOR: "Bekliyor",
  "KATSAYI GUNCELLENMELI": "Katsayı güncellenmeli",
  DOGRULANAMADI: "Doğrulanamadı",
  BASARILI: "Başarılı",
  BASARISIZ: "Başarısız",
};

export function decisionLabel(status: DecisionStatus | null | undefined): string {
  if (!status) return "Bekliyor";
  return DECISION_LABELS[status] ?? status;
}

export function truncate(text: string, max = 120): string {
  if (text.length <= max) return text;
  return `${text.slice(0, max - 1).trimEnd()}…`;
}

export function formatCoefficientState(state: string | null | undefined): string {
  switch (state) {
    case "computed":
      return "HESAP";
    case "reference":
      return "TABLO";
    case "manual":
      return "MANUEL";
    case "stale":
      return "BAYAT";
    default:
      return "BEKLİYOR";
  }
}
