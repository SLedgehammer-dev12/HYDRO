import * as THREE from "three";
import type {
  SceneData,
  SceneEquipment,
  SceneEquipmentType,
  ScenePoint,
  SceneSegment,
  SceneStatus,
} from "../../lib/scene";

/**
 * Scene-side layout model for the 3D field view.
 *
 * The component never computes engineering values: every number arrives in
 * `SceneData`. This module only decides how metres become scene units, how the
 * elevation profile is drawn and how equipment is stylised. Visual scale is
 * intentionally exaggerated (radius and vertical relief) so a 3 km line remains
 * readable on one screen.
 */

export const DISPLAY_SPAN = 26;
const GROUND_LIFT = 1.0;
const TERRAIN_DROP = 0.85;
const TERRAIN_HALF_WIDTH = 7;
const SUPPORT_COUNT = 9;
const Y_AXIS = new THREE.Vector3(0, 1, 0);
const Z_AXIS = new THREE.Vector3(0, 0, 1);

export type ColorMode = "pressure" | "utilization";
export type CameraPreset = "overview" | "profile" | "pig" | "equipment" | "top";

export interface ResolvedScene {
  data: SceneData;
  isDemo: boolean;
}

export const DEMO_SCENE: SceneData = {
  segments: [
    {
      id: "seg-1",
      label: "S1 · DN300",
      start_m: 0,
      end_m: 760,
      start_elevation_m: 412,
      end_elevation_m: 438,
      outside_diameter_mm: 323.9,
      wall_thickness_mm: 9.5,
      pressure_bar: 18,
      utilization: 0.22,
      status: "pass",
    },
    {
      id: "seg-2",
      label: "S2 · DN400",
      start_m: 760,
      end_m: 1680,
      start_elevation_m: 438,
      end_elevation_m: 409,
      outside_diameter_mm: 406.4,
      wall_thickness_mm: 10.3,
      pressure_bar: 26,
      utilization: 0.44,
      status: "pass",
    },
    {
      id: "seg-3",
      label: "S3 · DN450",
      start_m: 1680,
      end_m: 2540,
      start_elevation_m: 409,
      end_elevation_m: 463,
      outside_diameter_mm: 457,
      wall_thickness_mm: 12.7,
      pressure_bar: 34,
      utilization: 0.68,
      status: "warning",
    },
    {
      id: "seg-4",
      label: "S4 · DN350",
      start_m: 2540,
      end_m: 3280,
      start_elevation_m: 463,
      end_elevation_m: 452,
      outside_diameter_mm: 355.6,
      wall_thickness_mm: 9.1,
      pressure_bar: 39,
      utilization: 0.86,
      status: "warning",
    },
  ],
  equipment: [
    {
      id: "pump-1",
      type: "pump",
      label: "Pompa P-01",
      distance_m: 0,
      elevation_m: 412,
      status: "pass",
    },
    {
      id: "test-head-1",
      type: "test-head",
      label: "Test başlığı TH-01",
      distance_m: 90,
      elevation_m: 414,
      status: "warning",
    },
    {
      id: "launcher-1",
      type: "pig-launcher",
      label: "Pig gönderici",
      distance_m: 1400,
      elevation_m: 421,
      status: "pass",
    },
    {
      id: "valve-1",
      type: "valve",
      label: "Ana hat vanası V-01",
      distance_m: 760,
      elevation_m: 438,
      status: "pass",
    },
    {
      id: "gauge-1",
      type: "gauge",
      label: "Manometre PI-02",
      distance_m: 1680,
      elevation_m: 409,
      status: "pass",
    },
    {
      id: "valve-2",
      type: "valve",
      label: "Ana hat vanası V-02",
      distance_m: 2540,
      elevation_m: 463,
      status: "warning",
    },
    {
      id: "receiver-1",
      type: "pig-receiver",
      label: "Pig alıcı",
      distance_m: 3240,
      elevation_m: 452,
      status: "pass",
    },
  ],
  pig: {
    distance_m: 2050,
    progress: 0.63,
    speed_m_per_s: 0.42,
  },
  flow_speed_m_per_s: 1.15,
  pressure_min_bar: 8,
  pressure_max_bar: 42,
  profile_points: [
    [0, 410],
    [380, 424],
    [760, 434],
    [950, 432],
    [1350, 416],
    [1680, 406],
    [2000, 420],
    [2300, 437],
    [2540, 458],
    [2900, 459],
    [3280, 449],
  ],
  warnings: ["Demo sahne: kot ve ekipman konumları semboliktir."],
};

/** Empty or unusable payloads fall back to the demo field so the view is never blank. */
export function resolveSceneData(data: SceneData | null | undefined): ResolvedScene {
  const usable =
    data &&
    Array.isArray(data.segments) &&
    data.segments.some(
      (segment) =>
        Number.isFinite(segment.start_m) &&
        Number.isFinite(segment.end_m) &&
        Number.isFinite(segment.start_elevation_m) &&
        Number.isFinite(segment.end_elevation_m) &&
        Math.abs(segment.end_m - segment.start_m) > 0,
    );
  if (!usable) {
    return { data: DEMO_SCENE, isDemo: true };
  }
  return {
    data: {
      ...data,
      equipment: Array.isArray(data.equipment) ? data.equipment : [],
      warnings: Array.isArray(data.warnings) ? data.warnings : [],
    },
    isDemo: false,
  };
}

export interface LayoutSegment {
  segment: SceneSegment;
  index: number;
  start: THREE.Vector3;
  end: THREE.Vector3;
  mid: THREE.Vector3;
  direction: THREE.Vector3;
  /** Maps a Y-axis cylinder onto the pipe direction. */
  quaternion: THREE.Quaternion;
  /** Maps a Z-axis torus onto the pipe direction. */
  ringQuaternion: THREE.Quaternion;
  radius: number;
  innerRadius: number;
  distanceStart: number;
  distanceEnd: number;
}

export interface LayoutEquipment {
  equipment: SceneEquipment;
  pipePoint: THREE.Vector3;
  groundPoint: THREE.Vector3;
  side: number;
  radius: number;
}

export interface SupportPost {
  x: number;
  baseY: number;
  topY: number;
  z: number;
}

export interface TickMark {
  distance: number;
  position: THREE.Vector3;
  label: string;
}

export interface ProfileSample {
  distance: number;
  elevation: number;
  ridge: THREE.Vector3;
}

export interface TerrainMesh {
  geometry: THREE.BufferGeometry;
  ridgeLine: THREE.Vector3[];
  edgeLineLeft: THREE.Vector3[];
  edgeLineRight: THREE.Vector3[];
}

export interface CameraView {
  position: THREE.Vector3;
  target: THREE.Vector3;
}

export interface SceneRanges {
  pressure: { min: number; max: number };
  utilization: { min: number; max: number };
}

export interface SceneLayout {
  totalLengthM: number;
  span: number;
  center: THREE.Vector3;
  elevationRangeM: number;
  stationScale: number;
  verticalScale: number;
  ranges: SceneRanges;
  segments: LayoutSegment[];
  equipment: LayoutEquipment[];
  supports: SupportPost[];
  ticks: TickMark[];
  profile: ProfileSample[];
  terrain: TerrainMesh;
  views: Record<"overview" | "profile" | "top", CameraView>;
  stationToX: (distance: number) => number;
  elevationToY: (elevation: number) => number;
  segmentAt: (distance: number) => LayoutSegment;
  sample: (distance: number, target: THREE.Vector3) => THREE.Vector3;
  groundYAt: (distance: number) => number;
}

function finite(value: number | null | undefined, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function stationOf(segment: SceneSegment): [number, number] {
  return [Math.min(segment.start_m, segment.end_m), Math.max(segment.start_m, segment.end_m)];
}

function visualRadius(segment: SceneSegment): number {
  const od = finite(segment.outside_diameter_mm, 0);
  const base = od > 0 ? (od / 1000) * 0.75 : 0.22;
  return clamp(base, 0.16, 0.38);
}

function visualInnerRadius(segment: SceneSegment, radius: number): number {
  const od = finite(segment.outside_diameter_mm, 0);
  const wt = finite(segment.wall_thickness_mm, 0);
  const realRatio = od > 0 && wt > 0 ? (2 * wt) / od : 0.05;
  // Wall thickness is exaggerated so the cutaway reads as a wall, not a hairline.
  const visualRatio = clamp(realRatio * 4.5, 0.06, 0.3);
  return radius * (1 - visualRatio);
}

function profilePairs(data: SceneData, totalLengthM: number): ScenePoint[] {
  const points: ScenePoint[] = [];
  const raw = data.profile_points;
  if (Array.isArray(raw)) {
    for (const point of raw) {
      if (!point || point.length < 2) continue;
      const distance = finite(point[0], Number.NaN);
      const elevation = finite(point[1], Number.NaN);
      if (!Number.isFinite(distance) || !Number.isFinite(elevation)) continue;
      points.push([clamp(distance, 0, totalLengthM), elevation]);
    }
  }
  if (points.length === 0) {
    for (const segment of data.segments) {
      points.push([finite(segment.start_m, 0), finite(segment.start_elevation_m, 0)]);
    }
    const last = data.segments[data.segments.length - 1];
    if (last) {
      points.push([finite(last.end_m, totalLengthM), finite(last.end_elevation_m, 0)]);
    }
  }
  points.sort((a, b) => a[0] - b[0]);
  // Guarantee coverage across the whole line.
  if (points[0][0] > 0) points.unshift([0, points[0][1]]);
  if (points[points.length - 1][0] < totalLengthM) {
    points.push([totalLengthM, points[points.length - 1][1]]);
  }
  return points;
}

function elevationFromProfile(profile: ScenePoint[], distance: number): number {
  if (profile.length === 0) return 0;
  if (distance <= profile[0][0]) return profile[0][1];
  const last = profile[profile.length - 1];
  if (distance >= last[0]) return last[1];
  for (let index = 1; index < profile.length; index += 1) {
    const [d1, e1] = profile[index];
    const [d0, e0] = profile[index - 1];
    if (distance <= d1) {
      const t = d1 === d0 ? 0 : (distance - d0) / (d1 - d0);
      return e0 + (e1 - e0) * t;
    }
  }
  return last[1];
}

const RAMP_LOW = new THREE.Color("#0a2334");
const RAMP_MID = new THREE.Color("#14545c");
const RAMP_HIGH = new THREE.Color("#8a7434");
const RAMP_TEMP = new THREE.Color();

function rampColor(fraction: number, target: THREE.Color): THREE.Color {
  const t = clamp(fraction, 0, 1);
  if (t < 0.55) {
    return target.copy(RAMP_LOW).lerp(RAMP_MID, t / 0.55);
  }
  return target.copy(RAMP_MID).lerp(RAMP_HIGH, (t - 0.55) / 0.45);
}

function buildTerrain(
  layout: Omit<SceneLayout, "terrain">,
): TerrainMesh {
  const { totalLengthM, profile, stationToX, elevationToY } = layout;
  const samples = 72;
  const lanes = [-1, -0.62, -0.28, 0, 0.28, 0.62, 1];
  const positions: number[] = [];
  const colors: number[] = [];
  const indices: number[] = [];
  const ridgeLine: THREE.Vector3[] = [];
  const edgeLineLeft: THREE.Vector3[] = [];
  const edgeLineRight: THREE.Vector3[] = [];
  const temp = new THREE.Color();
  const pairs: ScenePoint[] = profile.map(
    (point) => [point.distance, point.elevation] as ScenePoint,
  );
  const minElevation = profile.length ? Math.min(...profile.map((point) => point.elevation)) : 0;
  const maxElevation = profile.length ? Math.max(...profile.map((point) => point.elevation)) : 1;
  const elevationRange = Math.max(1, maxElevation - minElevation);

  for (let s = 0; s <= samples; s += 1) {
    const distance = (s / samples) * totalLengthM;
    const elevation = elevationFromProfile(pairs, distance);
    // The ribbon always stays under the pipe, even when the survey says the
    // ground rises above it. The pipe remains the readable datum.
    let ridgeY = elevationToY(elevation) - 0.04;
    const pipeSample = layout.sample(distance, new THREE.Vector3());
    ridgeY = Math.min(ridgeY, pipeSample.y - TERRAIN_DROP);
    ridgeY = Math.max(ridgeY, 0.04);
    const elevationFraction = (elevation - minElevation) / elevationRange;

    for (let laneIndex = 0; laneIndex < lanes.length; laneIndex += 1) {
      const lane = lanes[laneIndex];
      const falloff = Math.pow(Math.abs(lane), 1.35);
      const y = ridgeY * (1 - falloff) + 0.02 * falloff;
      const x = stationToX(distance);
      const z = lane * TERRAIN_HALF_WIDTH;
      positions.push(x, y, z);

      rampColor(elevationFraction, temp);
      const contourBand = Math.floor(elevation / 6) % 2 === 0 ? 1 : 0.88;
      temp.multiplyScalar((0.55 + 0.45 * (1 - Math.abs(lane))) * contourBand);
      colors.push(temp.r, temp.g, temp.b);
    }

    const laneCount = lanes.length;
    const rowStart = s * laneCount;
    if (s < samples) {
      for (let laneIndex = 0; laneIndex < laneCount - 1; laneIndex += 1) {
        const a = rowStart + laneIndex;
        const b = a + laneCount;
        // Winding chosen so the surface normal points up.
        indices.push(a, a + 1, b, b, a + 1, b + 1);
      }
    }

    const centerX = stationToX(distance);
    ridgeLine.push(new THREE.Vector3(centerX, ridgeY + 0.015, 0));
    edgeLineLeft.push(
      new THREE.Vector3(centerX, ridgeY * 0.475 + 0.02, -TERRAIN_HALF_WIDTH * 0.62),
    );
    edgeLineRight.push(
      new THREE.Vector3(centerX, ridgeY * 0.475 + 0.02, TERRAIN_HALF_WIDTH * 0.62),
    );
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();

  return { geometry, ridgeLine, edgeLineLeft, edgeLineRight };
}

function buildViews(
  center: THREE.Vector3,
  span: number,
): SceneLayout["views"] {
  return {
    overview: {
      position: new THREE.Vector3(center.x + span * 0.09, center.y + span * 0.44, span * 0.92),
      target: center.clone().add(new THREE.Vector3(0, 0.15, 0)),
    },
    profile: {
      position: new THREE.Vector3(center.x, center.y + span * 0.04, span * 1.04),
      target: new THREE.Vector3(center.x, center.y, 0),
    },
    top: {
      position: new THREE.Vector3(center.x + 0.01, span * 1.08, span * 0.3),
      target: center.clone(),
    },
  };
}

export function buildSceneLayout(data: SceneData): SceneLayout {
  const cleanedSegments = data.segments.filter(
    (segment) => Number.isFinite(segment.start_m) && Number.isFinite(segment.end_m),
  );
  const lastEnd = cleanedSegments.reduce(
    (max, segment) => Math.max(max, finite(segment.start_m, 0), finite(segment.end_m, 0)),
    0,
  );
  const profileDistance = (data.profile_points ?? []).reduce(
    (max, point) => (point && Number.isFinite(point[0]) ? Math.max(max, point[0]) : max),
    0,
  );
  const totalLengthM = Math.max(10, lastEnd, profileDistance);
  const stationScale = DISPLAY_SPAN / totalLengthM;

  const elevationValues: number[] = [];
  for (const segment of cleanedSegments) {
    elevationValues.push(finite(segment.start_elevation_m));
    elevationValues.push(finite(segment.end_elevation_m));
  }
  for (const point of data.profile_points ?? []) {
    if (point && Number.isFinite(point[1])) elevationValues.push(point[1]);
  }
  for (const item of data.equipment ?? []) {
    if (Number.isFinite(item.elevation_m)) elevationValues.push(item.elevation_m);
  }
  if (data.pig && Number.isFinite(data.pig.elevation_m)) {
    elevationValues.push(data.pig.elevation_m as number);
  }
  const minElevationM = elevationValues.length ? Math.min(...elevationValues) : 0;
  const maxElevationM = elevationValues.length ? Math.max(...elevationValues) : 1;
  const elevationRangeM = Math.max(1, maxElevationM - minElevationM);
  const verticalScale =
    clamp(elevationRangeM * stationScale * 4.5, 1.2, 5.0) / elevationRangeM;

  const stationToX = (distance: number): number =>
    (distance - totalLengthM / 2) * stationScale;
  const elevationToY = (elevation: number): number =>
    GROUND_LIFT + (elevation - minElevationM) * verticalScale;

  const segments: LayoutSegment[] = cleanedSegments.map((segment, index) => {
    const [distanceStart, distanceEnd] = stationOf(segment);
    const start = new THREE.Vector3(
      stationToX(finite(segment.start_m, 0)),
      elevationToY(finite(segment.start_elevation_m, minElevationM)),
      0,
    );
    const end = new THREE.Vector3(
      stationToX(finite(segment.end_m, totalLengthM)),
      elevationToY(finite(segment.end_elevation_m, minElevationM)),
      0,
    );
    const direction = end.clone().sub(start);
    if (direction.lengthSq() < 1e-8) direction.set(1, 0, 0);
    direction.normalize();
    const radius = visualRadius(segment);
    return {
      segment,
      index,
      start,
      end,
      mid: start.clone().lerp(end, 0.5),
      direction,
      quaternion: new THREE.Quaternion().setFromUnitVectors(Y_AXIS, direction),
      ringQuaternion: new THREE.Quaternion().setFromUnitVectors(Z_AXIS, direction),
      radius,
      innerRadius: visualInnerRadius(segment, radius),
      distanceStart,
      distanceEnd,
    };
  });

  const fallbackSegment = segments[0];
  const segmentAt = (distance: number): LayoutSegment => {
    let best = fallbackSegment;
    let bestDistance = Number.POSITIVE_INFINITY;
    for (const segment of segments) {
      const low = Math.min(segment.distanceStart, segment.distanceEnd);
      const high = Math.max(segment.distanceStart, segment.distanceEnd);
      if (distance >= low && distance <= high) return segment;
      const delta = distance < low ? low - distance : distance - high;
      if (delta < bestDistance) {
        bestDistance = delta;
        best = segment;
      }
    }
    return best;
  };

  const sample = (distance: number, target: THREE.Vector3): THREE.Vector3 => {
    const segment = segmentAt(distance);
    const low = Math.min(segment.distanceStart, segment.distanceEnd);
    const high = Math.max(segment.distanceStart, segment.distanceEnd);
    const span = high - low;
    const t = span > 1e-6 ? clamp((distance - low) / span, 0, 1) : 0;
    return target.copy(segment.start).lerp(segment.end, t);
  };

  const profilePairsValue = profilePairs(data, totalLengthM);

  const groundYAt = (distance: number): number => {
    const pipe = sample(distance, new THREE.Vector3());
    const terrainElevation = elevationFromProfile(profilePairsValue, distance);
    const ridge = Math.min(elevationToY(terrainElevation) - 0.04, pipe.y - TERRAIN_DROP);
    return Math.max(0.04, ridge);
  };

  const profile: ProfileSample[] = [];
  const profileSamples = 64;
  for (let index = 0; index <= profileSamples; index += 1) {
    const distance = (index / profileSamples) * totalLengthM;
    const elevation = elevationFromProfile(profilePairsValue, distance);
    const pipe = sample(distance, new THREE.Vector3());
    profile.push({
      distance,
      elevation,
      ridge: new THREE.Vector3(
        stationToX(distance),
        Math.max(0.04, Math.min(elevationToY(elevation), pipe.y - TERRAIN_DROP)),
        0,
      ),
    });
  }

  const centerY =
    (elevationToY(minElevationM) + elevationToY(maxElevationM)) / 2 + 0.2;
  const center = new THREE.Vector3(0, centerY, 0);

  const equipment: LayoutEquipment[] = (data.equipment ?? []).map((item) => {
    const distance = clamp(finite(item.distance_m, 0), 0, totalLengthM);
    const pipePoint = sample(distance, new THREE.Vector3());
    const equipmentSide = equipmentSideFor(item);
    return {
      equipment: item,
      pipePoint,
      groundPoint: new THREE.Vector3(pipePoint.x, groundYAt(distance), equipmentSide * 1.15),
      side: equipmentSide,
      radius: segmentAt(distance).radius,
    };
  });

  const pressureValues = cleanedSegments
    .map((segment) => segment.pressure_bar)
    .filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  const pressureMin = Number.isFinite(data.pressure_min_bar)
    ? (data.pressure_min_bar as number)
    : pressureValues.length
      ? Math.min(...pressureValues)
      : 0;
  const pressureMax = Number.isFinite(data.pressure_max_bar)
    ? (data.pressure_max_bar as number)
    : pressureValues.length
      ? Math.max(...pressureValues)
      : 1;
  const ranges: SceneRanges = {
    pressure: {
      min: pressureMin,
      max: pressureMax > pressureMin ? pressureMax : pressureMin + 1,
    },
    utilization: { min: 0, max: 1 },
  };

  const supports: SupportPost[] = [];
  for (let index = 1; index <= SUPPORT_COUNT; index += 1) {
    const distance = (index / (SUPPORT_COUNT + 1)) * totalLengthM;
    const pipe = sample(distance, new THREE.Vector3());
    const segment = segmentAt(distance);
    const baseY = groundYAt(distance);
    const topY = pipe.y - segment.radius * 0.85;
    if (topY - baseY > 0.08) {
      supports.push({ x: pipe.x, baseY, topY, z: 0 });
    }
  }

  const ticks: TickMark[] = [];
  const niceSteps = [50, 100, 250, 500, 1000, 2000, 2500, 5000, 10000, 20000];
  const tickStep =
    niceSteps.find((step) => totalLengthM / step <= 6) ?? niceSteps[niceSteps.length - 1];
  const tickDistances: number[] = [];
  for (let distance = 0; distance <= totalLengthM + 1e-6; distance += tickStep) {
    tickDistances.push(Math.min(distance, totalLengthM));
  }
  if (tickDistances[tickDistances.length - 1] < totalLengthM) {
    tickDistances.push(totalLengthM);
  }
  for (const distance of tickDistances) {
    ticks.push({
      distance,
      position: new THREE.Vector3(
        stationToX(distance),
        0.03,
        TERRAIN_HALF_WIDTH * 0.82 + 1.1,
      ),
      label: formatDistance(distance),
    });
  }

  const partial: Omit<SceneLayout, "terrain"> = {
    totalLengthM,
    span: DISPLAY_SPAN,
    center,
    elevationRangeM,
    stationScale,
    verticalScale,
    ranges,
    segments,
    equipment,
    supports,
    ticks,
    profile,
    views: buildViews(center, DISPLAY_SPAN),
    stationToX,
    elevationToY,
    segmentAt,
    sample,
    groundYAt,
  };

  return { ...partial, terrain: buildTerrain(partial) };
}

function equipmentSideFor(item: SceneEquipment): number {
  switch (item.type) {
    case "pump":
      return 1;
    case "pig-launcher":
      return -1;
    case "pig-receiver":
      return -1;
    case "test-head":
    case "gauge":
      return 0.55;
    default:
      return 0;
  }
}

/** Panel background for the equipment status, not the pipe colour. */
export const STATUS_META: Record<
  SceneStatus,
  { label: string; color: string; dot: string }
> = {
  pass: { label: "Uygun", color: "#34d399", dot: "bg-emerald-400" },
  warning: { label: "Uyarı", color: "#f5b544", dot: "bg-amber-400" },
  fail: { label: "Kritik", color: "#fb7185", dot: "bg-rose-400" },
  pending: { label: "Bekliyor", color: "#8fa3bd", dot: "bg-mist-400" },
};

export function statusMeta(status: SceneStatus | undefined) {
  return STATUS_META[status ?? "pending"];
}

export const EQUIPMENT_LABEL: Record<SceneEquipmentType, string> = {
  valve: "Vana",
  pump: "Pompa",
  "test-head": "Test başlığı",
  "pig-launcher": "Pig gönderici",
  "pig-receiver": "Pig alıcı",
  gauge: "Manometre",
};

const UTILIZATION_STOPS: Array<[number, string]> = [
  [0, "#2dd4bf"],
  [0.35, "#34d399"],
  [0.62, "#a3e635"],
  [0.8, "#f5b544"],
  [0.92, "#fb923c"],
  [1, "#fb7185"],
];

const UNKNOWN_COLOR = new THREE.Color("#5b7189");

/** Green → amber → red. Unknown data stays neutral instead of pretending to be safe. */
export function colorForSegment(
  segment: SceneSegment,
  mode: ColorMode,
  ranges: SceneRanges,
): THREE.Color {
  if (mode === "utilization") {
    const utilization = segment.utilization;
    if (typeof utilization !== "number" || !Number.isFinite(utilization)) {
      return UNKNOWN_COLOR.clone();
    }
    return colorFromStops(utilization, UTILIZATION_STOPS);
  }
  const pressure = segment.pressure_bar;
  if (typeof pressure !== "number" || !Number.isFinite(pressure)) {
    return UNKNOWN_COLOR.clone();
  }
  const span = Math.max(1e-6, ranges.pressure.max - ranges.pressure.min);
  const fraction = clamp((pressure - ranges.pressure.min) / span, 0, 1);
  return colorFromStops(fraction, UTILIZATION_STOPS);
}

function colorFromStops(
  value: number,
  stops: Array<[number, string]>,
): THREE.Color {
  const t = clamp(value, 0, 1);
  for (let index = 1; index < stops.length; index += 1) {
    const [high, highColor] = stops[index];
    const [low, lowColor] = stops[index - 1];
    if (t <= high) {
      const local = high === low ? 0 : (t - low) / (high - low);
      return new THREE.Color(lowColor).lerp(new THREE.Color(highColor), local);
    }
  }
  return new THREE.Color(stops[stops.length - 1][1]);
}

export function legendGradient(): string {
  return `linear-gradient(90deg, ${UTILIZATION_STOPS.map(
    ([stop, color]) => `${color} ${Math.round(stop * 100)}%`,
  ).join(", ")})`;
}

/** Current pig distance: `progress` (0..1) wins when the server supplies it. */
export function pigStartDistance(data: SceneData, totalLengthM: number): number {
  const progress = data.pig?.progress;
  if (typeof progress === "number" && Number.isFinite(progress)) {
    return clamp(progress, 0, 1) * totalLengthM;
  }
  return clamp(finite(data.pig?.distance_m, 0), 0, totalLengthM);
}

export function formatDistance(metres: number): string {
  if (!Number.isFinite(metres)) return "—";
  if (Math.abs(metres) >= 1000) {
    return `${numberFormat1.format(metres / 1000)} km`;
  }
  return `${numberFormat0.format(metres)} m`;
}

export const numberFormat0 = new Intl.NumberFormat("tr-TR", {
  maximumFractionDigits: 0,
});

export const numberFormat1 = new Intl.NumberFormat("tr-TR", {
  maximumFractionDigits: 1,
  minimumFractionDigits: 0,
});

export const percentFormat = new Intl.NumberFormat("tr-TR", {
  style: "percent",
  maximumFractionDigits: 0,
});

export function formatPressure(value: number | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return `${numberFormat1.format(value)} bar`;
}

export function formatUtilization(value: number | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return percentFormat.format(value);
}

export function formatDiameter(segment: SceneSegment): string {
  return `OD ${numberFormat1.format(segment.outside_diameter_mm)} / WT ${numberFormat1.format(
    segment.wall_thickness_mm,
  )} mm`;
}

export function focusEquipmentFor(
  equipment: LayoutEquipment[],
  selectedId: string | null,
): LayoutEquipment | null {
  if (equipment.length === 0) return null;
  const selected = equipment.find((item) => item.equipment.id === selectedId);
  if (selected) return selected;
  return (
    equipment.find((item) => item.equipment.type === "valve") ??
    equipment.find((item) => item.equipment.type === "pump") ??
    equipment[0]
  );
}
