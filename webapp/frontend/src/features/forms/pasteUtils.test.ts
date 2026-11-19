import { describe, expect, it } from "vitest";
import {
  isTabularClipboard,
  parseCellNum,
  parseFillingPaste,
  parseMeasurementsPaste,
  parseMonitoringPaste,
  parsePigRunsPaste,
} from "./pasteUtils";

describe("pasteUtils", () => {
  it("parses Turkish decimal numbers and ignores blanks", () => {
    expect(parseCellNum(" 12,5 ")).toBe(12.5);
    expect(parseCellNum("")).toBeNull();
    expect(parseCellNum("abc")).toBeNull();
  });

  it("detects tabular clipboard content", () => {
    expect(isTabularClipboard("08:00\t75,4\t12,1")).toBe(true);
    expect(isTabularClipboard("row1\nrow2")).toBe(true);
    expect(isTabularClipboard("12,5")).toBe(false);
  });

  it("parses Excel TSV filling, monitoring, measurement and pig-run rows", () => {
    const filling = parseFillingPaste("\n08:00\t100,5\t25,2\t100,5\t11,0\t4,5\n\n");
    expect(filling).toHaveLength(1);
    expect(filling[0]).toMatchObject({
      time_str: "08:00",
      meter_reading_m3: 100.5,
      delta_volume_m3: 25.2,
      water_inlet_temp_c: 11.0,
    });

    const monitoring = parseMonitoringPaste("09:00\t84,2\t12,3\t13,1\t13,2\t13,4\t13,5");
    expect(monitoring).toHaveLength(1);
    expect(monitoring[0]).toMatchObject({
      time_str: "09:00",
      pressure_bar: 84.2,
      soil_1_c: 13.1,
      pipe_1_c: 13.2,
    });

    const measurements = parseMeasurementsPaste("910,2\t1200\t88,5\t95,0\t82,1\t88,0");
    expect(measurements).toHaveLength(1);
    expect(measurements[0]).toMatchObject({
      pipe_top_elev_m: 910.2,
      station_m: 1200,
      max_pressure_bar: 88.5,
    });

    const pigs = parsePigRunsPaste("Pig Tipi\tAtılış\tAlınış\tSüre\nBi-Di Pig\t08:00\t09:30\t90\tKP 12");
    expect(pigs).toHaveLength(1);
    expect(pigs[0]).toMatchObject({
      pig_type: "Bi-Di Pig",
      launch_time: "08:00",
      receive_time: "09:30",
      duration_min: 90,
      note: "KP 12",
    });
  });
});
