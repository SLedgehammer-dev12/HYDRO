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
  Session,
  SessionListItem,
  SessionUpdateResponse,
  SnapshotMapping,
  SpecResponse,
  TablePointResponse,
  TestResultRecord,
  TestType,
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

function uuid(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `ws-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
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
      "Sunucuya ulaşılamadı. Backend çalışmıyor olabilir; arayüz demo modunda devam ediyor.",
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
  if (!(error instanceof ApiError)) return false;
  return (
    error.status === 0 ||
    error.status === 404 ||
    error.status === 500 ||
    error.status === 501 ||
    error.status === 502 ||
    error.status === 503
  );
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

  createProject: (body: ProjectInput, signal?: AbortSignal) =>
    apiFetch<Project>("/projects", { method: "POST", body, signal }),

  updateProject: (id: string, body: Partial<ProjectInput>, signal?: AbortSignal) =>
    apiFetch<Project>(`/projects/${id}`, { method: "PUT", body, signal }),

  deleteProject: (id: string, signal?: AbortSignal) =>
    apiFetch<void>(`/projects/${id}`, { method: "DELETE", signal }),

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
    body: { name?: string; snapshot: Record<string, unknown> },
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
};
