import { Suspense, lazy, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Sidebar } from "./components/layout/Sidebar";
import { TopBar } from "./components/layout/TopBar";
import { DecisionStrip } from "./components/layout/DecisionStrip";
import { RightPanel } from "./components/layout/RightPanel";
import { ToastHost } from "./components/ui/ToastHost";
import { PageErrorBoundary } from "./components/PageErrorBoundary";
import { DashboardPage } from "./pages/DashboardPage";
import { hydrateSessionResults, useBackendProbe, useProjects, useSaveSession, useSessions } from "./hooks/queries";
import { useAppStore } from "./store/useAppStore";
import {
  BOTAS_FORM_BY_CODE,
  TAB_BY_KEY,
  VISIBLE_TABS,
  formCodeFromHash,
  hashForTab,
  tabFromHash,
} from "./lib/constants";
import { api, apiErrorMessage } from "./lib/api";
import { createEmptyInputs } from "./lib/mock";
import { toApiInputs } from "./lib/normalize";

const ProjectsPage = lazy(() =>
  import("./pages/ProjectsPage").then((module) => ({ default: module.ProjectsPage })),
);
const GeometryPage = lazy(() =>
  import("./pages/GeometryPage").then((module) => ({ default: module.GeometryPage })),
);
const CoefficientsPage = lazy(() =>
  import("./pages/CoefficientsPage").then((module) => ({ default: module.CoefficientsPage })),
);
const AirPage = lazy(() =>
  import("./pages/AirPage").then((module) => ({ default: module.AirPage })),
);
const PressurePage = lazy(() =>
  import("./pages/PressurePage").then((module) => ({ default: module.PressurePage })),
);
const SectionFormPage = lazy(() =>
  import("./pages/SectionFormPage").then((module) => ({ default: module.SectionFormPage })),
);
const ReportsPage = lazy(() =>
  import("./pages/ReportsPage").then((module) => ({ default: module.ReportsPage })),
);
const SettingsPage = lazy(() =>
  import("./pages/SettingsPage").then((module) => ({ default: module.SettingsPage })),
);
const OcrPage = lazy(() => import("./features/ocr/OcrPage"));

const HelpDialog = lazy(() =>
  import("./components/layout/HelpDialog").then((module) => ({ default: module.HelpDialog })),
);
const CommandPalette = lazy(() =>
  import("./components/layout/CommandPalette").then((module) => ({
    default: module.CommandPalette,
  })),
);
const UpdateManagerModal = lazy(() =>
  import("./components/layout/UpdateManagerModal").then((module) => ({
    default: module.UpdateManagerModal,
  })),
);
const RevisionConflictModal = lazy(() =>
  import("./components/layout/RevisionConflictModal").then((module) => ({
    default: module.RevisionConflictModal,
  })),
);
const GuidedTourOverlay = lazy(() =>
  import("./components/onboarding/GuidedTourOverlay").then((module) => ({
    default: module.GuidedTourOverlay,
  })),
);

const SKELETON_CARDS = ["kpi-1", "kpi-2", "kpi-3", "kpi-4"] as const;

function PageSkeleton() {
  return (
    <div className="min-h-[720px] space-y-4" aria-busy="true" aria-label="Sayfa yükleniyor">
      <div className="h-[72px] rounded-xl border border-[var(--border)] bg-[var(--surface-2)] animate-pulse" />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {SKELETON_CARDS.map((cardKey) => (
          <div
            key={cardKey}
            className="h-[92px] rounded-xl border border-[var(--border)] bg-[var(--surface-2)] animate-pulse"
          />
        ))}
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <div className="h-[320px] rounded-xl border border-[var(--border)] bg-[var(--surface-2)] animate-pulse" />
        <div className="h-[320px] rounded-xl border border-[var(--border)] bg-[var(--surface-2)] animate-pulse" />
      </div>
    </div>
  );
}

function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target.isContentEditable;
}

/* Derin bağlantı: kalıcı sekme yüklenmeden önce URL hash'i önceliklidir. */
if (typeof window !== "undefined" && window.location.hash.length > 1) {
  const initial = tabFromHash(window.location.hash);
  const initialForm = formCodeFromHash(window.location.hash);
  if (initial !== useAppStore.getState().tab) {
    useAppStore.getState().setTab(initial);
  }
  if (initialForm && initialForm !== useAppStore.getState().activeFormCode) {
    useAppStore.getState().setActiveFormCode(initialForm);
  }
}

export default function App() {
  const tab = useAppStore((state) => state.tab);
  const setTab = useAppStore((state) => state.setTab);
  const activeFormCode = useAppStore((state) => state.activeFormCode);
  const setActiveFormCode = useAppStore((state) => state.setActiveFormCode);
  const theme = useAppStore((state) => state.theme);
  const rightPanelOpen = useAppStore((state) => state.rightPanelOpen);
  const updateModalOpen = useAppStore((state) => state.updateModalOpen);
  const revisionConflict = useAppStore((state) => state.revisionConflict);
  const tourActive = useAppStore((state) => state.tourActive);
  const dirty = useAppStore((state) => state.dirty);
  const backend = useAppStore((state) => state.backend);
  const sessionId = useAppStore((state) => state.sessionId);
  const applySessionInputs = useAppStore((state) => state.applySessionInputs);
  const setSessionMeta = useAppStore((state) => state.setSessionMeta);
  const setProject = useAppStore((state) => state.setProject);
  const pushToast = useAppStore((state) => state.pushToast);

  const queryClient = useQueryClient();
  const [helpOpen, setHelpOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);

  useBackendProbe();
  const sessionsQuery = useSessions();
  const projectsQuery = useProjects();
  const saveSession = useSaveSession();
  const bootstrapped = useRef(false);

  /* Tema */
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  /* Kaydedilmemiş değişikliklerde tarayıcı sekmesini kapatma koruması (R7) */
  useEffect(() => {
    if (!dirty) return;
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty]);

  /* Hash yönlendirme */
  useEffect(() => {
    const onHash = () => {
      const nextTab = tabFromHash(window.location.hash);
      const nextForm = formCodeFromHash(window.location.hash);
      setTab(nextTab);
      if (nextForm) setActiveFormCode(nextForm);
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, [setTab, setActiveFormCode]);

  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [tab, activeFormCode]);

  useEffect(() => {
    const target = hashForTab(tab, activeFormCode);
    if (window.location.hash !== target) {
      window.history.replaceState(null, "", target);
    }
    if (tab === "forms") {
      const spec = BOTAS_FORM_BY_CODE[activeFormCode];
      document.title = spec ? `${spec.shortCode} ${spec.title} · HYDRO` : "Test Bölümü Formları · HYDRO";
    } else {
      document.title = `${TAB_BY_KEY[tab].label} · HYDRO`;
    }
  }, [tab, activeFormCode]);

  /* Oturum geri yükleme (backend bağlıysa) */
  useEffect(() => {
    if (
      backend !== "online" ||
      bootstrapped.current ||
      !sessionsQuery.isFetchedAfterMount ||
      !projectsQuery.isFetchedAfterMount
    ) {
      return;
    }
    const list = sessionsQuery.data;
    if (!list) return;
    bootstrapped.current = true;
    void (async () => {
      try {
        const target = sessionId ? list.find((item) => item.id === sessionId) ?? list[0] : list[0];
        if (target && target.id.startsWith("demo-")) {
          // Oturum API'si henüz yok: yerel demo oturumu korunur.
          return;
        }
        if (target) {
          const session = await api.session(target.id);
          applySessionInputs(session.inputs);
          setSessionMeta({
            id: session.id,
            name: session.name,
            revision: session.revision,
            status: session.status,
          });
          void hydrateSessionResults(session.id);
          const project = projectsQuery.data?.find((item) => item.id === session.project_id);
          if (project) setProject(project);
          else if (session.project_id) setProject({ id: session.project_id, name: "" });
          else setProject(null);
          queryClient.setQueryData(["session", session.id], session);
          pushToast("info", "Oturum geri yüklendi", session.name);
        } else {
          const state = useAppStore.getState();
          const validProjectId =
            state.projectId &&
            !state.projectId.startsWith("demo-") &&
            projectsQuery.data?.some((item) => item.id === state.projectId)
              ? state.projectId
              : null;
          if (!validProjectId && state.projectId) {
            setProject(null);
          }
          const emptyInputs = createEmptyInputs();
          applySessionInputs(emptyInputs);
          const created = await api.createSession({
            name: "Yeni Kesit 1",
            project_id: validProjectId,
            inputs: toApiInputs(emptyInputs),
          });
          setSessionMeta({
            id: created.id,
            name: created.name,
            revision: created.revision,
            status: created.status,
          });
          pushToast("success", "Yeni oturum açıldı", `${created.name} · revizyon ${created.revision}`);
        }
      } catch (error) {
        pushToast("warning", "Oturum yüklenemedi", apiErrorMessage(error));
      }
    })();
  }, [
    backend,
    sessionsQuery.isFetchedAfterMount,
    projectsQuery.isFetchedAfterMount,
    sessionsQuery.data,
    projectsQuery.data,
    sessionId,
    applySessionInputs,
    setSessionMeta,
    setProject,
    queryClient,
    pushToast,
  ]);

  /* Klavye kısayolları */
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const modifier = event.metaKey || event.ctrlKey;
      if (modifier && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((prev) => !prev);
        return;
      }
      if (modifier && event.key.toLowerCase() === "s") {
        event.preventDefault();
        if (useAppStore.getState().tab === "forms") {
          window.dispatchEvent(new CustomEvent("hydro:save"));
          return;
        }
        if (!saveSession.isPending) saveSession.mutate();
        return;
      }
      if (modifier && event.key === "Enter") {
        event.preventDefault();
        window.dispatchEvent(new Event("hydro:evaluate"));
        return;
      }
      if (event.altKey && /^[1-9]$/.test(event.key)) {
        event.preventDefault();
        const next = VISIBLE_TABS[Number(event.key) - 1];
        if (next) setTab(next.key);
        return;
      }
      if (event.key === "?" && !isTyping(event.target)) {
        event.preventDefault();
        setHelpOpen(true);
      }
    };
    window.addEventListener("keydown", onKey, { capture: true });
    return () => window.removeEventListener("keydown", onKey, { capture: true });
  }, [saveSession, setTab]);

  const page = (() => {
    switch (tab) {
      case "dashboard":
        return <DashboardPage />;
      case "projects":
        return <ProjectsPage />;
      case "geometry":
        return <GeometryPage />;
      case "coefficients":
      case "coefficient_detail":
        /* Eski `#/coefficient-detail` bağlantısı birleşik Katsayılar sayfasına gider. */
        return <CoefficientsPage />;
      case "air":
        return <AirPage />;
      case "pressure":
        return <PressurePage />;
      case "forms":
        return <SectionFormPage />;
      case "field":
        /* Eski `#/field` bağlantısı birleşik Geometri & Saha sayfasına gider. */
        return <GeometryPage />;
      case "reports":
        return <ReportsPage />;
      case "ocr":
        return <OcrPage />;
      case "settings":
        return <SettingsPage />;
      default:
        return <DashboardPage />;
    }
  })();

  return (
    <div className="min-h-screen overflow-x-clip">
      <div className="flex min-h-screen">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <TopBar
            onOpenHelp={() => setHelpOpen(true)}
            onOpenCommandPalette={() => setPaletteOpen(true)}
          />
          {tab === "air" || tab === "pressure" || tab === "geometry" || tab === "forms" ? (
            <DecisionStrip />
          ) : null}

          <div className="mx-auto flex w-full max-w-[1500px] flex-1 gap-5 px-3 py-4 sm:px-4 sm:py-5">
            <main className="min-w-0 flex-1">
              {backend !== "online" ? (
                <div
                  role="status"
                  className="mb-3 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-200"
                >
                  <strong className="font-semibold">DEMO / ÇEVRİMDIŞI MOD</strong> — Sunucu bağlantısı yok;
                  hesaplamalar tarayıcı içinde çalışıyor, resmi PDF/XLSX çıktısı devre dışıdır.
                </div>
              ) : null}
              <PageErrorBoundary resetKey={tab} title={`${TAB_BY_KEY[tab].label} yüklenemedi`}>
                {/*
                  ÖNEMLİ: Sayfa geçişini AnimatePresence/motion ile sarmalamayın.
                  `mode="wait"` altında exit animasyonu tamamlanmazsa yeni sayfa hiç
                  mount edilmiyor ve sekme başlığı değişirken içerik Dashboard'da kalıyordu.
                  Basit key'li div + CSS animasyonu her zaman doğru içeriği render eder.
                */}
                <div key={tab} data-page={tab} className="page-transition">
                  <Suspense fallback={<PageSkeleton />}>{page}</Suspense>
                </div>
              </PageErrorBoundary>

              <footer className="mt-6 flex flex-wrap items-center justify-between gap-2 border-t border-[var(--border)] pt-3 text-[10px] text-[var(--text-faint)]">
                <span>
                  HYDRO · Hidrostatik Test Değerlendirme · sunucu:{" "}
                  <span className="font-mono">{backend === "online" ? "bağlı" : "çevrimdışı"}</span>
                </span>
                <span className="font-mono">4-NGTL 0-GN-P-002-5007 R4</span>
              </footer>
            </main>

            {rightPanelOpen && tab !== "forms" && tab !== "ocr" && tab !== "projects" ? (
              <RightPanel />
            ) : null}
          </div>
        </div>
      </div>

      {helpOpen ? (
        <Suspense fallback={null}>
          <HelpDialog open={helpOpen} onClose={() => setHelpOpen(false)} />
        </Suspense>
      ) : null}
      {paletteOpen ? (
        <Suspense fallback={null}>
          <CommandPalette
            open={paletteOpen}
            onClose={() => setPaletteOpen(false)}
            onOpenHelp={() => setHelpOpen(true)}
          />
        </Suspense>
      ) : null}
      {updateModalOpen ? (
        <Suspense fallback={null}>
          <UpdateManagerModal />
        </Suspense>
      ) : null}
      {revisionConflict ? (
        <Suspense fallback={null}>
          <RevisionConflictModal />
        </Suspense>
      ) : null}
      {tourActive ? (
        <Suspense fallback={null}>
          <GuidedTourOverlay />
        </Suspense>
      ) : null}
      <ToastHost />
    </div>
  );
}
