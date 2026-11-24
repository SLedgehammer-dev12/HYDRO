import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type {
  AppInputs,
  BackendMode,
  BotasFormCode,
  ExportEntry,
  HealthResponse,
  HistoryEntry,
  InputPatch,
  ResultBundle,
  SessionStatus,
  TabKey,
  ToastItem,
  ToastTone,
} from "../lib/types";
import {
  buildDemoResults,
  createDefaultInputs,
  createDemoHistory,
  createEmptyInputs,
} from "../lib/mock";
import { normalizeInputs } from "../lib/normalize";
import { nowIso } from "../lib/format";
import type { RevisionConflictState } from "../lib/sessionDiff";

export const PERSIST_KEY = "hydro-app-v1";

const makeId = (prefix: string): string =>
  `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;

const GEOMETRY_AFFECTING_KEYS = new Set<keyof AppInputs>([
  "geometry",
  "geometry_catalog",
  "segments",
  "section_profile",
  "material_grade",
]);

function freshState(empty = false) {
  const inputs = empty ? createEmptyInputs() : createDefaultInputs();
  return {
    inputs,
    results: buildDemoResults(inputs),
    history: empty ? [] : createDemoHistory(inputs),
  };
}

const initial = freshState();

export interface AppStore {
  tab: TabKey;
  activeFormCode: BotasFormCode;
  updateModalOpen: boolean;
  revisionConflict: RevisionConflictState | null;
  pendingScrollTarget: string | null;
  sessionId: string | null;
  sessionName: string;
  sessionStatus: SessionStatus;
  revision: number;
  dirty: boolean;

  projectId: string | null;
  projectName: string;
  projectCode: string;

  inputs: AppInputs;
  results: ResultBundle;

  theme: "dark" | "light";
  sidebarOpen: boolean;
  desktopSidebarOpen: boolean;
  rightPanelOpen: boolean;
  sceneScope: "section" | "project";
  onboardingDismissed: boolean;
  tourActive: boolean;
  tourStep: number;
  tourSampleProjectId: string | null;
  activeOcrJob: { id: string; fileName: string; stage: string } | null;

  backend: BackendMode;
  health: HealthResponse | null;
  lastBackendCheck: string | null;
  /** `/api/sessions` hazır mı? Health çalışırken oturum ucu 404 dönebilir. */
  sessionApiReady: boolean | null;
  pendingServerSync: boolean;
  storageQuotaError: boolean;

  history: HistoryEntry[];
  exports: ExportEntry[];
  toasts: ToastItem[];

  setTab: (tab: TabKey) => void;
  setActiveFormCode: (code: BotasFormCode) => void;
  openForm: (code: BotasFormCode) => void;
  setUpdateModalOpen: (open: boolean) => void;
  setRevisionConflict: (conflict: RevisionConflictState | null) => void;
  setPendingScrollTarget: (target: string | null) => void;
  setSessionMeta: (meta: {
    id?: string | null;
    name?: string;
    revision?: number;
    status?: SessionStatus;
  }) => void;
  setSessionName: (name: string) => void;
  setProject: (project: { id: string; name: string; code?: string } | null) => void;
  markDirty: () => void;
  markSaved: (revision?: number) => void;

  patchInputs: (patch: InputPatch) => void;
  setSegments: (segments: AppInputs["segments"]) => void;
  setProfilePoints: (points: AppInputs["profile_points"]) => void;
  setEquipment: (items: AppInputs["equipment"]) => void;
  updateSegment: (id: string, patch: Partial<AppInputs["segments"][number]>) => void;
  addSegment: () => void;
  removeSegment: (id: string) => void;
  moveSegment: (id: string, direction: -1 | 1) => void;
  toggleCheck: (key: keyof AppInputs["checks"]) => void;

  applySessionInputs: (raw: unknown) => void;
  setResults: (patch: Partial<ResultBundle>) => void;
  clearResults: () => void;

  setTheme: (theme: "dark" | "light") => void;
  toggleTheme: () => void;
  setSidebarOpen: (open: boolean) => void;
  toggleSidebar: () => void;
  toggleDesktopSidebar: () => void;
  toggleRightPanel: () => void;
  setSceneScope: (scope: "section" | "project") => void;

  setBackend: (mode: BackendMode, health?: HealthResponse | null) => void;
  setSessionApiReady: (ready: boolean | null) => void;
  setPendingServerSync: (pending: boolean) => void;
  setStorageQuotaError: (flag: boolean) => void;
  setOnboardingDismissed: (dismissed: boolean) => void;
  startTour: (sampleProjectId?: string | null) => void;
  setTourStep: (step: number) => void;
  endTour: () => void;
  setActiveOcrJob: (job: { id: string; fileName: string; stage: string } | null) => void;

  addHistory: (entry: Omit<HistoryEntry, "id" | "at"> & { at?: string }) => void;
  addExport: (entry: Omit<ExportEntry, "id" | "at"> & { at?: string }) => void;

  pushToast: (tone: ToastTone, title: string, description?: string) => void;
  dismissToast: (id: string) => void;

  resetSession: (name?: string) => void;
  clearLocalData: () => void;
}

export const useAppStore = create<AppStore>()(
  persist(
    (set, get) => ({
      tab: "dashboard",
      activeFormCode: "test_data",
      updateModalOpen: false,
      revisionConflict: null,
      pendingScrollTarget: null,
      sessionId: null,
      sessionName: "Bölüm 12–13 · Doğu Hattı",
      sessionStatus: "active",
      revision: 3,
      dirty: false,

      projectId: "demo-project-001",
      projectName: "Doğu Hattı Hidrostatik Testi",
      projectCode: "PRJ-DOGU-12",

      inputs: initial.inputs,
      results: initial.results,

      theme: "dark",
      sidebarOpen: false,
      desktopSidebarOpen: true,
      rightPanelOpen: false,
      sceneScope: "section",
      onboardingDismissed: false,
      tourActive: false,
      tourStep: 0,
      tourSampleProjectId: null,
      activeOcrJob: null,

      backend: "checking",
      health: null,
      lastBackendCheck: null,
      sessionApiReady: null,
      pendingServerSync: false,
      storageQuotaError: false,

      history: initial.history,
      exports: [],
      toasts: [],

      setTab: (tab) => set({ tab }),
      setActiveFormCode: (activeFormCode) => set({ activeFormCode }),
      openForm: (activeFormCode) => set({ tab: "forms", activeFormCode }),
      setUpdateModalOpen: (updateModalOpen) => set({ updateModalOpen }),
      setRevisionConflict: (revisionConflict) => set({ revisionConflict }),
      setPendingScrollTarget: (pendingScrollTarget) => set({ pendingScrollTarget }),

      setSessionMeta: (meta) =>
        set((state) => ({
          sessionId: meta.id === undefined ? state.sessionId : meta.id,
          sessionName: meta.name ?? state.sessionName,
          revision: meta.revision ?? state.revision,
          sessionStatus: meta.status ?? state.sessionStatus,
        })),

      setSessionName: (sessionName) => set({ sessionName, dirty: true }),

      setProject: (project) =>
        set({
          projectId: project?.id ?? null,
          projectName: project?.name ?? "",
          projectCode: project?.code ?? "",
        }),

      markDirty: () => set({ dirty: true }),
      markSaved: (revision) =>
        set((state) => ({ dirty: false, revision: revision ?? state.revision })),

      patchInputs: (patch) =>
        set((state) => {
          const merged: AppInputs = { ...state.inputs };
          let geometryAffected = false;
          for (const key of Object.keys(patch) as Array<keyof AppInputs>) {
            if (GEOMETRY_AFFECTING_KEYS.has(key)) geometryAffected = true;
            const update = patch[key];
            if (update === undefined) continue;
            const current = merged[key];
            if (Array.isArray(current) || typeof current === "string") {
              (merged as unknown as Record<string, unknown>)[key] = update;
            } else {
              (merged as unknown as Record<string, unknown>)[key] = {
                ...(current as Record<string, unknown>),
                ...(update as Record<string, unknown>),
              };
            }
          }
          return {
            inputs: merged,
            dirty: true,
            ...(geometryAffected
              ? { results: { ...state.results, geometry: undefined } }
              : {}),
          };
        }),

      setSegments: (segments) =>
        set((state) => ({
          inputs: { ...state.inputs, segments },
          dirty: true,
          results: { ...state.results, geometry: undefined },
        })),

      setProfilePoints: (profile_points) =>
        set((state) => ({ inputs: { ...state.inputs, profile_points }, dirty: true })),

      setEquipment: (equipment) =>
        set((state) => ({ inputs: { ...state.inputs, equipment }, dirty: true })),

      updateSegment: (id, patch) =>
        set((state) => ({
          inputs: {
            ...state.inputs,
            segments: state.inputs.segments.map((segment) =>
              segment.id === id ? { ...segment, ...patch } : segment,
            ),
          },
          dirty: true,
          results: { ...state.results, geometry: undefined },
        })),

      addSegment: () =>
        set((state) => {
          const last = state.inputs.segments[state.inputs.segments.length - 1];
          const nextStation = last
            ? (last.start_station_m ?? 0) + (last.length_m ?? 0)
            : 0;
          const segment = {
            id: makeId("seg"),
            nps_label: state.inputs.geometry_catalog.size_option.replace(/\s*-\s*OD.*$/, ""),
            schedule_label: state.inputs.geometry_catalog.schedule_option,
            outside_diameter_mm: state.inputs.geometry.outside_diameter_mm ?? 406.4,
            wall_thickness_mm: state.inputs.geometry.wall_thickness_mm ?? 8.74,
            length_m: 1_000,
            start_station_m: nextStation,
            material_grade: "",
            smys_mpa: null,
          };
          return {
            inputs: { ...state.inputs, segments: [...state.inputs.segments, segment] },
            dirty: true,
            results: { ...state.results, geometry: undefined },
          };
        }),

      removeSegment: (id) =>
        set((state) => {
          const segments = state.inputs.segments.filter((segment) => segment.id !== id);
          let station = 0;
          const renumbered = segments.map((segment) => {
            const next = { ...segment, start_station_m: station };
            station += segment.length_m ?? 0;
            return next;
          });
          return {
            inputs: { ...state.inputs, segments: renumbered },
            dirty: true,
            results: { ...state.results, geometry: undefined },
          };
        }),

      moveSegment: (id, direction) =>
        set((state) => {
          const segments = [...state.inputs.segments];
          const index = segments.findIndex((segment) => segment.id === id);
          const target = index + direction;
          if (index < 0 || target < 0 || target >= segments.length) return state;
          const [item] = segments.splice(index, 1);
          segments.splice(target, 0, item);
          let station = 0;
          const renumbered = segments.map((segment) => {
            const next = { ...segment, start_station_m: station };
            station += segment.length_m ?? 0;
            return next;
          });
          return {
            inputs: { ...state.inputs, segments: renumbered },
            dirty: true,
            results: { ...state.results, geometry: undefined },
          };
        }),

      toggleCheck: (key) =>
        set((state) => ({
          inputs: {
            ...state.inputs,
            checks: { ...state.inputs.checks, [key]: !state.inputs.checks[key] },
          },
          dirty: true,
        })),

      applySessionInputs: (raw) => {
        const inputs = normalizeInputs(raw);
        set({ inputs, results: buildDemoResults(inputs) });
      },

      setResults: (patch) =>
        set((state) => ({
          results: { ...state.results, ...patch, lastComputedAt: patch.lastComputedAt ?? nowIso() },
        })),

      clearResults: () => {
        const inputs = get().inputs;
        set({ results: buildDemoResults(inputs) });
      },

      setTheme: (theme) => {
        if (typeof document !== "undefined") {
          document.documentElement.dataset.theme = theme;
        }
        set({ theme });
      },

      toggleTheme: () => {
        const theme = get().theme === "dark" ? "light" : "dark";
        if (typeof document !== "undefined") {
          document.documentElement.dataset.theme = theme;
        }
        set({ theme });
      },

      setSidebarOpen: (sidebarOpen) => set({ sidebarOpen }),
      toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
      toggleDesktopSidebar: () =>
        set((state) => ({ desktopSidebarOpen: !state.desktopSidebarOpen })),
      toggleRightPanel: () => set((state) => ({ rightPanelOpen: !state.rightPanelOpen })),
      setSceneScope: (sceneScope) => set({ sceneScope }),

      setBackend: (backend, health) =>
        set({
          backend,
          health: health === undefined ? get().health : health,
          lastBackendCheck: nowIso(),
          sessionApiReady: backend === "demo" ? false : get().sessionApiReady,
        }),

      setSessionApiReady: (sessionApiReady) => set({ sessionApiReady }),
      setPendingServerSync: (pendingServerSync) => set({ pendingServerSync }),
      setStorageQuotaError: (storageQuotaError) => set({ storageQuotaError }),
      setOnboardingDismissed: (onboardingDismissed) => set({ onboardingDismissed }),
      startTour: (sampleProjectId = null) =>
        set({
          tourActive: true,
          tourStep: 0,
          tourSampleProjectId: sampleProjectId ?? null,
          onboardingDismissed: true,
        }),
      setTourStep: (tourStep) => set({ tourStep: Math.max(0, tourStep) }),
      endTour: () => set({ tourActive: false, tourStep: 0, tourSampleProjectId: null }),
      setActiveOcrJob: (activeOcrJob) => set({ activeOcrJob }),

      addHistory: (entry) =>
        set((state) => ({
          history: [
            { ...entry, id: makeId("hist"), at: entry.at ?? nowIso() },
            ...state.history,
          ].slice(0, 24),
        })),

      addExport: (entry) =>
        set((state) => ({
          exports: [
            { ...entry, id: makeId("exp"), at: entry.at ?? nowIso() },
            ...state.exports,
          ].slice(0, 16),
        })),

      pushToast: (tone, title, description) =>
        set((state) => ({
          toasts: [...state.toasts, { id: makeId("toast"), tone, title, description }].slice(-4),
        })),

      dismissToast: (id) =>
        set((state) => ({ toasts: state.toasts.filter((toast) => toast.id !== id) })),

      resetSession: (name) => {
        const state = freshState(true);
        set({
          ...state,
          sessionId: null,
          sessionName: name ?? "Yeni Test Bölümü",
          sessionStatus: "draft",
          revision: 0,
          dirty: false,
          revisionConflict: null,
          exports: [],
        });
      },

      clearLocalData: () => {
        try {
          localStorage.removeItem(PERSIST_KEY);
        } catch {
          /* yoksay */
        }
        const state = freshState();
        set({
          ...state,
          sessionId: null,
          sessionName: "Yeni Test Bölümü",
          sessionStatus: "draft",
          revision: 0,
          dirty: false,
          revisionConflict: null,
          pendingServerSync: false,
          storageQuotaError: false,
          projectId: null,
          projectName: "",
          projectCode: "",
          exports: [],
          toasts: [],
          tab: "projects",
        });
      },
    }),
    {
      name: PERSIST_KEY,
      storage: createJSONStorage(() => ({
        getItem: (name: string) => {
          try {
            return localStorage.getItem(name);
          } catch {
            return null;
          }
        },
        setItem: (name: string, value: string) => {
          try {
            localStorage.setItem(name, value);
            if (useAppStore?.getState?.().storageQuotaError) {
              useAppStore.setState({ storageQuotaError: false });
            }
          } catch {
            if (useAppStore?.setState) {
              useAppStore.setState({ storageQuotaError: true });
            }
          }
        },
        removeItem: (name: string) => {
          try {
            localStorage.removeItem(name);
          } catch {
            /* yoksay */
          }
        },
      })),
      partialize: (state) => ({
        tab: state.tab,
        activeFormCode: state.activeFormCode,
        sessionId: state.sessionId,
        sessionName: state.sessionName,
        sessionStatus: state.sessionStatus,
        revision: state.revision,
        pendingServerSync: state.pendingServerSync,
        projectId: state.projectId,
        projectName: state.projectName,
        projectCode: state.projectCode,
        inputs: state.inputs,
        results: state.results,
        history: state.history,
        exports: state.exports,
        theme: state.theme,
        rightPanelOpen: state.rightPanelOpen,
        onboardingDismissed: state.onboardingDismissed,
      }),
      /**
       * Eski sürümlerden gelen `inputs` şeması eksik olabilir (ör. `section_meta`).
       * Kayıtlı durumu her zaman güncel varsayılanlarla birleştirip normalize
       * ediyoruz; aksi halde ilk render eksik alana erişip çöker.
       */
      merge: (persisted, current) => {
        const saved = (persisted ?? {}) as Partial<AppStore>;
        return {
          ...current,
          ...saved,
          inputs: normalizeInputs(saved.inputs),
        };
      },
      onRehydrateStorage: () => (state) => {
        if (state?.theme && typeof document !== "undefined") {
          document.documentElement.dataset.theme = state.theme;
        }
      },
    },
  ),
);
