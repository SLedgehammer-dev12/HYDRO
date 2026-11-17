/**
 * Backend kapalıyken arayüzün tüm durumlarını gösterebilmesi için yerel demo verisi.
 * Bu veri hiçbir zaman resmi sonuç olarak sunulmaz; her yerde "DEMO" etiketi taşır.
 */
import { DEFAULT_ALIASES, FIELD_CATALOG } from "./fields";
import type {
  Discrepancy,
  ExtractedField,
  MappingFieldRule,
  MappingProfile,
  OcrAnalysisResult,
  OcrAnalysisSummary,
  OcrStatus,
  ValidationIssue,
} from "./types";

function field(
  value: string | number,
  unit: string,
  confidence: number,
  rawText: string,
  page: number,
): ExtractedField {
  return { value, unit, confidence, raw_text: rawText, page };
}

function buildMappingFields(keys: readonly string[]): Record<string, MappingFieldRule> {
  const fields: Record<string, MappingFieldRule> = {};
  for (const key of keys) {
    const descriptor = FIELD_CATALOG.find((item) => item.key === key);
    if (!descriptor) continue;
    fields[key] = {
      aliases: [...(DEFAULT_ALIASES[key] ?? [descriptor.label])],
      unit: descriptor.unit,
      required: descriptor.required,
    };
  }
  return fields;
}

export const DEMO_MAPPING_PROFILES: MappingProfile[] = [
  {
    id: "demo-mp-bot-021",
    name: "BOT-FRM-CDB-001-021 R2",
    format_key: "bot-frm-cdb-001-021",
    schema_version: 1,
    is_default: true,
    mode: "pre_extract",
    created_at: "2026-11-15T18:00:00Z",
    updated_at: "2026-11-15T18:00:00Z",
    mapping: {
      schema_version: 1,
      sections: [
        {
          name: "air",
          heading_aliases: ["Hava İçerik Testi", "Air Content Test"],
          before: "pressure",
        },
        {
          name: "pressure",
          heading_aliases: ["Basınç Testi", "Pressure Test"],
        },
      ],
      fields: {
        ...buildMappingFields(FIELD_CATALOG.map((descriptor) => descriptor.key)),
        test_pressure_bar: {
          aliases: [
            "Hidrostatik Test Basıncı",
            "Hid. Test Basıncı (Ptest)",
            "Test Basıncı",
            "Test Pressure",
          ],
          unit: "bar",
          required: true,
        },
        "air_test.vpa": {
          aliases: ["Fiili İlave Su", "Gerçek Hacim", "Actual Added Water", "Vpa"],
          unit: "m³",
          required: true,
        },
      },
      table_hints: { column_count: 2, label_value_layout: "same_line" },
    },
  },
  {
    id: "demo-mp-generic",
    name: "Genel Etiket Profili",
    format_key: "generic-labels",
    schema_version: 1,
    is_default: false,
    mode: "pre_extract",
    created_at: "2026-11-15T18:10:00Z",
    updated_at: "2026-11-15T18:10:00Z",
    mapping: {
      schema_version: 1,
      sections: [],
      fields: buildMappingFields([
        "report_no",
        "date",
        "operator",
        "pipe_od_mm",
        "wall_mm",
        "length_m",
        "test_pressure_bar",
        "air_test.vpa",
        "pressure_test.pa",
        "result",
      ]),
      table_hints: { column_count: 2, label_value_layout: "same_line" },
    },
  },
];

export const DEMO_STATUS: OcrStatus = {
  available: true,
  status_text: "OCR hazır (Tesseract + Pillow). Metin katmanlı PDF önceliklidir.",
  engine: {
    name: "tesseract",
    version: "5.3.4",
    languages: ["tur", "eng"],
    default_language: "tur+eng",
  },
  pdf_rasterizer: {
    available: false,
    engine: null,
    note: "Taranmış PDF için PyMuPDF veya pdf2image + Poppler gerekir; görsel OCR çalışmaya devam eder.",
  },
  limits: {
    max_file_size_bytes: 500 * 1024 * 1024,
    max_pdf_pages: 200,
    max_ocr_pages: 200,
    supported_extensions: [".pdf", ".xlsx", ".xls", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"],
  },
  queue: { queued: 0, running: 0, max_concurrency: 1 },
  thresholds: {
    auto_fill: 0.85,
    low_confidence: 0.6,
    critical_confidence: 0.4,
    human_review_required: true,
  },
  mapping_profiles: { default_id: "demo-mp-bot-021", count: DEMO_MAPPING_PROFILES.length },
};

const DEMO_DISCREPANCIES: Discrepancy[] = [
  {
    field: "test_pressure_bar",
    label: "Test basıncı",
    reported: 80.0,
    calculated: 80.0,
    unit: "bar",
    delta: 0,
    tolerance: "±0.05 bar",
    status: "match",
    severity: "info",
    message: "Rapor değeri hesaplanan değerle uyuşuyor.",
  },
  {
    field: "air_test.vpa",
    label: "Hava testi Vpa",
    reported: 0.00775,
    calculated: 0.00768,
    unit: "m³",
    delta: 0.00007,
    tolerance: "%1 veya 1 mL",
    status: "mismatch",
    severity: "critical",
    message:
      "Rapor değeri hesaplanan değerden 0,000070 m³ yüksek; tolerans dışı. Kabul akışı durduruldu.",
  },
  {
    field: "pipe_od_mm",
    label: "Dış çap",
    reported: 406.4,
    calculated: 406.4,
    unit: "mm",
    delta: 0,
    tolerance: "±0.5 mm",
    status: "match",
    severity: "info",
    message: "Rapor değeri hesaplanan değerle uyuşuyor.",
  },
  {
    field: "length_m",
    label: "Hat uzunluğu",
    reported: 12000.0,
    calculated: 12000.0,
    unit: "m",
    delta: 0,
    tolerance: "±1.0 m",
    status: "match",
    severity: "info",
    message: "Rapor değeri hesaplanan değerle uyuşuyor.",
  },
  {
    field: "pressure_test.delta_t",
    label: "Sıcaklık farkı (dT)",
    reported: 2.4,
    calculated: 2.4,
    unit: "°C",
    delta: 0,
    tolerance: "±0.5 °C",
    status: "match",
    severity: "info",
    message: "Rapor değeri hesaplanan değerle uyuşuyor.",
  },
  {
    field: "pressure_test.pa",
    label: "Basınç düşüşü (Pa)",
    reported: 0.55,
    calculated: 0.55,
    unit: "bar",
    delta: 0,
    tolerance: "±0.05 bar",
    status: "match",
    severity: "info",
    message: "Rapor değeri hesaplanan değerle uyuşuyor.",
  },
  {
    field: "air_test.a",
    label: "Hava testi A",
    reported: 44.971994,
    calculated: null,
    unit: "10^-6/bar",
    delta: null,
    tolerance: "%2 veya 2 micro/bar",
    status: "missing_in_calculation",
    severity: "info",
    message: "Hesaplanan A değeri gönderilmedi; bu alan karşılaştırma dışı bırakıldı.",
  },
];

const DEMO_ISSUES: ValidationIssue[] = [
  {
    field: "air_test.a",
    code: "low_confidence",
    message: "Hava testi A alanı düşük güvenle okundu (%31); insan onayı gerekli.",
    severity: "critical",
  },
  {
    field: "test_pressure_bar",
    code: "low_confidence",
    message: "Test basıncı alanı düşük güvenle okundu (%58); insan onayı gerekli.",
    severity: "warning",
  },
  {
    field: "pressure_test.t_final",
    code: "low_confidence",
    message: "Bitiş sıcaklığı alanı düşük güvenle okundu (%55); insan onayı gerekli.",
    severity: "warning",
  },
  {
    field: "section_id",
    code: "ambiguous_candidate",
    message: "Bölüm No iki yerde geçiyor (12 ve 12); en yüksek güvenli aday seçildi.",
    severity: "info",
  },
  {
    field: "operator",
    code: "unverified_label",
    message: "Operatör adı form başlığından okundu; imza ile karşılaştırılmalı.",
    severity: "warning",
  },
];

export const DEMO_RESULT: OcrAnalysisResult = {
  id: "demo-c2d3f1a4",
  status: "succeeded",
  source: "mixed",
  page_count: 2,
  character_count: 4210,
  confidence: 0.79,
  needs_human_review: true,
  metrics: { low_confidence_fields: 3, critical_confidence_fields: 1 },
  report: {
    schema_version: 1,
    report_no: field("BOT-2026-0142", "", 0.93, "BOT-2026-0142", 1),
    date: field("2026-11-15", "ISO tarih", 0.88, "15.11.2026", 1),
    operator: field("M. Yıldız", "", 0.72, "Operatör: M. Yıldız", 1),
    section_id: field("12", "", 0.81, "Bölüm No: 12", 1),
    pipe_od_mm: field(406.4, "mm", 0.95, "406,4 mm", 1),
    wall_mm: field(8.74, "mm", 0.93, "8,74 mm", 1),
    length_m: field(12000.0, "m", 0.9, "12.000 m", 1),
    test_pressure_bar: field(80.0, "bar", 0.58, "80,0 bar", 1),
    air_test: {
      vp: field(0.00768, "m³", 0.88, "0,00768", 2),
      vpa: field(0.00775, "m³", 0.87, "0,00775", 2),
      a: field(44.971994, "10^-6/bar", 0.31, "44,97", 2),
    },
    pressure_test: {
      t_initial: field(22.4, "°C", 0.9, "22,4 °C", 2),
      t_final: field(20.0, "°C", 0.55, "20,0 °C", 2),
      delta_t: field(2.4, "°C", 0.62, "2,4", 2),
      pa: field(0.55, "bar", 0.9, "0,55 bar", 2),
      a: null,
      b: null,
    },
    result: field("PASS", "", 0.92, "PASS", 2),
    notes: null,
    warnings: [],
  },
  discrepancies: DEMO_DISCREPANCIES,
  issues: DEMO_ISSUES,
  warnings: [
    "OCR kullanıldı; tüm alanlar insan onayından geçmelidir.",
    "Fiili ilave su (Vpa) değeri virgüllü ondalıkla yazılmış; ondalık/binlik ayrımı kontrol edildi.",
    "Sayfa 2'deki el yazısı imza alanı doğrulanmaz; hukuki geçerlilik için ayrı süreç gerekir.",
  ],
  approved_fields: null,
  error: null,
  created_at: "2026-11-15T20:00:00Z",
  started_at: "2026-11-15T20:00:01Z",
  finished_at: "2026-11-15T20:00:04Z",
  demo: true,
};

export const DEMO_HISTORY: OcrAnalysisSummary[] = [
  {
    id: DEMO_RESULT.id,
    status: "succeeded",
    source: "mixed",
    confidence: 0.79,
    page_count: 2,
    created_at: "2026-11-15T20:00:00Z",
    finished_at: "2026-11-15T20:00:04Z",
    warnings_count: 3,
    discrepancies_count: DEMO_DISCREPANCIES.length,
    blocking_count: 1,
  },
];

/** Hesaplanan değerler için örnek payload; "Örnek doldur" butonu kullanır. */
export const SAMPLE_CALCULATED: Record<string, unknown> = {
  pipe_od_mm: 406.4,
  wall_mm: 8.74,
  length_m: 12000.0,
  test_pressure_bar: 80.0,
  air_test: {
    vp_m3: 0.00768,
    vpa_m3: 0.00768,
    a_micro_per_bar: 44.971994,
  },
  pressure_test: {
    t_initial_c: 22.4,
    t_final_c: 20.0,
    delta_t_c: 2.4,
    pa_bar: 0.55,
    a_micro_per_bar: 44.971994,
    b_micro_per_c: 188.661,
  },
  result: "PASS",
};
