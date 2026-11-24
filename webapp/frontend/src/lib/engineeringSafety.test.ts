import { describe, expect, it } from "vitest";
import {
  DEMO_META,
  computeB,
  computePressure,
  createDefaultInputs,
  createEmptyInputs,
} from "./mock";
import { normalizeInputs } from "./normalize";
import {
  buildBackendComparisonCsv,
  buildBackendComparisonReportText,
  buildReportText,
  buildSnapshot,
} from "./report";

describe("Slice 5 engineering safety & coefficient regressions", () => {
  it("keeps water_backend separate from table labels, merges OCR report_meta and mirrors ambient temp", () => {
    const normalized = normalizeInputs({
      modes: {
        air_a_reference: "table_v1_bicubic",
        pressure_a_reference: "BOTAŞ referans tablosu - aktif T/P",
      },
      report: { report_no: "", operator: "", date: "", section_id: "" },
      report_meta: {
        report_no: "OCR-77",
        operator: "Ali Veli",
        date: "2026-11-20",
        section_id: "K-08",
      },
      air: { ambient_temperature_c: 1.5 },
    });

    expect(normalized.water_backend).toBe("table_v1_bicubic");
    expect(normalized.modes.air_a_reference).toBe("");
    expect(normalized.modes.pressure_a_reference).toBe("BOTAŞ referans tablosu - aktif T/P");
    expect(normalized.report).toEqual({
      report_no: "OCR-77",
      operator: "Ali Veli",
      date: "2026-11-20",
      section_id: "K-08",
    });
    expect(normalized.field.ambient_temperature_c).toBe(1.5);
  });

  it("produces negative beta_water and B at 0-2 C and flags negative_b by B sign rather than Pt sign", () => {
    const bCold = computeB({
      source: "auto",
      temperature_c: 1,
      pressure_bar: 30,
      steel_alpha_micro_per_c: 12,
      steel_model: "volumetric",
      backend: "table_v1",
    });
    expect(bCold.water_beta_micro_per_c).not.toBeNull();
    expect(bCold.water_beta_micro_per_c as number).toBeLessThan(0);
    expect(bCold.b_micro_per_c).toBeLessThan(0);

    const geom = {
      sections: [{ outside_diameter_mm: 406.4, wall_thickness_mm: 8.74, length_m: 1000 }],
    };

    const positiveBNegDt = computePressure({
      geometry: geom,
      a_micro_per_bar: 45,
      b_micro_per_c: 180,
      delta_t_c: -2,
      actual_pressure_change_bar: -5,
    });
    expect(positiveBNegDt.theoretical_pressure_change_bar).toBeLessThan(0);
    expect(positiveBNegDt.negative_b).toBe(false);

    const negativeBNegDt = computePressure({
      geometry: geom,
      a_micro_per_bar: 45,
      b_micro_per_c: -20,
      delta_t_c: -2,
      actual_pressure_change_bar: 0.5,
    });
    expect(negativeBNegDt.theoretical_pressure_change_bar).toBeGreaterThan(0);
    expect(negativeBNegDt.negative_b).toBe(true);
    expect(negativeBNegDt.decision.summary).toContain("B negatif");

    const zeroB = computePressure({
      geometry: geom,
      a_micro_per_bar: 45,
      b_micro_per_c: 0,
      delta_t_c: 2,
      actual_pressure_change_bar: 0,
    });
    expect(zeroB.negative_b).toBe(false);
    expect(zeroB.theoretical_pressure_change_bar).toBe(0);
    expect(createEmptyInputs().pressure.derive_delta_t).toBe(false);
  });

  it("neutralizes spreadsheet formula prefixes in CSV cells while keeping numbers numeric and roundtrips snapshots", () => {
    const formulaComparison = {
      temperature_c: 10,
      pressure_bar: 50,
      items: [
        {
          backend: { key: "table_v1", label: "=cmd|' /C calc'!A0", distribution_ready: true },
          a_micro_per_bar: 45.0,
          beta_micro_per_c: -19.37,
          density_kg_per_m3: 1000.2,
          error: null,
        },
        {
          backend: { key: "other", label: "+SUM(A1:A2)", distribution_ready: true },
          a_micro_per_bar: null,
          beta_micro_per_c: null,
          density_kg_per_m3: null,
          error: "@malicious",
        },
      ],
    };
    const csv = buildBackendComparisonCsv(formulaComparison, "table_v1");
    expect(csv).toContain("'=cmd|");
    expect(csv).toContain("'+SUM(A1:A2)");
    expect(csv).toContain("'@malicious");
    // Negative numbers remain plain numeric cells without quote prefix
    expect(csv).toContain(",-19.37,");

    const defaults = createDefaultInputs();
    defaults.water_backend = "table_v1_bicubic";
    defaults.air.ambient_temperature_c = 1.5;
    defaults.field.ambient_temperature_c = 1.5;
    const snap = buildSnapshot(defaults, { source: "live" }, DEMO_META);
    expect(snap.water_backend_option).toBe("IAPWS-IF97 Region 1 (Bicubic)");
    expect((snap.modes as Record<string, unknown>).air_a_mode).toBe("Otomatik");
    expect((snap.modes as Record<string, unknown>).pressure_b_source).toBe(
      "Kurum ici tablo (varsayilan)",
    );

    const restored = normalizeInputs(snap);
    expect(restored.water_backend).toBe("table_v1_bicubic");
    expect(restored.modes.air_a_mode).toBe("auto");
    expect(restored.modes.pressure_b_source).toBe("institutional");
    expect(restored.segments.length).toBeGreaterThan(0);
    expect(restored.air.ambient_temperature_c).toBe(1.5);
    expect(restored.field.ambient_temperature_c).toBe(1.5);
    expect(restored.report).toEqual(defaults.report);

    const legacyIapws = normalizeInputs({ water_backend: "iapws" });
    expect(legacyIapws.water_backend).toBe("iapws95_dev");
  });

  it("includes +2 C warning, Tilk/Tson, active backend and backend comparison in report & exports", () => {
    const inputs = createEmptyInputs();
    inputs.water_backend = "coolprop";
    inputs.air.ambient_temperature_c = 1.2;
    inputs.pressure.t_initial_c = 14.5;
    inputs.pressure.t_final_c = 12.0;
    inputs.pressure.delta_t_c = 2.5;
    inputs.report = {
      report_no: "RPR-90",
      operator: "M. Demir",
      date: "2026-11-20",
      section_id: "K-05",
    };

    const comparison = {
      temperature_c: 10,
      pressure_bar: 50,
      items: [
        {
          backend: { key: "table_v1", label: "IAPWS-IF97 Region 1", distribution_ready: true },
          a_micro_per_bar: 46.1,
          beta_micro_per_c: 99.6,
          density_kg_per_m3: 1001.8,
          error: null,
        },
        {
          backend: { key: "coolprop", label: "IAPWS-95", distribution_ready: true },
          a_micro_per_bar: 46.2,
          beta_micro_per_c: 99.9,
          density_kg_per_m3: 1001.9,
          error: null,
        },
        {
          backend: { key: "broken_dev", label: "Broken Backend", distribution_ready: false },
          a_micro_per_bar: null,
          beta_micro_per_c: null,
          density_kg_per_m3: null,
          error: "Backend kurulu degil",
        },
      ],
    };

    const txt = buildReportText(inputs, { source: "live", backendCompare: comparison }, DEMO_META);
    expect(txt).toContain("IAPWS-95 (coolprop)");
    expect(txt).toContain("UYARI (10.1)");
    expect(txt).toContain("Başlangıç Tilk");
    expect(txt).toContain("Bitiş Tson");
    expect(txt).toContain("BACKEND KARŞILAŞTIRMASI");

    const cmpTxt = buildBackendComparisonReportText(comparison, "coolprop", DEMO_META);
    expect(cmpTxt).toContain("SU ÖZELLİĞİ BACKEND KARŞILAŞTIRMA RAPORU");
    expect(cmpTxt).toContain("* IAPWS-95");
    expect(cmpTxt).toContain("HATA: Backend kurulu degil");

    const cmpCsv = buildBackendComparisonCsv(comparison, "coolprop");
    expect(cmpCsv).toContain("backend_key,backend_label,active");
    expect(cmpCsv).toContain("coolprop,IAPWS-95,true");
    expect(cmpCsv).toContain("Backend kurulu degil");

    const snap = buildSnapshot(inputs, { source: "live" }, DEMO_META);
    expect(snap.water_backend_option).toBe("IAPWS-95");
    expect(snap.report).toEqual(inputs.report);
  });
});
