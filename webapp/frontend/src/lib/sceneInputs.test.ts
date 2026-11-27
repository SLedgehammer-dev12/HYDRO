import { describe, expect, it } from "vitest";
import {
  countDistinctProfileStations,
  parseSurveyPointsText,
} from "../components/geometry/SiteSurveyPanel";
import {
  buildDemoResults,
  buildSceneData,
  buildSectionDetailSceneData,
  computeProfile,
  createDefaultInputs,
  createEmptyInputs,
  sectionsFromInputs,
  simplifyProfilePointsRdp,
} from "./mock";
import { buildSceneLayout } from "../components/three/sceneModel";
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

  it("computes per-segment SMYS limits in computeProfile, buildSceneData, and normalizeInputs", () => {
    const inputs = createEmptyInputs();
    inputs.material_grade = "API 5L PSL2 X65 / L450 - SMYS 450 MPa";
    inputs.section_profile = {
      highest_elevation_m: 100,
      lowest_elevation_m: 100,
      start_elevation_m: 100,
      end_elevation_m: 100,
      design_pressure_bar: 100,
      smys_mpa: 450,
    };
    inputs.pump_location = "Baslangic noktasi";
    inputs.field.monitored_pressure_bar = 130;
    inputs.segments = [
      {
        id: "s1",
        nps_label: "NPS 16",
        schedule_label: "Sch 20",
        outside_diameter_mm: 406.4,
        wall_thickness_mm: 8.74,
        length_m: 500,
        start_station_m: 0,
        material_grade: "API 5L PSL2 X65 / L450 - SMYS 450 MPa",
        smys_mpa: 450,
      },
      {
        id: "s2",
        nps_label: "NPS 16",
        schedule_label: "Sch 20",
        outside_diameter_mm: 406.4,
        wall_thickness_mm: 8.74,
        length_m: 500,
        start_station_m: 500,
        material_grade: "API 5L PSL2 X42 / L290 - SMYS 290 MPa",
        smys_mpa: 290,
      },
    ];

    const normalized = normalizeInputs(inputs);
    expect(normalized.segments[1].smys_mpa).toBe(290);
    expect(normalized.segments[1].material_grade).toContain("X42");

    const sections = sectionsFromInputs(normalized);
    const prof = computeProfile({
      geometry: { sections },
      design_pressure_bar: 100,
      smys_mpa: 450,
      location_class: normalized.location_class,
      highest_elevation_m: 100,
      lowest_elevation_m: 100,
      start_elevation_m: 100,
      end_elevation_m: 100,
      pump_location: normalized.pump_location,
      monitored_pressure_bar: 130,
    });
    expect(prof.limiting_segment_index).toBe(2);
    expect(prof.limiting_smys_mpa).toBe(290);
    expect(prof.limiting_pipe_description).toContain("Limit segment 2");
    expect(prof.limiting_pipe_description).toContain("SMYS=290.0 MPa");

    // Non-survey scene uses per-segment SMYS
    const approxScene = buildSceneData(normalized, { profile: prof });
    expect(approxScene.segments).toHaveLength(2);
    expect(approxScene.segments[0].smys_mpa).toBe(450);
    expect(approxScene.segments[1].smys_mpa).toBe(290);
    expect((approxScene.segments[1].utilization ?? 0)).toBeGreaterThan(
      approxScene.segments[0].utilization ?? 0,
    );

    // Survey scene uses per-segment SMYS too
    normalized.profile_points = [
      { station_m: 0, elevation_m: 100 },
      { station_m: 1000, elevation_m: 100 },
    ];
    const surveyScene = buildSceneData(normalized, { profile: prof });
    const seg1 = surveyScene.segments.find((s) => s.end_m <= 500);
    const seg2 = surveyScene.segments.find((s) => s.start_m >= 500);
    expect(seg1?.smys_mpa).toBe(450);
    expect(seg2?.smys_mpa).toBe(290);
    expect((seg2?.utilization ?? 0)).toBeGreaterThan(seg1?.utilization ?? 0);

    // toApiInputs -> normalizeInputs round-trip preserves segment smys_mpa and material_grade
    const roundTripped = normalizeInputs(toApiInputs(normalized));
    expect(roundTripped.segments[0].smys_mpa).toBe(450);
    expect(roundTripped.segments[1].smys_mpa).toBe(290);
    expect(roundTripped.segments[1].material_grade).toContain("X42");

    // Custom numeric SMYS segment (without grade) does not inherit top-level X65 label,
    // and segment SMYS boundary at 500 m survives a close terrain point at 499.4 m.
    normalized.profile_points = [
      { station_m: 0, elevation_m: 100 },
      { station_m: 499.4, elevation_m: 110 },
      { station_m: 1000, elevation_m: 100 },
    ];
    normalized.segments[1].material_grade = "";
    normalized.segments[1].smys_mpa = 305;
    const boundaryScene = buildSceneData(normalized, { profile: prof });
    const hasExactBoundary = boundaryScene.segments.some((s) => Math.abs(s.end_m - 500) < 0.01);
    expect(hasExactBoundary).toBe(true);
    const customSeg = boundaryScene.segments.find((s) => s.start_m >= 500);
    expect(customSeg?.smys_mpa).toBe(305);
    expect(customSeg?.grade).toBeNull();

    // buildDemoResults derives profile when line SMYS is null if all segments have SMYS
    normalized.section_profile.smys_mpa = null;
    const demoSegOnly = buildDemoResults(normalized);
    expect(demoSegOnly.profile?.limiting_smys_mpa).toBe(305);
  });

  it("preserves RDP profile spikes, guarantees detail launcher/receiver/pig, and scales overview slimmer than detail", () => {
    const denseCurve = Array.from({ length: 140 }, (_, idx) => ({
      x: idx * 50,
      y: 250 + Math.sin(idx / 12) * 15,
    }));
    denseCurve[43] = { x: 43 * 50, y: 410 };
    denseCurve[97] = { x: 97 * 50, y: 120 };

    const simplified = simplifyProfilePointsRdp(denseCurve, 24);
    expect(simplified.length).toBeLessThanOrEqual(24);
    expect(simplified.some((p) => p.x === 43 * 50 && p.y === 410)).toBe(true);
    expect(simplified.some((p) => p.x === 97 * 50 && p.y === 120)).toBe(true);

    const inputs = createDefaultInputs();
    inputs.equipment = [];
    inputs.field.pig_distance_m = null;
    inputs.profile_points = denseCurve.map((p) => ({ station_m: p.x, elevation_m: p.y }));
    const detailScene = buildSectionDetailSceneData(inputs);

    expect(detailScene.equipment.some((eq) => eq.type === "pig-launcher")).toBe(true);
    expect(detailScene.equipment.some((eq) => eq.type === "pig-receiver")).toBe(true);
    expect(detailScene.pig).not.toBeNull();
    expect(detailScene.pig?.distance_m).toBe(0);

    const overviewLayout = buildSceneLayout(detailScene, { mode: "overview", verticalScaleMode: "auto" });
    const detailLayout = buildSceneLayout(detailScene, { mode: "detail", verticalScaleMode: "4x" });
    expect(overviewLayout.segments[0].radius).toBeLessThan(detailLayout.segments[0].radius);
    expect(overviewLayout.segments[0].radius).toBeLessThanOrEqual(0.16);
    expect(detailLayout.verticalExaggeration).toBeGreaterThan(overviewLayout.verticalExaggeration);
    expect(overviewLayout.elevationTicks.length).toBeGreaterThan(0);
  });
});
