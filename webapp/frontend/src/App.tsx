import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Sidebar } from "./components/layout/Sidebar";
import { TopBar } from "./components/layout/TopBar";
import { DecisionStrip } from "./components/layout/DecisionStrip";
import { RightPanel } from "./components/layout/RightPanel";
import { HelpDialog } from "./components/layout/HelpDialog";
import { ToastHost } from "./components/ui/ToastHost";
import { PageErrorBoundary } from "./components/PageErrorBoundary";
import { DashboardPage } from "./pages/DashboardPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { GeometryPage } from "./pages/GeometryPage";
import { CoefficientsPage } from "./pages/CoefficientsPage";
import { AirPage } from "./pages/AirPage";
import { PressurePage } from "./pages/PressurePage";
import { ReportsPage } from "./pages/ReportsPage";
import { SettingsPage } from "./pages/SettingsPage";
import OcrPage from "./features/ocr/OcrPage";
import { hydrateSessionResults, useBackendProbe, useProjects, useSaveSession, useSessions } from "./hooks/queries";
import { useAppStore } from "./store/useAppStore";
import { TAB_BY_KEY, VISIBLE_TABS, hashForTab, tabFromHash } from "./lib/constants";
import { api, apiErrorMessage } from "./lib/api";
import { createEmptyInputs } from "./lib/mock";
import { toApiInputs } from "./lib/normalize";

function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target.isContentEditable;
}

/* Derin bağlantı: kalıcı sekme yüklenmeden önce URL hash'i önceliklidir. */
if (typeof window !== "undefined" && window.location.hash.length > 1) {
  const initial = tabFromHash(window.location.hash);
  if (initial !== useAppStore.getState().tab) {
    useAppStore.getState().setTab(initial);
  }
}

export default function App() {
  const tab = useAppStore((state) => state.tab);
  const setTab = useAppStore((state) => state.setTab);
  const theme = useAppStore((state) => state.theme);
  const rightPanelOpen = useAppStore((state) => state.rightPanelOpen);
  const backend = useAppStore((state) => state.backend);
  const sessionId = useAppStore((state) => state.sessionId);
  const applySessionInputs = useAppStore((state) => state.applySessionInputs);
  const setSessionMeta = useAppStore((state) => state.setSessionMeta);
  const setProject = useAppStore((state) => state.setProject);
  const pushToast = useAppStore((state) => state.pushToast);

  const queryClient = useQueryClient();
  const [helpOpen, setHelpOpen] = useState(false);

  useBackendProbe();
  const sessionsQuery = useSessions();
  const projectsQuery = useProjects();
  const saveSession = useSaveSession();
  const bootstrapped = useRef(false);

  /* Tema */
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  /* Hash yönlendirme */
  useEffect(() => {
    const onHash = () => setTab(tabFromHash(window.location.hash));
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, [setTab]);

  useEffect(() => {
    const target = hashForTab(tab);
    if (window.location.hash !== target) {
      window.history.replaceState(null, "", target);
    }
    document.title = `${TAB_BY_KEY[tab].label} · HYDRO`;
  }, [tab]);

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
      if (modifier && event.key.toLowerCase() === "s") {
        event.preventDefault();
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
    <div className="min-h-screen">
      <div className="flex min-h-screen">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <TopBar onOpenHelp={() => setHelpOpen(true)} />
          <DecisionStrip />

          <div className="mx-auto flex w-full max-w-[1500px] flex-1 gap-5 px-3 py-4 sm:px-4 sm:py-5">
            <main className="min-w-0 flex-1">
              <PageErrorBoundary resetKey={tab} title={`${TAB_BY_KEY[tab].label} yüklenemedi`}>
                {/*
                  ÖNEMLİ: Sayfa geçişini AnimatePresence/motion ile sarmalamayın.
                  `mode="wait"` altında exit animasyonu tamamlanmazsa yeni sayfa hiç
                  mount edilmiyor ve sekme başlığı değişirken içerik Dashboard'da kalıyordu.
                  Basit key'li div + CSS animasyonu her zaman doğru içeriği render eder.
                */}
                <div key={tab} data-page={tab} className="page-transition">
                  {page}
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

            {rightPanelOpen ? <RightPanel /> : null}
          </div>
        </div>
      </div>

      <HelpDialog open={helpOpen} onClose={() => setHelpOpen(false)} />
      <ToastHost />
    </div>
  );
}
