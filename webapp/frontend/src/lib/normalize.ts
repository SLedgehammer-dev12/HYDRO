import { createDefaultInputs } from "./mock";
import { parseNumber } from "./format";
import type {
  AMode,
  AppInputs,
  BSource,
  CheckKey,
  SegmentRow,
  SteelModel,
} from "./types";

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const asRecord = (value: unknown): Record<string, unknown> => (isRecord(value) ? value : {});

const asNumber = (value: unknown, fallback: number | null): number | null => {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const parsed = parseNumber(value);
    return parsed !== null && Number.isFinite(parsed) ? parsed : fallback;
  }
  return fallback;
};

const asNumberRequired = (value: unknown, fallback: number): number => {
  const parsed = asNumber(value, null);
  return parsed === null ? fallback : parsed;
};

const asString = (value: unknown, fallback = ""): string =>
  typeof value === "string" ? value : fallback;

const asBool = (value: unknown, fallback: boolean): boolean =>
  typeof value === "boolean" ? value : fallback;

const A_MODES: AMode[] = ["auto", "table", "manual"];
const B_SOURCES: BSource[] = ["institutional", "gail", "auto"];
const STEEL_MODELS: SteelModel[] = ["volumetric", "linear", "volumetric_temperature"];

function asAMode(value: unknown, fallback: AMode): AMode {
  return A_MODES.includes(value as AMode) ? (value as AMode) : fallback;
}

function asBSource(value: unknown, fallback: BSource): BSource {
  return B_SOURCES.includes(value as BSource) ? (value as BSource) : fallback;
}

function asSteelModel(value: unknown, fallback: SteelModel): SteelModel {
  return STEEL_MODELS.includes(value as SteelModel) ? (value as SteelModel) : fallback;
}

function asBMode(value: unknown, fallback: "auto" | "table" | "manual") {
  return value === "auto" || value === "table" || value === "manual" ? value : fallback;
}

function asSegments(value: unknown, fallback: SegmentRow[]): SegmentRow[] {
  if (!Array.isArray(value) || value.length === 0) return fallback;
  const rows: SegmentRow[] = [];
  value.forEach((item, index) => {
    const row = asRecord(item);
    const od = asNumber(row.outside_diameter_mm, null);
    const wt = asNumber(row.wall_thickness_mm, null);
    const length = asNumber(row.length_m, null);
    if (od === null || wt === null || length === null) return;
    rows.push({
      id: asString(row.id, `seg-${index + 1}`),
      nps_label: asString(row.nps_label),
      schedule_label: asString(row.schedule_label),
      outside_diameter_mm: od,
      wall_thickness_mm: wt,
      length_m: length,
      start_station_m: asNumber(row.start_station_m, null),
    });
  });
  return rows.length > 0 ? rows : fallback;
}

/** API `inputs` nesnesini (kısmi olabilir) yerel modele birleştirir. */
export function normalizeInputs(raw: unknown): AppInputs {
  const base = createDefaultInputs();
  if (!isRecord(raw)) return base;

  const geometry = asRecord(raw.geometry);
  const catalog = asRecord(raw.geometry_catalog);
  const profile = asRecord(raw.section_profile);
  const air = asRecord(raw.air);
  const pressure = asRecord(raw.pressure);
  const field = asRecord(raw.field);
  const helper = asRecord(raw.helper);
  const modes = asRecord(raw.modes);
  const checks = asRecord(raw.checks);
  const report = asRecord(raw.report);

  const airA = asNumber(air.a_micro_per_bar, base.air.a_micro_per_bar);
  const pressureA = asNumber(pressure.a_micro_per_bar, base.pressure.a_micro_per_bar);

  const next: AppInputs = {
    ...base,
    geometry: {
      outside_diameter_mm: asNumber(geometry.outside_diameter_mm, base.geometry.outside_diameter_mm),
      wall_thickness_mm: asNumber(geometry.wall_thickness_mm, base.geometry.wall_thickness_mm),
      length_m: asNumber(geometry.length_m, base.geometry.length_m),
    },
    geometry_catalog: {
      size_option: asString(catalog.size_option, base.geometry_catalog.size_option),
      schedule_option: asString(catalog.schedule_option, base.geometry_catalog.schedule_option),
    },
    segments: asSegments(raw.segments, base.segments),
    section_profile: {
      highest_elevation_m: asNumber(profile.highest_elevation_m, base.section_profile.highest_elevation_m),
      lowest_elevation_m: asNumber(profile.lowest_elevation_m, base.section_profile.lowest_elevation_m),
      start_elevation_m: asNumber(profile.start_elevation_m, base.section_profile.start_elevation_m),
      end_elevation_m: asNumber(profile.end_elevation_m, base.section_profile.end_elevation_m),
      design_pressure_bar: asNumber(profile.design_pressure_bar, base.section_profile.design_pressure_bar),
      smys_mpa: asNumber(profile.smys_mpa, base.section_profile.smys_mpa),
    },
    material_grade: asString(raw.material_grade, base.material_grade),
    location_class: asString(raw.location_class, base.location_class),
    pump_location: asString(raw.pump_location, base.pump_location),
    air: {
      temperature_c: asNumber(air.temperature_c, base.air.temperature_c),
      pressure_bar: asNumber(air.pressure_bar, base.air.pressure_bar),
      a_micro_per_bar: airA,
      pressure_rise_bar: asNumberRequired(air.pressure_rise_bar, base.air.pressure_rise_bar),
      k_factor: asNumberRequired(air.k_factor, base.air.k_factor),
      actual_added_water_m3: asNumber(air.actual_added_water_m3, base.air.actual_added_water_m3),
      ambient_temperature_c: asNumber(air.ambient_temperature_c, base.air.ambient_temperature_c),
    },
    pressure: {
      temperature_c: asNumber(pressure.temperature_c, base.pressure.temperature_c),
      pressure_bar: asNumber(pressure.pressure_bar, base.pressure.pressure_bar),
      a_micro_per_bar: pressureA,
      b_micro_per_c: asNumber(pressure.b_micro_per_c, base.pressure.b_micro_per_c),
      delta_t_c: asNumber(pressure.delta_t_c, base.pressure.delta_t_c),
      actual_pressure_change_bar: asNumber(
        pressure.actual_pressure_change_bar,
        base.pressure.actual_pressure_change_bar,
      ),
      t_initial_c: asNumber(pressure.t_initial_c, base.pressure.t_initial_c),
      t_final_c: asNumber(pressure.t_final_c, base.pressure.t_final_c),
      derive_delta_t: asBool(pressure.derive_delta_t, base.pressure.derive_delta_t),
    },
    field: {
      ambient_temperature_c: asNumber(field.ambient_temperature_c, base.field.ambient_temperature_c),
      pig_distance_m: asNumber(field.pig_distance_m, base.field.pig_distance_m),
      pig_travel_time_min: asNumber(field.pig_travel_time_min, base.field.pig_travel_time_min),
      pig_speed_m_per_s: asNumber(field.pig_speed_m_per_s, base.field.pig_speed_m_per_s),
      pig_speed_km_per_h: asNumber(field.pig_speed_km_per_h, base.field.pig_speed_km_per_h),
      monitored_pressure_bar: asNumber(field.monitored_pressure_bar, base.field.monitored_pressure_bar),
    },
    helper: {
      steel_alpha_micro_per_c: asNumberRequired(
        helper.steel_alpha_micro_per_c,
        base.helper.steel_alpha_micro_per_c,
      ),
      water_beta_micro_per_c: asNumber(helper.water_beta_micro_per_c, base.helper.water_beta_micro_per_c),
    },
    modes: {
      air_a_mode: asAMode(modes.air_a_mode, base.modes.air_a_mode),
      air_a_reference: asString(modes.air_a_reference, base.modes.air_a_reference),
      pressure_a_mode: asAMode(modes.pressure_a_mode, base.modes.pressure_a_mode),
      pressure_a_reference: asString(modes.pressure_a_reference, base.modes.pressure_a_reference),
      pressure_b_mode: asBMode(modes.pressure_b_mode, base.modes.pressure_b_mode),
      pressure_b_source: asBSource(modes.pressure_b_source, base.modes.pressure_b_source),
      pressure_b_reference: asString(modes.pressure_b_reference, base.modes.pressure_b_reference),
      steel_model: asSteelModel(modes.steel_model, base.modes.steel_model),
      k_preset: asString(modes.k_preset, base.modes.k_preset),
      steel_preset: asString(modes.steel_preset, base.modes.steel_preset),
      pig_mode: asString(modes.pig_mode, base.modes.pig_mode),
    },
    checks: {
      ...base.checks,
      ...(Object.keys(checks).reduce<Partial<Record<CheckKey, boolean>>>((acc, key) => {
        if (typeof checks[key] === "boolean") {
          acc[key as CheckKey] = checks[key] as boolean;
        }
        return acc;
      }, {})),
    },
    report: {
      report_no: asString(report.report_no, base.report.report_no),
      operator: asString(report.operator, base.report.operator),
      date: asString(report.date, base.report.date),
      section_id: asString(report.section_id, base.report.section_id),
    },
  };

  return next;
}

/** Yerel modeli API `inputs` gövdesine çevirir (modlar masaüstü etiketi taşımaz). */
export function toApiInputs(inputs: AppInputs): Record<string, unknown> {
  const { report: _report, ...rest } = inputs;
  return {
    ...rest,
    segments: inputs.segments.map((segment) => ({
      outside_diameter_mm: segment.outside_diameter_mm,
      wall_thickness_mm: segment.wall_thickness_mm,
      length_m: segment.length_m,
      nps_label: segment.nps_label || null,
      schedule_label: segment.schedule_label || null,
      start_station_m: segment.start_station_m ?? null,
    })),
  };
}
