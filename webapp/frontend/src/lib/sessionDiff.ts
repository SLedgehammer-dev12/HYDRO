import { ApiError } from "./api";
import { CHECK_DEFINITIONS, STEEL_MODEL_OPTIONS } from "./constants";
import { num } from "./format";
import { normalizeInputs } from "./normalize";
import type {
  AppInputs,
  EquipmentInputItem,
  ProfilePointItem,
  SectionLandmarkItem,
  SegmentRow,
  Session,
  SessionStatus,
  TestType,
} from "./types";

export type ConflictSourceAction = "save_session" | "snapshot_upload" | "save_result";

export interface ServerConflictDiffEntry {
  path: string;
  incoming: unknown;
  server: unknown;
}

export interface SessionDiffItem {
  path: string;
  group: string;
  label: string;
  localValue: unknown;
  serverValue: unknown;
  localDisplay: string;
  serverDisplay: string;
}

export interface RevisionConflictState {
  sessionId: string;
  localRevision: number;
  localName: string;
  localStatus: SessionStatus;
  localInputs: AppInputs;
  serverSession: Session;
  serverDiff: ServerConflictDiffEntry[];
  sourceAction: ConflictSourceAction;
  detectedAt: string;
  refreshWarning?: string;
  pendingSnapshot?: {
    snapshot: Record<string, unknown>;
    mode: "merge" | "replace";
  };
  pendingResult?: {
    testType: TestType;
    payload: Record<string, unknown>;
  };
}

export interface ExtractedRevisionConflict {
  serverSession: Session;
  expectedRevision: number | null;
  currentRevision: number;
  serverDiff: ServerConflictDiffEntry[];
}

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function extractRevisionConflict(error: unknown): ExtractedRevisionConflict | null {
  if (!(error instanceof ApiError)) return null;
  if (error.status !== 409 || error.code !== "revision_conflict") return null;

  const rawCurrent = error.details.current;
  if (!isPlainRecord(rawCurrent)) return null;
  if (typeof rawCurrent.id !== "string" || typeof rawCurrent.revision !== "number" || !Number.isFinite(rawCurrent.revision)) {
    return null;
  }

  const expectedRaw = error.details.expected_revision;
  const expectedRevision =
    typeof expectedRaw === "number" && Number.isFinite(expectedRaw) ? expectedRaw : null;

  const serverDiff: ServerConflictDiffEntry[] = [];
  if (Array.isArray(error.details.diff)) {
    for (const item of error.details.diff) {
      if (isPlainRecord(item) && typeof item.path === "string" && item.path.trim().length > 0) {
        serverDiff.push({
          path: item.path,
          incoming: item.incoming,
          server: item.server,
        });
      }
    }
  }

  return {
    serverSession: rawCurrent as unknown as Session,
    expectedRevision,
    currentRevision: rawCurrent.revision,
    serverDiff,
  };
}

const SECTION_GROUP_LABELS: Record<string, string> = {
  top: "Oturum",
  section_meta: "Kesit Kimliği",
  geometry: "Boru Geometrisi",
  geometry_catalog: "Boru Kataloğu",
  section_profile: "Kesit Profili & Tasarım",
  air: "Hava İçerik Testi",
  pressure: "Basınç Değişim Testi",
  field: "Saha & Pig",
  helper: "Malzeme Katsayıları",
  modes: "Hesaplama Modları",
  checks: "Saha Kontrol Listesi",
  report: "Rapor Kimliği",
};

const FIELD_LABELS: Record<string, string> = {
  name: "Test Bölümü adı",
  status: "Durum",
  project_id: "Bağlı proje",
  notes: "Oturum notları",
  active_tab: "Aktif sekme",
  water_backend: "Su özelliği backend'i",
  material_grade: "Boru kalitesi",
  location_class: "Lokasyon sınıfı",
  pump_location: "Pompa konumu",
  segments: "Boru segmentleri",
  profile_points: "Kot profili noktaları",
  landmarks: "Özel geçiş & tesisler",
  equipment: "Saha ekipmanları",

  "section_meta.section_no": "Kesit no",
  "section_meta.description": "Açıklama",
  "section_meta.location": "Konum / KP aralığı",
  "section_meta.start_kp": "Başlangıç KP",
  "section_meta.end_kp": "Bitiş KP",
  "section_meta.test_date": "Test tarihi",
  "section_meta.test_type": "Test türü",
  "section_meta.notes": "Kesit notları",

  "geometry.outside_diameter_mm": "Dış çap D (mm)",
  "geometry.wall_thickness_mm": "Et kalınlığı t (mm)",
  "geometry.length_m": "Hat uzunluğu L (m)",

  "geometry_catalog.size_option": "Katalog çap seçimi",
  "geometry_catalog.schedule_option": "Et kalınlığı (Schedule)",

  "section_profile.highest_elevation_m": "En yüksek kot (m)",
  "section_profile.lowest_elevation_m": "En düşük kot (m)",
  "section_profile.start_elevation_m": "Başlangıç kotu (m)",
  "section_profile.end_elevation_m": "Bitiş kotu (m)",
  "section_profile.design_pressure_bar": "Tasarım basıncı DP (bar)",
  "section_profile.smys_mpa": "SMYS (MPa)",

  "air.temperature_c": "Hava testi su sıcaklığı (°C)",
  "air.pressure_bar": "Hava testi basıncı (bar)",
  "air.a_micro_per_bar": "A katsayısı (hava testi)",
  "air.pressure_rise_bar": "Basınç artışı ΔP (bar)",
  "air.k_factor": "K faktörü",
  "air.actual_added_water_m3": "Fiili ilave su Vpa (m³)",
  "air.ambient_temperature_c": "Ortam sıcaklığı (°C)",

  "pressure.temperature_c": "Basınç testi su sıcaklığı (°C)",
  "pressure.pressure_bar": "Basınç testi basıncı (bar)",
  "pressure.a_micro_per_bar": "A katsayısı (basınç testi)",
  "pressure.b_micro_per_c": "B katsayısı (10⁻⁶/°C)",
  "pressure.delta_t_c": "Sıcaklık farkı ΔT (°C)",
  "pressure.actual_pressure_change_bar": "Fiili basınç farkı Pa (bar)",
  "pressure.t_initial_c": "Başlangıç sıcaklığı Tilk (°C)",
  "pressure.t_final_c": "Bitiş sıcaklığı Tson (°C)",
  "pressure.derive_delta_t": "ΔT türetilsin (Tson − Tilk)",

  "field.ambient_temperature_c": "Ortam sıcaklığı (°C)",
  "field.pig_distance_m": "Pig mesafesi (m)",
  "field.pig_travel_time_min": "Pig süresi (dk)",
  "field.pig_speed_m_per_s": "Pig hızı (m/s)",
  "field.pig_speed_km_per_h": "Pig hızı (km/sa)",
  "field.monitored_pressure_bar": "İzlenen basınç (bar)",

  "helper.steel_alpha_micro_per_c": "Çelik α (10⁻⁶/°C)",
  "helper.water_beta_micro_per_c": "Su β (10⁻⁶/°C)",

  "modes.air_a_mode": "Hava A modu",
  "modes.air_a_reference": "Hava A referans seçimi",
  "modes.pressure_a_mode": "Basınç A modu",
  "modes.pressure_a_reference": "Basınç A referans seçimi",
  "modes.pressure_b_mode": "Basınç B modu",
  "modes.pressure_b_source": "Basınç B kaynağı",
  "modes.pressure_b_reference": "Basınç B referans seçimi",
  "modes.steel_model": "Çelik genleşme modeli",
  "modes.k_preset": "K faktörü ön ayarı",
  "modes.steel_preset": "Çelik α ön ayarı",
  "modes.pig_mode": "Pig modu",

  "report.report_no": "Rapor no",
  "report.operator": "Operatör",
  "report.date": "Rapor tarihi",
  "report.section_id": "Rapor bölüm no",
};

const CHECK_LABELS: Record<string, string> = CHECK_DEFINITIONS.reduce<Record<string, string>>(
  (acc, item) => {
    acc[`checks.${item.key}`] = `${item.label} (Madde ${item.ref})`;
    return acc;
  },
  {},
);

const STATUS_LABELS: Record<string, string> = {
  draft: "Taslak",
  active: "Aktif",
  completed: "Tamamlandı",
  archived: "Arşiv",
};

const MODE_VALUE_LABELS: Record<string, string> = {
  auto: "Otomatik",
  table: "Tablo",
  manual: "Manuel",
  institutional: "Kurum içi tablo",
  gail: "GAIL tablosu",
};

const STEEL_LABELS: Record<string, string> = STEEL_MODEL_OPTIONS.reduce<Record<string, string>>(
  (acc, item) => {
    acc[item.value] = item.label;
    return acc;
  },
  {},
);

function describePath(path: string): { group: string; label: string } {
  const dot = path.indexOf(".");
  const section = dot >= 0 ? path.slice(0, dot) : "top";
  const group = SECTION_GROUP_LABELS[section] ?? "Diğer";
  const label = FIELD_LABELS[path] ?? CHECK_LABELS[path] ?? path;
  return { group, label };
}

function formatArraySummary(path: string, items: unknown[]): string {
  if (items.length === 0) return "0 kayıt";
  if (path === "segments") {
    let totalLength = 0;
    for (const raw of items) {
      if (isPlainRecord(raw) && typeof raw.length_m === "number" && Number.isFinite(raw.length_m)) {
        totalLength += raw.length_m;
      }
    }
    return totalLength > 0
      ? `${items.length} segment (Σ ${num(totalLength, 0)} m)`
      : `${items.length} segment`;
  }
  if (path === "profile_points") return `${items.length} kot noktası`;
  if (path === "equipment") return `${items.length} ekipman`;
  if (path === "landmarks") return `${items.length} tesis / geçiş`;
  return `${items.length} kayıt`;
}

export function formatDiffValue(path: string, value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "Evet" : "Hayır";
  if (typeof value === "number") {
    return Number.isFinite(value) ? num(value, 6) : "—";
  }
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed) return "—";
    if (path === "status") return STATUS_LABELS[trimmed] ?? trimmed;
    if (path === "modes.steel_model") return STEEL_LABELS[trimmed] ?? trimmed;
    if (
      path === "modes.air_a_mode" ||
      path === "modes.pressure_a_mode" ||
      path === "modes.pressure_b_mode" ||
      path === "modes.pressure_b_source"
    ) {
      return MODE_VALUE_LABELS[trimmed] ?? trimmed;
    }
    return value;
  }
  if (Array.isArray(value)) {
    return formatArraySummary(path, value);
  }
  return JSON.stringify(value);
}

function stripSegmentIds(items: unknown[]): unknown[] {
  return items.map((item) => {
    if (!isPlainRecord(item)) return item;
    const copy = { ...item };
    delete copy.id;
    return copy;
  });
}

export function valuesEqual(a: unknown, b: unknown): boolean {
  if (typeof a === "boolean" || typeof b === "boolean") {
    return typeof a === typeof b && a === b;
  }
  if (typeof a === "number" && typeof b === "number") {
    return Number.isFinite(a) && Number.isFinite(b) && a === b;
  }
  if (Array.isArray(a) && Array.isArray(b)) {
    if (a.length !== b.length) return false;
    return a.every((item, idx) => valuesEqual(item, b[idx]));
  }
  if (isPlainRecord(a) && isPlainRecord(b)) {
    const keysA = Object.keys(a);
    const keysB = Object.keys(b);
    if (keysA.length !== keysB.length) return false;
    return keysA.every((key) => key in b && valuesEqual(a[key], b[key]));
  }
  return a === b;
}

const SCALAR_TOP_KEYS = [
  "water_backend",
  "material_grade",
  "location_class",
  "pump_location",
] as const;

const OBJECT_SECTIONS = [
  "section_meta",
  "geometry",
  "geometry_catalog",
  "section_profile",
  "air",
  "pressure",
  "field",
  "helper",
  "modes",
  "checks",
  "report",
] as const;

const LIST_SECTIONS = ["segments", "profile_points", "landmarks", "equipment"] as const;

function makeDiffItem(path: string, localValue: unknown, serverValue: unknown): SessionDiffItem {
  const { group, label } = describePath(path);
  return {
    path,
    group,
    label,
    localValue,
    serverValue,
    localDisplay: formatDiffValue(path, localValue),
    serverDisplay: formatDiffValue(path, serverValue),
  };
}

export function computeSessionDiff(
  local: { name: string; status: SessionStatus; inputs: AppInputs },
  serverSession: Session,
): SessionDiffItem[] {
  const diff: SessionDiffItem[] = [];
  const serverInputs = normalizeInputs(serverSession.inputs);

  const normalizedLocalName = local.name.trim() || serverSession.name;
  if (normalizedLocalName !== serverSession.name) {
    diff.push(makeDiffItem("name", normalizedLocalName, serverSession.name));
  }
  if (local.status !== serverSession.status) {
    diff.push(makeDiffItem("status", local.status, serverSession.status));
  }

  for (const key of SCALAR_TOP_KEYS) {
    if (!valuesEqual(local.inputs[key], serverInputs[key])) {
      diff.push(makeDiffItem(key, local.inputs[key], serverInputs[key]));
    }
  }

  for (const section of OBJECT_SECTIONS) {
    const localObj = local.inputs[section] as unknown as Record<string, unknown>;
    const serverObj = serverInputs[section] as unknown as Record<string, unknown>;
    const keys = Array.from(new Set([...Object.keys(serverObj), ...Object.keys(localObj)]));
    for (const key of keys) {
      if (section === "air" && key === "ambient_temperature_c") continue;
      if (!valuesEqual(localObj[key], serverObj[key])) {
        diff.push(makeDiffItem(`${section}.${key}`, localObj[key], serverObj[key]));
      }
    }
  }

  for (const section of LIST_SECTIONS) {
    const localArr = local.inputs[section];
    const serverArr = serverInputs[section];
    const cmpLocal = section === "segments" ? stripSegmentIds(localArr) : localArr;
    const cmpServer = section === "segments" ? stripSegmentIds(serverArr) : serverArr;
    if (!valuesEqual(cmpLocal, cmpServer)) {
      diff.push(makeDiffItem(section, localArr, serverArr));
    }
  }

  return diff;
}

export function buildDiffFromServerEntries(entries: ServerConflictDiffEntry[]): SessionDiffItem[] {
  return entries.map((entry) => makeDiffItem(entry.path, entry.incoming, entry.server));
}

function cloneInputs(inputs: AppInputs): AppInputs {
  return normalizeInputs(JSON.parse(JSON.stringify(inputs)) as AppInputs);
}

export function applyDiffResolutions(
  local: { name: string; status: SessionStatus; inputs: AppInputs },
  serverSession: Session,
  choices: Record<string, "local" | "server">,
): { name: string; status: SessionStatus; inputs: AppInputs } {
  let nextName = serverSession.name;
  let nextStatus: SessionStatus = serverSession.status;
  const nextInputs = cloneInputs(normalizeInputs(serverSession.inputs));
  const localNormalized = cloneInputs(local.inputs);

  for (const [path, choice] of Object.entries(choices)) {
    if (choice !== "local") continue;

    if (path === "name") {
      nextName = local.name.trim() || serverSession.name;
      continue;
    }
    if (path === "status") {
      nextStatus = local.status;
      continue;
    }
    if (
      path === "water_backend" ||
      path === "material_grade" ||
      path === "location_class" ||
      path === "pump_location"
    ) {
      nextInputs[path] = localNormalized[path];
      continue;
    }
    if (path === "segments") {
      nextInputs.segments = localNormalized.segments.map((item): SegmentRow => ({ ...item }));
      continue;
    }
    if (path === "profile_points") {
      nextInputs.profile_points = localNormalized.profile_points.map(
        (item): ProfilePointItem => ({ ...item }),
      );
      continue;
    }
    if (path === "landmarks") {
      nextInputs.landmarks = localNormalized.landmarks.map(
        (item): SectionLandmarkItem => ({ ...item }),
      );
      continue;
    }
    if (path === "equipment") {
      nextInputs.equipment = localNormalized.equipment.map(
        (item): EquipmentInputItem => ({ ...item }),
      );
      continue;
    }

    const dot = path.indexOf(".");
    if (dot > 0) {
      const section = path.slice(0, dot);
      const key = path.slice(dot + 1);
      if ((OBJECT_SECTIONS as readonly string[]).includes(section)) {
        const targetSection = nextInputs[section as (typeof OBJECT_SECTIONS)[number]] as unknown as Record<string, unknown>;
        const sourceSection = localNormalized[section as (typeof OBJECT_SECTIONS)[number]] as unknown as Record<string, unknown>;
        targetSection[key] = sourceSection[key];
      }
    }
  }

  // Keep canonical ambient temperature mirrored across field and air sections
  nextInputs.air.ambient_temperature_c = nextInputs.field.ambient_temperature_c;

  return {
    name: nextName,
    status: nextStatus,
    inputs: nextInputs,
  };
}
