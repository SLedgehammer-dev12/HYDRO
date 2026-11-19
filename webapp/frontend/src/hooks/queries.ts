import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api, isRecoverableError } from "../lib/api";
import {
  DEMO_GRADES,
  DEMO_META,
  DEMO_OCR_STATUS,
  DEMO_PIPES,
  DEMO_REFERENCE_TABLES,
  DEMO_SPEC,
  buildDemoResults,
  buildSceneData,
  computeA,
  computeAir,
  computeB,
  computeBackendComparison,
  computeCompare,
  computeGeometry,
  computePig,
  computeProfile,
  computePressure,
  computeTablePoint,
  createDemoHistory,
  createDemoSession,
  demoProjects,
  demoSessionDetail,
  demoSessions,
  sleep,
} from "../lib/mock";
import { useAppStore } from "../store/useAppStore";
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
  Project,
  ProjectInput,
  ProjectSceneResponse,
  ReferenceTableMeta,
  ResultBundle,
  SectionFormRecord,
  SectionFormScanResponse,
  SectionFormUpdatePayload,
  SectionFormUpdateResponse,
  Session,
  SessionFormsResponse,
  SessionListItem,
  SessionStatus,
  SpecResponse,
  TablePointResponse,
  TestResultRecord,
  TestType,
  UpdateManagerStatus,
} from "../lib/types";
import { BOTAS_FORM_NAV_ITEMS, CHECK_DEFINITIONS } from "../lib/constants";
import { toApiInputs } from "../lib/normalize";

export interface Resolved<T> {
  data: T;
  mode: "live" | "demo";
}

async function resolveWithMock<T>(
  real: () => Promise<T>,
  mock: () => T | Promise<T>,
): Promise<Resolved<T>> {
  const { backend } = useAppStore.getState();
  if (backend === "demo") {
    return { data: await mock(), mode: "demo" };
  }
  try {
    return { data: await real(), mode: "live" };
  } catch (error) {
    if (isRecoverableError(error)) {
      useAppStore.getState().setBackend("demo");
      return { data: await mock(), mode: "demo" };
    }
    throw error;
  }
}

const isOnline = () => useAppStore.getState().backend === "online";

/* ------------------------------------------------------------------ */
/* Sistem                                                              */
/* ------------------------------------------------------------------ */

function normalizeHealth(raw: Record<string, unknown>): HealthResponse {
  const db = (raw.db ?? {}) as Record<string, unknown>;
  const dataDir = (raw.data_dir ?? {}) as Record<string, unknown>;
  const ocr = (raw.ocr ?? {}) as Record<string, unknown>;
  const queue = (ocr.queue ?? {}) as Record<string, unknown>;
  const statusRaw = typeof raw.status === "string" ? raw.status : "fail";
  const status: HealthResponse["status"] =
    statusRaw === "ok" || statusRaw === "healthy"
      ? "ok"
      : statusRaw === "degraded"
        ? "degraded"
        : "fail";
  return {
    status,
    version: typeof raw.version === "string" ? raw.version : "—",
    engine: typeof raw.engine === "string" ? raw.engine : "hidrostatik_test",
    db: {
      ok: typeof db.ok === "boolean" ? db.ok : false,
      dialect: typeof db.dialect === "string" ? db.dialect : "—",
      migration: typeof db.migration === "string" ? db.migration : "—",
    },
    data_dir: {
      ok: typeof dataDir.ok === "boolean" ? dataDir.ok : false,
      writable: typeof dataDir.writable === "boolean" ? dataDir.writable : false,
    },
    ocr: {
      available: typeof ocr.available === "boolean" ? ocr.available : false,
      status: typeof ocr.status === "string" ? ocr.status : "OCR durumu bilinmiyor.",
      queue: {
        queued: typeof queue.queued === "number" ? queue.queued : 0,
        running: typeof queue.running === "number" ? queue.running : 0,
      },
    },
    uptime_s: typeof raw.uptime_s === "number" ? raw.uptime_s : 0,
  };
}

export function useBackendProbe() {
  const queryClient = useQueryClient();
  return useQuery<HealthResponse | null>({
    queryKey: ["health"],
    queryFn: async () => {
      const prevBackend = useAppStore.getState().backend;
      try {
        const raw = await api.health();
        const health = normalizeHealth(raw as unknown as Record<string, unknown>);
        useAppStore.getState().setBackend("online", health);
        if (prevBackend !== "online") {
          void queryClient.invalidateQueries({ queryKey: ["sessions"] });
          void queryClient.invalidateQueries({ queryKey: ["projects"] });
          void queryClient.invalidateQueries({ queryKey: ["session-forms"] });
          void queryClient.invalidateQueries({ queryKey: ["project-scene"] });
          void queryClient.invalidateQueries({ queryKey: ["session"] });
        }
        return health;
      } catch {
        useAppStore.getState().setBackend("demo", null);
        return null;
      }
    },
    retry: false,
    refetchInterval: 45_000,
    staleTime: 15_000,
  });
}

export function useMeta() {
  return useQuery<MetaResponse>({
    queryKey: ["meta"],
    queryFn: async () => (await resolveWithMock(() => api.meta(), () => DEMO_META)).data,
    initialData: DEMO_META,
    initialDataUpdatedAt: 0,
    staleTime: 300_000,
  });
}

export function useSpec() {
  return useQuery<SpecResponse>({
    queryKey: ["spec"],
    queryFn: async () => (await resolveWithMock(() => api.spec(), () => DEMO_SPEC)).data,
    initialData: DEMO_SPEC,
    initialDataUpdatedAt: 0,
    staleTime: 300_000,
  });
}

/* ------------------------------------------------------------------ */
/* Katalog                                                             */
/* ------------------------------------------------------------------ */

export function usePipes() {
  return useQuery<Pick<ListResponse<PipeOption>, "items">>({
    queryKey: ["catalog", "pipes"],
    queryFn: async () => {
      const result = await resolveWithMock(
        () => api.pipes(),
        () => ({ items: DEMO_PIPES, total: DEMO_PIPES.length, limit: 200, offset: 0 }),
      );
      return { items: result.data.items };
    },
    initialData: { items: DEMO_PIPES },
    initialDataUpdatedAt: 0,
    staleTime: 300_000,
  });
}

export function useGrades() {
  return useQuery<{ items: GradeOption[] }>({
    queryKey: ["catalog", "grades"],
    queryFn: async () => {
      const result = await resolveWithMock(
        () => api.grades(),
        () => ({
          items: DEMO_GRADES,
          total: DEMO_GRADES.length,
          limit: 50,
          offset: 0,
        }),
      );
      return { items: result.data.items };
    },
    initialData: { items: DEMO_GRADES },
    initialDataUpdatedAt: 0,
    staleTime: 300_000,
  });
}

export function useReferenceTables() {
  return useQuery<{ items: ReferenceTableMeta[] }>({
    queryKey: ["catalog", "reference-tables"],
    queryFn: async () => {
      const result = await resolveWithMock(
        () => api.referenceTables(),
        () => ({
          items: DEMO_REFERENCE_TABLES,
          total: DEMO_REFERENCE_TABLES.length,
          limit: 20,
          offset: 0,
        }),
      );
      return { items: result.data.items };
    },
    initialData: { items: DEMO_REFERENCE_TABLES },
    initialDataUpdatedAt: 0,
    staleTime: 300_000,
  });
}

export function useCatalog() {
  const pipes = usePipes();
  const grades = useGrades();
  const tables = useReferenceTables();
  return {
    pipes: pipes.data?.items ?? DEMO_PIPES,
    grades: grades.data?.items ?? DEMO_GRADES,
    referenceTables: tables.data?.items ?? DEMO_REFERENCE_TABLES,
    isLoading: pipes.isLoading || grades.isLoading || tables.isLoading,
  };
}

/* ------------------------------------------------------------------ */
/* Oturumlar                                                           */
/* ------------------------------------------------------------------ */

export function useSessions(
  projectId?: string | null,
  options?: { enabled?: boolean },
) {
  const backend = useAppStore((state) => state.backend);
  return useQuery<SessionListItem[]>({
    queryKey: ["sessions", projectId ?? "all"],
    enabled: (options?.enabled ?? true) && backend !== "checking",
    queryFn: async () => {
      const state = useAppStore.getState();
      const fallback = () => ({
        items: demoSessions(state.inputs, state.sessionName, projectId),
        total: demoSessions(state.inputs, state.sessionName, projectId).length,
        limit: 100,
        offset: 0,
      });
      if (state.backend === "demo") {
        state.setSessionApiReady(false);
        return fallback().items;
      }
      try {
        const response = await api.sessions(projectId);
        state.setSessionApiReady(true);
        return response.items;
      } catch (error) {
        if (isRecoverableError(error)) {
          state.setSessionApiReady(false);
          return fallback().items;
        }
        throw error;
      }
    },
    initialData: DEMO_SESSION_LIST_FALLBACK(projectId),
    initialDataUpdatedAt: 0,
    staleTime: 20_000,
  });
}

function DEMO_SESSION_LIST_FALLBACK(projectId?: string | null): SessionListItem[] {
  const state = useAppStore.getState();
  return demoSessions(state.inputs, state.sessionName, projectId);
}

/* ------------------------------------------------------------------ */
/* Projeler                                                            */
/* ------------------------------------------------------------------ */

export function useProjects() {
  const backend = useAppStore((state) => state.backend);
  return useQuery<Project[]>({
    queryKey: ["projects"],
    enabled: backend !== "checking",
    queryFn: async () => {
      const state = useAppStore.getState();
      if (state.backend === "demo") return demoProjects();
      try {
        const response = await api.projects();
        return response.items;
      } catch (error) {
        if (isRecoverableError(error)) return demoProjects();
        throw error;
      }
    },
    initialData: DEMO_PROJECTS_FALLBACK,
    initialDataUpdatedAt: 0,
    staleTime: 30_000,
  });
}

function DEMO_PROJECTS_FALLBACK(): Project[] {
  return demoProjects();
}

function cacheProject(
  queryClient: ReturnType<typeof useQueryClient>,
  project: Project,
  mode: "add" | "replace" | "remove",
) {
  queryClient.setQueryData<Project[]>(["projects"], (current) => {
    const items = current ?? [];
    if (mode === "add") return [project, ...items];
    if (mode === "remove") return items.filter((item) => item.id !== project.id);
    return items.map((item) => (item.id === project.id ? project : item));
  });
}

export function useCreateProject() {
  const queryClient = useQueryClient();
  return useMutation<Project, Error, ProjectInput>({
    mutationFn: async (payload) => {
      const state = useAppStore.getState();
      if (state.backend !== "online") {
        await sleep(320);
        const now = new Date().toISOString();
        return {
          id: `demo-project-${Date.now().toString(36)}`,
          code: payload.code?.trim() || `PRJ-${Date.now().toString(36).slice(-4).toUpperCase()}`,
          name: payload.name,
          client: payload.client?.trim() || null,
          description: payload.description?.trim() || null,
          section_count: 0,
          created_at: now,
          updated_at: now,
        };
      }
      return api.createProject(payload);
    },
    onSuccess: (project) => {
      cacheProject(queryClient, project, "add");
      useAppStore.getState().pushToast("success", "Proje oluşturuldu", project.name);
    },
    onError: (error) => {
      useAppStore.getState().pushToast("error", "Proje oluşturulamadı", error.message);
    },
  });
}

export function useUpdateProject() {
  const queryClient = useQueryClient();
  return useMutation<Project, Error, { id: string; patch: Partial<ProjectInput> }>({
    mutationFn: async ({ id, patch }) => {
      const state = useAppStore.getState();
      if (state.backend !== "online") {
        await sleep(280);
        const current = queryClient.getQueryData<Project[]>(["projects"])?.find((p) => p.id === id);
        return {
          ...(current ?? {
            id,
            code: "",
            name: patch.name ?? "",
            client: null,
            description: null,
            section_count: 0,
            created_at: new Date().toISOString(),
          }),
          ...patch,
          client: patch.client ?? current?.client ?? null,
          description: patch.description ?? current?.description ?? null,
          updated_at: new Date().toISOString(),
        } as Project;
      }
      return api.updateProject(id, patch);
    },
    onSuccess: (project) => {
      cacheProject(queryClient, project, "replace");
      useAppStore.getState().pushToast("success", "Proje güncellendi", project.name);
    },
    onError: (error) => {
      useAppStore.getState().pushToast("error", "Proje güncellenemedi", error.message);
    },
  });
}

export function useDeleteProject() {
  const queryClient = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: async (id) => {
      const state = useAppStore.getState();
      if (state.backend !== "online") {
        await sleep(240);
        return;
      }
      await api.deleteProject(id);
    },
    onSuccess: (_result, id) => {
      const removed = queryClient.getQueryData<Project[]>(["projects"])?.find((p) => p.id === id);
      cacheProject(
        queryClient,
        removed ?? ({ id } as Project),
        "remove",
      );
      const store = useAppStore.getState();
      if (store.projectId === id) {
        store.setProject(null);
        store.resetSession("Yeni oturum");
      }
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
      void queryClient.invalidateQueries({ queryKey: ["project-scene"] });
      void queryClient.invalidateQueries({ queryKey: ["session-forms"] });
      store.pushToast(
        "success",
        "Proje silindi",
        removed ? `${removed.name} ve bağlı kesitler silindi.` : "Proje ve bağlı kesitler silindi.",
      );
    },
    onError: (error) => {
      useAppStore.getState().pushToast("error", "Proje silinemedi", error.message);
    },
  });
}

export function useDuplicateSession() {
  const queryClient = useQueryClient();
  return useMutation<Session, Error, { id: string; name: string }>({
    mutationFn: async ({ id, name }) => {
      const state = useAppStore.getState();
      if (state.backend !== "online" || id.startsWith("demo-")) {
        await sleep(260);
        return { ...createDemoSession(), id: `demo-session-${Date.now().toString(36)}`, name };
      }
      return api.duplicateSession(id, name);
    },
    onSuccess: (session) => {
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      void queryClient.invalidateQueries({ queryKey: ["project-scene"] });
      useAppStore.getState().pushToast("success", "Kesit kopyalandı", session.name);
    },
    onError: (error) => {
      useAppStore.getState().pushToast("error", "Kesit kopyalanamadı", error.message);
    },
  });
}

export function useDeleteSection() {
  const queryClient = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: async (id) => {
      const state = useAppStore.getState();
      if (state.backend !== "online" || id.startsWith("demo-")) {
        await sleep(220);
        return;
      }
      await api.deleteSession(id);
    },
    onSuccess: (_result, id) => {
      const store = useAppStore.getState();
      if (store.sessionId === id) {
        store.setSessionMeta({ id: null, name: "Yeni oturum", status: "draft", revision: 0 });
      }
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      void queryClient.invalidateQueries({ queryKey: ["project-scene"] });
      store.pushToast("success", "Kesit silindi", "Kesit arşivlendi; proje kaydı korundu.");
    },
    onError: (error) => {
      useAppStore.getState().pushToast("error", "Kesit silinemedi", error.message);
    },
  });
}

export function useScanPlanProfile() {
  return useMutation<
    import("../lib/types").PlanProfileScanResponse,
    Error,
    { file: File; maxSectionLengthM?: number; maxElevationDiffM?: number | null }
  >({
    mutationFn: async (params) => api.scanPlanProfile(params),
    onError: (error) => {
      useAppStore.getState().pushToast("error", "Plan-profil taranamadı", error.message);
    },
  });
}

export function useCreateDraftSectionsBatch() {
  const queryClient = useQueryClient();
  return useMutation<
    { project_id: string; created_count: number; items: SessionListItem[] },
    Error,
    { projectId: string; sections: Array<Partial<import("../lib/types").DraftSectionItem>> }
  >({
    mutationFn: async ({ projectId, sections }) =>
      api.createProjectSectionsBatch(projectId, sections),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      void queryClient.invalidateQueries({ queryKey: ["project-scene"] });
      useAppStore
        .getState()
        .pushToast(
          "success",
          "Taslak kesitler oluşturuldu",
          `${data.created_count} taslak kesit projeye kaydedildi.`,
        );
    },
    onError: (error) => {
      useAppStore.getState().pushToast("error", "Taslak kesitler kaydedilemedi", error.message);
    },
  });
}

export function useCommitPlanProfile() {
  const queryClient = useQueryClient();
  return useMutation<PlanProfileCommitResponse, Error, PlanProfileCommitRequest>({
    mutationFn: async (body) => api.commitPlanProfile(body),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      void queryClient.invalidateQueries({ queryKey: ["session-forms"] });
      void queryClient.invalidateQueries({ queryKey: ["project-scene"] });
      useAppStore
        .getState()
        .pushToast(
          "success",
          "Plan-profil kesitleri kaydedildi",
          `${data.project.name} projesine ${data.created_count} kesit ve her biri için 11 boş BOTAŞ formu oluşturuldu.`,
        );
    },
    onError: (error) => {
      useAppStore.getState().pushToast("error", "Plan-profil kaydedilemedi", error.message);
    },
  });
}

function buildFallbackSessionForms(sessionId: string): SessionFormsResponse {
  const state = useAppStore.getState();
  const forms: SectionFormRecord[] = BOTAS_FORM_NAV_ITEMS.map((item) => ({
    id: `slot-${sessionId}-${item.code}`,
    form_code: item.code,
    botas_code: item.botasCode,
    form_title: item.title,
    required: item.required,
    order: item.order,
    status: "empty",
    analysis_id: null,
    source_filename: "",
    pages: [],
    form_date: state.inputs.section_meta.test_date || "",
    extracted_data: {},
    findings: [],
    warnings: [],
    revision: 0,
    filled_at: null,
    updated_at: null,
  }));
  const reqForms = BOTAS_FORM_NAV_ITEMS.filter((i) => i.required);
  return {
    session_id: sessionId,
    project_id: state.projectId,
    section_no: state.inputs.section_meta.section_no || state.sessionName || "Kesit",
    session_name: state.sessionName,
    summary: {
      required_total: reqForms.length,
      filled_required: 0,
      missing_required: reqForms.length,
      missing_titles: reqForms.map((i) => i.title),
      supplementary_filled: 0,
      failed_forms: [],
      warning_forms: [],
      passed_forms_count: 0,
      warning_forms_count: 0,
      findings_counts: { passed: 0, warning: 0, failed: 0 },
      first_issue_form_code: null,
      key_metrics: {},
      complete: false,
    },
    merged_header: {
      section_no: state.inputs.section_meta.section_no,
      start_kp: state.inputs.section_meta.start_kp,
      end_kp: state.inputs.section_meta.end_kp,
      outside_diameter_mm: state.inputs.geometry.outside_diameter_mm,
      wall_thickness_mm: state.inputs.geometry.wall_thickness_mm,
      length_m: state.inputs.geometry.length_m,
      design_pressure_bar: state.inputs.section_profile.design_pressure_bar,
      smys_mpa: state.inputs.section_profile.smys_mpa,
    },
    calculations: {},
    forms,
    missing_required_forms: reqForms.map((i) => ({
      form_code: i.code,
      botas_code: i.botasCode,
      form_title: i.title,
    })),
    checkpoints: CHECK_DEFINITIONS.map((chk) => ({
      key: chk.key,
      label: chk.label,
      ref: chk.ref,
      checked: Boolean(state.inputs.checks[chk.key]),
      status: state.inputs.checks[chk.key] ? "passed" : "pending",
      message: state.inputs.check_details?.[chk.key]?.message ?? "",
      source_forms: state.inputs.check_details?.[chk.key]?.source_forms ?? [],
    })),
  };
}

export function useSessionForms(sessionId: string | null) {
  const backend = useAppStore((state) => state.backend);
  return useQuery<SessionFormsResponse>({
    queryKey: ["session-forms", sessionId],
    queryFn: async () => {
      const state = useAppStore.getState();
      if (!sessionId || state.backend !== "online" || sessionId.startsWith("demo-")) {
        return buildFallbackSessionForms(sessionId ?? "demo-session");
      }
      return api.sessionForms(sessionId);
    },
    enabled: Boolean(sessionId) && backend !== "checking",
    staleTime: 10_000,
    retry: false,
  });
}

export function useUpdateSessionForm() {
  const queryClient = useQueryClient();
  return useMutation<
    SectionFormUpdateResponse,
    Error,
    { sessionId: string; formCode: string; payload: SectionFormUpdatePayload }
  >({
    mutationFn: async ({ sessionId, formCode, payload }) =>
      api.updateSessionForm(sessionId, formCode, payload),
    onSuccess: (res) => {
      const store = useAppStore.getState();
      queryClient.setQueryData(["session-forms", res.session.id], res.forms_payload);
      queryClient.setQueryData(["session", res.session.id], res.session);
      store.applySessionInputs(res.session.inputs);
      store.setSessionMeta({
        id: res.session.id,
        name: res.session.name,
        revision: res.session.revision,
        status: res.session.status,
      });
      store.markSaved(res.session.revision);
      void hydrateSessionResults(res.session.id);
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
      store.pushToast(
        "success",
        "Form kaydedildi ve kontrol edildi",
        `${res.form.botas_code} · Revizyon ${res.form.revision}`,
      );
    },
    onError: (error) => {
      useAppStore.getState().pushToast("error", "Form kaydedilemedi", error.message);
    },
  });
}

export function useScanSessionForm() {
  const queryClient = useQueryClient();
  return useMutation<
    SectionFormScanResponse,
    Error,
    {
      sessionId: string;
      formCode: string;
      files: File | File[];
      overwrite?: boolean;
      mode?: "replace" | "append";
    }
  >({
    mutationFn: async ({ sessionId, formCode, files, overwrite = true, mode = "replace" }) =>
      api.scanSessionForm(sessionId, formCode, files, { overwrite, mode }),
    onSuccess: (res, vars) => {
      const store = useAppStore.getState();
      queryClient.setQueryData(["session-forms", res.session.id], res.forms_payload);
      queryClient.setQueryData(["session", res.session.id], res.session);
      store.applySessionInputs(res.session.inputs);
      store.setSessionMeta({
        id: res.session.id,
        name: res.session.name,
        revision: res.session.revision,
        status: res.session.status,
      });
      store.markSaved(res.session.revision);
      void hydrateSessionResults(res.session.id);
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
      store.pushToast(
        "success",
        vars.mode === "append" ? "Devam sayfası eklendi" : "Doküman forma aktarıldı",
        vars.mode === "append"
          ? `${res.form.form_title} verileri birleştirildi ve kontroller güncellendi.`
          : `${res.form.form_title} tarandı ve kontroller güncellendi.`,
      );
    },
    onError: (error) => {
      useAppStore.getState().pushToast("error", "Doküman taranamadı", error.message);
    },
  });
}

export function useProjectScene(projectId: string | null, enabled = true) {
  const backend = useAppStore((state) => state.backend);
  return useQuery<ProjectSceneResponse>({
    queryKey: ["project-scene", projectId],
    enabled: Boolean(projectId) && enabled && backend !== "checking",
    queryFn: async () => {
      const state = useAppStore.getState();
      if (!projectId || state.backend !== "online" || projectId.startsWith("demo-")) {
        const local = buildSceneData(state.inputs, state.results);
        const total = local.segments.reduce(
          (acc, s) => Math.max(acc, s.end_m),
          0,
        );
        return {
          ...local,
          project_id: projectId ?? "demo-project-001",
          project_name: state.projectName || "Örnek Proje",
          section_count: local.segments.length ? 1 : 0,
          total_length_m: total,
          continuity_ok: true,
          sections: [],
        };
      }
      return api.projectScene(projectId);
    },
    staleTime: 15_000,
    retry: false,
  });
}

let activeSessionLoadSeq = 0;

export async function hydrateSessionResults(
  sessionId: string,
  expectedSeq?: number,
): Promise<void> {
  if (!sessionId || sessionId.startsWith("demo-") || useAppStore.getState().backend !== "online") {
    return;
  }
  const token = expectedSeq ?? activeSessionLoadSeq;
  try {
    const list = await api.results(sessionId, 20);
    if (token !== activeSessionLoadSeq || useAppStore.getState().sessionId !== sessionId) {
      return;
    }
    const patch: Partial<ResultBundle> = {};
    let latestComputed: string | undefined;
    for (const item of list.items ?? []) {
      if (!latestComputed && item.computed_at) latestComputed = item.computed_at;
      if (item.test_type === "air" && !patch.air) {
        patch.air = item.result as unknown as AirContentResponse;
      } else if (item.test_type === "pressure" && !patch.pressure) {
        patch.pressure = item.result as unknown as PressureVariationResponse;
      } else if (item.test_type === "profile" && !patch.profile) {
        patch.profile = item.result as unknown as PressureProfileResponse;
      } else if (item.test_type === "pig" && !patch.pig) {
        patch.pig = item.result as unknown as PigSpeedResponse;
      }
    }
    if (Object.keys(patch).length > 0) {
      const current = useAppStore.getState().results;
      useAppStore.getState().setResults({
        geometry: current.geometry,
        coefficients: current.coefficients,
        bCompare: current.bCompare,
        backendCompare: current.backendCompare,
        ...patch,
        lastComputedAt: latestComputed,
        source: "live",
      });
    }
  } catch {
    // Sunucu hesap geçmişi alınamazsa mevcut yerel hesaplar korunur.
  }
}

export function useOpenSession() {
  const queryClient = useQueryClient();
  return useMutation<Session, Error, string>({
    mutationFn: async (id) => {
      const seq = ++activeSessionLoadSeq;
      const state = useAppStore.getState();
      if (state.backend !== "online" || id.startsWith("demo-")) {
        await sleep(240);
        return demoSessionDetail(state.inputs, state.sessionName);
      }
      const session = await api.session(id);
      if (seq !== activeSessionLoadSeq) {
        throw new Error("Oturum seçimi değişti.");
      }
      return session;
    },
    onSuccess: (session) => {
      const seq = activeSessionLoadSeq;
      const store = useAppStore.getState();
      store.applySessionInputs(session.inputs);
      store.setSessionMeta({
        id: session.id,
        name: session.name,
        status: session.status,
        revision: session.revision,
      });
      store.markSaved(session.revision);
      queryClient.setQueryData(["session", session.id], session);
      void queryClient.invalidateQueries({ queryKey: ["results", session.id] });
      void hydrateSessionResults(session.id, seq);
      store.pushToast("success", "Kesit açıldı", session.name);
    },
    onError: (error) => {
      if (error.message === "Oturum seçimi değişti.") return;
      useAppStore.getState().pushToast("error", "Kesit açılamadı", error.message);
    },
  });
}

export function useSafeSwitchSession() {
  const openSession = useOpenSession();
  return {
    isPending: openSession.isPending,
    switchSession: (id: string) => {
      const state = useAppStore.getState();
      if (!id || id === state.sessionId) return;
      if (
        state.dirty &&
        typeof window !== "undefined" &&
        !window.confirm("Kaydedilmemiş değişiklikler var. Başka test bölümüne geçilsin mi?")
      ) {
        return;
      }
      openSession.mutate(id);
    },
  };
}

export function useSessionDetail(id: string | null) {
  const backend = useAppStore((state) => state.backend);
  return useQuery<Session>({
    queryKey: ["session", id],
    enabled: Boolean(id) && backend === "online",
    queryFn: async () => {
      const state = useAppStore.getState();
      if (!id) return createDemoSession();
      const result = await resolveWithMock(
        () => api.session(id),
        () => demoSessionDetail(state.inputs, state.sessionName),
      );
      return result.data;
    },
    staleTime: 10_000,
    retry: false,
  });
}

export function useSessionResults(id: string | null) {
  const backend = useAppStore((state) => state.backend);
  return useQuery<TestResultRecord[]>({
    queryKey: ["session", id, "results"],
    enabled: Boolean(id) && backend === "online",
    queryFn: async () => {
      if (!id) return [];
      const result = await resolveWithMock(
        () => api.results(id, 20),
        () => {
          const items = demoResultRecords();
          return { items, total: items.length, limit: 20, offset: 0 };
        },
      );
      return result.data.items;
    },
    staleTime: 15_000,
    retry: false,
  });
}

function demoResultRecords(): TestResultRecord[] {
  const state = useAppStore.getState();
  const results = state.results;
  const history = state.history.length > 0 ? state.history : createDemoHistory(state.inputs);
  return history.map((entry, index) => ({
    id: `demo-result-${index}`,
    test_type: entry.testType,
    result: {},
    decision: {
      status: entry.status,
      title: entry.title,
      summary: entry.summary,
      rule: "",
      margin: null,
    },
    computed_at: entry.at,
  }));
}

export interface SaveSessionResult {
  demo: boolean;
  session?: Session;
  revision?: number;
}

export function useSaveSession() {
  const queryClient = useQueryClient();
  return useMutation<SaveSessionResult, Error, { name?: string } | void>({
    mutationFn: async (arg) => {
      const state = useAppStore.getState();
      const name = (arg && arg.name) || state.sessionName;
      if (state.backend !== "online" || state.sessionApiReady === false) {
        await sleep(420);
        return { demo: true, revision: state.revision };
      }
      const realProjectId =
        state.projectId && !state.projectId.startsWith("demo-") ? state.projectId : null;
      if (!state.sessionId) {
        const created = await api.createSession({
          name,
          project_id: realProjectId,
          inputs: toApiInputs(state.inputs),
        });
        return { demo: false, session: created, revision: created.revision };
      }
      const updated = await api.updateSession(
        state.sessionId,
        {
          name,
          status: state.sessionStatus,
          project_id: realProjectId,
          inputs: toApiInputs(state.inputs),
        },
        state.revision,
      );
      return { demo: false, session: updated, revision: updated.revision };
    },
    onSuccess: (result) => {
      const store = useAppStore.getState();
      if (result.session) {
        store.setSessionMeta({
          id: result.session.id,
          name: result.session.name,
          revision: result.session.revision,
          status: result.session.status,
        });
      }
      store.markSaved(result.revision);
      store.pushToast(
        "success",
        result.demo ? "Tarayıcı oturumuna kaydedildi" : "Oturum kaydedildi",
        result.demo
          ? "Sunucu bağlantısı olmadığı için değişiklikler tarayıcıda tutuluyor."
          : `Revizyon ${result.revision ?? "-"} · ${new Date().toLocaleTimeString("tr-TR")}`,
      );
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
      void queryClient.invalidateQueries({ queryKey: ["session"] });
      void queryClient.invalidateQueries({ queryKey: ["project-scene"] });
    },
    onError: (error) => {
      useAppStore
        .getState()
        .pushToast("error", "Oturum kaydedilemedi", error.message);
    },
  });
}

export function useCreateSession() {
  const queryClient = useQueryClient();
  return useMutation<
    { session: Session; demo: boolean },
    Error,
    { name: string; inputs: Record<string, unknown>; projectId?: string | null }
  >({
    mutationFn: async ({ name, inputs, projectId }) => {
      const state = useAppStore.getState();
      if (state.backend !== "online" || state.sessionApiReady === false) {
        await sleep(360);
        return {
          demo: true,
          session: {
            ...createDemoSession(),
            name,
            project_id: projectId ?? state.projectId,
            revision: 0,
          },
        };
      }
      const rawProjectId = projectId ?? state.projectId;
      const realProjectId =
        rawProjectId && !rawProjectId.startsWith("demo-") ? rawProjectId : null;
      const session = await api.createSession({
        name,
        project_id: realProjectId,
        inputs,
      });
      return { demo: false, session };
    },
    onSuccess: ({ session, demo }) => {
      const store = useAppStore.getState();
      store.setSessionMeta({
        id: demo ? null : session.id,
        name: session.name,
        revision: session.revision,
        status: session.status,
      });
      store.pushToast(
        "success",
        "Yeni oturum oluşturuldu",
        demo ? "Çevrimdışı yerel oturum açıldı." : `${session.name} · revizyon ${session.revision}`,
      );
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
      /* Kesit sayısı proje kartlarında `section_count` olarak görünür. */
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      void queryClient.invalidateQueries({ queryKey: ["project-scene"] });
    },
    onError: (error) => {
      useAppStore.getState().pushToast("error", "Oturum açılamadı", error.message);
    },
  });
}

export function useDeleteSession() {
  const queryClient = useQueryClient();
  return useMutation<{ demo: boolean }, Error, string>({
    mutationFn: async (id) => {
      if (!isOnline()) {
        await sleep(240);
        return { demo: true };
      }
      await api.deleteSession(id);
      return { demo: false };
    },
    onSuccess: () => {
      useAppStore.getState().pushToast("info", "Oturum arşivlendi");
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
    },
    onError: (error) => {
      useAppStore.getState().pushToast("error", "Oturum silinemedi", error.message);
    },
  });
}

export function useSaveTestResult() {
  return useMutation<
    { saved: boolean; demo: boolean },
    Error,
    { testType: TestType; payload: Record<string, unknown>; status?: SessionStatus }
  >({
    mutationFn: async ({ testType, payload }) => {
      const state = useAppStore.getState();
      if (!state.sessionId || state.backend !== "online" || state.sessionApiReady === false) {
        return { saved: false, demo: true };
      }
      await api.saveResult(state.sessionId, { test_type: testType, payload }, state.revision);
      return { saved: true, demo: false };
    },
  });
}

/* ------------------------------------------------------------------ */
/* Katsayılar                                                          */
/* ------------------------------------------------------------------ */

export function useCoefficientA() {
  const store = useAppStore;
  return useMutation<Resolved<CoefficientAResponse>, Error, CoefficientARequest>({
    mutationFn: (request) =>
      resolveWithMock(
        () => api.coefficientA(request),
        () => computeA(request),
      ),
    onSuccess: ({ data, mode }) => {
      const state = store.getState();
      const bundle = { ...state.results.coefficients, pressureA: data };
      state.setResults({
        coefficients: bundle,
        source: mode,
      });
      state.addHistory({
        testType: "coefficient_a",
        title: "A katsayısı",
        status: "BASARILI",
        summary: `A = ${data.a_micro_per_bar} 10⁻⁶/bar · ${data.backend.label}`,
      });
    },
  });
}

export function useCoefficientB() {
  const store = useAppStore;
  return useMutation<Resolved<BSourceResult>, Error, CoefficientBRequest>({
    mutationFn: (request) =>
      resolveWithMock(
        () => api.coefficientB(request),
        () => computeB(request),
      ),
    onSuccess: ({ data, mode }) => {
      const state = store.getState();
      state.setResults({
        coefficients: { ...state.results.coefficients, pressureB: data },
        source: mode,
      });
      state.addHistory({
        testType: "coefficient_b",
        title: `B katsayısı · ${data.label}`,
        status: "BASARILI",
        summary: `B = ${data.b_micro_per_c} 10⁻⁶/°C · ${data.note}`,
      });
    },
  });
}

export function useCoefficientCompare() {
  const store = useAppStore;
  return useMutation<Resolved<BComparisonResponse>, Error, CoefficientCompareRequest>({
    mutationFn: (request) =>
      resolveWithMock(
        () => api.compareB(request),
        () => computeCompare(request),
      ),
    onSuccess: ({ data, mode }) => {
      store.getState().setResults({ bCompare: data, source: mode });
    },
  });
}

export function useBackendComparison() {
  const store = useAppStore;
  return useMutation<
    Resolved<BackendComparisonResponse>,
    Error,
    { temperature_c: number; pressure_bar: number }
  >({
    mutationFn: (request) =>
      resolveWithMock(
        () => api.backendComparison(request),
        () => computeBackendComparison(request.temperature_c, request.pressure_bar),
      ),
    onSuccess: ({ data, mode }) => {
      store.getState().setResults({ backendCompare: data, source: mode });
    },
  });
}

export function useTablePoint() {
  const store = useAppStore;
  return useMutation<
    Resolved<TablePointResponse>,
    Error,
    { table: "institutional" | "gail"; temperature_c: number; pressure_bar: number }
  >({
    mutationFn: (request) =>
      resolveWithMock(
        () => api.tablePoint({ ...request, repair_anomalies: true }),
        () => computeTablePoint(request.table, request.temperature_c, request.pressure_bar),
      ),
    onSuccess: ({ data, mode }) => {
      store.getState().setResults({ tablePoint: data, source: mode });
    },
  });
}

/* ------------------------------------------------------------------ */
/* Hesaplamalar                                                        */
/* ------------------------------------------------------------------ */

export function useCalculateGeometry() {
  const store = useAppStore;
  return useMutation<Resolved<GeometryResponse>, Error, GeometryIn["sections"]>({
    mutationFn: (sections) =>
      resolveWithMock(
        () => api.geometry({ sections }),
        () => computeGeometry(sections),
      ),
    onSuccess: ({ data, mode }) => {
      store.getState().setResults({ geometry: data, source: mode });
    },
  });
}

export function useCalculateAir() {
  const store = useAppStore;
  return useMutation<Resolved<AirContentResponse>, Error, AirContentRequest>({
    mutationFn: (request) =>
      resolveWithMock(
        () => api.airContent(request),
        () => computeAir(request),
      ),
    onSuccess: ({ data, mode }) => {
      const state = store.getState();
      state.setResults({ air: data, source: mode });
      state.addHistory({
        testType: "air",
        title: "Hava İçerik Testi",
        status: data.decision.status,
        summary: data.decision.summary,
      });
    },
  });
}

export function useCalculatePressure() {
  const store = useAppStore;
  return useMutation<Resolved<PressureVariationResponse>, Error, PressureVariationRequest>({
    mutationFn: (request) =>
      resolveWithMock(
        () => api.pressureVariation(request),
        () => computePressure(request),
      ),
    onSuccess: ({ data, mode }) => {
      const state = store.getState();
      state.setResults({ pressure: data, source: mode });
      state.addHistory({
        testType: "pressure",
        title: "Basınç Değişim Testi",
        status: data.decision.status,
        summary: data.decision.summary,
      });
    },
  });
}

export function useCalculateProfile() {
  const store = useAppStore;
  return useMutation<Resolved<PressureProfileResponse>, Error, PressureProfileRequest>({
    mutationFn: (request) =>
      resolveWithMock(
        () => api.pressureProfile(request),
        () => computeProfile(request),
      ),
    onSuccess: ({ data, mode }) => {
      store.getState().setResults({ profile: data, source: mode });
    },
  });
}

export function useCalculatePig() {
  const store = useAppStore;
  return useMutation<Resolved<PigSpeedResponse>, Error, PigSpeedRequest>({
    mutationFn: (request) =>
      resolveWithMock(
        () => api.pigSpeed(request),
        () => computePig(request),
      ),
    onSuccess: ({ data, mode }) => {
      store.getState().setResults({ pig: data, source: mode });
    },
  });
}

/* ------------------------------------------------------------------ */
/* OCR                                                                 */
/* ------------------------------------------------------------------ */

export function useOcrStatus() {
  return useQuery<OcrStatusResponse>({
    queryKey: ["ocr", "status"],
    queryFn: async () => {
      const result = await resolveWithMock(
        () => api.ocrStatus(),
        () => DEMO_OCR_STATUS,
      );
      return result.data;
    },
    initialData: DEMO_OCR_STATUS,
    initialDataUpdatedAt: 0,
    staleTime: 30_000,
  });
}

/* ------------------------------------------------------------------ */
/* Güncelleme Yöneticisi                                               */
/* ------------------------------------------------------------------ */

export function useUpdateStatus() {
  const backend = useAppStore((state) => state.backend);
  return useQuery<UpdateManagerStatus>({
    queryKey: ["update", "status"],
    queryFn: () => api.updateStatus(),
    enabled: backend === "online",
    staleTime: 30_000,
    retry: false,
    refetchInterval: (query) => {
      const st = query.state.data?.job?.state;
      return st === "checking" || st === "downloading" || st === "verifying" || st === "installing"
        ? 1_000
        : false;
    },
  });
}

export function useCheckUpdates() {
  const queryClient = useQueryClient();
  return useMutation<UpdateManagerStatus, Error, { force?: boolean; silent?: boolean } | void>({
    mutationFn: async (opts) => api.checkUpdates(opts?.force ?? true),
    onSuccess: (status, vars) => {
      queryClient.setQueryData(["update", "status"], status);
      if (vars && vars.silent) return;
      if (status.check_error) {
        useAppStore
          .getState()
          .pushToast("warning", "Güncelleme denetimi başarısız", status.check_error);
      } else if (status.update_available && status.latest_version) {
        useAppStore
          .getState()
          .pushToast(
            "info",
            `Yeni sürüm hazır: v${status.latest_version}`,
            "Güncelleme Yöneticisi üzerinden indirip doğrulayabilirsiniz.",
          );
      } else {
        useAppStore
          .getState()
          .pushToast("success", "Uygulama güncel", `Sürüm v${status.current_version} en güncel sürümdür.`);
      }
    },
    onError: (error, vars) => {
      if (vars && vars.silent) return;
      useAppStore.getState().pushToast("warning", "Güncelleme kontrolü yapılamadı", error.message);
    },
  });
}

export function useStartUpdateDownload() {
  const queryClient = useQueryClient();
  return useMutation<UpdateManagerStatus, Error, { assetName?: string } | void>({
    mutationFn: async (opts) => api.startUpdateDownload(opts?.assetName),
    onSuccess: (status) => {
      queryClient.setQueryData(["update", "status"], status);
      useAppStore
        .getState()
        .pushToast(
          "info",
          "Güncelleme indiriliyor",
          "SHA-256 ve Ed25519 dijital imza doğrulaması otomatik yapılacaktır.",
        );
    },
    onError: (error) => {
      useAppStore.getState().pushToast("error", "İndirme başlatılamadı", error.message);
    },
  });
}

export function useApplyUpdate() {
  const queryClient = useQueryClient();
  return useMutation<UpdateManagerStatus, Error, void>({
    mutationFn: async () => api.applyUpdate(),
    onSuccess: (status) => {
      queryClient.setQueryData(["update", "status"], status);
      useAppStore
        .getState()
        .pushToast(
          "success",
          "Kurulum başlatıldı",
          status.job?.message || "Uygulama güncellenip yeniden başlatılıyor...",
        );
    },
    onError: (error) => {
      useAppStore.getState().pushToast("error", "Kurulum başlatılamadı", error.message);
    },
  });
}

/* ------------------------------------------------------------------ */
/* Yardımcılar                                                         */
/* ------------------------------------------------------------------ */

export function refreshDerivedPreview() {
  const state = useAppStore.getState();
  const results = buildDemoResults(state.inputs);
  state.setResults(results);
  return results;
}

/* ------------------------------------------------------------------ */
/* Proje Veri Merkezi, Üreticiler, Arşiv & DB Yönetimi Hooks           */
/* ------------------------------------------------------------------ */

export function useProjectDataset(projectId: string | null, enabled = true) {
  const backend = useAppStore((state) => state.backend);
  return useQuery<import("../lib/types").ProjectDatasetResponse>({
    queryKey: ["project-dataset", projectId],
    enabled: Boolean(projectId) && enabled && backend === "online",
    queryFn: () => api.projectDataset(projectId!),
    staleTime: 10_000,
    retry: false,
  });
}

export function useGenerateProjectSections() {
  const queryClient = useQueryClient();
  return useMutation<
    import("../lib/types").ProjectGenerateSectionsResponse,
    Error,
    { projectId: string; payload: import("../lib/types").ProjectGenerateSectionsPayload }
  >({
    mutationFn: ({ projectId, payload }) => api.generateProjectSections(projectId, payload),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
      void queryClient.invalidateQueries({ queryKey: ["project-dataset", data.project_id] });
      void queryClient.invalidateQueries({ queryKey: ["project-scene"] });
      useAppStore
        .getState()
        .pushToast(
          "success",
          "Toplu kesitler oluşturuldu",
          `${data.created_count} kesit (${Math.round(data.target_section_length_m)} m hedef aralıkla) projeye eklendi.`,
        );
    },
    onError: (error) => {
      useAppStore.getState().pushToast("error", "Toplu kesit oluşturulamadı", error.message);
    },
  });
}

export function useSyncProjectForms() {
  const queryClient = useQueryClient();
  return useMutation<
    import("../lib/types").ProjectSyncFormsResponse,
    Error,
    { projectId: string; overwriteExisting?: boolean; formCodes?: string[] }
  >({
    mutationFn: ({ projectId, overwriteExisting = false, formCodes }) =>
      api.syncProjectForms(projectId, {
        overwrite_existing: overwriteExisting,
        form_codes: formCodes,
      }),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
      void queryClient.invalidateQueries({ queryKey: ["session-forms"] });
      void queryClient.invalidateQueries({ queryKey: ["project-dataset", data.project_id] });
      useAppStore
        .getState()
        .pushToast(
          "success",
          "Form başlıkları eşitlendi",
          `${data.sessions_processed} kesitte ${data.updated_forms} BOTAŞ formu güncellendi.`,
        );
    },
    onError: (error) => {
      useAppStore.getState().pushToast("error", "Form eşitleme başarısız", error.message);
    },
  });
}

export function useGenerateSampleProject() {
  const queryClient = useQueryClient();
  return useMutation<
    { project: Project; sections: SessionListItem[] },
    Error,
    import("../lib/types").SampleProjectPayload
  >({
    mutationFn: (payload) => api.generateSampleProject(payload),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
      void queryClient.invalidateQueries({ queryKey: ["db-stats"] });
      useAppStore
        .getState()
        .pushToast(
          "success",
          "Örnek proje üretildi",
          `${data.project.name} (${data.sections.length} kesit) veritabanına kaydedildi.`,
        );
    },
    onError: (error) => {
      useAppStore.getState().pushToast("error", "Örnek proje üretilemedi", error.message);
    },
  });
}

export function useCloneProject() {
  const queryClient = useQueryClient();
  return useMutation<
    { project: Project; section_count: number; mode: string },
    Error,
    { projectId: string; payload: import("../lib/types").ProjectClonePayload }
  >({
    mutationFn: ({ projectId, payload }) => api.cloneProject(projectId, payload),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
      void queryClient.invalidateQueries({ queryKey: ["db-stats"] });
      useAppStore
        .getState()
        .pushToast(
          "success",
          "Proje klonlandı",
          `${data.project.name} (${data.section_count} kesit · ${data.mode === "template" ? "Şablon" : "Tam"}) oluşturuldu.`,
        );
    },
    onError: (error) => {
      useAppStore.getState().pushToast("error", "Proje klonlanamadı", error.message);
    },
  });
}

export function useImportProjectArchive() {
  const queryClient = useQueryClient();
  return useMutation<
    import("../lib/types").ArchiveImportResponse,
    Error,
    { file: File; targetProjectName?: string; targetProjectCode?: string; includeAttachments?: boolean }
  >({
    mutationFn: (params) => api.importProjectArchive(params),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
      void queryClient.invalidateQueries({ queryKey: ["db-stats"] });
      useAppStore
        .getState()
        .pushToast(
          "success",
          "Proje arşivi içe aktarıldı",
          `${data.project.name}: ${data.imported_sections} kesit, ${data.imported_forms} form, ${data.imported_attachments} ek yüklendi.`,
        );
    },
    onError: (error) => {
      useAppStore.getState().pushToast("error", "Arşiv içe aktarılamadı", error.message);
    },
  });
}

export function useImportDesktopDb() {
  const queryClient = useQueryClient();
  return useMutation<
    import("../lib/types").DesktopDbImportResponse,
    Error,
    { file: File; projectName?: string; projectCode?: string }
  >({
    mutationFn: (params) => api.importDesktopDb(params),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
      void queryClient.invalidateQueries({ queryKey: ["db-stats"] });
      useAppStore
        .getState()
        .pushToast(
          "success",
          "Masaüstü veritabanı aktarıldı",
          `${data.project.name}: ${data.imported_sessions} kesit, ${data.imported_results} sonuç, ${data.imported_time_series} zaman kaydı eklendi.`,
        );
    },
    onError: (error) => {
      useAppStore.getState().pushToast("error", "Masaüstü DB aktarılamadı", error.message);
    },
  });
}

export function useDbStats(enabled = true) {
  const backend = useAppStore((state) => state.backend);
  return useQuery<import("../lib/types").DbStatsResponse>({
    queryKey: ["db-stats"],
    enabled: backend === "online" && enabled,
    queryFn: () => api.dbStats(),
    staleTime: 10_000,
    retry: false,
  });
}

export function useDbBackups(enabled = true) {
  const backend = useAppStore((state) => state.backend);
  return useQuery<import("../lib/types").DbBackupsResponse>({
    queryKey: ["db-backups"],
    enabled: backend === "online" && enabled,
    queryFn: () => api.dbBackups(),
    staleTime: 10_000,
    retry: false,
  });
}

export function useCreateDbBackup() {
  const queryClient = useQueryClient();
  return useMutation<import("../lib/types").DbBackupItem, Error, string | void>({
    mutationFn: (reason) => api.createDbBackup(reason || "manual"),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: ["db-backups"] });
      void queryClient.invalidateQueries({ queryKey: ["db-stats"] });
      useAppStore
        .getState()
        .pushToast("success", "Anlık yedek alındı", `${data.filename} başarıyla kaydedildi.`);
    },
    onError: (error) => {
      useAppStore.getState().pushToast("error", "Yedek alınamadı", error.message);
    },
  });
}

export function useRestoreDbBackup() {
  const queryClient = useQueryClient();
  return useMutation<
    import("../lib/types").DbRestoreResponse,
    Error,
    { backupFilename?: string; file?: File }
  >({
    mutationFn: (params) => api.restoreDbBackup(params),
    onSuccess: (data) => {
      void queryClient.invalidateQueries();
      useAppStore
        .getState()
        .pushToast(
          "success",
          "Veritabanı geri yüklendi",
          `Kaynak: ${data.source}. Güvenlik amacıyla geri yükleme öncesi yedek de alındı.`,
        );
    },
    onError: (error) => {
      useAppStore.getState().pushToast("error", "Geri yükleme başarısız", error.message);
    },
  });
}

export function useTrash(enabled = true) {
  const backend = useAppStore((state) => state.backend);
  return useQuery<import("../lib/types").TrashResponse>({
    queryKey: ["trash"],
    enabled: backend === "online" && enabled,
    queryFn: () => api.trash(),
    staleTime: 10_000,
    retry: false,
  });
}

export function useRestoreTrashItem() {
  const queryClient = useQueryClient();
  return useMutation<
    { entity_type: string; id: string; restored_sessions: number },
    Error,
    { entityType: "project" | "session"; entityId: string }
  >({
    mutationFn: ({ entityType, entityId }) => api.restoreTrash(entityType, entityId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["trash"] });
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
      void queryClient.invalidateQueries({ queryKey: ["db-stats"] });
      useAppStore.getState().pushToast("success", "Kayıt geri yüklendi");
    },
    onError: (error) => {
      useAppStore.getState().pushToast("error", "Geri yüklenemedi", error.message);
    },
  });
}

export function usePurgeTrashItem() {
  const queryClient = useQueryClient();
  return useMutation<
    { purged: boolean; entity_type: string; id: string },
    Error,
    { entityType: "project" | "session"; entityId: string }
  >({
    mutationFn: ({ entityType, entityId }) => api.purgeTrash(entityType, entityId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["trash"] });
      void queryClient.invalidateQueries({ queryKey: ["db-stats"] });
      useAppStore.getState().pushToast("info", "Kayıt kalıcı olarak silindi");
    },
    onError: (error) => {
      useAppStore.getState().pushToast("error", "Kalıcı silme başarısız", error.message);
    },
  });
}

export function useWorkspaces(enabled = true) {
  const backend = useAppStore((state) => state.backend);
  return useQuery<import("../lib/types").WorkspacesResponse>({
    queryKey: ["workspaces"],
    enabled: backend === "online" && enabled,
    queryFn: () => api.workspaces(),
    staleTime: 15_000,
    retry: false,
  });
}

export function useClaimWorkspace() {
  const queryClient = useQueryClient();
  return useMutation<
    { source_workspace_hash: string; target_workspace_hash: string; moved: Record<string, number> },
    Error,
    { sourceHash: string; sourceKey?: string }
  >({
    mutationFn: ({ sourceHash, sourceKey }) => api.claimWorkspace(sourceHash, sourceKey),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: ["workspaces"] });
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
      void queryClient.invalidateQueries({ queryKey: ["db-stats"] });
      useAppStore
        .getState()
        .pushToast(
          "success",
          "Çalışma alanı devralındı",
          `${data.moved.projects ?? 0} proje ve ${data.moved.sessions ?? 0} kesit mevcut çalışma alanına taşındı.`,
        );
    },
    onError: (error) => {
      useAppStore.getState().pushToast("error", "Devralma başarısız", error.message);
    },
  });
}

export function useRunDbMaintenance() {
  const queryClient = useQueryClient();
  return useMutation<
    import("../lib/types").DbMaintenanceResponse,
    Error,
    import("../lib/types").DbMaintenancePayload
  >({
    mutationFn: (payload) => api.runDbMaintenance(payload),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: ["db-stats"] });
      useAppStore
        .getState()
        .pushToast(
          "success",
          "Veritabanı bakımı tamamlandı",
          `Bütünlük: ${data.integrity_status} · Silinen çıktı: ${data.removed_export_files} · Yetim dosya: ${data.removed_orphan_files}`,
        );
    },
    onError: (error) => {
      useAppStore.getState().pushToast("error", "Bakım çalıştırılamadı", error.message);
    },
  });
}
