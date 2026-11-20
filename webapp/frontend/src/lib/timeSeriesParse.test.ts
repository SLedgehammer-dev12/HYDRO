import { describe, expect, it } from "vitest";
import { formatTsShort, parseTimeSeriesPaste } from "./timeSeriesParse";

describe("parseTimeSeriesPaste", () => {
  it("parses ISO timestamps, Turkish decimals, optional volume, notes and skips header row", () => {
    const raw = [
      "Zaman\tBasınç (bar)\tSıcaklık (°C)\tHacim (m3)\tNot",
      "2026-11-14T08:00:00Z\t80,25\t15,4\t10,5\tBaşlangıç okuması",
      "2026-11-14T12:00:00Z\t80,20\t15,2\t-\tÖğle",
    ].join("\n");

    const res = parseTimeSeriesPaste(raw);
    expect(res.error).toBeNull();
    expect(res.skipped).toBe(1);
    expect(res.records).toHaveLength(2);
    expect(res.records[0]).toEqual({
      timestamp: "2026-11-14T08:00:00.000Z",
      pressure_bar: 80.25,
      temperature_c: 15.4,
      volume_m3: 10.5,
      notes: "Başlangıç okuması",
      source: "batch",
    });
    expect(res.records[1].volume_m3).toBeNull();
    expect(res.records[1].notes).toBe("Öğle");
  });

  it("handles bare HH:MM timestamps with midnight day rollover and DD.MM.YYYY HH:MM format", () => {
    const bare = [
      "22:00;82,1;14,8",
      "02:00;82,0;14,7",
      "08:00;81,9;14,6",
    ].join("\n");
    const bareRes = parseTimeSeriesPaste(bare, "2026-11-14");
    expect(bareRes.error).toBeNull();
    expect(bareRes.records[0].timestamp).toBe("2026-11-14T22:00:00.000Z");
    expect(bareRes.records[1].timestamp).toBe("2026-11-15T02:00:00.000Z");
    expect(bareRes.records[2].timestamp).toBe("2026-11-15T08:00:00.000Z");

    const tr = parseTimeSeriesPaste("14.11.2026 08:30\t85.5\t0");
    expect(tr.error).toBeNull();
    expect(tr.records[0].timestamp).toBe("2026-11-14T08:30:00.000Z");
    expect(tr.records[0].temperature_c).toBe(0);
    expect(formatTsShort(tr.records[0].timestamp)).toBe("14.11 08:30");
  });

  it("returns explicit Turkish line error for malformed timestamp or missing column", () => {
    const badTs = parseTimeSeriesPaste("xx:yy\t80\t15");
    expect(badTs.error).toContain("1. satırda zaman formatı tanınmadı");

    const badCols = parseTimeSeriesPaste("08:00\t80");
    expect(badCols.error).toContain("1. satırda en az 3 sütun olmalı");

    const badNum = parseTimeSeriesPaste("08:00\tabc\t15");
    expect(badNum.error).toContain("1. satırda basınç");
  });
});
