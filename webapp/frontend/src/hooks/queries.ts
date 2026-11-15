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

export function useSessions() {
  return useQuery<SessionListItem[]>({
    queryKey: ["sessions"],
    queryFn: async () => {
      const state = useAppStore.getState();
      const fallback = () => ({
        items: demoSessions(state.inputs, state.sessionName),
        total: 3,
        limit: 50,
        offset: 0,
      });
      if (state.backend === "demo") {
        state.setSessionApiReady(false);
        return fallback().items;
      }
      try {
        const response = await api.sessions();
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
    initialData: DEMO_SESSION_LIST_FALLBACK(),
    initialDataUpdatedAt: 0,
    staleTime: 20_000,
  });
}

function DEMO_SESSION_LIST_FALLBACK(): SessionListItem[] {
  const state = useAppStore.getState();
  return demoSessions(state.inputs, state.sessionName);
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
      if (!state.sessionId) {
        const created = await api.createSession({
          name,
          inputs: toApiInputs(state.inputs),
        });
        return { demo: false, session: created, revision: created.revision };
      }
      const updated = await api.updateSession(
        state.sessionId,
        {
          name,
          status: state.sessionStatus,
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
    { name: string; inputs: Record<string, unknown> }
  >({
    mutationFn: async ({ name, inputs }) => {
      const state = useAppStore.getState();
      if (state.backend !== "online" || state.sessionApiReady === false) {
        await sleep(360);
        return { demo: true, session: { ...createDemoSession(), name, revision: 0 } };
      }
      const session = await api.createSession({ name, inputs });
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
