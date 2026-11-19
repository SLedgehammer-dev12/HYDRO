/**
 * Backend erişilemediğinde kullanılan demo motoru.
 *
 * Amaç: arayüz boş görünmesin ve formlar gerçek API yokken de çalışsın.
 * Formüller sözleşmedeki/parity matrisindeki domain ilişkilerini yaklaşık
 * olarak yansıtır; resmi karar üretmez ve her ekranda "demo" olarak işaretlenir.
 */

import type {
  AirContentRequest,
  AirContentResponse,
  AppInputs,
  BackendComparisonResponse,
  BComparisonResponse,
  BSourceResult,
  CoefficientARequest,
  CoefficientAResponse,
  CoefficientBRequest,
  CoefficientCompareRequest,
  DecisionStatus,
  EquipmentInputItem,
  GeometryIn,
  GeometryResponse,
  GeometrySummary,
  GradeOption,
  HistoryEntry,
  MetaResponse,
  OcrStatusResponse,
  PigSpeedRequest,
  PigSpeedResponse,
  PipeOption,
  PressureProfileRequest,
  PressureProfileResponse,
  PressureVariationRequest,
  PressureVariationResponse,
  PressurizationResponse,
  Project,
  ReferenceTableMeta,
  ResultBundle,
  Session,
  SessionListItem,
  SpecResponse,
  TablePointResponse,
} from "./types";
import {
  FALLBACK_LIMITS,
  FALLBACK_LOCATION_CLASSES,
  FALLBACK_PIG_MODES,
  FALLBACK_PUMP_LOCATIONS,
  STEEL_ALPHA_DEFAULT,
  WATER_DENSITY_15C,
} from "./constants";
import { formatKp, parseKpMeters } from "./kp";
import type { SceneData, SceneEquipment, SceneLandmark, SceneSegment } from "./scene";

const round = (value: number, digits = 6): number => {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
};

const clamp = (value: number, min: number, max: number): number =>
  Math.min(max, Math.max(min, value));

export const sleep = (ms = 320): Promise<void> =>
  new Promise((resolve) => setTimeout(resolve, ms));

export const DEMO_NOW = "2026-11-15T19:42:11Z";

/* ------------------------------------------------------------------ */
/* Meta / katalog sabitleri                                            */
/* ------------------------------------------------------------------ */

export const DEMO_META: MetaResponse = {
  app: { name: "Hidrostatik Test Değerlendirme", version: "1.9.1" },
  spec: {
    code: "4-NGTL 0-GN-P-002-5007 R4",
    title: "Hidrostatik Test ve İçten Denetleme Şartnamesi",
  },
  engine: {
    domain_schema: 1,
    decision_statuses: [
      "BEKLIYOR",
      "KATSAYI GUNCELLENMELI",
      "DOGRULANAMADI",
      "BASARILI",
      "BASARISIZ",
    ],
  },
  water_backends: [
    {
      key: "table_v1",
      label: "Table Interpolation v1",
      distribution_ready: true,
      note: "0-40 °C, 1-150 bar · bilinear",
    },
    {
      key: "table_v1_bicubic",
      label: "Table Interpolation v1 (Bicubic)",
      distribution_ready: true,
      note: "0-40 °C, 1-150 bar · bicubic",
    },
    {
      key: "coolprop",
      label: "CoolProp EOS",
      distribution_ready: true,
      note: "Varsayılan (kuruluysa)",
    },
  ],
  b_sources: [
    { key: "institutional", label: "Kurum içi A/B kontrol tablosu", default: true },
    { key: "gail", label: "GAIL referans tablosu" },
    { key: "auto", label: "Otomatik β − çelik genleşmesi" },
  ],
  steel_models: ["volumetric", "linear", "volumetric_temperature"],
  location_classes: FALLBACK_LOCATION_CLASSES,
  pump_locations: FALLBACK_PUMP_LOCATIONS,
  pig_modes: FALLBACK_PIG_MODES,
  limits: FALLBACK_LIMITS,
  features: { ocr: true, scene: true, dev_backends: false, auth: "none" },
  units: {
    pressure: "bar",
    temperature: "°C",
    length: "m",
    diameter: "mm",
    volume: "m³",
    a: "10⁻⁶/bar",
    b: "10⁻⁶/°C",
  },
};

export const DEMO_SPEC: SpecResponse = {
  code: DEMO_META.spec.code,
  title: DEMO_META.spec.title,
  acceptance_rules: {
    air: { text: "Vpa < 1.06 x Vp", factor: 1.06 },
    pressure: { text: "(Pa - Pt) <= 0.3 bar", tolerance_bar: 0.3 },
  },
  sign_convention: { delta_t: "ΔT = Tilk - Tson", pa: "Pa = Pilk - Pson" },
  checks: [
    {
      key: "ambient_temp",
      label: "Dolum sırasında hava sıcaklığı +2 °C limitine göre kontrol edildi",
      reference: "10.1",
    },
    {
      key: "forms",
      label: "21.1-21.5 saha formları dolduruldu",
      reference: "21",
    },
  ],
  notes: [
    "Nihai karar ASME B31.8 ve proje prosedürü ile birlikte değerlendirilmelidir.",
    "OCR çıktısı resmi kabul raporu değildir; insan onayı zorunludur.",
  ],
};

export const DEMO_PIPES: PipeOption[] = [
  {
    nps: "8",
    dn: "200",
    outside_diameter_mm: 219.1,
    option_label: "NPS 8 (DN 200) - OD 219.10 mm",
    schedules: [
      { label: "Sch 20 - 6.35 mm", wall_thickness_mm: 6.35 },
      { label: "Sch 40 - 8.18 mm", wall_thickness_mm: 8.18 },
      { label: "Sch 80 - 12.70 mm", wall_thickness_mm: 12.7 },
    ],
  },
  {
    nps: "10",
    dn: "250",
    outside_diameter_mm: 273.1,
    option_label: "NPS 10 (DN 250) - OD 273.10 mm",
    schedules: [
      { label: "Sch 20 - 6.35 mm", wall_thickness_mm: 6.35 },
      { label: "Sch 30 - 7.80 mm", wall_thickness_mm: 7.8 },
      { label: "Sch 40 - 9.27 mm", wall_thickness_mm: 9.27 },
    ],
  },
  {
    nps: "12",
    dn: "300",
    outside_diameter_mm: 323.9,
    option_label: "NPS 12 (DN 300) - OD 323.90 mm",
    schedules: [
      { label: "Sch 20 - 6.35 mm", wall_thickness_mm: 6.35 },
      { label: "Sch 30 - 8.38 mm", wall_thickness_mm: 8.38 },
      { label: "Sch 40 - 10.31 mm", wall_thickness_mm: 10.31 },
    ],
  },
  {
    nps: "14",
    dn: "350",
    outside_diameter_mm: 355.6,
    option_label: "NPS 14 (DN 350) - OD 355.60 mm",
    schedules: [
      { label: "Sch 10 - 6.35 mm", wall_thickness_mm: 6.35 },
      { label: "Sch 20 - 7.92 mm", wall_thickness_mm: 7.92 },
      { label: "Sch 30 - 9.53 mm", wall_thickness_mm: 9.53 },
    ],
  },
  {
    nps: "16",
    dn: "400",
    outside_diameter_mm: 406.4,
    option_label: "NPS 16 (DN 400) - OD 406.40 mm",
    schedules: [
      { label: "Sch 10 - 6.35 mm", wall_thickness_mm: 6.35 },
      { label: "Sch 20 - 8.74 mm", wall_thickness_mm: 8.74 },
      { label: "Sch 30 - 12.70 mm", wall_thickness_mm: 12.7 },
    ],
  },
  {
    nps: "20",
    dn: "500",
    outside_diameter_mm: 508.0,
    option_label: "NPS 20 (DN 500) - OD 508.00 mm",
    schedules: [
      { label: "Sch 10 - 6.35 mm", wall_thickness_mm: 6.35 },
      { label: "Sch 20 - 9.53 mm", wall_thickness_mm: 9.53 },
      { label: "Sch 30 - 15.09 mm", wall_thickness_mm: 15.09 },
    ],
  },
  {
    nps: "24",
    dn: "600",
    outside_diameter_mm: 610.0,
    option_label: "NPS 24 (DN 600) - OD 610.00 mm",
    schedules: [
      { label: "Sch 10 - 6.35 mm", wall_thickness_mm: 6.35 },
      { label: "Sch 20 - 9.53 mm", wall_thickness_mm: 9.53 },
      { label: "Sch 30 - 17.48 mm", wall_thickness_mm: 17.48 },
    ],
  },
  {
    nps: "30",
    dn: "750",
    outside_diameter_mm: 762.0,
    option_label: "NPS 30 (DN 750) - OD 762.00 mm",
    schedules: [
      { label: "Sch 10 - 7.92 mm", wall_thickness_mm: 7.92 },
      { label: "Sch 20 - 12.70 mm", wall_thickness_mm: 12.7 },
    ],
  },
  {
    nps: "36",
    dn: "900",
    outside_diameter_mm: 914.0,
    option_label: "NPS 36 (DN 900) - OD 914.00 mm",
    schedules: [
      { label: "Sch 10 - 7.92 mm", wall_thickness_mm: 7.92 },
      { label: "Sch 20 - 12.70 mm", wall_thickness_mm: 12.7 },
      { label: "Sch 30 - 19.05 mm", wall_thickness_mm: 19.05 },
    ],
  },
];

export const DEMO_GRADES: GradeOption[] = [
  { grade: "X42", iso_label: "L290", smys_mpa: 290, option_label: "API 5L PSL2 X42 / L290 - SMYS 290 MPa" },
  { grade: "X46", iso_label: "L320", smys_mpa: 320, option_label: "API 5L PSL2 X46 / L320 - SMYS 320 MPa" },
  { grade: "X52", iso_label: "L360", smys_mpa: 360, option_label: "API 5L PSL2 X52 / L360 - SMYS 360 MPa" },
  { grade: "X56", iso_label: "L390", smys_mpa: 390, option_label: "API 5L PSL2 X56 / L390 - SMYS 390 MPa" },
  { grade: "X60", iso_label: "L415", smys_mpa: 415, option_label: "API 5L PSL2 X60 / L415 - SMYS 415 MPa" },
  { grade: "X65", iso_label: "L450", smys_mpa: 450, option_label: "API 5L PSL2 X65 / L450 - SMYS 450 MPa" },
  { grade: "X70", iso_label: "L485", smys_mpa: 485, option_label: "API 5L PSL2 X70 / L485 - SMYS 485 MPa" },
  { grade: "X80", iso_label: "L555", smys_mpa: 555, option_label: "API 5L PSL2 X80 / L555 - SMYS 555 MPa" },
];

export const DEMO_REFERENCE_TABLES: ReferenceTableMeta[] = [
  {
    key: "institutional",
    label: "Kurum içi A/B kontrol tablosu",
    option_label: "BOTAŞ referans tablosu - aktif T/P",
    temperature: { min: 1, max: 25, step: 1, count: 25 },
    pressure: { min: 30, max: 120, step: 1, count: 91 },
    a_unit: "10⁻⁶/bar",
    b_unit: "10⁻⁶/°C",
    source_note: "A ve B Katsayısı.xlsx",
    a_repair: { enabled: true, band_c: 7, pressure_range_bar: [81, 100] },
  },
  {
    key: "gail",
    label: "GAIL referans tablosu",
    option_label: "GAIL referans tablosu - aktif T/P",
    temperature: { min: 2, max: 30, step: 2, count: 15 },
    pressure: { min: 30, max: 120, step: 10, count: 10 },
    a_unit: "10⁻⁶/bar",
    b_unit: "10⁻⁶/°C",
    source_note: "GAIL-STD-PL-DOC-TS-012 Table-1 ve Fig.1",
  },
];

/* ------------------------------------------------------------------ */
/* Girdiler                                                            */
/* ------------------------------------------------------------------ */

export const DEMO_GEOMETRY = {
  outside_diameter_mm: 406.4,
  wall_thickness_mm: 8.74,
  length_m: 12_000,
};

export function createDefaultSegments(): AppInputs["segments"] {
  return [
    {
      id: "seg-demo-1",
      nps_label: "NPS 16 (DN 400)",
      schedule_label: "Sch 20 - 8.74 mm",
      outside_diameter_mm: 406.4,
      wall_thickness_mm: 8.74,
      length_m: 4_200,
      start_station_m: 0,
    },
    {
      id: "seg-demo-2",
      nps_label: "NPS 14 (DN 350)",
      schedule_label: "Sch 30 - 9.53 mm",
      outside_diameter_mm: 355.6,
      wall_thickness_mm: 9.53,
      length_m: 5_300,
      start_station_m: 4_200,
    },
    {
      id: "seg-demo-3",
      nps_label: "NPS 12 (DN 300)",
      schedule_label: "Sch 30 - 8.38 mm",
      outside_diameter_mm: 323.9,
      wall_thickness_mm: 8.38,
      length_m: 2_500,
      start_station_m: 9_500,
    },
  ];
}

export function createDefaultInputs(): AppInputs {
  const inputs: AppInputs = {
    water_backend: "table_v1",
    section_meta: {
      section_no: "K-01",
      description: "Bölüm 12–13 · Doğu Hattı",
      location: "KP 0+000 – 12+000",
      start_kp: "0+000",
      end_kp: "12+000",
      test_date: "2026-11-15",
      test_type: "Hidrostatik test",
      notes: "",
    },
    geometry: { ...DEMO_GEOMETRY },
    geometry_catalog: {
      size_option: "NPS 16 (DN 400) - OD 406.40 mm",
      schedule_option: "Sch 20 - 8.74 mm",
    },
    segments: createDefaultSegments(),
    profile_points: [],
    landmarks: [],
    equipment: [],
    section_profile: {
      highest_elevation_m: 320,
      lowest_elevation_m: 180,
      start_elevation_m: 200,
      end_elevation_m: 310,
      design_pressure_bar: 80,
      smys_mpa: 450,
    },
    material_grade: "API 5L PSL2 X65 / L450 - SMYS 450 MPa",
    location_class: "Class 1 - min 1.25 x dizayn basinci",
    pump_location: "Baslangic noktasi",
    air: {
      temperature_c: 20,
      pressure_bar: 80,
      a_micro_per_bar: 44.971994,
      pressure_rise_bar: 1,
      k_factor: 1.02,
      actual_added_water_m3: 0.0861,
      ambient_temperature_c: 5,
    },
    pressure: {
      temperature_c: 20,
      pressure_bar: 80,
      a_micro_per_bar: 44.971994,
      b_micro_per_c: 188.661,
      delta_t_c: 2,
      actual_pressure_change_bar: 5.95,
      t_initial_c: 22,
      t_final_c: 20,
      derive_delta_t: true,
    },
    field: {
      ambient_temperature_c: 5,
      pig_distance_m: 5_000,
      pig_travel_time_min: 45,
      pig_speed_m_per_s: null,
      pig_speed_km_per_h: null,
      monitored_pressure_bar: 112,
    },
    helper: { steel_alpha_micro_per_c: STEEL_ALPHA_DEFAULT, water_beta_micro_per_c: 218.297191 },
    modes: {
      air_a_mode: "auto",
      air_a_reference: "",
      pressure_a_mode: "auto",
      pressure_a_reference: "",
      pressure_b_mode: "table",
      pressure_b_source: "institutional",
      pressure_b_reference: "BOTAŞ referans tablosu - aktif T/P",
      steel_model: "volumetric",
      k_preset: "Kaynaklı boru - 1.02",
      steel_preset: "Karbon çelik - 12.0",
      pig_mode: "Temizlik pigi",
    },
    checks: {
      ambient_temp: true,
      temp_probes: true,
      fill_air_entry: true,
      fill_records: true,
      thermal_balance: false,
      air_content_limit: true,
      pressurization_volume: false,
      two_hour_hold: false,
      pressure_records: false,
      depressurize_discharge: false,
      forms: false,
    },
    report: {
      report_no: "BOT-2026-0142",
      operator: "M. Yılmaz",
      date: "2026-11-15",
      section_id: "12-13",
    },
  };

  const geometry = geometryForInputs(inputs);
  if (geometry) {
    const summary = toSummary(geometry);
    const vp =
      ((summary.elasticity_term + (inputs.air.a_micro_per_bar ?? 44.972)) *
        1e-6 *
        summary.internal_volume_m3 *
        1.0 *
        inputs.air.k_factor);
    inputs.air.actual_added_water_m3 = round(vp * 1.06 * 0.955, 6);
  }

  return inputs;
}

export function createEmptyInputs(): AppInputs {
  return {
    water_backend: "table_v1",
    section_meta: {
      section_no: "",
      description: "",
      location: "",
      start_kp: "",
      end_kp: "",
      test_date: "",
      test_type: "Hidrostatik test",
      notes: "",
    },
    geometry: {
      outside_diameter_mm: null,
      wall_thickness_mm: null,
      length_m: null,
    },
    geometry_catalog: {
      size_option: "",
      schedule_option: "",
    },
    segments: [],
    profile_points: [],
    landmarks: [],
    equipment: [],
    section_profile: {
      highest_elevation_m: null,
      lowest_elevation_m: null,
      start_elevation_m: null,
      end_elevation_m: null,
      design_pressure_bar: null,
      smys_mpa: null,
    },
    material_grade: "",
    location_class: "Class 1 - min 1.25 x dizayn basinci",
    pump_location: "Baslangic noktasi",
    air: {
      temperature_c: null,
      pressure_bar: null,
      a_micro_per_bar: null,
      pressure_rise_bar: 1,
      k_factor: 1.02,
      actual_added_water_m3: null,
      ambient_temperature_c: null,
    },
    pressure: {
      temperature_c: null,
      pressure_bar: null,
      a_micro_per_bar: null,
      b_micro_per_c: null,
      delta_t_c: null,
      actual_pressure_change_bar: null,
      t_initial_c: null,
      t_final_c: null,
      derive_delta_t: false,
    },
    field: {
      ambient_temperature_c: null,
      pig_distance_m: null,
      pig_travel_time_min: null,
      pig_speed_m_per_s: null,
      pig_speed_km_per_h: null,
      monitored_pressure_bar: null,
    },
    helper: { steel_alpha_micro_per_c: STEEL_ALPHA_DEFAULT, water_beta_micro_per_c: null },
    modes: {
      air_a_mode: "auto",
      air_a_reference: "",
      pressure_a_mode: "auto",
      pressure_a_reference: "",
      pressure_b_mode: "table",
      pressure_b_source: "institutional",
      pressure_b_reference: "BOTAŞ referans tablosu - aktif T/P",
      steel_model: "volumetric",
      k_preset: "Kaynaklı boru - 1.02",
      steel_preset: "Karbon çelik - 12.0",
      pig_mode: "Temizlik pigi",
    },
    checks: {
      ambient_temp: false,
      temp_probes: false,
      fill_air_entry: false,
      fill_records: false,
      thermal_balance: false,
      air_content_limit: false,
      pressurization_volume: false,
      two_hour_hold: false,
      pressure_records: false,
      depressurize_discharge: false,
      forms: false,
    },
    report: {
      report_no: "",
      operator: "",
      date: "",
      section_id: "",
    },
  };
}

/* ------------------------------------------------------------------ */
/* Saf hesap yardımcıları                                             */
/* ------------------------------------------------------------------ */

export function sectionsFromInputs(inputs: AppInputs): GeometryIn["sections"] {
  const validSegments = inputs.segments.filter(
    (s) =>
      isPositive(s.outside_diameter_mm) &&
      isPositive(s.wall_thickness_mm) &&
      isPositive(s.length_m),
  );
  if (validSegments.length > 0) {
    return validSegments.map((s) => ({
      outside_diameter_mm: s.outside_diameter_mm as number,
      wall_thickness_mm: s.wall_thickness_mm as number,
      length_m: s.length_m as number,
      nps_label: s.nps_label || null,
      schedule_label: s.schedule_label || null,
      start_station_m: s.start_station_m ?? null,
    }));
  }
  const g = inputs.geometry;
  if (isPositive(g.outside_diameter_mm) && isPositive(g.wall_thickness_mm) && isPositive(g.length_m)) {
    return [
      {
        outside_diameter_mm: g.outside_diameter_mm,
        wall_thickness_mm: g.wall_thickness_mm,
        length_m: g.length_m,
        nps_label: inputs.geometry_catalog.size_option || null,
        schedule_label: inputs.geometry_catalog.schedule_option || null,
        start_station_m: 0,
      },
    ];
  }
  return [];
}

function isPositive(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value) && value > 0;
}

export function computeGeometry(sections: GeometryIn["sections"]): GeometryResponse {
  const results = sections.map((section, index) => {
    const ri = section.outside_diameter_mm / 2 - section.wall_thickness_mm;
    const volume = Math.PI * (ri / 1000) ** 2 * section.length_m;
    return {
      index: index + 1,
      outside_diameter_mm: section.outside_diameter_mm,
      wall_thickness_mm: section.wall_thickness_mm,
      length_m: section.length_m,
      internal_radius_mm: round(ri, 3),
      internal_volume_m3: round(volume, 6),
      elasticity_term: round((0.884 * ri) / section.wall_thickness_mm, 6),
    };
  });

  const totalLength = results.reduce((sum, s) => sum + s.length_m, 0);
  const totalVolume = results.reduce((sum, s) => sum + s.internal_volume_m3, 0);
  const elasticity =
    totalVolume > 0
      ? results.reduce((sum, s) => sum + s.elasticity_term * s.internal_volume_m3, 0) / totalVolume
      : 0;
  const equivalentRadius =
    totalLength > 0 ? Math.sqrt(totalVolume / (Math.PI * totalLength)) * 1000 : 0;

  return {
    section_count: results.length,
    total_length_m: round(totalLength, 6),
    internal_volume_m3: round(totalVolume, 6),
    internal_radius_mm: round(equivalentRadius, 3),
    elasticity_term: round(elasticity, 6),
    sections: results,
  };
}

export function toSummary(geometry: GeometryResponse): GeometrySummary {
  return {
    total_length_m: geometry.total_length_m,
    internal_volume_m3: geometry.internal_volume_m3,
    internal_radius_mm: geometry.internal_radius_mm,
    elasticity_term: geometry.elasticity_term,
  };
}

export function geometryForInputs(inputs: AppInputs): GeometryResponse | null {
  const sections = sectionsFromInputs(inputs);
  if (sections.length === 0) return null;
  return computeGeometry(sections);
}

export function computeA(inputs: CoefficientARequest): CoefficientAResponse {
  const temperature = clamp(inputs.temperature_c, 0, 40);
  const pressure = clamp(inputs.pressure_bar, 1, 150);
  const normalizedA = 44.971994 - 0.0125 * (pressure - 80) + 0.135 * (temperature - 20);
  return {
    a_micro_per_bar: round(normalizedA, 6),
    temperature_c: inputs.temperature_c,
    pressure_bar: inputs.pressure_bar,
    backend: {
      key: inputs.backend ?? "table_v1",
      label:
        inputs.backend === "coolprop"
          ? "CoolProp EOS"
          : inputs.backend === "table_v1_bicubic"
            ? "Table Interpolation v1 (Bicubic)"
            : "Table Interpolation v1",
      distribution_ready: true,
    },
    state: "computed",
  };
}

export function estimateWaterBeta(t: number, p: number): number {
  const tZero = 3.98 - 0.021 * Math.max(0, p - 1);
  const dt = t - tZero;
  return round(14.5 * dt - 0.125 * dt * dt, 6);
}

export function computeB(inputs: CoefficientBRequest): BSourceResult {
  const t = inputs.temperature_c;
  const p = inputs.pressure_bar;
  const beta = estimateWaterBeta(t, p);

  if (inputs.source === "auto") {
    const alpha = inputs.steel_alpha_micro_per_c;
    let effective = 3 * alpha;
    if (inputs.steel_model === "linear") effective = alpha;
    if (inputs.steel_model === "volumetric_temperature") {
      const alphaAtT = 10.8 + 0.012 * t;
      effective = 3 * alphaAtT;
    }
    const prefix = inputs.backend ? `Otomatik hesap (${inputs.backend})` : "Otomatik hesap";
    return {
      b_micro_per_c: round(beta - effective, 6),
      source: "auto",
      label: "Otomatik β - çelik genleşmesi",
      note:
        inputs.steel_model === "linear"
          ? `${prefix}: β = ${round(beta, 6)}, α = ${alpha.toFixed(3)}; B = β − α.`
          : inputs.steel_model === "volumetric_temperature"
            ? `${prefix}: β = ${round(beta, 6)}; α(T) = ${round(10.8 + 0.012 * t, 6)}; B = β − 3·α(T).`
            : `${prefix}: β = ${round(beta, 6)}, çelik α = ${alpha.toFixed(3)}; B = β − 3·α.`,
      repaired_table: false,
      water_beta_micro_per_c: round(beta, 6),
      steel_alpha_micro_per_c: alpha,
      steel_model: inputs.steel_model,
    };
  }

  const institutional = inputs.source === "institutional";
  const value = institutional
    ? 188.661 + 0.35 * (t - 20) - 0.01 * (p - 80)
    : 184.03 + 0.3 * (t - 20) - 0.008 * (p - 80);

  return {
    b_micro_per_c: round(value, 6),
    source: inputs.source,
    label: institutional ? "Kurum içi A/B kontrol tablosu" : "GAIL referans tablosu",
    note: institutional
      ? "Bilinear tablo interpolasyonu (kurum içi / BOTAŞ)."
      : "GAIL referans tablosu interpolasyonu.",
    repaired_table: institutional && Math.abs(t - 7) < 1 && p >= 81 && p <= 100,
    water_beta_micro_per_c: null,
    steel_alpha_micro_per_c: null,
    steel_model: "",
  };
}

export function computeCompare(inputs: CoefficientCompareRequest): BComparisonResponse {
  const institutional = computeB({ ...inputs, source: "institutional" });
  const gail = computeB({ ...inputs, source: "gail" });
  const auto = computeB({ ...inputs, source: "auto" });
  return {
    temperature_c: inputs.temperature_c,
    pressure_bar: inputs.pressure_bar,
    institutional,
    gail,
    auto,
    deltas: {
      institutional_vs_gail: round(institutional.b_micro_per_c - gail.b_micro_per_c, 6),
      auto_vs_institutional: round(auto.b_micro_per_c - institutional.b_micro_per_c, 6),
      auto_vs_gail: round(auto.b_micro_per_c - gail.b_micro_per_c, 6),
    },
  };
}

export function computeAir(request: AirContentRequest): AirContentResponse {
  const geometry = computeGeometry(request.geometry.sections);
  const summary = toSummary(geometry);
  const theoretical =
    ((summary.elasticity_term + request.a_micro_per_bar) *
      1e-6 *
      summary.internal_volume_m3 *
      request.pressure_rise_bar *
      request.k_factor);
  const limit = theoretical * 1.06;
  const ratio = theoretical > 0 ? request.actual_added_water_m3 / theoretical : 0;
  const passed = request.actual_added_water_m3 < limit * (1 - 1e-9);
  const margin = limit - request.actual_added_water_m3;

  return {
    theoretical_added_water_m3: round(theoretical, 6),
    acceptance_limit_m3: round(limit, 6),
    actual_added_water_m3: round(request.actual_added_water_m3, 6),
    ratio: round(ratio, 6),
    passed,
    geometry: summary,
    decision: {
      status: passed ? "BASARILI" : "BASARISIZ",
      title: "Hava İçerik Testi",
      summary: `Vp = ${round(theoretical, 6)} m³, limit = ${round(limit, 6)} m³, Vpa = ${round(
        request.actual_added_water_m3,
        6,
      )} m³, oran = ${round(ratio, 6)}. Kural: Vpa < 1.06 x Vp; marj = ${round(margin, 6)} m³.`,
      rule: "Vpa < 1.06 x Vp",
      margin: round(margin, 6),
    },
  };
}

export function computePressure(request: PressureVariationRequest): PressureVariationResponse {
  const geometry = computeGeometry(request.geometry.sections);
  const summary = toSummary(geometry);
  const denominator = summary.elasticity_term + request.a_micro_per_bar;
  const theoretical = denominator !== 0 ? (request.b_micro_per_c * request.delta_t_c) / denominator : 0;
  const upper = theoretical + 0.3;
  const margin = request.actual_pressure_change_bar - theoretical;
  const passed = margin <= 0.3 + 1e-9;
  const negativeB = request.b_micro_per_c < 0;
  let summaryText = `Pt = ${round(theoretical, 6)} bar, üst sınır = ${round(upper, 6)} bar, Pa = ${round(
    request.actual_pressure_change_bar,
    6,
  )} bar, fark = ${round(margin, 6)} bar. Kural: (Pa - Pt) <= 0.3 bar.`;
  if (negativeB) {
    summaryText += " B negatif: dP işareti ters döner ve geçerlidir.";
  }

  return {
    theoretical_pressure_change_bar: round(theoretical, 6),
    allowable_upper_pressure_change_bar: round(upper, 6),
    actual_pressure_change_bar: round(request.actual_pressure_change_bar, 6),
    margin_bar: round(margin, 6),
    passed,
    negative_b: negativeB,
    geometry: summary,
    decision: {
      status: passed ? "BASARILI" : "BASARISIZ",
      title: "Basınç Değişim Testi",
      summary: summaryText,
      rule: "(Pa - Pt) <= 0.3 bar",
      margin: round(margin, 6),
    },
  };
}

export function computeProfile(request: PressureProfileRequest): PressureProfileResponse {
  const geometry = computeGeometry(request.geometry.sections);
  const factors = FALLBACK_LOCATION_CLASSES.find((c) => c.label === request.location_class);
  const factor = factors?.minimum_test_factor ?? 1.25;
  const classNumber = factors?.class_number ?? 1;
  const requiredMin = request.design_pressure_bar * factor;
  const maxLow = Math.min(
    ...request.geometry.sections.map(
      (s) => (20 * request.smys_mpa * s.wall_thickness_mm) / s.outside_diameter_mm,
    ),
  );
  const headPerM = (WATER_DENSITY_15C * 9.80665) / 1e5;
  const span = headPerM * (request.highest_elevation_m - request.lowest_elevation_m);
  const startToHigh = headPerM * Math.abs(request.start_elevation_m - request.highest_elevation_m);
  const startToLow = headPerM * Math.abs(request.start_elevation_m - request.lowest_elevation_m);
  const endToHigh = headPerM * Math.abs(request.end_elevation_m - request.highest_elevation_m);
  const endToLow = headPerM * Math.abs(request.end_elevation_m - request.lowest_elevation_m);

  const startWindow = {
    location_label: "Baslangic noktasi",
    location_elevation_m: request.start_elevation_m,
    hydraulic_head_to_high_point_bar: round(startToHigh, 3),
    hydraulic_head_to_low_point_bar: round(startToLow, 3),
    minimum_required_pressure_bar: round(requiredMin + startToHigh, 3),
    maximum_allowable_pressure_bar: round(maxLow - startToLow, 3),
  };
  const endWindow = {
    location_label: "Bitis noktasi",
    location_elevation_m: request.end_elevation_m,
    hydraulic_head_to_high_point_bar: round(endToHigh, 3),
    hydraulic_head_to_low_point_bar: round(endToLow, 3),
    minimum_required_pressure_bar: round(requiredMin + endToHigh, 3),
    maximum_allowable_pressure_bar: round(maxLow - endToLow, 3),
  };
  const selected = request.pump_location === "Bitis noktasi" ? endWindow : startWindow;
  const withinLength = geometry.total_length_m <= 20_000;
  const withinVolume = geometry.internal_volume_m3 <= 12_500;
  const withinSpan = requiredMin + span <= maxLow;
  const feasible = withinLength && withinVolume && withinSpan;
  const monitored = request.monitored_pressure_bar ?? null;
  const meetsMin = monitored === null ? null : monitored >= selected.minimum_required_pressure_bar;
  const underMax = monitored === null ? null : monitored <= selected.maximum_allowable_pressure_bar;
  const passed = feasible && meetsMin !== false && underMax !== false;

  const limiting = request.geometry.sections.reduce(
    (best, s) => {
      const p = (20 * request.smys_mpa * s.wall_thickness_mm) / s.outside_diameter_mm;
      return p < best.p ? { p, s } : best;
    },
    {
      p: (20 * request.smys_mpa * request.geometry.sections[0].wall_thickness_mm) /
        request.geometry.sections[0].outside_diameter_mm,
      s: request.geometry.sections[0],
    },
  );

  return {
    location_class: {
      label: request.location_class,
      class_number: classNumber,
      minimum_test_factor: factor,
      spec_reference: factors?.spec_reference ?? "NGTL 5007 / 4.2",
    },
    required_minimum_pressure_at_high_point_bar: round(requiredMin, 3),
    maximum_allowable_pressure_at_low_point_bar: round(maxLow, 3),
    hydraulic_span_bar: round(span, 3),
    required_pressure_with_span_bar: round(requiredMin + span, 3),
    start_window: startWindow,
    end_window: endWindow,
    selected_window: selected,
    limiting_pressure_at_100_smys_bar: round(limiting.p, 3),
    limiting_pipe_description: `OD=${limiting.s.outside_diameter_mm.toFixed(2)} mm | Et=${limiting.s.wall_thickness_mm.toFixed(2)} mm`,
    total_length_m: geometry.total_length_m,
    total_internal_volume_m3: geometry.internal_volume_m3,
    within_length_limit: withinLength,
    within_volume_limit: withinVolume,
    within_100_smys_span_limit: withinSpan,
    feasible,
    monitored_pressure_bar: monitored,
    monitored_meets_minimum: meetsMin,
    monitored_under_maximum: underMax,
    decision: {
      status: passed ? "BASARILI" : "BASARISIZ",
      title: "Test Bölümü Basınç Penceresi",
      summary:
        monitored === null
          ? `Pencere ${round(selected.minimum_required_pressure_bar, 3)} - ${round(
              selected.maximum_allowable_pressure_bar,
              3,
            )} bar. İzlenen basınç girilmedi.`
          : `Seçili pompa noktası için izlenen basınç ${round(monitored, 3)} bar; pencere ${round(
              selected.minimum_required_pressure_bar,
              3,
            )} - ${round(selected.maximum_allowable_pressure_bar, 3)} bar.`,
      rule: "min <= P <= max; L <= 20000 m; Vt <= 12500 m³",
      margin:
        monitored === null
          ? null
          : round(
              Math.min(monitored - selected.minimum_required_pressure_bar, selected.maximum_allowable_pressure_bar - monitored),
              3,
            ),
    },
  };
}

export function computePig(request: PigSpeedRequest): PigSpeedResponse {
  const speed = request.distance_m / (request.travel_time_min * 60);
  const mode = FALLBACK_PIG_MODES.find((m) => m.label === request.mode) ?? FALLBACK_PIG_MODES[0];
  const limit = mode.max_speed_m_per_s;
  const passed = limit === null ? null : speed <= limit;
  const status = passed === null ? "BILGI" : passed ? "UYGUN" : "LIMIT ASILDI";
  const decisionStatus: DecisionStatus = passed === null ? "DOGRULANAMADI" : passed ? "BASARILI" : "BASARISIZ";

  return {
    distance_m: request.distance_m,
    travel_time_min: request.travel_time_min,
    speed_m_per_s: round(speed, 6),
    speed_km_per_h: round(speed * 3.6, 6),
    limit: {
      label: mode.label,
      spec_reference: mode.spec_reference,
      max_speed_m_per_s: limit,
      max_speed_km_per_h: limit === null ? null : round(limit * 3.6, 3),
    },
    passed,
    status,
    summary:
      limit === null
        ? `Hesaplanan pig hızı = ${round(speed, 6)} m/s (${round(speed * 3.6, 3)} km/sa). Bu modda hız limiti tanımlı değildir.`
        : `Hesaplanan pig hızı = ${round(speed, 6)} m/s (${round(speed * 3.6, 3)} km/sa). ${mode.spec_reference} için limit ${passed ? "aşılmadı" : "aşıldı"}.`,
    decision: {
      status: decisionStatus,
      title: "Pig Hız Hesabı",
      summary:
        limit === null
          ? `Hız ${round(speed, 6)} m/s; bu modda limit tanımlı değil.`
          : `Hız ${round(speed, 6)} m/s; limit ${limit} m/s.`,
      rule: limit === null ? "bilgi amaçlı" : "hız <= limit",
      margin: limit === null ? null : round(limit - speed, 6),
    },
  };
}

export function computeDensity(temperatureC: number, pressureBar: number) {
  return round(WATER_DENSITY_15C + 0.034 * (pressureBar - 1) - 0.24 * (temperatureC - 15), 3);
}

export function computePressurization(
  initialVolume: number,
  addedVolume: number,
  theoreticalVolume: number,
  pressure: number,
  expectedPressure: number,
): PressurizationResponse {
  const actual = initialVolume + addedVolume;
  const volumeDeviation = actual > 0 ? ((actual - theoreticalVolume) / actual) * 100 : 0;
  const pressureDeviation = pressure - expectedPressure;
  const tolerance = Math.max(0.05, 0.001 * expectedPressure);
  const withinVolume = volumeDeviation <= 0.2 + 1e-9;
  const withinPressure = Math.abs(pressureDeviation) <= tolerance;
  const passed = withinVolume && withinPressure;

  return {
    volume_deviation_percent: round(volumeDeviation, 3),
    pressure_deviation_bar: round(pressureDeviation, 3),
    within_volume_limit: withinVolume,
    within_pressure_limit: withinPressure,
    passed,
    volume_limit_percent: 0.2,
    pressure_tolerance_bar: round(tolerance, 3),
    underfilled: volumeDeviation < 0,
    volume_shortfall_percent: volumeDeviation < 0 ? round(-volumeDeviation, 3) : 0,
    decision: {
      status: passed ? "BASARILI" : "BASARISIZ",
      title: "Basınçlandırma Kontrolü",
      summary: `Hacim sapması %${round(volumeDeviation, 3)}, basınç sapması ${round(pressureDeviation, 3)} bar (tolerans ${round(tolerance, 3)} bar).`,
      rule: "hacim sapması <= %0,2 ve |dP| <= tolerans",
      margin: round(Math.min(0.2 - Math.abs(volumeDeviation), tolerance - Math.abs(pressureDeviation)), 3),
    },
  };
}

export function computeTablePoint(
  table: "institutional" | "gail",
  temperatureC: number,
  pressureBar: number,
): TablePointResponse {
  const a = computeA({ temperature_c: temperatureC, pressure_bar: pressureBar });
  const b = computeB({
    source: table,
    temperature_c: temperatureC,
    pressure_bar: pressureBar,
    steel_alpha_micro_per_c: STEEL_ALPHA_DEFAULT,
    steel_model: "volumetric",
  });
  const repaired = table === "institutional" && Math.abs(temperatureC - 7) < 1 && pressureBar >= 81 && pressureBar <= 100;
  return {
    table,
    table_label: table === "institutional" ? "Kurum içi A/B kontrol tablosu" : "GAIL referans tablosu",
    requested: { temperature_c: temperatureC, pressure_bar: pressureBar },
    a_micro_per_bar: round(repaired ? a.a_micro_per_bar + 1.6 : a.a_micro_per_bar, 6),
    b_micro_per_c: b.b_micro_per_c,
    source_note:
      table === "institutional"
        ? "BOTAŞ referans tablosu - yerel interpolasyon" + (repaired ? " - onarılmış A" : "")
        : "GAIL referans tablosu - yerel interpolasyon",
    repaired,
    repair_note: repaired
      ? "Onarılmış A değeri: ham hücre komşu geçerli basınçlardan lineer interpolasyonla onarıldı; B ham tablodan alındı."
      : "",
  };
}

export function computeBackendComparison(
  temperatureC: number,
  pressureBar: number,
): BackendComparisonResponse {
  const base = computeA({ temperature_c: temperatureC, pressure_bar: pressureBar });
  const beta = estimateWaterBeta(temperatureC, pressureBar);
  return {
    temperature_c: temperatureC,
    pressure_bar: pressureBar,
    items: [
      {
        backend: { key: "table_v1", label: "Table Interpolation v1", distribution_ready: true },
        a_micro_per_bar: base.a_micro_per_bar,
        beta_micro_per_c: beta,
        density_kg_per_m3: computeDensity(temperatureC, pressureBar),
        error: null,
      },
      {
        backend: { key: "table_v1_bicubic", label: "Table Interpolation v1 (Bicubic)", distribution_ready: true },
        a_micro_per_bar: round(base.a_micro_per_bar + 0.000004, 6),
        beta_micro_per_c: round(beta + 0.00012, 6),
        density_kg_per_m3: computeDensity(temperatureC, pressureBar),
        error: null,
      },
      {
        backend: { key: "coolprop", label: "CoolProp EOS", distribution_ready: true },
        a_micro_per_bar: round(base.a_micro_per_bar - 0.000001, 6),
        beta_micro_per_c: round(beta - 0.00005, 6),
        density_kg_per_m3: computeDensity(temperatureC, pressureBar),
        error: null,
      },
    ],
  };
}

/* ------------------------------------------------------------------ */
/* Demo sonuçlar                                                      */
/* ------------------------------------------------------------------ */

export function buildDemoResults(inputs: AppInputs): ResultBundle {
  const geometry = geometryForInputs(inputs) ?? undefined;
  const sections = sectionsFromInputs(inputs);
  if (!geometry || sections.length === 0) {
    return { source: "demo" as const };
  }

  const airA = inputs.air.a_micro_per_bar ?? computeA({
    temperature_c: inputs.air.temperature_c ?? 20,
    pressure_bar: inputs.air.pressure_bar ?? 80,
  }).a_micro_per_bar;
  const air =
    inputs.air.actual_added_water_m3 !== null
      ? computeAir({
          geometry: { sections },
          a_micro_per_bar: airA,
          pressure_rise_bar: inputs.air.pressure_rise_bar,
          k_factor: inputs.air.k_factor,
          actual_added_water_m3: inputs.air.actual_added_water_m3,
        })
      : undefined;

  const b = inputs.pressure.b_micro_per_c ?? 188.661;
  const pressure =
    inputs.pressure.actual_pressure_change_bar !== null &&
    inputs.pressure.delta_t_c !== null
      ? computePressure({
          geometry: { sections },
          a_micro_per_bar: inputs.pressure.a_micro_per_bar ?? 44.972,
          b_micro_per_c: b,
          delta_t_c: inputs.pressure.delta_t_c,
          actual_pressure_change_bar: inputs.pressure.actual_pressure_change_bar,
        })
      : undefined;

  const profile =
    inputs.section_profile.design_pressure_bar &&
    inputs.section_profile.smys_mpa &&
    inputs.section_profile.highest_elevation_m !== null &&
    inputs.section_profile.lowest_elevation_m !== null &&
    inputs.section_profile.start_elevation_m !== null &&
    inputs.section_profile.end_elevation_m !== null
      ? computeProfile({
          geometry: { sections },
          design_pressure_bar: inputs.section_profile.design_pressure_bar,
          smys_mpa: inputs.section_profile.smys_mpa,
          location_class: inputs.location_class,
          highest_elevation_m: inputs.section_profile.highest_elevation_m,
          lowest_elevation_m: inputs.section_profile.lowest_elevation_m,
          start_elevation_m: inputs.section_profile.start_elevation_m,
          end_elevation_m: inputs.section_profile.end_elevation_m,
          pump_location: inputs.pump_location,
          monitored_pressure_bar: inputs.field.monitored_pressure_bar,
        })
      : undefined;

  const pig =
    inputs.field.pig_distance_m && inputs.field.pig_travel_time_min
      ? computePig({
          mode: inputs.modes.pig_mode,
          distance_m: inputs.field.pig_distance_m,
          travel_time_min: inputs.field.pig_travel_time_min,
        })
      : undefined;

  const hasAirTP = inputs.air.temperature_c !== null && inputs.air.pressure_bar !== null;
  const hasPressureTP =
    inputs.pressure.temperature_c !== null && inputs.pressure.pressure_bar !== null;

  const coefficientA = hasAirTP
    ? computeA({
        temperature_c: inputs.air.temperature_c as number,
        pressure_bar: inputs.air.pressure_bar as number,
        backend: inputs.water_backend,
      })
    : undefined;
  const pressureA = hasPressureTP
    ? computeA({
        temperature_c: inputs.pressure.temperature_c as number,
        pressure_bar: inputs.pressure.pressure_bar as number,
        backend: inputs.water_backend,
      })
    : undefined;
  const pressureB = hasPressureTP
    ? computeB({
        source: inputs.modes.pressure_b_source,
        temperature_c: inputs.pressure.temperature_c as number,
        pressure_bar: inputs.pressure.pressure_bar as number,
        steel_alpha_micro_per_c: inputs.helper.steel_alpha_micro_per_c,
        steel_model: inputs.modes.steel_model,
        backend: inputs.water_backend,
      })
    : undefined;

  return {
    geometry,
    air,
    pressure,
    profile,
    pig,
    ...(coefficientA || pressureA || pressureB
      ? {
          coefficients: {
            ...(coefficientA ? { airA: coefficientA } : {}),
            ...(pressureA ? { pressureA } : {}),
            ...(pressureB ? { pressureB } : {}),
          },
        }
      : {}),
    ...(hasPressureTP
      ? {
          bCompare: computeCompare({
            temperature_c: inputs.pressure.temperature_c as number,
            pressure_bar: inputs.pressure.pressure_bar as number,
            steel_alpha_micro_per_c: inputs.helper.steel_alpha_micro_per_c,
            steel_model: inputs.modes.steel_model,
            backend: inputs.water_backend,
          }),
          backendCompare: computeBackendComparison(
            inputs.pressure.temperature_c as number,
            inputs.pressure.pressure_bar as number,
          ),
        }
      : {}),
    source: "demo" as const,
    lastComputedAt: DEMO_NOW,
  };
}

function demoHistory(inputs: AppInputs): HistoryEntry[] {
  const results = buildDemoResults(inputs);
  return [
    {
      id: "hist-1",
      testType: "air",
      title: "Hava İçerik Testi",
      status: results.air?.decision.status ?? "BEKLIYOR",
      summary: results.air?.decision.summary ?? "Hesaplama bekleniyor.",
      at: "2026-11-15T19:40:00Z",
    },
    {
      id: "hist-2",
      testType: "pressure",
      title: "Basınç Değişim Testi",
      status: results.pressure?.decision.status ?? "BEKLIYOR",
      summary: results.pressure?.decision.summary ?? "Hesaplama bekleniyor.",
      at: "2026-11-15T18:12:00Z",
    },
    {
      id: "hist-3",
      testType: "coefficient_b",
      title: "B katsayısı · kurum içi",
      status: "BASARILI",
      summary: "Kurum içi A/B kontrol tablosundan B = 188,661 10⁻⁶/°C okundu.",
      at: "2026-11-15T17:58:00Z",
    },
    {
      id: "hist-4",
      testType: "profile",
      title: "Test bölümü basınç penceresi",
      status: results.profile?.decision.status ?? "BEKLIYOR",
      summary: results.profile?.decision.summary ?? "Profil hesabı bekleniyor.",
      at: "2026-11-15T17:42:00Z",
    },
    {
      id: "hist-5",
      testType: "pig",
      title: "Pig hız hesabı",
      status: results.pig?.decision.status ?? "BEKLIYOR",
      summary: results.pig?.summary ?? "Pig hesabı bekleniyor.",
      at: "2026-11-15T17:30:00Z",
    },
  ];
}

export function createDemoHistory(inputs: AppInputs): HistoryEntry[] {
  return demoHistory(inputs);
}

export const DEMO_PROJECTS: Project[] = [
  {
    id: "demo-project-001",
    code: "PRJ-DOGU-12",
    name: "Doğu Hattı Hidrostatik Testi",
    client: "BOTAŞ",
    description: "Bölüm 12–13 doğu hattı; 2026 kasım test kampanyası.",
    section_count: 2,
    created_at: "2026-11-10T08:00:00Z",
    updated_at: "2026-11-15T19:40:12Z",
  },
  {
    id: "demo-project-002",
    code: "PRJ-KUZEY-09",
    name: "Kuzey Kol Bağlantısı",
    client: "BOTAŞ",
    description: "Bölüm 09 kuzey kol; taslak kesitler.",
    section_count: 1,
    created_at: "2026-11-12T10:30:00Z",
    updated_at: "2026-11-14T15:22:00Z",
  },
];

export const DEMO_SESSION_LIST: SessionListItem[] = [
  {
    id: "demo-session-001",
    project_id: "demo-project-001",
    name: "K-01 · Bölüm 12–13 · Doğu Hattı",
    status: "active",
    revision: 3,
    updated_at: "2026-11-15T19:40:12Z",
    result_summary: { air: { status: "BASARILI" }, pressure: { status: "BASARILI" } },
    section_meta: {
      section_no: "K-01",
      description: "Bölüm 12–13 · Doğu Hattı",
      location: "KP 0+000 – 12+000",
      start_kp: "0+000",
      end_kp: "12+000",
      test_date: "2026-11-15",
      test_type: "Hidrostatik test",
      notes: "",
    },
  },
  {
    id: "demo-session-002",
    project_id: "demo-project-002",
    name: "K-01 · Bölüm 09 · Kuzey Kol",
    status: "draft",
    revision: 1,
    updated_at: "2026-11-14T15:22:00Z",
    result_summary: { air: { status: "BEKLIYOR" }, pressure: { status: "BEKLIYOR" } },
    section_meta: {
      section_no: "K-01",
      description: "Bölüm 09 · Kuzey Kol",
      location: "KP 0+000 – 8+500",
      start_kp: "0+000",
      end_kp: "8+500",
      test_date: "2026-11-14",
      test_type: "Hidrostatik test",
      notes: "",
    },
  },
  {
    id: "demo-session-003",
    project_id: "demo-project-001",
    name: "K-02 · Bölüm 13–14 · Depolama Bağlantısı",
    status: "completed",
    revision: 7,
    updated_at: "2026-11-11T09:05:00Z",
    result_summary: { air: { status: "BASARILI" }, pressure: { status: "BASARILI" } },
    section_meta: {
      section_no: "K-02",
      description: "Bölüm 13–14 · Depolama Bağlantısı",
      location: "KP 12+000 – 21+500",
      start_kp: "12+000",
      end_kp: "21+500",
      test_date: "2026-11-11",
      test_type: "Hidrostatik test",
      notes: "",
    },
  },
];

export function createDemoSession(): Session {
  const inputs = createDefaultInputs();
  return {
    id: "demo-session-001",
    project_id: "demo-project-001",
    name: "Bölüm 12–13 · Doğu Hattı",
    status: "active",
    revision: 3,
    inputs: inputs as unknown as Record<string, unknown>,
    wizard_state: { active: false, step: 2, completed: [0, 1] },
    result_summary: {
      air: { status: "BASARILI", computed_at: "2026-11-15T19:40:00Z" },
      pressure: { status: "BASARILI", computed_at: "2026-11-15T18:12:00Z" },
      checklist: { checked: 5, total: 11 },
      last_computed_at: "2026-11-15T19:40:00Z",
    },
    created_at: "2026-11-15T17:20:00Z",
    updated_at: "2026-11-15T19:40:12Z",
    deleted_at: null,
  };
}

export const DEMO_OCR_STATUS: OcrStatusResponse = {
  available: true,
  status_text: "OCR hazır (Tesseract + Pillow).",
  engine: {
    name: "tesseract",
    version: "5.3.4",
    languages: ["tur", "eng"],
    default_language: "tur+eng",
  },
  pdf_rasterizer: {
    available: false,
    engine: null,
    note: "Taranmış PDF için PyMuPDF veya pdf2image + Poppler gerekir.",
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
  mapping_profiles: { default_id: null, count: 0 },
};

/* ------------------------------------------------------------------ */
/* 3D sahne adaptörü                                                  */
/* ------------------------------------------------------------------ */

function interpolateElevation(profile: Array<{ x: number; y: number }>, x: number): number {
  if (profile.length === 0) return 0;
  if (x <= profile[0].x) return profile[0].y;
  for (let i = 1; i < profile.length; i += 1) {
    const left = profile[i - 1];
    const right = profile[i];
    if (x <= right.x) {
      const span = right.x - left.x;
      return span <= 0 ? right.y : left.y + ((right.y - left.y) * (x - left.x)) / span;
    }
  }
  return profile[profile.length - 1].y;
}

export function resolveProfileCurve(
  inputs: AppInputs,
  totalLength: number,
): { points: Array<{ x: number; y: number }>; hasSurveyProfile: boolean } {
  const sp = inputs.section_profile;
  const startElev = sp.start_elevation_m ?? sp.lowest_elevation_m ?? 0;
  const endElev = sp.end_elevation_m ?? sp.highest_elevation_m ?? startElev;
  const highest = sp.highest_elevation_m ?? Math.max(startElev, endElev);
  const lowest = sp.lowest_elevation_m ?? Math.min(startElev, endElev);

  const rawSorted = (inputs.profile_points ?? [])
    .filter((pt) => Number.isFinite(pt.station_m) && Number.isFinite(pt.elevation_m))
    .map((pt) => ({ x: clamp(pt.station_m, 0, totalLength), y: pt.elevation_m }))
    .sort((a, b) => a.x - b.x);
  const deduped: Array<{ x: number; y: number }> = [];
  for (const pt of rawSorted) {
    const prev = deduped[deduped.length - 1];
    if (!prev || Math.abs(pt.x - prev.x) > 0.5) {
      deduped.push(pt);
    } else {
      deduped[deduped.length - 1] = pt;
    }
  }

  if (deduped.length >= 2) {
    if (deduped[0].x > 0) deduped.unshift({ x: 0, y: deduped[0].y });
    if (deduped[deduped.length - 1].x < totalLength) {
      deduped.push({ x: totalLength, y: deduped[deduped.length - 1].y });
    }
    return { points: deduped, hasSurveyProfile: true };
  }

  const approx = [
    { x: 0, y: startElev },
    { x: totalLength * 0.33, y: highest },
    { x: totalLength * 0.68, y: lowest },
    { x: totalLength, y: endElev },
  ].sort((a, b) => a.x - b.x);
  return { points: approx, hasSurveyProfile: false };
}

export function buildDefaultEquipmentInputs(inputs: AppInputs): EquipmentInputItem[] {
  const sections = sectionsFromInputs(inputs);
  const totalLength = sections.reduce((sum, s) => sum + s.length_m, 0);
  const { points: profile } = resolveProfileCurve(inputs, totalLength);
  const pumpAtStart =
    !inputs.pump_location.includes("Bitis") && !inputs.pump_location.includes("Bitiş");
  const pumpStation = pumpAtStart ? 0 : totalLength;
  const pumpElev = round(interpolateElevation(profile, pumpStation), 1);
  const offsetHead = Math.min(40, totalLength * 0.01);
  const headStation = round(pumpAtStart ? offsetHead : Math.max(0, totalLength - offsetHead), 1);
  const launcherStation = round(
    pumpAtStart ? Math.min(20, totalLength) : Math.max(0, totalLength - 20),
    1,
  );

  return [
    {
      id: "eq-valve-start",
      type: "valve",
      label: "Başlangıç vanası",
      station_m: 0,
      elevation_m: round(interpolateElevation(profile, 0), 1),
      status: "pass",
    },
    {
      id: "eq-pump",
      type: "pump",
      label: "Pompa",
      station_m: round(pumpStation, 1),
      elevation_m: pumpElev,
      status: "pass",
    },
    {
      id: "eq-head",
      type: "test-head",
      label: "Test başlığı",
      station_m: headStation,
      elevation_m: round(interpolateElevation(profile, headStation), 1),
      status: "pass",
    },
    {
      id: "eq-launcher",
      type: "pig-launcher",
      label: "Pig başlatıcı",
      station_m: launcherStation,
      elevation_m: round(interpolateElevation(profile, launcherStation), 1),
      status: "pass",
    },
    {
      id: "eq-valve-end",
      type: "valve",
      label: "Bitiş vanası",
      station_m: round(totalLength, 1),
      elevation_m: round(interpolateElevation(profile, totalLength), 1),
      status: "pass",
    },
  ];
}

export function buildSceneData(inputs: AppInputs, results: { profile?: PressureProfileResponse; pig?: PigSpeedResponse }): SceneData {
  const sections = sectionsFromInputs(inputs);
  if (sections.length === 0) {
    return {
      segments: [],
      equipment: [],
      is_survey_profile: false,
      is_custom_equipment: false,
      warnings: ["Geometri girilmediği için sahne boş."],
    };
  }

  const totalLength = sections.reduce((sum, s) => sum + s.length_m, 0);
  const { points: profile, hasSurveyProfile } = resolveProfileCurve(inputs, totalLength);

  const startKpM = parseKpMeters(inputs.section_meta.start_kp);
  const pumpAtStart = !inputs.pump_location.includes("Bitis") && !inputs.pump_location.includes("Bitiş");
  const pumpStation = pumpAtStart ? 0 : totalLength;
  const pumpElev = interpolateElevation(profile, pumpStation);
  const basePressure =
    results.profile?.monitored_pressure_bar ??
    inputs.field.monitored_pressure_bar ??
    inputs.air.pressure_bar ??
    results.profile?.selected_window.minimum_required_pressure_bar ??
    0;
  const smysMpa = inputs.section_profile.smys_mpa ?? 450;
  const maxAllowable = results.profile?.maximum_allowable_pressure_at_low_point_bar ?? 193.55;
  const segments: SceneSegment[] = [];

  if (hasSurveyProfile) {
    const sectionRanges: Array<{
      start: number;
      end: number;
      outside_diameter_mm: number;
      wall_thickness_mm: number;
      nps_label: string | null;
    }> = [];
    let cursor = 0;
    for (const sec of sections) {
      sectionRanges.push({
        start: cursor,
        end: cursor + sec.length_m,
        outside_diameter_mm: sec.outside_diameter_mm,
        wall_thickness_mm: sec.wall_thickness_mm,
        nps_label: sec.nps_label ?? null,
      });
      cursor += sec.length_m;
    }

    let chosenProfile = profile;
    if (profile.length > 38) {
      let minIdx = 0;
      let maxIdx = 0;
      profile.forEach((pt, idx) => {
        if (pt.y < profile[minIdx].y) minIdx = idx;
        if (pt.y > profile[maxIdx].y) maxIdx = idx;
      });
      const keep = new Set<number>([0, profile.length - 1, minIdx, maxIdx]);
      const slots = 36 - keep.size;
      for (let slot = 1; slot <= slots; slot += 1) {
        const idx = Math.min(profile.length - 1, Math.round((slot * (profile.length - 1)) / (slots + 1)));
        keep.add(idx);
      }
      chosenProfile = Array.from(keep)
        .sort((a, b) => a - b)
        .map((idx) => profile[idx]);
    }

    const rawBreakpoints = [
      0,
      ...sectionRanges.map((r) => r.end),
      ...chosenProfile.map((p) => p.x),
      totalLength,
    ]
      .filter((v) => Number.isFinite(v) && v >= 0 && v <= totalLength)
      .sort((a, b) => a - b);

    const breakpoints: number[] = [];
    for (const bp of rawBreakpoints) {
      if (breakpoints.length === 0 || bp - breakpoints[breakpoints.length - 1] >= 1.0) {
        breakpoints.push(bp);
      }
    }
    if (breakpoints.length > 0 && breakpoints[breakpoints.length - 1] < totalLength) {
      if (totalLength - breakpoints[breakpoints.length - 1] >= 1.0) {
        breakpoints.push(totalLength);
      } else {
        breakpoints[breakpoints.length - 1] = totalLength;
      }
    }

    for (let index = 0; index < breakpoints.length - 1; index += 1) {
      const start = breakpoints[index];
      const end = breakpoints[index + 1];
      const mid = 0.5 * (start + end);
      const sec =
        sectionRanges.find((r) => mid >= r.start && mid <= r.end) ??
        sectionRanges[sectionRanges.length - 1];
      const z0 = interpolateElevation(profile, start);
      const z1 = interpolateElevation(profile, end);
      const zMid = 0.5 * (z0 + z1);
      const headBar = (WATER_DENSITY_15C * 9.80665 * (zMid - pumpElev)) / 100_000;
      const segPressure = basePressure > 0 ? Math.max(0, round(basePressure - headBar, 2)) : 0;
      const limitSmys =
        smysMpa > 0 && sec.outside_diameter_mm > 0
          ? (20 * smysMpa * sec.wall_thickness_mm) / sec.outside_diameter_mm
          : maxAllowable;
      const utilization = basePressure > 0 && limitSmys > 0 ? round(segPressure / limitSmys, 4) : 0;
      const status =
        basePressure <= 0
          ? "pending"
          : utilization > 1
            ? "fail"
            : utilization > 0.9
              ? "warning"
              : "pass";
      const labelPrefix = inputs.section_meta.section_no || sec.nps_label || `Kesit ${index + 1}`;
      const segLabel =
        startKpM !== null
          ? `${labelPrefix} · KP ${formatKp(startKpM + start)}–${formatKp(startKpM + end)}`
          : `${labelPrefix} · #${index + 1}`;
      segments.push({
        id: `scene-seg-${index + 1}`,
        label: segLabel,
        start_m: round(start, 2),
        end_m: round(end, 2),
        start_elevation_m: round(z0, 2),
        end_elevation_m: round(z1, 2),
        outside_diameter_mm: sec.outside_diameter_mm,
        wall_thickness_mm: sec.wall_thickness_mm,
        pressure_bar: basePressure > 0 ? segPressure : undefined,
        utilization: basePressure > 0 ? utilization : undefined,
        status,
      });
    }
  } else {
    let station = 0;
    sections.forEach((section, index) => {
      const start = station;
      const end = station + section.length_m;
      const utilization = maxAllowable > 0 ? basePressure / maxAllowable : 0;
      const status = utilization > 1 ? "fail" : utilization > 0.9 ? "warning" : "pass";
      segments.push({
        id: `scene-seg-${index + 1}`,
        label:
          section.nps_label ??
          `Segment ${index + 1} · ${section.outside_diameter_mm.toFixed(1)} mm`,
        start_m: start,
        end_m: end,
        start_elevation_m: interpolateElevation(profile, start),
        end_elevation_m: interpolateElevation(profile, end),
        outside_diameter_mm: section.outside_diameter_mm,
        wall_thickness_mm: section.wall_thickness_mm,
        pressure_bar: basePressure > 0 ? basePressure : undefined,
        utilization: round(utilization, 4),
        status,
      });
      station = end;
    });
  }

  const rawCustomEquipment = (inputs.equipment ?? []).filter(
    (item) => Number.isFinite(item.station_m) && item.label.trim().length > 0,
  );
  const hasCustomEquipment = rawCustomEquipment.length > 0;
  const equipmentSource = hasCustomEquipment
    ? rawCustomEquipment
    : buildDefaultEquipmentInputs(inputs);

  const equipment: SceneEquipment[] = equipmentSource.map((item) => {
    const dist = clamp(item.station_m, 0, totalLength);
    return {
      id: item.id,
      type: item.type,
      label: item.label.trim(),
      distance_m: round(dist, 1),
      elevation_m: round(item.elevation_m ?? interpolateElevation(profile, dist), 1),
      status: item.status ?? "pass",
    };
  });

  if (!hasCustomEquipment && hasSurveyProfile && profile.length >= 3) {
    let maxPt = profile[0];
    let minPt = profile[0];
    for (const pt of profile) {
      if (pt.y > maxPt.y) maxPt = pt;
      if (pt.y < minPt.y) minPt = pt;
    }
    if (maxPt.x > 40 && maxPt.x < totalLength - 40) {
      equipment.push({
        id: "eq-summit",
        type: "gauge",
        label: `Zirve · ${round(maxPt.y, 1)} m${startKpM !== null ? ` (KP ${formatKp(startKpM + maxPt.x)})` : ""}`,
        distance_m: round(maxPt.x, 1),
        elevation_m: round(maxPt.y, 1),
        status: "warning",
      });
    }
    if (minPt.x > 40 && minPt.x < totalLength - 40 && Math.abs(minPt.x - maxPt.x) > 40) {
      equipment.push({
        id: "eq-lowpoint",
        type: "gauge",
        label: `Maks. Statik Yük · ${round(minPt.y, 1)} m${startKpM !== null ? ` (KP ${formatKp(startKpM + minPt.x)})` : ""}`,
        distance_m: round(minPt.x, 1),
        elevation_m: round(minPt.y, 1),
        status: "pass",
      });
    }
  }

  const landmarks: SceneLandmark[] = (inputs.landmarks ?? []).map((lm, idx) => {
    const dist = clamp(lm.station_m, 0, totalLength);
    return {
      id: `lm-${idx + 1}`,
      distance_m: round(dist, 1),
      elevation_m: lm.elevation_m ?? round(interpolateElevation(profile, dist), 1),
      kp: lm.kp || (startKpM !== null ? formatKp(startKpM + dist) : undefined),
      kind: lm.kind,
      label: lm.label,
    };
  });

  const segPressures = segments
    .map((seg) => seg.pressure_bar)
    .filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  const computedMinPressure = segPressures.length ? Math.min(...segPressures) : undefined;
  const computedMaxPressure = segPressures.length ? Math.max(...segPressures) : undefined;

  const pigDistance = inputs.field.pig_distance_m ?? totalLength / 2;
  const pigSpeed = results.pig?.speed_m_per_s ?? inputs.field.pig_speed_m_per_s ?? null;

  const warnings: string[] = [];
  if (results.profile?.feasible === false) {
    warnings.push("Basınç penceresi üç limitin tamamını sağlamıyor; sahne yalnızca gösterim amaçlıdır.");
  }
  if (!hasSurveyProfile) {
    warnings.push(
      "Kot profili 4 noktadan yaklaşık türetildi; gerçek topoğrafya için kot profili noktaları (profile_points) girin.",
    );
  }
  if (!hasCustomEquipment) {
    warnings.push(
      "Ekipman konumları varsayılan yerleşimle yaklaşık gösteriliyor; gerçek saha ekipmanları (equipment) eklenebilir.",
    );
  }

  return {
    segments,
    equipment,
    pig: {
      distance_m: Math.min(pigDistance, totalLength),
      elevation_m: interpolateElevation(profile, Math.min(pigDistance, totalLength)),
      progress: totalLength > 0 ? Math.min(pigDistance / totalLength, 1) : 0,
      speed_m_per_s: pigSpeed ?? undefined,
    },
    flow_speed_m_per_s: pigSpeed ?? 1.2,
    pressure_min_bar:
      computedMinPressure ?? results.profile?.selected_window.minimum_required_pressure_bar ?? undefined,
    pressure_max_bar:
      computedMaxPressure ?? results.profile?.selected_window.maximum_allowable_pressure_bar ?? undefined,
    start_kp_m: startKpM,
    is_survey_profile: hasSurveyProfile,
    is_custom_equipment: hasCustomEquipment,
    profile_points: profile.map((p) => [round(p.x, 2), round(p.y, 2)]),
    landmarks,
    warnings,
  };
}

/* ------------------------------------------------------------------ */
/* Demo "sunucu" yanıtları                                            */
/* ------------------------------------------------------------------ */

export function demoSessionDetail(inputs: AppInputs, name: string): Session {
  return {
    ...createDemoSession(),
    name,
    inputs: inputs as unknown as Record<string, unknown>,
  };
}

export function demoSessions(
  _inputs: AppInputs,
  name: string,
  projectId: string | null = null,
): SessionListItem[] {
  const items: SessionListItem[] = [
    {
      id: "demo-session-001",
      project_id: projectId ?? "demo-project-001",
      name,
      status: "active",
      revision: 3,
      updated_at: new Date().toISOString(),
    },
    ...DEMO_SESSION_LIST.slice(1),
  ];
  if (!projectId) return items;
  return items.filter((item) => item.project_id === projectId);
}

export function demoProjects(): Project[] {
  return DEMO_PROJECTS.map((project) => ({
    ...project,
    section_count: DEMO_SESSION_LIST.filter(
      (session) => session.project_id === project.id,
    ).length,
  }));
}

export type MockInputs = AppInputs;
