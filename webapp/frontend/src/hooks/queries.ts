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
  PressureProfileRequest,
  PressureProfileResponse,
  PressureVariationRequest,
  PressureVariationResponse,
  Project,
  ProjectInput,
  ReferenceTableMeta,
  Session,
  SessionListItem,
  SessionStatus,
  SpecResponse,
  TablePointResponse,
  TestResultRecord,
  TestType,
} from "../lib/types";
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
      // Yalnızca ağ hatasında tüm uygulamayı demo moduna al. 404/500 gibi
      // uç-bazlı eksikler yerel yedeğe düşer, sağlık durumu korunur.
      if (error instanceof ApiError && error.status === 0) {
        useAppStore.getState().setBackend("demo");
      }
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
  return useQuery<HealthResponse | null>({
    queryKey: ["health"],
    queryFn: async () => {
      try {
        const raw = await api.health();
        const health = normalizeHealth(raw as unknown as Record<string, unknown>);
        useAppStore.getState().setBackend("online", health);
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

export function useSessions(projectId?: string | null) {
  return useQuery<SessionListItem[]>({
    queryKey: ["sessions", projectId ?? "all"],
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
  return useQuery<Project[]>({
    queryKey: ["projects"],
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
      if (store.projectId === id) store.setProject(null);
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
      store.pushToast("success", "Proje silindi", removed?.name ?? "Proje arşivlendi.");
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

export function useOpenSession() {
  const queryClient = useQueryClient();
  return useMutation<Session, Error, string>({
    mutationFn: async (id) => {
      const state = useAppStore.getState();
      if (state.backend !== "online" || id.startsWith("demo-")) {
        await sleep(240);
        return demoSessionDetail(state.inputs, state.sessionName);
      }
      return api.session(id);
    },
    onSuccess: (session) => {
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
      store.pushToast("success", "Kesit açıldı", session.name);
    },
    onError: (error) => {
      useAppStore.getState().pushToast("error", "Kesit açılamadı", error.message);
    },
  });
}

export function useSessionDetail(id: string | null) {
  return useQuery<Session>({
    queryKey: ["session", id],
    enabled: Boolean(id) && isOnline(),
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
  return useQuery<TestResultRecord[]>({
    queryKey: ["session", id, "results"],
    enabled: Boolean(id) && isOnline(),
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
        result.demo ? "Yerel demo oturumuna kaydedildi" : "Oturum kaydedildi",
        result.demo
          ? "Backend bağlı olmadığı için değişiklikler tarayıcıda tutuluyor."
          : `Revizyon ${result.revision ?? "-"} · ${new Date().toLocaleTimeString("tr-TR")}`,
      );
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
      void queryClient.invalidateQueries({ queryKey: ["session"] });
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
        demo ? "Demo modunda yerel oturum açıldı." : `${session.name} · revizyon ${session.revision}`,
      );
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
      /* Kesit sayısı proje kartlarında `section_count` olarak görünür. */
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
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
/* Yardımcılar                                                         */
/* ------------------------------------------------------------------ */

export function refreshDerivedPreview() {
  const state = useAppStore.getState();
  const results = buildDemoResults(state.inputs);
  state.setResults(results);
  return results;
}
