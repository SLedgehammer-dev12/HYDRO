import { describe, expect, it } from "vitest";
import {
  countDistinctProfileStations,
  parseSurveyPointsText,
} from "../components/geometry/SiteSurveyPanel";
import { buildDemoResults, buildSceneData, createDefaultInputs, createEmptyInputs } from "./mock";
import { normalizeInputs, toApiInputs } from "./normalize";

describe("3D real profile_points and equipment inputs", () => {
  it("normalizes and serializes canonical and legacy equipment entries", () => {
    const raw = {
      ...createEmptyInputs(),
      geometry: { outside_diameter_mm: 406.4, wall_thickness_mm: 8.74, length_m: 1200 },
      profile_points: [
        { station_m: 1200, elevation_m: 260 },
        { station_m: 0, elevation_m: 200 },
      ],
      equipment: [
        {
          id: "eq-2",
          kind: "test_head",
          label: "Ölçüm Test Başlığı",
          distance_m: 900,
          elevation_m: null,
          status: "warning",
        },
        {
          id: "eq-1",
          kind: "mainline",
          label: "Ana Hat Vanası",
          station_m: 120,
          elevation_m: 215.5,
        },
        {
          type: "valve",
          label: "   ",
          station_m: 300,
        },
      ],
    };

    const normalized = normalizeInputs(raw);
    expect(normalized.profile_points).toEqual([
      { station_m: 0, elevation_m: 200 },
      { station_m: 1200, elevation_m: 260 },
    ]);
    expect(normalized.equipment).toEqual([
      {
        id: "eq-1",
        type: "valve",
        label: "Ana Hat Vanası",
        station_m: 120,
        elevation_m: 215.5,
        status: "pass",
      },
      {
        id: "eq-2",
        type: "test-head",
        label: "Ölçüm Test Başlığı",
        station_m: 900,
        elevation_m: null,
        status: "warning",
      },
    ]);

    const payload = toApiInputs(normalized);
    expect(payload.profile_points).toEqual(normalized.profile_points);
    expect(payload.equipment).toEqual(normalized.equipment);
  });

  it("parses CSV, TSV, decimal comma and KP coordinates safely in parseSurveyPointsText", () => {
    const raw = [
      "İstasyon;Kot",
      "KP 1+500\t485,2",
      "KP 0+500\t410",
      "0,420.5",
      "2000; 510,75",
      ", 450",
      "bad-line",
      "-10, 400",
      "3000, 12000",
    ].join("\n");

    const parsed = parseSurveyPointsText(raw, 1000);
    expect(parsed.points).toEqual([
      { station_m: 0, elevation_m: 420.5 },
      { station_m: 500, elevation_m: 485.2 },
      { station_m: 2000, elevation_m: 510.75 },
    ]);
    expect(parsed.invalidLines).toBe(5);
    expect(
      countDistinctProfileStations(
        [
          { station_m: 1200, elevation_m: 100 },
          { station_m: 1800, elevation_m: 120 },
        ],
        1000,
      ),
    ).toBe(1);
  });

  it("emits approximate warnings without being swallowed when feasible is false", () => {
    const inputs = createDefaultInputs();
    const baseProfile = buildDemoResults(inputs).profile!;
    const scene = buildSceneData(inputs, {
      profile: {
        ...baseProfile,
        feasible: false,
      },
    });

    expect(scene.is_survey_profile).toBe(false);
    expect(scene.is_custom_equipment).toBe(false);
    expect(scene.warnings).toHaveLength(3);
    expect(scene.warnings?.some((w) => w.includes("üç limitin"))).toBe(true);
    expect(scene.warnings?.some((w) => w.includes("profile_points"))).toBe(true);
    expect(scene.warnings?.some((w) => w.includes("equipment"))).toBe(true);
  });

  it("requires >=2 distinct stations for is_survey_profile and interpolates custom equipment elevation", () => {
    const duplicateOnly = createDefaultInputs();
    duplicateOnly.profile_points = [
      { station_m: 10, elevation_m: 100 },
      { station_m: 10.1, elevation_m: 120 },
    ];
    expect(buildSceneData(duplicateOnly, {}).is_survey_profile).toBe(false);

    const real = createEmptyInputs();
    real.geometry = { outside_diameter_mm: 406.4, wall_thickness_mm: 8.74, length_m: 1000 };
    real.section_profile = {
      highest_elevation_m: 200,
      lowest_elevation_m: 100,
      start_elevation_m: 100,
      end_elevation_m: 200,
      design_pressure_bar: 80,
      smys_mpa: 450,
    };
    real.profile_points = [
      { station_m: 0, elevation_m: 100 },
      { station_m: 1000, elevation_m: 200 },
    ];
    real.equipment = [
      {
        id: "eq-mid",
        type: "gauge",
        label: "Orta Ölçer",
        station_m: 500,
        elevation_m: null,
        status: "warning",
      },
    ];

    const scene = buildSceneData(real, {});
    expect(scene.is_survey_profile).toBe(true);
    expect(scene.is_custom_equipment).toBe(true);
    expect(scene.warnings).toEqual([]);
    expect(scene.equipment).toEqual([
      {
        id: "eq-mid",
        type: "gauge",
        label: "Orta Ölçer",
        distance_m: 500,
        elevation_m: 150,
        status: "warning",
      },
    ]);
  });
});
