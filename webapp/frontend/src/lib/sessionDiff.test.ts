import { describe, expect, it } from "vitest";
import { ApiError } from "./api";
import { createDefaultInputs } from "./mock";
import {
  applyDiffResolutions,
  buildDiffFromServerEntries,
  computeSessionDiff,
  extractRevisionConflict,
  formatDiffValue,
  valuesEqual,
} from "./sessionDiff";
import type { Session } from "./types";

function makeServerSession(overrides: Partial<Session> = {}): Session {
  const inputs = createDefaultInputs();
  return {
    id: "sess-1",
    project_id: "proj-1",
    name: "Kesit K-01",
    status: "active",
    revision: 4,
    inputs: inputs as unknown as Record<string, unknown>,
    wizard_state: null,
    result_summary: {},
    created_at: "2026-11-20T07:00:00Z",
    updated_at: "2026-11-20T08:00:00Z",
    deleted_at: null,
    ...overrides,
  };
}

describe("sessionDiff helpers", () => {
  it("extracts 409 revision_conflict error payload safely", () => {
    const server = makeServerSession({ revision: 5 });
    const err = new ApiError(409, "revision_conflict", "Çakışma", {
      expected_revision: 3,
      current_revision: 5,
      current: server,
      diff: [{ path: "geometry.length_m", incoming: 14000, server: 12000 }],
    });

    const extracted = extractRevisionConflict(err);
    expect(extracted).not.toBeNull();
    expect(extracted?.currentRevision).toBe(5);
    expect(extracted?.expectedRevision).toBe(3);
    expect(extracted?.serverSession.id).toBe("sess-1");
    expect(extracted?.serverDiff).toEqual([
      { path: "geometry.length_m", incoming: 14000, server: 12000 },
    ]);

    expect(extractRevisionConflict(new ApiError(400, "bad_request", "Hata"))).toBeNull();
    expect(extractRevisionConflict(new Error("generic"))).toBeNull();
  });

  it("diffs changed scalar, numeric 0 vs null, checks, and segments ignoring client-only id", () => {
    const localInputs = createDefaultInputs();
    localInputs.geometry.length_m = 0;
    localInputs.checks.air_content_limit = true;
    localInputs.field.ambient_temperature_c = 1.5;
    localInputs.air.ambient_temperature_c = 1.5;
    // Only ids differ for segment rows -> must NOT produce diff
    localInputs.segments = localInputs.segments.map((seg, idx) => ({
      ...seg,
      id: `client-only-id-${idx}`,
    }));

    const serverInputs = createDefaultInputs();
    serverInputs.geometry.length_m = null;
    serverInputs.checks.air_content_limit = false;
    serverInputs.field.ambient_temperature_c = 8.0;
    serverInputs.air.ambient_temperature_c = 8.0;
    const serverSession = makeServerSession({
      inputs: serverInputs as unknown as Record<string, unknown>,
    });

    const items = computeSessionDiff(
      {
        name: "Kesit K-01 Revize",
        status: "active",
        projectId: "proj-local-2",
        inputs: localInputs,
      },
      serverSession,
    );

    const byPath = Object.fromEntries(items.map((item) => [item.path, item]));
    expect(byPath.name.localDisplay).toBe("Kesit K-01 Revize");
    expect(byPath.project_id.localValue).toBe("proj-local-2");
    expect(byPath.project_id.serverValue).toBe("proj-1");
    expect(byPath["geometry.length_m"].localDisplay).toBe("0");
    expect(byPath["geometry.length_m"].serverDisplay).toBe("—");
    expect(byPath["checks.air_content_limit"].localDisplay).toBe("Evet");
    expect(byPath["checks.air_content_limit"].serverDisplay).toBe("Hayır");
    expect(byPath["field.ambient_temperature_c"]).toBeDefined();
    // Canonical ambient temperature deduplication: air.ambient_temperature_c is omitted
    expect(byPath["air.ambient_temperature_c"]).toBeUndefined();
    expect(byPath.segments).toBeUndefined();

    // Normalized segment start_station_m: undefined vs null on server produces zero diff
    serverInputs.segments = serverInputs.segments.map((seg) => ({
      ...seg,
      start_station_m: null,
    }));
    localInputs.segments = localInputs.segments.map((seg) => ({
      ...seg,
      start_station_m: undefined as unknown as number | null,
    }));
    const noSegDiff = computeSessionDiff(
      { name: "Kesit K-01 Revize", status: "active", inputs: localInputs },
      makeServerSession({ inputs: serverInputs as unknown as Record<string, unknown> }),
    );
    expect(noSegDiff.find((item) => item.path === "segments")).toBeUndefined();
  });

  it("distinguishes bool vs numeric 0/1, formats array sections, and resolves project_id", () => {
    expect(valuesEqual(false, 0)).toBe(false);
    expect(valuesEqual(true, 1)).toBe(false);
    expect(valuesEqual(0, "")).toBe(false);
    expect(valuesEqual(0, 0)).toBe(true);

    const serverInputs = createDefaultInputs();
    const localInputs = createDefaultInputs();
    localInputs.profile_points = [{ station_m: 0, elevation_m: 100 }];
    localInputs.equipment = [
      { id: "eq-1", type: "valve", label: "Vana", station_m: 10, elevation_m: 100, status: "pass" },
    ];
    const serverSession = makeServerSession({
      project_id: "proj-srv",
      inputs: serverInputs as unknown as Record<string, unknown>,
    });

    const items = computeSessionDiff(
      { name: "Kesit K-01", status: "active", projectId: null, inputs: localInputs },
      serverSession,
    );
    const byPath = Object.fromEntries(items.map((item) => [item.path, item]));
    expect(byPath.profile_points.localDisplay).toBe("1 kot noktası");
    expect(byPath.equipment.localDisplay).toBe("1 ekipman");
    expect(byPath.project_id.localValue).toBeNull();

    const keepServerProject = applyDiffResolutions(
      { name: "Kesit K-01", status: "active", projectId: null, inputs: localInputs },
      serverSession,
      { project_id: "server", profile_points: "local" },
    );
    expect(keepServerProject.projectId).toBe("proj-srv");
    expect(keepServerProject.inputs.profile_points).toHaveLength(1);
  });

  it("applies selective per-row local/server choices and syncs ambient temperature", () => {
    const serverInputs = createDefaultInputs();
    serverInputs.geometry.length_m = 10_000;
    serverInputs.air.temperature_c = 18;
    serverInputs.field.ambient_temperature_c = 12;
    serverInputs.air.ambient_temperature_c = 12;

    const localInputs = createDefaultInputs();
    localInputs.geometry.length_m = 14_500;
    localInputs.air.temperature_c = 25;
    localInputs.field.ambient_temperature_c = 1.2;
    localInputs.air.ambient_temperature_c = 1.2;

    const serverSession = makeServerSession({
      name: "Sunucu Adi",
      inputs: serverInputs as unknown as Record<string, unknown>,
    });

    const merged = applyDiffResolutions(
      { name: "Yerel Adi", status: "active", inputs: localInputs },
      serverSession,
      {
        name: "server",
        "geometry.length_m": "local",
        "air.temperature_c": "server",
        "field.ambient_temperature_c": "local",
      },
    );

    expect(merged.name).toBe("Sunucu Adi");
    expect(merged.inputs.geometry.length_m).toBe(14_500);
    expect(merged.inputs.air.temperature_c).toBe(18);
    expect(merged.inputs.field.ambient_temperature_c).toBe(1.2);
    expect(merged.inputs.air.ambient_temperature_c).toBe(1.2);
  });

  it("formats server diff entries and preserves numeric 0", () => {
    expect(formatDiffValue("pressure.delta_t_c", 0)).toBe("0");
    const built = buildDiffFromServerEntries([
      { path: "pressure.delta_t_c", incoming: 0, server: 2 },
      { path: "water_backend", incoming: "coolprop", server: "table_v1" },
    ]);
    expect(built).toHaveLength(2);
    expect(built[0].label).toContain("ΔT");
    expect(built[0].localDisplay).toBe("0");
    expect(built[1].group).toBe("Oturum");
  });
});
