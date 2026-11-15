/** Kanonik rapor alanları, etiket alias'ları ve rapor düzleştirme yardımcıları. */
import type { ExtractedField, OcrReport } from "./types";

export type FieldGroup = "header" | "geometry" | "air" | "pressure" | "result" | "other";

export interface FieldDescriptor {
  key: string;
  label: string;
  unit: string;
  required: boolean;
  group: FieldGroup;
}

/**
 * Sıra, masaüstü raporundaki alan sırasıyla aynıdır
 * (hidrostatik_test/domain/report_schema.py → ALL_FIELDS).
 */
export const FIELD_CATALOG: readonly FieldDescriptor[] = [
  { key: "report_no", label: "Rapor No", unit: "", required: false, group: "header" },
  { key: "date", label: "Tarih", unit: "ISO tarih", required: false, group: "header" },
  { key: "operator", label: "Operatör", unit: "", required: false, group: "header" },
  { key: "section_id", label: "Bölüm No", unit: "", required: false, group: "header" },
  { key: "pipe_od_mm", label: "Dış çap", unit: "mm", required: true, group: "geometry" },
  { key: "wall_mm", label: "Et kalınlığı", unit: "mm", required: true, group: "geometry" },
  { key: "length_m", label: "Hat uzunluğu", unit: "m", required: true, group: "geometry" },
  {
    key: "test_pressure_bar",
    label: "Test basıncı",
    unit: "bar",
    required: true,
    group: "geometry",
  },
  { key: "air_test.vp", label: "Hava testi Vp", unit: "m³", required: false, group: "air" },
  { key: "air_test.vpa", label: "Hava testi Vpa", unit: "m³", required: false, group: "air" },
  {
    key: "air_test.a",
    label: "Hava testi A",
    unit: "10^-6/bar",
    required: false,
    group: "air",
  },
  {
    key: "pressure_test.t_initial",
    label: "Başlangıç sıcaklığı (Tilk)",
    unit: "°C",
    required: false,
    group: "pressure",
  },
  {
    key: "pressure_test.t_final",
    label: "Bitiş sıcaklığı (Tson)",
    unit: "°C",
    required: false,
    group: "pressure",
  },
  {
    key: "pressure_test.delta_t",
    label: "Sıcaklık farkı (dT)",
    unit: "°C",
    required: false,
    group: "pressure",
  },
  {
    key: "pressure_test.pa",
    label: "Basınç düşüşü (Pa)",
    unit: "bar",
    required: false,
    group: "pressure",
  },
  {
    key: "pressure_test.a",
    label: "Basınç testi A",
    unit: "10^-6/bar",
    required: false,
    group: "pressure",
  },
  {
    key: "pressure_test.b",
    label: "Basınç testi B",
    unit: "10^-6/°C",
    required: false,
    group: "pressure",
  },
  { key: "result", label: "Sonuç", unit: "PASS / FAIL", required: false, group: "result" },
  { key: "notes", label: "Notlar", unit: "", required: false, group: "result" },
];

export const FIELD_DESCRIPTOR_BY_KEY: ReadonlyMap<string, FieldDescriptor> = new Map(
  FIELD_CATALOG.map((descriptor) => [descriptor.key, descriptor]),
);

/** Form etiketleri yarın netleşecek; bugünkü varsayılan alias listesi. */
export const DEFAULT_ALIASES: Record<string, readonly string[]> = {
  report_no: ["Rapor No", "Rapor Numarası", "Report No", "Belge No"],
  date: ["Test Tarihi", "Rapor Tarihi", "Tarih", "Date"],
  operator: ["Operatör", "Test Sorumlusu", "Gözetmen", "Inspector"],
  section_id: ["Bölüm No", "Kesim No", "Section No", "Segment"],
  pipe_od_mm: ["Boru Dış Çapı", "Dış Çap", "Outside Diameter", "Pipe OD"],
  wall_mm: ["Et Kalınlığı", "Cidar Kalınlığı", "Wall Thickness", "WT"],
  length_m: ["Test Uzunluğu", "Hat Uzunluğu", "Uzunluk", "Length"],
  test_pressure_bar: [
    "Hidrostatik Test Basıncı",
    "Test Basıncı",
    "Test Pressure",
    "Ptest",
  ],
  "air_test.vp": ["Teorik İlave Su", "Teorik Hacim", "Theoretical Volume", "Vp"],
  "air_test.vpa": ["Fiili İlave Su", "Gerçek Hacim", "Actual Volume", "Vpa"],
  "air_test.a": ["A (hava)", "Hava Testi A", "A"],
  "pressure_test.t_initial": [
    "Başlangıç Sıcaklığı",
    "İlk Sıcaklık",
    "Initial Temperature",
    "Tilk",
    "T1",
  ],
  "pressure_test.t_final": [
    "Bitiş Sıcaklığı",
    "Son Sıcaklık",
    "Final Temperature",
    "Tson",
    "T2",
  ],
  "pressure_test.delta_t": ["Sıcaklık Farkı", "Delta T", "ΔT", "dT"],
  "pressure_test.pa": ["Basınç Düşüşü", "Basınç Farkı", "Pressure Drop", "Pa"],
  "pressure_test.a": ["A (basınç)", "Basınç Testi A"],
  "pressure_test.b": ["B Katsayısı", "B Coefficient", "B"],
  result: ["Test Sonucu", "Sonuç", "Karar", "Result", "Verdict"],
  notes: ["Açıklama", "Notlar", "Remarks", "Notes"],
};

export function fieldLabel(key: string): string {
  const descriptor = FIELD_DESCRIPTOR_BY_KEY.get(key);
  if (descriptor) return descriptor.label;
  const last = key.split(".").pop() ?? key;
  return last
    .replace(/_/g, " ")
    .replace(/\b[a-z]/g, (letter) => letter.toUpperCase());
}

export function fieldUnit(key: string): string {
  return FIELD_DESCRIPTOR_BY_KEY.get(key)?.unit ?? "";
}

export function isExtractedField(value: unknown): value is ExtractedField {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
  const record = value as Record<string, unknown>;
  return typeof record.confidence === "number" && typeof record.unit === "string";
}

function readPath(source: unknown, key: string): unknown {
  const parts = key.split(".");
  let current: unknown = source;
  for (const part of parts) {
    if (current === null || typeof current !== "object") return undefined;
    current = (current as Record<string, unknown>)[part];
  }
  return current;
}

export interface FlatField {
  descriptor: FieldDescriptor;
  field: ExtractedField;
}

const NON_FIELD_KEYS = new Set(["schema_version", "warnings", "air_test", "pressure_test"]);

function syntheticDescriptor(key: string): FieldDescriptor {
  return {
    key,
    label: fieldLabel(key),
    unit: "",
    required: false,
    group: "other",
  };
}

/** Rapor ağacındaki tüm `ExtractedField` düğümlerini tablo sırasına göre düzleştirir. */
export function flattenReport(report: OcrReport | null | undefined): FlatField[] {
  const flattened: FlatField[] = [];
  if (!report) return flattened;

  const known = new Set<string>();
  for (const descriptor of FIELD_CATALOG) {
    known.add(descriptor.key);
    const field = readPath(report, descriptor.key);
    if (isExtractedField(field)) {
      flattened.push({ descriptor, field });
    }
  }

  const extras: FlatField[] = [];
  const visit = (value: unknown, prefix: string, depth: number): void => {
    if (value === null || typeof value !== "object" || Array.isArray(value)) return;
    if (isExtractedField(value)) {
      if (prefix && !known.has(prefix)) {
        extras.push({ descriptor: syntheticDescriptor(prefix), field: value });
      }
      return;
    }
    if (depth >= 2) return;
    for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
      if (!prefix && NON_FIELD_KEYS.has(key)) continue;
      const nextKey = prefix ? `${prefix}.${key}` : key;
      visit(child, nextKey, depth + 1);
    }
  };
  visit(report, "", 0);

  return [...flattened, ...extras];
}

export function reportWarnings(report: OcrReport | null | undefined): string[] {
  return report?.warnings ?? [];
}
