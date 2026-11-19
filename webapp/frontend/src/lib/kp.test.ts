import { describe, expect, it } from "vitest";
import {
  evaluateProjectKpContinuity,
  evaluateSegmentConsistency,
  extractKpFromLocation,
  formatKp,
  normalizeKpText,
  parseKpMeters,
} from "./kp";
import type { SegmentRow, SessionListItem } from "./types";

function makeSession(
  id: string,
  name: string,
  sectionNo: string,
  startKp: string,
  endKp: string,
): SessionListItem {
  return {
    id,
    project_id: "proj-1",
    name,
    status: "active",
    revision: 1,
    updated_at: "2026-11-19T00:00:00Z",
    section_meta: {
      section_no: sectionNo,
      description: "",
      location: "",
      start_kp: startKp,
      end_kp: endKp,
      test_date: "",
      test_type: "Hidrostatik test",
      notes: "",
    },
  };
}

describe("KP parsers & formatters", () => {
  it("parses chainage, km, m and numeric values", () => {
    expect(parseKpMeters("0+000")).toBe(0);
    expect(parseKpMeters("12+350")).toBe(12350);
    expect(parseKpMeters("KP 12+345,5")).toBe(12345.5);
    expect(parseKpMeters("12.5 km")).toBe(12500);
    expect(parseKpMeters("12000 m")).toBe(12000);
    expect(parseKpMeters("gecersiz")).toBeNull();
    expect(parseKpMeters(-5)).toBeNull();
  });

  it("formats and extracts KP ranges", () => {
    expect(formatKp(12000)).toBe("12+000");
    expect(formatKp(12345.5)).toBe("12+345,5");
    expect(normalizeKpText("kp 5.5 km")).toBe("5+500");
    expect(extractKpFromLocation("KP 0+000 - 12+000")).toEqual({
      start_kp: "0+000",
      end_kp: "12+000",
    });
  });
});

describe("KP continuity and segment checks", () => {
  it("passes when consecutive sections align cleanly without gaps or overlaps", () => {
    const res = evaluateProjectKpContinuity([
      makeSession("s1", "Kesit 1", "K-01", "0+000", "5+000"),
      makeSession("s2", "Kesit 2", "K-02", "5+000", "12+000"),
    ]);
    expect(res.status).toBe("pass");
    expect(res.sumMatchesPipeline).toBe(true);
    expect(res.totalSectionsLengthM).toBe(12000);
    expect(res.issues).toHaveLength(0);
  });

  it("fails and reports gaps or overlaps between sections", () => {
    const gapped = evaluateProjectKpContinuity([
      makeSession("s1", "Kesit 1", "K-01", "0+000", "5+000"),
      makeSession("s2", "Kesit 2", "K-02", "5+500", "12+000"),
    ]);
    expect(gapped.status).toBe("fail");
    expect(gapped.issues.some((msg) => msg.includes("boşluk"))).toBe(true);

    const overlapped = evaluateProjectKpContinuity([
      makeSession("s1", "Kesit 1", "K-01", "0+000", "5+200"),
      makeSession("s2", "Kesit 2", "K-02", "5+000", "12+000"),
    ]);
    expect(overlapped.status).toBe("fail");
    expect(overlapped.issues.some((msg) => msg.includes("bindirme"))).toBe(true);
  });

  it("evaluates segment total length against section bounds", () => {
    const segments: SegmentRow[] = [
      {
        id: "seg-1",
        outside_diameter_mm: 609.6,
        wall_thickness_mm: 7.1,
        length_m: 1000,
        start_station_m: 0,
        nps_label: "24 in",
        schedule_label: "STD",
      },
      {
        id: "seg-2",
        outside_diameter_mm: 609.6,
        wall_thickness_mm: 9.5,
        length_m: 2000,
        start_station_m: 1000,
        nps_label: "24 in",
        schedule_label: "XS",
      },
    ];
    const meta = makeSession("s1", "Kesit 1", "K-01", "0+000", "3+000").section_meta!;
    const ok = evaluateSegmentConsistency({ segments, sectionMeta: meta, fallbackLengthM: 3000 });
    expect(ok.status).toBe("pass");
    expect(ok.lengthMatchesSection).toBe(true);

    const mismatch = evaluateSegmentConsistency({
      segments: segments.slice(0, 1),
      sectionMeta: meta,
      fallbackLengthM: 3000,
    });
    expect(mismatch.status).toBe("fail");
    expect(mismatch.lengthMatchesSection).toBe(false);
  });
});
