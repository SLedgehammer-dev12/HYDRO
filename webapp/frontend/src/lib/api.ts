/**
 * HYDRO API istemcisi.
 *
 * - Taban yol `/api` (Vite proxy → 127.0.0.1:8080).
 * - Workspace anahtarı `X-Session-ID` başlığında localStorage'dan gönderilir.
 * - Hata zarfı (`code`, `message`, `details`, `request_id`) `ApiError`'a çevrilir.
 * - AbortSignal ve zaman aşımı desteklenir.
 */

import type {
  AirContentRequest,
  AirContentResponse,
  BackendComparisonResponse,
  BComparisonResponse,
  BSourceResult,
  CoefficientARequest,
  CoefficientAResponse,
  CoefficientBRequest,
  CoefficientCompareRequest,
  ExportResult,
  GeometryIn,
  GeometryResponse,
  GradeOption,
  HealthResponse,
  ListResponse,
  MetaResponse,
  OcrStatusResponse,
  PigSpeedRequest,
  PigSpeedResponse,
  PipeOption,
  PlanProfileCommitRequest,
  PlanProfileCommitResponse,
  PressureProfileRequest,
  PressureProfileResponse,
  PressureVariationRequest,
  PressureVariationResponse,
  PressurizationResponse,
  Project,
  ProjectInput,
  ReferenceCompareResponse,
  ReferenceTableMeta,
  ScheduleOption,
  SectionFormScanResponse,
  SectionFormUpdatePayload,
  SectionFormUpdateResponse,
  Session,
  SessionFormsResponse,
  SessionListItem,
  SessionUpdateResponse,
  SnapshotMapping,
  SpecResponse,
  TablePointResponse,
  TestResultRecord,
  TestType,
  UpdateManagerStatus,
} from "./types";

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "/api";
const WORKSPACE_KEY = "hydro.workspace-id";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;
  readonly requestId: string;

  constructor(
    status: number,
    code: string,
    message: string,
    details: Record<string, unknown> = {},
    requestId = "",
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }
}

export interface ServerConflictDiffEntry {
  path: string;
  incoming: unknown;
  server: unknown;
}

export interface ExtractedRevisionConflict {
  serverSession: Session;
  expectedRevision: number | null;
  currentRevision: number;
  serverDiff: ServerConflictDiffEntry[];
}

export function extractRevisionConflict(error: unknown): ExtractedRevisionConflict | null {
  if (!(error instanceof ApiError)) return null;
  if (error.status !== 409 || error.code !== "revision_conflict") return null;

  const rawCurrent = error.details.current;
  if (typeof rawCurrent !== "object" || rawCurrent === null || Array.isArray(rawCurrent)) {
    return null;
  }
  const currentRecord = rawCurrent as Record<string, unknown>;
  if (
    typeof currentRecord.id !== "string" ||
    typeof currentRecord.revision !== "number" ||
    !Number.isFinite(currentRecord.revision)
  ) {
    return null;
  }

  const expectedRaw = error.details.expected_revision;
  const expectedRevision =
    typeof expectedRaw === "number" && Number.isFinite(expectedRaw) ? expectedRaw : null;

  const serverDiff: ServerConflictDiffEntry[] = [];
  if (Array.isArray(error.details.diff)) {
    for (const item of error.details.diff) {
      if (
        typeof item === "object" &&
        item !== null &&
        !Array.isArray(item) &&
        typeof (item as Record<string, unknown>).path === "string" &&
        ((item as Record<string, unknown>).path as string).trim().length > 0
      ) {
        const entry = item as Record<string, unknown>;
        serverDiff.push({
          path: entry.path as string,
          incoming: entry.incoming,
          server: entry.server,
        });
      }
    }
  }

  return {
    serverSession: rawCurrent as unknown as Session,
    expectedRevision,
    currentRevision: currentRecord.revision,
    serverDiff,
  };
}

function uuid(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `ws-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export function setWorkspaceId(workspaceKey: string): string {
  const clean = workspaceKey.trim();
  if (!clean) return getWorkspaceId();
  try {
    localStorage.setItem(WORKSPACE_KEY, clean);
  } catch {
    /* depolama kapalı olabilir */
  }
  return clean;
}

export function getWorkspaceId(): string {
  try {
    const existing = localStorage.getItem(WORKSPACE_KEY);
    if (existing) return existing;
    const created = uuid();
    localStorage.setItem(WORKSPACE_KEY, created);
    return created;
  } catch {
    return uuid();
  }
}

const ADMIN_TOKEN_KEY = "hydro.admin_token";

export function getAdminToken(): string {
  try {
    return (sessionStorage.getItem(ADMIN_TOKEN_KEY) ?? "").trim();
  } catch {
    return "";
  }
}

export function setAdminToken(token: string): string {
  const clean = token.trim();
  try {
    if (clean) sessionStorage.setItem(ADMIN_TOKEN_KEY, clean);
    else sessionStorage.removeItem(ADMIN_TOKEN_KEY);
  } catch {
    /* sessionStorage kapalı olabilir */
  }
  return clean;
}

function adminHeadersFor(path: string): Record<string, string> {
  if (!path.startsWith("/system/") && !path.startsWith("/update/")) return {};
  const tok = getAdminToken();
  return tok ? { "X-Hydro-Admin-Token": tok } : {};
}

export interface ApiFetchOptions {
  method?: string;
  body?: unknown;
  signal?: AbortSignal;
  headers?: Record<string, string>;
  ifMatch?: string | number;
  timeoutMs?: number;
}

function isFormData(value: unknown): value is FormData {
  return typeof FormData !== "undefined" && value instanceof FormData;
}

async function parseError(response: Response): Promise<ApiError> {
  let body: Record<string, unknown> | null = null;
  try {
    body = (await response.json()) as Record<string, unknown>;
  } catch {
    body = null;
  }
  const code = typeof body?.code === "string" ? body.code : `http_${response.status}`;
  const message =
    typeof body?.message === "string" && body.message.trim().length > 0
      ? body.message
      : response.status === 404
        ? "İstenen kaynak sunucuda bulunamadı."
        : response.status === 500
          ? "Sunucu iç hatası oluştu. Backend hazır olmayabilir."
          : `Sunucu isteği başarısız oldu (${response.status}).`;
  const details =
    body?.details && typeof body.details === "object" && !Array.isArray(body.details)
      ? (body.details as Record<string, unknown>)
      : {};
  const requestId = typeof body?.request_id === "string" ? body.request_id : "";
  return new ApiError(response.status, code, message, details, requestId);
}

export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const {
    method = "GET",
    body,
    signal,
    headers = {},
    ifMatch,
    timeoutMs = 20_000,
  } = options;

  const controller = new AbortController();
  const onAbort = () => controller.abort();
  if (signal) {
    if (signal.aborted) controller.abort();
    else signal.addEventListener("abort", onAbort, { once: true });
  }
  const timer = timeoutMs > 0 ? setTimeout(() => controller.abort(), timeoutMs) : null;

  const requestHeaders: Record<string, string> = {
    Accept: "application/json",
    "X-Session-ID": getWorkspaceId(),
    ...adminHeadersFor(path),
    ...headers,
  };

  let payload: BodyInit | undefined;
  if (body !== undefined && body !== null) {
    if (isFormData(body)) {
      payload = body;
    } else {
      requestHeaders["Content-Type"] = "application/json";
      payload = JSON.stringify(body);
    }
  }
  if (ifMatch !== undefined) {
    requestHeaders["If-Match"] = `"${ifMatch}"`;
  }

  try {
    const response = await fetch(`${API_BASE}${path}`, {
      method,
      headers: requestHeaders,
      body: payload,
      signal: controller.signal,
    });

    const workspace = response.headers.get("X-Session-ID");
    if (workspace) {
      try {
        localStorage.setItem(WORKSPACE_KEY, workspace);
      } catch {
        /* depolama kapalı olabilir */
      }
    }

    if (!response.ok) {
      throw await parseError(response);
    }

    if (response.status === 204) return undefined as T;
    const contentType = response.headers.get("Content-Type") ?? "";
    if (!contentType.includes("application/json")) {
      return (await response.text()) as unknown as T;
    }
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError(0, "aborted", "İstek iptal edildi veya zaman aşımına uğradı.");
    }
    throw new ApiError(
      0,
      "network_error",
      "Sunucuya ulaşılamadı. Bağlantı sağlanana kadar yerel hesaplama kullanılıyor.",
    );
  } finally {
    if (timer) clearTimeout(timer);
    if (signal) signal.removeEventListener("abort", onAbort);
  }
}

function parseFilename(disposition: string | null, fallback: string): string {
  if (!disposition) return fallback;
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
  if (encoded?.[1]) {
    try {
      return decodeURIComponent(encoded[1]);
    } catch {
      return fallback;
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(disposition);
  return plain?.[1] ?? fallback;
}

export async function apiDownload(
  path: string,
  options: ApiFetchOptions & { fallbackFilename: string },
): Promise<ExportResult> {
  const { fallbackFilename, ...rest } = options;
  const controller = new AbortController();
  const timer = rest.timeoutMs === 0 ? null : setTimeout(() => controller.abort(), rest.timeoutMs ?? 60_000);
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      method: rest.method ?? "GET",
      headers: {
        Accept: "*/*",
        "X-Session-ID": getWorkspaceId(),
        ...adminHeadersFor(path),
        ...(rest.body ? { "Content-Type": "application/json" } : {}),
        ...rest.headers,
      },
      body: rest.body ? JSON.stringify(rest.body) : undefined,
      signal: rest.signal ?? controller.signal,
    });
    if (!response.ok) throw await parseError(response);
    return {
      blob: await response.blob(),
      filename: parseFilename(response.headers.get("Content-Disposition"), fallbackFilename),
    };
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError(0, "network_error", "Dosya indirilemedi; sunucuya ulaşılamadı.");
  } finally {
    if (timer) clearTimeout(timer);
  }
}

export function isRecoverableError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 0 && error.code !== "aborted";
}

export function apiErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.requestId ? `${error.message} (request_id: ${error.requestId})` : error.message;
  }
  if (error instanceof Error) return error.message;
  return "Beklenmeyen bir hata oluştu.";
}

export const api = {
  health: (signal?: AbortSignal) =>
    apiFetch<HealthResponse>("/health", { signal, timeoutMs: 4_000 }),

  meta: (signal?: AbortSignal) => apiFetch<MetaResponse>("/meta", { signal }),

  spec: (signal?: AbortSignal) => apiFetch<SpecResponse>("/meta/spec", { signal }),

  pipes: (query?: string, signal?: AbortSignal) => {
    const params = new URLSearchParams({ limit: "200" });
    if (query) params.set("q", query);
    return apiFetch<ListResponse<PipeOption>>(`/catalog/pipes?${params.toString()}`, { signal });
  },

  pipeSchedules: (nps: string, signal?: AbortSignal) =>
    apiFetch<{ nps: string; dn: string; outside_diameter_mm: number; items: ScheduleOption[] }>(
      `/catalog/pipes/${encodeURIComponent(nps)}/schedules`,
      { signal },
    ),

  grades: (signal?: AbortSignal) =>
    apiFetch<ListResponse<GradeOption>>("/catalog/grades?limit=50", { signal }),

  referenceTables: (signal?: AbortSignal) =>
    apiFetch<ListResponse<ReferenceTableMeta>>("/catalog/reference-tables", { signal }),

  coefficientA: (body: CoefficientARequest, signal?: AbortSignal) =>
    apiFetch<CoefficientAResponse>("/coefficients/a", { method: "POST", body, signal }),

  coefficientB: (body: CoefficientBRequest, signal?: AbortSignal) =>
    apiFetch<BSourceResult>("/coefficients/b", { method: "POST", body, signal }),

  compareB: (body: CoefficientCompareRequest, signal?: AbortSignal) =>
    apiFetch<BComparisonResponse>("/coefficients/compare", { method: "POST", body, signal }),

  tablePoint: (
    body: { table: "institutional" | "gail"; temperature_c: number; pressure_bar: number; repair_anomalies?: boolean },
    signal?: AbortSignal,
  ) => apiFetch<TablePointResponse>("/coefficients/table", { method: "POST", body, signal }),

  referenceCompare: (
    body: { temperature_c: number; pressure_bar: number; repair_anomalies?: boolean },
    signal?: AbortSignal,
  ) => apiFetch<ReferenceCompareResponse>("/coefficients/reference-compare", { method: "POST", body, signal }),

  backendComparison: (
    body: { temperature_c: number; pressure_bar: number; include_dev_backends?: boolean },
    signal?: AbortSignal,
  ) =>
    apiFetch<BackendComparisonResponse>("/coefficients/backend-comparison", {
      method: "POST",
      body,
      signal,
    }),

  geometry: (body: GeometryIn, signal?: AbortSignal) =>
    apiFetch<GeometryResponse>("/calculations/geometry", { method: "POST", body, signal }),

  airContent: (body: AirContentRequest, signal?: AbortSignal) =>
    apiFetch<AirContentResponse>("/calculations/air-content", { method: "POST", body, signal }),

  pressureVariation: (body: PressureVariationRequest, signal?: AbortSignal) =>
    apiFetch<PressureVariationResponse>("/calculations/pressure-variation", {
      method: "POST",
      body,
      signal,
    }),

  pressureProfile: (body: PressureProfileRequest, signal?: AbortSignal) =>
    apiFetch<PressureProfileResponse>("/calculations/pressure-profile", {
      method: "POST",
      body,
      signal,
    }),

  pigSpeed: (body: PigSpeedRequest, signal?: AbortSignal) =>
    apiFetch<PigSpeedResponse>("/calculations/pig-speed", { method: "POST", body, signal }),

  pressurization: (
    body: {
      initial_volume_m3: number;
      added_volume_m3: number;
      theoretical_volume_m3: number;
      pressure_bar: number;
      expected_pressure_bar: number;
    },
    signal?: AbortSignal,
  ) => apiFetch<PressurizationResponse>("/calculations/pressurization", { method: "POST", body, signal }),

  pressurizationRamp: (
    body: {
      readings: Array<{
        elapsed_min: number;
        pressure_bar: number;
        cumulative_added_volume_m3: number;
      }>;
      test_pressure_100_smys_bar: number;
      total_filled_volume_m3: number;
    },
    signal?: AbortSignal,
  ) =>
    apiFetch<import("./types").PressurizationRampResponse>("/calculations/pressurization-ramp", {
      method: "POST",
      body,
      signal,
    }),

  pressureHold: (
    body: {
      readings: Array<{ elapsed_min: number; pressure_bar: number; temperature_c: number }>;
      target_pressure_bar: number;
    },
    signal?: AbortSignal,
  ) =>
    apiFetch<import("./types").PressureHoldResponse>("/calculations/pressure-hold", {
      method: "POST",
      body,
      signal,
    }),

  depressurization: (body: import("./types").DepressurizationRequest, signal?: AbortSignal) =>
    apiFetch<import("./types").OperationCheckResponse>("/calculations/depressurization", {
      method: "POST",
      body,
      signal,
    }),

  discharge: (body: import("./types").DischargeRequest, signal?: AbortSignal) =>
    apiFetch<import("./types").OperationCheckResponse>("/calculations/discharge", {
      method: "POST",
      body,
      signal,
    }),

  thermalBalance: (records: import("./types").TimeSeriesRecordInput[], signal?: AbortSignal) =>
    apiFetch<import("./types").ThermalBalanceResponse>("/calculations/thermal-balance", {
      method: "POST",
      body: { records },
      signal,
    }),

  timeSeries: (
    sessionId: string,
    params?: { limit?: number; offset?: number; from?: string; to?: string },
    signal?: AbortSignal,
  ) => {
    const query = new URLSearchParams();
    if (params?.limit !== undefined) query.set("limit", String(params.limit));
    if (params?.offset !== undefined) query.set("offset", String(params.offset));
    if (params?.from) query.set("from", params.from);
    if (params?.to) query.set("to", params.to);
    const qs = query.toString();
    return apiFetch<ListResponse<import("./types").TimeSeriesRecordItem>>(
      `/sessions/${sessionId}/time-series${qs ? `?${qs}` : ""}`,
      { signal },
    );
  },

  timeSeriesSummary: (sessionId: string, signal?: AbortSignal) =>
    apiFetch<import("./types").TimeSeriesSummary>(`/sessions/${sessionId}/time-series/summary`, {
      signal,
    }),

  addTimeSeries: (
    sessionId: string,
    body: import("./types").TimeSeriesRecordInput,
    signal?: AbortSignal,
  ) =>
    apiFetch<import("./types").TimeSeriesAddResponse>(`/sessions/${sessionId}/time-series`, {
      method: "POST",
      body,
      signal,
    }),

  batchTimeSeries: (
    sessionId: string,
    body: {
      records: import("./types").TimeSeriesRecordInput[];
      mode?: "append" | "replace";
      source?: string | null;
    },
    signal?: AbortSignal,
  ) =>
    apiFetch<import("./types").TimeSeriesBatchResponse>(
      `/sessions/${sessionId}/time-series/batch`,
      {
        method: "POST",
        body,
        signal,
      },
    ),

  deleteTimeSeries: (sessionId: string, recordId: string, signal?: AbortSignal) =>
    apiFetch<void>(`/sessions/${sessionId}/time-series/${recordId}`, {
      method: "DELETE",
      signal,
    }),

  clearTimeSeries: (sessionId: string, signal?: AbortSignal) =>
    apiFetch<import("./types").TimeSeriesClearResponse>(`/sessions/${sessionId}/time-series`, {
      method: "DELETE",
      signal,
    }),

  syncTimeSeriesForm: (
    sessionId: string,
    body: {
      form_code: "leak_stabilization" | "pressure_test";
      direction: "from_form" | "to_form";
      mode?: "append" | "replace";
      base_date?: string | null;
    },
    signal?: AbortSignal,
  ) =>
    apiFetch<import("./types").TimeSeriesSyncFormResponse>(
      `/sessions/${sessionId}/time-series/sync-form`,
      {
        method: "POST",
        body,
        signal,
      },
    ),

  waterDensity: (body: { temperature_c: number; pressure_bar: number }, signal?: AbortSignal) =>
    apiFetch<{ density_kg_per_m3: number; temperature_c: number; pressure_bar: number }>(
      "/calculations/water-density",
      { method: "POST", body, signal },
    ),

  sessions: (projectId?: string | null, signal?: AbortSignal) => {
    const params = new URLSearchParams({ limit: "100" });
    if (projectId) params.set("project_id", projectId);
    return apiFetch<ListResponse<SessionListItem>>(`/sessions?${params.toString()}`, { signal });
  },

  session: (id: string, signal?: AbortSignal) => apiFetch<Session>(`/sessions/${id}`, { signal }),

  projects: (signal?: AbortSignal) =>
    apiFetch<ListResponse<Project>>("/projects?limit=200", { signal }),

  project: (id: string, signal?: AbortSignal) => apiFetch<Project>(`/projects/${id}`, { signal }),

  projectScene: (id: string, signal?: AbortSignal) =>
    apiFetch<import("./types").ProjectSceneResponse>(`/projects/${id}/scene`, { signal }),

  createProject: (body: ProjectInput, signal?: AbortSignal) =>
    apiFetch<Project>("/projects", { method: "POST", body, signal }),

  updateProject: (id: string, body: Partial<ProjectInput>, signal?: AbortSignal) =>
    apiFetch<Project>(`/projects/${id}`, { method: "PUT", body, signal }),

  deleteProject: (id: string, signal?: AbortSignal) =>
    apiFetch<void>(`/projects/${id}`, { method: "DELETE", signal }),

  scanPlanProfile: (
    params: {
      file: File;
      maxSectionLengthM?: number;
      maxElevationDiffM?: number | null;
    },
    signal?: AbortSignal,
  ) => {
    const form = new FormData();
    form.append("file", params.file);
    form.append("max_section_length_m", String(params.maxSectionLengthM ?? 12000));
    if (params.maxElevationDiffM !== null && params.maxElevationDiffM !== undefined) {
      form.append("max_elevation_diff_m", String(params.maxElevationDiffM));
    }
    return apiFetch<import("./types").PlanProfileScanResponse>("/projects/plan-profile/scan", {
      method: "POST",
      body: form,
      signal,
      timeoutMs: 90_000,
    });
  },

  createProjectSectionsBatch: (
    projectId: string,
    sections: Array<Partial<import("./types").DraftSectionItem>>,
    signal?: AbortSignal,
  ) =>
    apiFetch<{ project_id: string; created_count: number; items: SessionListItem[] }>(
      `/projects/${projectId}/sections/batch`,
      {
        method: "POST",
        body: { sections },
        signal,
      },
    ),

  commitPlanProfile: (body: PlanProfileCommitRequest, signal?: AbortSignal) =>
    apiFetch<PlanProfileCommitResponse>("/projects/plan-profile/commit", {
      method: "POST",
      body,
      signal,
    }),

  sessionForms: (sessionId: string, signal?: AbortSignal) =>
    apiFetch<SessionFormsResponse>(`/sessions/${sessionId}/forms`, { signal }),

  updateSessionForm: (
    sessionId: string,
    formCode: string,
    body: SectionFormUpdatePayload,
    ifMatch?: number | null,
    signal?: AbortSignal,
  ) =>
    apiFetch<SectionFormUpdateResponse>(`/sessions/${sessionId}/forms/${formCode}`, {
      method: "PUT",
      body,
      ifMatch: ifMatch !== undefined && ifMatch !== null ? ifMatch : body.revision ?? undefined,
      signal,
    }),

  scanSessionForm: (
    sessionId: string,
    formCode: string,
    filesInput: File | File[],
    options: { overwrite?: boolean; mode?: "replace" | "append" } = {},
    signal?: AbortSignal,
  ) => {
    const list = Array.isArray(filesInput) ? filesInput : [filesInput];
    const form = new FormData();
    if (list.length === 1) {
      form.append("file", list[0]);
    } else {
      for (const f of list) {
        form.append("files", f);
      }
    }
    form.append("overwrite", (options.overwrite ?? true) ? "true" : "false");
    form.append("mode", options.mode ?? "replace");
    return apiFetch<SectionFormScanResponse>(`/sessions/${sessionId}/forms/${formCode}/scan`, {
      method: "POST",
      body: form,
      signal,
      timeoutMs: 180_000,
    });
  },

  createSession: (
    body: { name?: string; project_id?: string | null; inputs?: Record<string, unknown> },
    signal?: AbortSignal,
  ) => apiFetch<Session>("/sessions", { method: "POST", body, signal }),

  updateSession: (
    id: string,
    body: {
      name?: string;
      status?: string;
      project_id?: string | null;
      inputs?: Record<string, unknown>;
    },
    revision: number,
    signal?: AbortSignal,
  ) =>
    apiFetch<SessionUpdateResponse>(`/sessions/${id}`, {
      method: "PUT",
      body,
      ifMatch: revision,
      signal,
    }),

  deleteSession: (id: string, signal?: AbortSignal) =>
    apiFetch<void>(`/sessions/${id}`, { method: "DELETE", signal }),

  duplicateSession: (id: string, name: string, signal?: AbortSignal) =>
    apiFetch<Session>(`/sessions/${id}/duplicate`, { method: "POST", body: { name }, signal }),

  results: (id: string, limit = 20, signal?: AbortSignal) =>
    apiFetch<ListResponse<TestResultRecord>>(`/sessions/${id}/results?limit=${limit}`, { signal }),

  saveResult: (
    id: string,
    body: { test_type: TestType; payload: Record<string, unknown> },
    revision?: number,
    signal?: AbortSignal,
  ) =>
    apiFetch<{ id: string; test_type: TestType; decision: TestResultRecord["decision"]; session_revision: number }>(
      `/sessions/${id}/results`,
      { method: "POST", body, ifMatch: revision, signal },
    ),

  summary: (id: string, signal?: AbortSignal) =>
    apiFetch<Record<string, unknown>>(`/sessions/${id}/summary`, { signal }),

  exportSession: (id: string, format: "pdf" | "xlsx" | "txt", signal?: AbortSignal) =>
    apiDownload(`/sessions/${id}/export?format=${format}`, {
      signal,
      fallbackFilename: `hidrostatik_test_raporu.${format}`,
    }),

  exportPreview: (id: string, signal?: AbortSignal) =>
    apiFetch<{ format: "txt"; content: string }>(`/sessions/${id}/export?format=txt&preview=true`, {
      signal,
    }),

  freeReport: (
    body: {
      format: "pdf" | "xlsx" | "txt";
      title: string;
      metadata: Record<string, string>;
      geometry_data: Record<string, string>;
      test_results: Record<string, string>;
      checklist: Array<Record<string, unknown>>;
    },
    signal?: AbortSignal,
  ) =>
    apiDownload("/reports/export", {
      method: "POST",
      body,
      signal,
      fallbackFilename: `hidrostatik_test_raporu.${body.format}`,
    }),

  snapshotDownload: (id: string, signal?: AbortSignal) =>
    apiDownload(`/sessions/${id}/snapshot`, {
      signal,
      fallbackFilename: "hidrostatik_test_girdileri.json",
    }),

  snapshotUpload: (
    id: string,
    snapshot: Record<string, unknown>,
    revision: number,
    mode: "merge" | "replace" = "merge",
    signal?: AbortSignal,
  ) =>
    apiFetch<SessionUpdateResponse & { mapping: SnapshotMapping }>(`/sessions/${id}/snapshot`, {
      method: "POST",
      body: { snapshot, mode },
      ifMatch: revision,
      signal,
    }),

  importSnapshot: (
    body: { name?: string; project_id?: string | null; snapshot: Record<string, unknown> },
    signal?: AbortSignal,
  ) =>
    apiFetch<{ session: Session; mapping: SnapshotMapping }>("/import/desktop-snapshot", {
      method: "POST",
      body,
      signal,
    }),

  stats: (signal?: AbortSignal) =>
    apiFetch<{
      total_sessions: number;
      total_tests: number;
      time_series_records: number;
      by_status: Record<string, number>;
      by_type: Record<string, number>;
      ocr: { queued: number; running: number; succeeded: number; failed: number };
    }>("/stats", { signal }),

  ocrStatus: (signal?: AbortSignal) =>
    apiFetch<OcrStatusResponse>("/ocr/status", { signal }),

  updateStatus: (signal?: AbortSignal) =>
    apiFetch<UpdateManagerStatus>("/update/status", { signal, timeoutMs: 5_000 }),

  checkUpdates: (force = true, signal?: AbortSignal) =>
    apiFetch<UpdateManagerStatus>(`/update/check?force=${force ? "true" : "false"}`, {
      method: "POST",
      signal,
      timeoutMs: 15_000,
    }),

  startUpdateDownload: (assetName?: string, signal?: AbortSignal) => {
    const qs = assetName ? `?asset_name=${encodeURIComponent(assetName)}` : "";
    return apiFetch<UpdateManagerStatus>(`/update/download${qs}`, {
      method: "POST",
      signal,
      timeoutMs: 30_000,
    });
  },

  applyUpdate: (signal?: AbortSignal) =>
    apiFetch<UpdateManagerStatus>("/update/apply", {
      method: "POST",
      signal,
      timeoutMs: 60_000,
    }),

  downloadVerifiedUpdateFile: (fallbackFilename: string, signal?: AbortSignal) =>
    apiDownload("/update/download/file", {
      signal,
      fallbackFilename,
      timeoutMs: 120_000,
    }),

  /* ---------------------------------------------------------------- */
  /* Proje Veri Merkezi, Üreticiler ve Veritabanı Yönetimi           */
  /* ---------------------------------------------------------------- */

  projectDataset: (projectId: string, signal?: AbortSignal) =>
    apiFetch<import("./types").ProjectDatasetResponse>(`/projects/${projectId}/dataset`, { signal }),

  exportProjectDataset: (
    projectId: string,
    format: import("./types").ProjectExportFormat,
    signal?: AbortSignal,
  ) =>
    apiDownload(`/projects/${projectId}/export`, {
      method: "POST",
      body: { format },
      signal,
      fallbackFilename: `proje_veri_ozeti.${format}`,
      timeoutMs: 90_000,
    }),

  generateProjectSections: (
    projectId: string,
    body: import("./types").ProjectGenerateSectionsPayload,
    signal?: AbortSignal,
  ) =>
    apiFetch<import("./types").ProjectGenerateSectionsResponse>(
      `/projects/${projectId}/generate-sections`,
      { method: "POST", body, signal },
    ),

  syncProjectForms: (
    projectId: string,
    body: { overwrite_existing?: boolean; form_codes?: string[] },
    signal?: AbortSignal,
  ) =>
    apiFetch<import("./types").ProjectSyncFormsResponse>(`/projects/${projectId}/sync-forms`, {
      method: "POST",
      body,
      signal,
    }),

  generateSampleProject: (body: import("./types").SampleProjectPayload, signal?: AbortSignal) =>
    apiFetch<{ project: Project; sections: SessionListItem[] }>("/projects/generate-sample", {
      method: "POST",
      body,
      signal,
      timeoutMs: 60_000,
    }),

  cloneProject: (
    projectId: string,
    body: import("./types").ProjectClonePayload,
    signal?: AbortSignal,
  ) =>
    apiFetch<{ project: Project; section_count: number; mode: string }>(
      `/projects/${projectId}/clone`,
      { method: "POST", body, signal },
    ),

  downloadProjectArchive: (
    projectId: string,
    includeAttachments = true,
    signal?: AbortSignal,
  ) =>
    apiDownload(
      `/projects/${projectId}/archive?include_attachments=${includeAttachments ? "true" : "false"}`,
      {
        signal,
        fallbackFilename: "proje_arsivi.hydroproj.zip",
        timeoutMs: 120_000,
      },
    ),

  importProjectArchive: (
    params: {
      file: File;
      targetProjectName?: string;
      targetProjectCode?: string;
      includeAttachments?: boolean;
    },
    signal?: AbortSignal,
  ) => {
    const form = new FormData();
    form.append("file", params.file);
    if (params.targetProjectName?.trim()) {
      form.append("target_project_name", params.targetProjectName.trim());
    }
    if (params.targetProjectCode?.trim()) {
      form.append("target_project_code", params.targetProjectCode.trim());
    }
    form.append("include_attachments", (params.includeAttachments ?? true) ? "true" : "false");
    return apiFetch<import("./types").ArchiveImportResponse>("/projects/import-archive", {
      method: "POST",
      body: form,
      signal,
      timeoutMs: 120_000,
    });
  },

  importDesktopDb: (
    params: { file: File; projectName?: string; projectCode?: string },
    signal?: AbortSignal,
  ) => {
    const form = new FormData();
    form.append("file", params.file);
    if (params.projectName?.trim()) form.append("project_name", params.projectName.trim());
    if (params.projectCode?.trim()) form.append("project_code", params.projectCode.trim());
    return apiFetch<import("./types").DesktopDbImportResponse>("/import/desktop-db", {
      method: "POST",
      body: form,
      signal,
      timeoutMs: 120_000,
    });
  },

  workspaces: (signal?: AbortSignal) =>
    apiFetch<import("./types").WorkspacesResponse>("/system/workspaces", { signal }),

  claimWorkspace: (sourceWorkspaceHash: string, sourceWorkspaceKey?: string, signal?: AbortSignal) =>
    apiFetch<{
      source_workspace_hash: string;
      target_workspace_hash: string;
      moved: Record<string, number>;
    }>("/system/workspaces/claim", {
      method: "POST",
      body: {
        source_workspace_hash: sourceWorkspaceHash,
        ...(sourceWorkspaceKey ? { source_workspace_key: sourceWorkspaceKey } : {}),
      },
      signal,
    }),

  dbStats: (signal?: AbortSignal) =>
    apiFetch<import("./types").DbStatsResponse>("/system/db-stats", { signal }),

  dbBackups: (signal?: AbortSignal) =>
    apiFetch<import("./types").DbBackupsResponse>("/system/db-backups", { signal }),

  createDbBackup: (reason = "manual", signal?: AbortSignal) =>
    apiFetch<import("./types").DbBackupItem>("/system/db-backup", {
      method: "POST",
      body: { reason },
      signal,
    }),

  downloadDbBackup: (filename: string, signal?: AbortSignal) =>
    apiDownload(`/system/db-backups/${encodeURIComponent(filename)}`, {
      signal,
      fallbackFilename: filename,
      timeoutMs: 120_000,
    }),

  restoreDbBackup: (
    params: { backupFilename?: string; file?: File },
    signal?: AbortSignal,
  ) => {
    if (params.file) {
      const form = new FormData();
      form.append("file", params.file);
      return apiFetch<import("./types").DbRestoreResponse>("/system/db-restore", {
        method: "POST",
        body: form,
        signal,
        timeoutMs: 120_000,
      });
    }
    return apiFetch<import("./types").DbRestoreResponse>("/system/db-restore", {
      method: "POST",
      body: { backup_filename: params.backupFilename ?? "" },
      signal,
      timeoutMs: 120_000,
    });
  },

  trash: (signal?: AbortSignal) =>
    apiFetch<import("./types").TrashResponse>("/system/trash", { signal }),

  restoreTrash: (entityType: "project" | "session", entityId: string, signal?: AbortSignal) =>
    apiFetch<{ entity_type: string; id: string; restored_sessions: number }>(
      "/system/trash/restore",
      {
        method: "POST",
        body: { entity_type: entityType, entity_id: entityId },
        signal,
      },
    ),

  purgeTrash: (entityType: "project" | "session", entityId: string, signal?: AbortSignal) =>
    apiFetch<{ purged: boolean; entity_type: string; id: string }>(
      `/system/trash/${entityType}/${encodeURIComponent(entityId)}`,
      { method: "DELETE", signal },
    ),

  runDbMaintenance: (
    body: import("./types").DbMaintenancePayload,
    signal?: AbortSignal,
  ) =>
    apiFetch<import("./types").DbMaintenanceResponse>("/system/db-maintenance", {
      method: "POST",
      body,
      signal,
      timeoutMs: 60_000,
    }),
};
