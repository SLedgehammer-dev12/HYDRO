import { describe, expect, it } from "vitest";
import { DEMO_META, createEmptyInputs } from "./mock";
import { buildReportText, reportFileName } from "./report";
import type { HistoryEntry, ResultBundle } from "./types";

describe("report helpers", () => {
  it("builds safe filenames for exports", () => {
    const file = reportFileName("pdf", "BOT/FRM 01");
    expect(file).toMatch(/^hidrostatik_test_BOT_FRM_01_\d{8}_\d{6}\.pdf$/);
  });

  it("renders default BEKLIYOR report and section 8 when operations exist in history", () => {
    const inputs = createEmptyInputs();
    inputs.report = {
      report_no: "R-2026-01",
      operator: "Test Mühendisi",
      date: "2026-11-19",
      section_id: "K-01",
    };
    const results: ResultBundle = { source: "live", coefficients: {} };
    const history: HistoryEntry[] = [
      {
        id: "h-1",
        testType: "depressurization",
        title: "Basınç düşürme (16)",
        status: "BASARILI",
        summary: "Vana çapı 2 inç uygun.",
        at: "2026-11-19T10:00:00Z",
      },
      {
        id: "h-2",
        testType: "discharge",
        title: "Boşaltma (17)",
        status: "BASARISIZ",
        summary: "Boşaltma pigi kullanılmadı.",
        at: "2026-11-19T10:05:00Z",
      },
    ];

    const txt = buildReportText(inputs, results, DEMO_META, new Date("2026-11-19T10:10:00Z"), history);
    expect(txt).toContain("Hava içerik     : BEKLIYOR");
    expect(txt).toContain("Basınç değişim  : BEKLIYOR");
    expect(txt).toContain("8. OPERASYON SONUÇLARI (14–17)");
    expect(txt).toContain("Basınç düşürme (16)");
    expect(txt).toContain("Vana çapı 2 inç uygun.");
    expect(txt).toContain("Boşaltma pigi kullanılmadı.");
  });
});
