import type {
  AppInputs,
  BackendComparisonItem,
  BackendComparisonResponse,
  HistoryEntry,
  MetaResponse,
  ResultBundle,
  TestType,
} from "./types";
import { CHECK_DEFINITIONS } from "./constants";
import { dateOnly, fmt, formatInput, num } from "./format";
import { PUMP_LABELS } from "./constants";

function resolveWaterBackendLabel(meta: MetaResponse, key: string): string {
  const matched = meta.water_backends.find((b) => b.key === key);
  return matched ? `${matched.label} (${matched.key})` : key || meta.water_backends[0]?.label || "table_v1";
}

function findReferenceItem(items: BackendComparisonItem[]): BackendComparisonItem | undefined {
  return (
    items.find((item) => item.backend.key === "table_v1" && !item.error) ??
    items.find((item) => !item.error)
  );
}

export function reportFileName(extension: string, reportNo?: string): string {
  const stamp = new Date()
    .toISOString()
    .replace(/[-:]/g, "")
    .replace("T", "_")
    .slice(0, 15);
  const prefix = reportNo?.trim() ? `hidrostatik_test_${reportNo.trim()}` : "hidrostatik_test_raporu";
  return `${prefix.replace(/[^a-zA-Z0-9._-]+/g, "_")}_${stamp}.${extension}`;
}

const OPERATION_TITLES: Array<[TestType, string]> = [
  ["pressurization_ramp", "Basınçlandırma izleme (14.1–14.2)"],
  ["pressure_hold", "2 saatlik bekleme (14.3)"],
  ["depressurization", "Basınç düşürme (16)"],
  ["discharge", "Boşaltma (17)"],
];

export function buildReportText(
  inputs: AppInputs,
  results: ResultBundle,
  meta: MetaResponse,
  generatedAt = new Date(),
  history: HistoryEntry[] = [],
): string {
  const air = results.air;
  const pressure = results.pressure;
  const profile = results.profile;
  const pig = results.pig;
  const checked = CHECK_DEFINITIONS.filter((c) => inputs.checks[c.key]).length;
  const airDecision = air?.decision.status ?? "BEKLIYOR";
  const pressureDecision = pressure?.decision.status ?? "BEKLIYOR";

  const lines: string[] = [];
  const rule = (char = "=") => char.repeat(72);

  lines.push(rule());
  lines.push("HİDROSTATİK TEST DEĞERLENDİRME RAPORU");
  lines.push(rule());
  lines.push(`Uygulama        : ${meta.app.name}`);
  lines.push(`Sürüm           : ${meta.app.version}`);
  lines.push(`Şartname        : ${meta.spec.code}`);
  lines.push(`                  ${meta.spec.title}`);
  lines.push(`Oluşturma       : ${generatedAt.toLocaleString("tr-TR")}`);
  lines.push(`Rapor No        : ${inputs.report.report_no || "—"}`);
  lines.push(`Operatör        : ${inputs.report.operator || "—"}`);
  lines.push(`Tarih           : ${inputs.report.date ? dateOnly(inputs.report.date) : "—"}`);
  lines.push(`Bölüm           : ${inputs.report.section_id || "—"}`);
  lines.push(`Su backend'i    : ${resolveWaterBackendLabel(meta, inputs.water_backend)}`);
  lines.push("");

  lines.push("1. BORU KESİTİ");
  lines.push(rule("-"));
  lines.push(`Dış çap (mm)    : ${fmt.mm(inputs.geometry.outside_diameter_mm)}`);
  lines.push(`Et kalınlığı    : ${fmt.mm(inputs.geometry.wall_thickness_mm)}`);
  lines.push(`Hat uzunluğu    : ${fmt.m(inputs.geometry.length_m)}`);
  lines.push(`Malzeme kalitesi: ${inputs.material_grade || "—"}`);
  lines.push(`SMYS            : ${fmt.mpa(inputs.section_profile.smys_mpa)}`);
  lines.push(`Location Class  : ${inputs.location_class || "—"}`);
  lines.push(`Pompa konumu    : ${PUMP_LABELS[inputs.pump_location] ?? (inputs.pump_location || "—")}`);
  lines.push(
    `Kotlar (m)      : başlangıç ${num(inputs.section_profile.start_elevation_m, 2)} · en yüksek ${num(
      inputs.section_profile.highest_elevation_m,
      2,
    )} · en düşük ${num(inputs.section_profile.lowest_elevation_m, 2)} · bitiş ${num(
      inputs.section_profile.end_elevation_m,
      2,
    )}`,
  );
  if (results.geometry) {
    lines.push(`Toplam hacim    : ${fmt.m3Short(results.geometry.internal_volume_m3)}`);
    lines.push(`Toplam uzunluk  : ${fmt.m(results.geometry.total_length_m)}`);
  }
  lines.push("");

  if (inputs.segments.length > 0) {
    lines.push("2. SEGMENT LİSTESİ");
    lines.push(rule("-"));
    lines.push("No  NPS / Schedule                 OD (mm)   Et (mm)    L (m)");
    inputs.segments.forEach((segment, index) => {
      lines.push(
        `${String(index + 1).padEnd(3)} ${(segment.nps_label || "—").padEnd(30)} ${String(
          num(segment.outside_diameter_mm, 2),
        ).padStart(8)} ${String(num(segment.wall_thickness_mm, 2)).padStart(9)} ${String(
          num(segment.length_m, 2),
        ).padStart(8)}`,
      );
    });
    lines.push("");
  }

  const ambientTemp = inputs.air.ambient_temperature_c ?? inputs.field.ambient_temperature_c;

  lines.push("3. HAVA İÇERİK TESTİ");
  lines.push(rule("-"));
  lines.push(`Su sıcaklığı    : ${fmt.c(inputs.air.temperature_c)}`);
  lines.push(`Su basıncı      : ${fmt.bar(inputs.air.pressure_bar)}`);
  lines.push(`A katsayısı     : ${fmt.a(inputs.air.a_micro_per_bar)}`);
  lines.push(`Basınç artışı   : ${fmt.bar(inputs.air.pressure_rise_bar)}`);
  lines.push(`K faktörü       : ${num(inputs.air.k_factor, 4)}`);
  lines.push(`Fiili ilave su  : ${fmt.m3(inputs.air.actual_added_water_m3)}`);
  lines.push(`Ortam sıcaklığı : ${fmt.c(ambientTemp)}`);
  if (ambientTemp !== null && ambientTemp < 2) {
    lines.push("UYARI (10.1)    : Ortam sıcaklığı +2 °C altındadır; Şartname 10.1 dolum kısıtı ihlali!");
  }
  lines.push(`Teorik Vp       : ${fmt.m3(air?.theoretical_added_water_m3)}`);
  lines.push(`Kabul limiti    : ${fmt.m3(air?.acceptance_limit_m3)}`);
  lines.push(`Oran (Vpa/Vp)   : ${num(air?.ratio, 6)}`);
  lines.push(`Karar           : ${airDecision}`);
  if (air) lines.push(`Özet            : ${air.decision.summary}`);
  lines.push("");

  lines.push("4. BASINÇ DEĞİŞİM TESTİ");
  lines.push(rule("-"));
  lines.push(`Su sıcaklığı    : ${fmt.c(inputs.pressure.temperature_c)}`);
  lines.push(`Su basıncı      : ${fmt.bar(inputs.pressure.pressure_bar)}`);
  lines.push(`A katsayısı     : ${fmt.a(inputs.pressure.a_micro_per_bar)}`);
  lines.push(`B katsayısı     : ${fmt.b(inputs.pressure.b_micro_per_c)}`);
  if (inputs.pressure.t_initial_c !== null || inputs.pressure.t_final_c !== null) {
    lines.push(`Başlangıç Tilk  : ${fmt.c(inputs.pressure.t_initial_c)}`);
    lines.push(`Bitiş Tson      : ${fmt.c(inputs.pressure.t_final_c)}`);
  }
  lines.push(`ΔT (Tilk−Tson)  : ${fmt.c(inputs.pressure.delta_t_c)}`);
  lines.push(`Pa (Pilk−Pson)  : ${fmt.bar(inputs.pressure.actual_pressure_change_bar)}`);
  lines.push(`Teorik Pt       : ${fmt.bar(pressure?.theoretical_pressure_change_bar)}`);
  lines.push(`Üst sınır       : ${fmt.bar(pressure?.allowable_upper_pressure_change_bar)}`);
  lines.push(`Marj            : ${fmt.bar(pressure?.margin_bar)}`);
  lines.push(`Karar           : ${pressureDecision}`);
  if (pressure) lines.push(`Özet            : ${pressure.decision.summary}`);
  lines.push("");

  lines.push("5. OPERASYON KONTROL NOKTALARI");
  lines.push(rule("-"));
  lines.push(`Tamamlanan      : ${checked}/${CHECK_DEFINITIONS.length}`);
  CHECK_DEFINITIONS.forEach((check) => {
    lines.push(`[${inputs.checks[check.key] ? "X" : " "}] ${check.label} (${check.ref})`);
  });
  lines.push("");

  if (profile) {
    lines.push("6. BASINÇ PENCERESİ");
    lines.push(rule("-"));
    lines.push(`Seçili pencere  : ${fmt.bar(profile.selected_window.minimum_required_pressure_bar)} — ${fmt.bar(profile.selected_window.maximum_allowable_pressure_bar)}`);
    lines.push(`İzlenen basınç  : ${fmt.bar(profile.monitored_pressure_bar)}`);
    lines.push(`Hidrolik span   : ${fmt.bar(profile.hydraulic_span_bar)}`);
    lines.push(`100% SMYS limit : ${fmt.bar(profile.limiting_pressure_at_100_smys_bar)}`);
    lines.push(`Uygun           : ${profile.feasible ? "EVET" : "HAYIR"}`);
    lines.push("");
  }

  if (pig) {
    lines.push("7. PİG HIZ HESABI");
    lines.push(rule("-"));
    lines.push(`Mod             : ${pig.limit.label} (${pig.limit.spec_reference})`);
    lines.push(`Mesafe          : ${fmt.m(pig.distance_m)}`);
    lines.push(`Süre            : ${num(pig.travel_time_min, 2)} dk`);
    lines.push(`Hız             : ${fmt.ms(pig.speed_m_per_s)} · ${fmt.kmh(pig.speed_km_per_h)}`);
    lines.push(`Durum           : ${pig.status}`);
    lines.push("");
  }

  const operationLines: string[] = [];
  for (const [testType, title] of OPERATION_TITLES) {
    const entry = history.find((item) => item.testType === testType);
    if (entry) {
      operationLines.push(`${title.padEnd(36)}: ${entry.status}`);
      operationLines.push(`  ${entry.summary}`);
    }
  }
  if (operationLines.length > 0) {
    lines.push("8. OPERASYON SONUÇLARI (14–17)");
    lines.push(rule("-"));
    lines.push(...operationLines);
    lines.push("");
  }

  if (results.backendCompare && results.backendCompare.items.length > 0) {
    const refItem = findReferenceItem(results.backendCompare.items);
    lines.push(
      `BACKEND KARŞILAŞTIRMASI (T=${fmt.c(results.backendCompare.temperature_c)}, P=${fmt.bar(
        results.backendCompare.pressure_bar,
      )})`,
    );
    lines.push(rule("-"));
    for (const item of results.backendCompare.items) {
      const marker = item.backend.key === inputs.water_backend ? "*" : " ";
      if (item.error) {
        lines.push(`${marker} ${item.backend.label}: HATA - ${item.error}`);
        continue;
      }
      const deltaA =
        refItem?.a_micro_per_bar != null && item.a_micro_per_bar != null
          ? item.a_micro_per_bar - refItem.a_micro_per_bar
          : null;
      const deltaBeta =
        refItem?.beta_micro_per_c != null && item.beta_micro_per_c != null
          ? item.beta_micro_per_c - refItem.beta_micro_per_c
          : null;
      lines.push(
        `${marker} ${item.backend.label}: A=${num(item.a_micro_per_bar, 6)} (ΔA=${
          deltaA !== null ? num(deltaA, 6) : "—"
        }) · β=${num(item.beta_micro_per_c, 6)} (Δβ=${
          deltaBeta !== null ? num(deltaBeta, 6) : "—"
        }) · ρ=${num(item.density_kg_per_m3, 2)} kg/m³`,
      );
    }
    lines.push("");
  }

  lines.push("9. NİHAİ KARAR");
  lines.push(rule("-"));
  lines.push(`Hava içerik     : ${airDecision} · Kural: Vpa < 1.06 x Vp`);
  lines.push(`Basınç değişim  : ${pressureDecision} · Kural: (Pa − Pt) ≤ 0,3 bar`);
  lines.push("");

  lines.push("10. NOT");
  lines.push(rule("-"));
  lines.push("Nihai karar ASME B31.8 ve proje prosedürü ile birlikte değerlendirilmelidir.");
  lines.push("İşaret sözleşmesi: ΔT = Tilk − Tson; Pa = Pilk − Pson.");
  lines.push("Hidrolik kot hesabında 15 °C su yoğunluğu (999,1 kg/m³) kullanılır.");
  lines.push("Resmi kabul için sunucu kaydı ve");
  lines.push("yetkili personel onayı gereklidir.");
  lines.push(rule());

  return lines.join("\n");
}

export function buildSnapshot(
  inputs: AppInputs,
  results: ResultBundle,
  meta: MetaResponse,
): Record<string, unknown> {
  const str = (v: number | null | undefined) => (v === null || v === undefined ? "" : formatInput(v, 6));
  return {
    schema_version: 1,
    saved_at_utc: new Date().toISOString(),
    app_version: meta.app.version,
    active_tab: inputs.air.pressure_rise_bar === 1 ? "air" : "pressure",
    water_backend_option:
      meta.water_backends.find((b) => b.key === inputs.water_backend)?.label ??
      inputs.water_backend ??
      meta.water_backends[0]?.label ??
      "Table Interpolation v1",
    geometry: {
      outside_diameter_mm: str(inputs.geometry.outside_diameter_mm),
      wall_thickness_mm: str(inputs.geometry.wall_thickness_mm),
      length_m: str(inputs.geometry.length_m),
    },
    section_profile: {
      highest_elevation_m: str(inputs.section_profile.highest_elevation_m),
      lowest_elevation_m: str(inputs.section_profile.lowest_elevation_m),
      start_elevation_m: str(inputs.section_profile.start_elevation_m),
      end_elevation_m: str(inputs.section_profile.end_elevation_m),
      design_pressure_bar: str(inputs.section_profile.design_pressure_bar),
      smys_mpa: str(inputs.section_profile.smys_mpa),
    },
    geometry_catalog: inputs.geometry_catalog,
    material_grade: inputs.material_grade,
    location_class: inputs.location_class,
    pump_location: inputs.pump_location,
    air: {
      temperature_c: str(inputs.air.temperature_c),
      pressure_bar: str(inputs.air.pressure_bar),
      a_micro_per_bar: str(inputs.air.a_micro_per_bar),
      pressure_rise_bar: str(inputs.air.pressure_rise_bar),
      k_factor: str(inputs.air.k_factor),
      actual_added_water_m3: str(inputs.air.actual_added_water_m3),
      ambient_temperature_c: str(inputs.air.ambient_temperature_c ?? inputs.field.ambient_temperature_c),
    },
    pressure: {
      temperature_c: str(inputs.pressure.temperature_c),
      pressure_bar: str(inputs.pressure.pressure_bar),
      a_micro_per_bar: str(inputs.pressure.a_micro_per_bar),
      b_micro_per_c: str(inputs.pressure.b_micro_per_c),
      delta_t_c: str(inputs.pressure.delta_t_c),
      actual_pressure_change_bar: str(inputs.pressure.actual_pressure_change_bar),
      t_initial_c: str(inputs.pressure.t_initial_c),
      t_final_c: str(inputs.pressure.t_final_c),
      derive_delta_t: inputs.pressure.derive_delta_t,
    },
    field: {
      ambient_temperature_c: str(inputs.field.ambient_temperature_c ?? inputs.air.ambient_temperature_c),
      pig_distance_m: str(inputs.field.pig_distance_m),
      pig_travel_time_min: str(inputs.field.pig_travel_time_min),
      pig_speed_m_per_s: str(results.pig?.speed_m_per_s),
      pig_speed_km_per_h: str(results.pig?.speed_km_per_h),
    },
    helper: {
      steel_alpha_micro_per_c: str(inputs.helper.steel_alpha_micro_per_c),
      water_beta_micro_per_c: str(inputs.helper.water_beta_micro_per_c),
    },
    modes: {
      air_a_mode:
        inputs.modes.air_a_mode === "auto"
          ? "Otomatik"
          : inputs.modes.air_a_mode === "table"
            ? "Tablo"
            : "Manuel",
      pressure_a_mode:
        inputs.modes.pressure_a_mode === "auto"
          ? "Otomatik"
          : inputs.modes.pressure_a_mode === "table"
            ? "Tablo"
            : "Manuel",
      pressure_b_mode:
        inputs.modes.pressure_b_mode === "auto"
          ? "Otomatik"
          : inputs.modes.pressure_b_mode === "table"
            ? "Tablo"
            : "Manuel",
      pressure_b_source:
        inputs.modes.pressure_b_source === "gail"
          ? "GAIL referans tablosu"
          : inputs.modes.pressure_b_source === "auto"
            ? "Otomatik (beta - 3*alpha)"
            : "Kurum ici tablo (varsayilan)",
      steel_model:
        inputs.modes.steel_model === "linear"
          ? "Lineer alpha"
          : inputs.modes.steel_model === "volumetric_temperature"
            ? "Sicakliga bagli 3*alpha(T)"
            : "Hacimsel 3*alpha (varsayilan)",
      air_a_reference: inputs.modes.air_a_reference,
      pressure_a_reference: inputs.modes.pressure_a_reference,
      pressure_b_reference: inputs.modes.pressure_b_reference,
      k_preset: inputs.modes.k_preset,
      steel_preset: inputs.modes.steel_preset,
      pig_mode: inputs.modes.pig_mode,
    },
    checks: inputs.checks,
    geometry_segments: inputs.segments.map((segment) => ({
      outside_diameter_mm: str(segment.outside_diameter_mm),
      wall_thickness_mm: str(segment.wall_thickness_mm),
      length_m: str(segment.length_m),
      nps_label: segment.nps_label,
      schedule_label: segment.schedule_label,
    })),
    report: { ...inputs.report },
    report_entries: [],
  };
}

export function buildBackendComparisonReportText(
  comparison: BackendComparisonResponse,
  activeBackendKey: string,
  meta: MetaResponse,
  generatedAt = new Date(),
): string {
  const rule = (char = "=") => char.repeat(76);
  const refItem = findReferenceItem(comparison.items);
  const lines: string[] = [
    rule(),
    "SU ÖZELLİĞİ BACKEND KARŞILAŞTIRMA RAPORU",
    rule(),
    `Uygulama        : ${meta.app.name} (${meta.app.version})`,
    `Şartname        : ${meta.spec.code}`,
    `Oluşturma       : ${generatedAt.toLocaleString("tr-TR")}`,
    `Sıcaklık T      : ${fmt.c(comparison.temperature_c)}`,
    `Basınç P        : ${fmt.bar(comparison.pressure_bar)}`,
    `Seçili backend  : ${resolveWaterBackendLabel(meta, activeBackendKey)}`,
    `Referans satır  : ${refItem ? refItem.backend.label : "yok"}`,
    "",
    "Backend                             A (10^-6/bar)    ΔA (ref)    β (10^-6/°C)    Δβ (ref)  ρ (kg/m³)  Durum",
    rule("-"),
  ];

  for (const item of comparison.items) {
    const label = `${item.backend.key === activeBackendKey ? "* " : "  "}${item.backend.label}`;
    if (item.error) {
      lines.push(`${label.padEnd(36)} — HATA: ${item.error}`);
      continue;
    }
    const dA =
      refItem?.a_micro_per_bar != null && item.a_micro_per_bar != null
        ? item.a_micro_per_bar - refItem.a_micro_per_bar
        : null;
    const dBeta =
      refItem?.beta_micro_per_c != null && item.beta_micro_per_c != null
        ? item.beta_micro_per_c - refItem.beta_micro_per_c
        : null;
    const tag = item.backend.distribution_ready ? "Hazır" : "Geliştirme";
    lines.push(
      `${label.padEnd(36)} ${String(num(item.a_micro_per_bar, 6)).padStart(12)} ${String(
        dA !== null ? num(dA, 6) : "—",
      ).padStart(11)} ${String(num(item.beta_micro_per_c, 6)).padStart(14)} ${String(
        dBeta !== null ? num(dBeta, 6) : "—",
      ).padStart(11)} ${String(num(item.density_kg_per_m3, 2)).padStart(10)}  ${tag}`,
    );
  }
  lines.push(rule());
  return lines.join("\n");
}

function csvCell(value: string | number | boolean | null | undefined): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "number") {
    return Number.isFinite(value) ? String(value) : "";
  }
  if (typeof value === "boolean") {
    return String(value);
  }
  const safe = /^[=+\-@\t\r]/.test(value) ? `'${value}` : value;
  return /[",\n\r]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
}

export function buildBackendComparisonCsv(
  comparison: BackendComparisonResponse,
  activeBackendKey: string,
): string {
  const refItem = findReferenceItem(comparison.items);
  const header = [
    "backend_key",
    "backend_label",
    "active",
    "distribution_ready",
    "temperature_c",
    "pressure_bar",
    "a_micro_per_bar",
    "delta_a_vs_ref",
    "beta_micro_per_c",
    "delta_beta_vs_ref",
    "density_kg_per_m3",
    "error",
  ].join(",");

  const rows = comparison.items.map((item) => {
    const dA =
      refItem?.a_micro_per_bar != null && item.a_micro_per_bar != null
        ? Number((item.a_micro_per_bar - refItem.a_micro_per_bar).toFixed(6))
        : "";
    const dBeta =
      refItem?.beta_micro_per_c != null && item.beta_micro_per_c != null
        ? Number((item.beta_micro_per_c - refItem.beta_micro_per_c).toFixed(6))
        : "";
    return [
      csvCell(item.backend.key),
      csvCell(item.backend.label),
      csvCell(item.backend.key === activeBackendKey),
      csvCell(item.backend.distribution_ready),
      csvCell(comparison.temperature_c),
      csvCell(comparison.pressure_bar),
      csvCell(item.a_micro_per_bar),
      csvCell(dA),
      csvCell(item.beta_micro_per_c),
      csvCell(dBeta),
      csvCell(item.density_kg_per_m3),
      csvCell(item.error ?? ""),
    ].join(",");
  });

  return [header, ...rows].join("\n");
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 2_000);
}

export function downloadText(text: string, filename: string): void {
  downloadBlob(new Blob([text], { type: "text/plain;charset=utf-8" }), filename);
}

export function downloadJson(data: unknown, filename: string): void {
  downloadBlob(
    new Blob([JSON.stringify(data, null, 2)], { type: "application/json;charset=utf-8" }),
    filename,
  );
}
