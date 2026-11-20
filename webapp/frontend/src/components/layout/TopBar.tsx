import { useEffect, useRef, useState } from "react";
import {
  ArrowUpCircle,
  Check,
  ChevronDown,
  HelpCircle,
  Loader2,
  Menu,
  Moon,
  PanelRightClose,
  PanelRightOpen,
  Plus,
  Save,
  Sun,
  Wifi,
  WifiOff,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { api, apiErrorMessage } from "../../lib/api";
import { relativeTime } from "../../lib/format";
import {
  useCreateSession,
  useMeta,
  useProjects,
  useSaveSession,
  useSessions,
  useUpdateStatus,
} from "../../hooks/queries";
import { useAppStore } from "../../store/useAppStore";
import { toApiInputs } from "../../lib/normalize";
import { Badge } from "../ui/Badge";
import { Button, IconButton } from "../ui/Button";
import { ConfirmDialog } from "../ui/Dialog";
import { HydroLogo } from "../ui/HydroLogo";
import { cn } from "../../lib/utils";

export function TopBar({ onOpenHelp }: { onOpenHelp: () => void }) {
  const tab = useAppStore((state) => state.tab);
  const projectId = useAppStore((state) => state.projectId);
  const sessionName = useAppStore((state) => state.sessionName);
  const sessionStatus = useAppStore((state) => state.sessionStatus);
  const sessionId = useAppStore((state) => state.sessionId);
  const projectCode = useAppStore((state) => state.projectCode);
  const setProject = useAppStore((state) => state.setProject);
  const revision = useAppStore((state) => state.revision);
  const dirty = useAppStore((state) => state.dirty);
  const theme = useAppStore((state) => state.theme);
  const backend = useAppStore((state) => state.backend);
  const sessionApiReady = useAppStore((state) => state.sessionApiReady);
  const rightPanelOpen = useAppStore((state) => state.rightPanelOpen);
  const desktopSidebarOpen = useAppStore((state) => state.desktopSidebarOpen);
  const setTheme = useAppStore((state) => state.setTheme);
  const toggleSidebar = useAppStore((state) => state.toggleSidebar);
  const toggleDesktopSidebar = useAppStore((state) => state.toggleDesktopSidebar);
  const toggleRightPanel = useAppStore((state) => state.toggleRightPanel);
  const setTab = useAppStore((state) => state.setTab);
  const setSessionMeta = useAppStore((state) => state.setSessionMeta);
  const setSessionName = useAppStore((state) => state.setSessionName);
  const markSaved = useAppStore((state) => state.markSaved);
  const setRevisionConflict = useAppStore((state) => state.setRevisionConflict);
  const applySessionInputs = useAppStore((state) => state.applySessionInputs);
  const resetSession = useAppStore((state) => state.resetSession);
  const setUpdateModalOpen = useAppStore((state) => state.setUpdateModalOpen);
  const pushToast = useAppStore((state) => state.pushToast);

  const { data: sessions } = useSessions();
  const { data: projects } = useProjects();
  const { data: meta } = useMeta();
  const { data: updateStatus } = useUpdateStatus();
  const saveSession = useSaveSession();
  const createSession = useCreateSession();
  const queryClient = useQueryClient();

  const [pickerOpen, setPickerOpen] = useState(false);
  const [confirmNew, setConfirmNew] = useState(false);
  const [draftName, setDraftName] = useState(sessionName);
  const [switching, setSwitching] = useState(false);
  const pickerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setDraftName(sessionName);
  }, [sessionName]);

  useEffect(() => {
    if (!pickerOpen) return;
    const onClick = (event: MouseEvent) => {
      if (!pickerRef.current?.contains(event.target as Node)) setPickerOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [pickerOpen]);

  const statusTone =
    sessionStatus === "completed" ? "pass" : sessionStatus === "archived" ? "neutral" : "info";

  async function selectSession(id: string) {
    setPickerOpen(false);
    const item = sessions?.find((session) => session.id === id);
    if (!item) return;
    if (backend !== "online" || item.id.startsWith("demo-") || sessionApiReady === false) {
      setSessionMeta({ name: item.name, revision: item.revision, status: item.status });
      pushToast(
        "info",
        "Yerel Test Bölümü görünümü",
        sessionApiReady === false
          ? "Bölüm servisi hazır değil; yerel bölüm verileri gösteriliyor."
          : "Sunucu bağlı olmadığı için yerel bölüm verileri gösteriliyor.",
      );
      return;
    }
    setSwitching(true);
    try {
      const session = await api.session(id);
      applySessionInputs(session.inputs);
      setSessionMeta({
        id: session.id,
        name: session.name,
        revision: session.revision,
        status: session.status,
      });
      markSaved(session.revision);
      setRevisionConflict(null);
      const project = projects?.find((item) => item.id === session.project_id);
      if (project) setProject(project);
      else if (session.project_id) setProject({ id: session.project_id, name: "" });
      else setProject(null);
      queryClient.setQueryData(["session", session.id], session);
      pushToast("success", "Test Bölümü açıldı", `${session.name} · revizyon ${session.revision}`);
    } catch (error) {
      pushToast("error", "Test Bölümü açılamadı", apiErrorMessage(error));
    } finally {
      setSwitching(false);
    }
  }

  function createNew() {
    const name = `Test Bölümü ${(sessions?.length ?? 0) + 1}`;
    resetSession(name);
    const inputs = toApiInputs(useAppStore.getState().inputs);
    createSession.mutate({ name, inputs, projectId });
  }

  return (
    <>
      <header className="sticky top-0 z-40 border-b border-[var(--border)] bg-[color-mix(in_srgb,var(--canvas)_82%,transparent)] px-3 py-1 backdrop-blur-xl sm:px-4">
        <div className="mx-auto flex max-w-[1500px] items-center gap-2.5">
          <IconButton
            label={
              desktopSidebarOpen
                ? "Sol gezinme menüsünü gizle / aç"
                : "Sol gezinme menüsünü göster"
            }
            onClick={() => {
              if (typeof window !== "undefined" && window.innerWidth < 1024) {
                toggleSidebar();
              } else {
                toggleDesktopSidebar();
              }
            }}
          >
            <Menu size={20} />
          </IconButton>

          <button
            type="button"
            className={cn(
              "items-center gap-2 rounded-lg px-1 py-0.5 text-left transition-opacity hover:opacity-85",
              desktopSidebarOpen ? "hidden sm:inline-flex lg:hidden" : "hidden sm:inline-flex",
            )}
            onClick={() => setTab("dashboard")}
            aria-label="HYDRO Ana Sayfa"
          >
            <HydroLogo size={28} />
            <span className="hidden text-sm font-extrabold tracking-tight text-[var(--text)] sm:inline">
              HYDRO
            </span>
          </button>

          <div className="relative min-w-0" ref={pickerRef}>
            <button
              type="button"
              className="flex h-9 min-w-0 max-w-[155px] items-center gap-2 rounded-xl border border-[var(--border-strong)] bg-[var(--surface-2)] px-2.5 py-1 text-left transition-colors hover:border-[var(--primary)] hover:bg-[var(--surface-3)] sm:max-w-[380px]"
              aria-haspopup="listbox"
              aria-expanded={pickerOpen}
              onClick={() => setPickerOpen((value) => !value)}
            >
              <div className="flex min-w-0 items-center gap-2">
                <span className="truncate text-[13.5px] font-bold tracking-[-0.01em] text-[var(--text)]">
                  {switching ? "Yükleniyor…" : sessionName}
                </span>
                <Badge tone={statusTone} className="hidden sm:inline-flex">
                  {sessionStatus === "completed"
                    ? "Tamamlandı"
                    : sessionStatus === "archived"
                      ? "Arşiv"
                      : sessionStatus === "active"
                        ? "Aktif"
                        : "Taslak"}
                </Badge>
                <span className="hidden items-center gap-1 whitespace-nowrap text-[10.5px] text-[var(--text-muted)] lg:inline-flex">
                  {projectCode ? (
                    <>
                      <span className="font-mono">{projectCode}</span>
                      <span aria-hidden>·</span>
                    </>
                  ) : null}
                  <span>rev.{revision}</span>
                  <span aria-hidden>·</span>
                  <span className={cn(dirty ? "tone-warning" : "tone-pass")}>
                    {dirty ? "Kaydedilmedi" : "Kaydedildi"}
                  </span>
                </span>
              </div>
              <ChevronDown size={15} className="shrink-0 text-[var(--text-soft)]" aria-hidden />
            </button>

            {pickerOpen ? (
              <div
                className="absolute left-0 top-[calc(100%+8px)] z-50 w-[min(420px,calc(100vw-24px))] overflow-hidden rounded-xl border border-[var(--border-strong)] bg-[var(--surface)] shadow-2xl"
                role="listbox"
                aria-label="Test Bölümü seçici"
              >
                <div className="border-b border-[var(--border)] p-2.5">
                  <label className="field-label" htmlFor="session-rename">
                    Test Bölümü adı
                  </label>
                  <div className="mt-1 flex gap-1.5">
                    <input
                      id="session-rename"
                      className="input"
                      value={draftName}
                      maxLength={120}
                      onChange={(event) => setDraftName(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") {
                          setSessionName(draftName.trim() || sessionName);
                          setPickerOpen(false);
                        }
                      }}
                    />
                    <Button
                      size="sm"
                      variant="primary"
                      icon={<Check size={12} />}
                      onClick={() => {
                        setSessionName(draftName.trim() || sessionName);
                        setPickerOpen(false);
                      }}
                    >
                      Adlandır
                    </Button>
                  </div>
                </div>
                <div className="max-h-[280px] overflow-y-auto scroll-thin p-1.5">
                  {(sessions ?? []).map((session) => (
                    <button
                      key={session.id}
                      type="button"
                      role="option"
                      aria-selected={session.id === sessionId}
                      className={cn(
                        "flex w-full items-start gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors hover:bg-[var(--surface-3)]",
                        session.id === sessionId && "bg-[var(--primary-soft)]",
                      )}
                      onClick={() => void selectSession(session.id)}
                    >
                      <span
                        className={cn(
                          "mt-1 status-dot",
                          session.result_summary?.air?.status === "BASARILI"
                            ? "tone-pass"
                            : "tone-pending",
                        )}
                        aria-hidden
                      />
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center justify-between gap-2">
                          <span className="truncate text-[12.5px] font-medium">{session.name}</span>
                          {session.id === sessionId ? <Check size={13} className="tone-pass" /> : null}
                        </span>
                        <span className="mt-0.5 block text-[10.5px] text-[var(--text-faint)]">
                          {session.status} · rev. {session.revision} · {relativeTime(session.updated_at)}
                        </span>
                      </span>
                    </button>
                  ))}
                </div>
                <div className="border-t border-[var(--border)] p-1.5">
                  <button
                    type="button"
                    className="nav-item"
                    onClick={() => {
                      setPickerOpen(false);
                      if (dirty) setConfirmNew(true);
                      else createNew();
                    }}
                  >
                    <Plus size={14} aria-hidden />
                    Yeni Bölüm
                  </button>
                </div>
              </div>
            ) : null}
          </div>

          <div className="ml-auto flex items-center gap-2">
            <Button
              size="sm"
              variant="primary"
              className="hidden sm:inline-flex"
              icon={saveSession.isPending ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
              disabled={saveSession.isPending}
              onClick={() => {
                if (tab === "forms") window.dispatchEvent(new CustomEvent("hydro:save"));
                else saveSession.mutate();
              }}
            >
              {saveSession.isPending ? "Kaydediliyor" : "Kaydet"}
            </Button>
            <IconButton
              label="Kaydet"
              className="sm:hidden"
              disabled={saveSession.isPending}
              onClick={() => {
                if (tab === "forms") window.dispatchEvent(new CustomEvent("hydro:save"));
                else saveSession.mutate();
              }}
            >
              {saveSession.isPending ? <Loader2 size={18} className="animate-spin" /> : <Save size={18} />}
            </IconButton>

            <Button
              size="sm"
              className="hidden md:inline-flex"
              icon={<Plus size={15} />}
              onClick={() => {
                if (dirty) setConfirmNew(true);
                else createNew();
              }}
            >
              Yeni Bölüm
            </Button>

            {updateStatus?.update_available && updateStatus.latest_version ? (
              <button
                type="button"
                className="badge badge-pass hidden md:inline-flex"
                title={`Yeni sürüm v${updateStatus.latest_version} mevcut — Güncelleme Yöneticisini aç`}
                onClick={() => setUpdateModalOpen(true)}
              >
                <ArrowUpCircle size={12} aria-hidden />
                v{updateStatus.latest_version} Güncelle
              </button>
            ) : null}

            <button
              type="button"
              className={cn(
                "badge hidden sm:inline-flex",
                backend === "online" && sessionApiReady !== false
                  ? "badge-pass"
                  : backend === "online"
                    ? "badge-warning"
                    : backend === "demo"
                      ? "badge-warning"
                      : "badge-pending",
              )}
              title={
                backend === "online" && sessionApiReady === false
                  ? "Sunucu çalışıyor ancak oturum servisi yanıt vermiyor; yerel veriler kullanılıyor."
                  : backend === "online"
                    ? `Sunucu bağlı · sürüm ${meta?.app.version ?? "—"}`
                    : "Sunucu bağlı değil; yerel hesaplama kullanılıyor. Tıklayınca Ayarlar açılır."
              }
              onClick={() => setTab("settings")}
            >
              {backend === "online" ? <Wifi size={12} /> : <WifiOff size={12} />}
              {backend === "online" && sessionApiReady === false
                ? "Kısmi"
                : backend === "online"
                  ? "Bağlı"
                  : backend === "demo"
                    ? "Çevrimdışı"
                    : "Kontrol"}
            </button>

            <IconButton
              label={theme === "dark" ? "Açık temaya geç" : "Koyu temaya geç"}
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            >
              {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
            </IconButton>

            <IconButton label="Kısayollar ve yardım" className="hidden sm:grid" onClick={onOpenHelp}>
              <HelpCircle size={18} />
            </IconButton>

            <IconButton
              label={rightPanelOpen ? "Canlı özet panelini gizle" : "Canlı özet panelini göster"}
              className={
                tab === "forms" || tab === "ocr" || tab === "projects" ? "hidden" : "hidden 2xl:grid"
              }
              onClick={toggleRightPanel}
            >
              {rightPanelOpen ? <PanelRightClose size={18} /> : <PanelRightOpen size={18} />}
            </IconButton>
          </div>
        </div>
      </header>

      <ConfirmDialog
        open={confirmNew}
        title="Yeni Test Bölümü açılsın mı?"
        message={
          <span>
            Kaydedilmemiş değişiklikler var. Yeni Test Bölümü açarsanız sunucuya kaydedilmemiş
            mevcut değişiklikler kaybolur.
          </span>
        }
        confirmLabel="Yeni Bölüm Aç"
        onConfirm={createNew}
        onClose={() => setConfirmNew(false)}
      />
    </>
  );
}
