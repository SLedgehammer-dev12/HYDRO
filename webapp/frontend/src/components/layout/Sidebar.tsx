import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowUpCircle,
  Check,
  ChevronDown,
  ChevronRight,
  Circle,
  Droplet,
  FileText,
  FolderKanban,
  Gauge,
  LayoutDashboard,
  Map as MapIcon,
  RefreshCw,
  Ruler,
  ScanLine,
  Settings,
  Sigma,
  Table2,
  Wind,
  X,
  XCircle,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { BOTAS_FORM_NAV_ITEMS, VISIBLE_TABS } from "../../lib/constants";
import type { BackendMode, BotasFormCode, TabKey } from "../../lib/types";
import {
  useCheckUpdates,
  useMeta,
  useOpenSession,
  useSessionForms,
  useSessions,
  useUpdateStatus,
} from "../../hooks/queries";
import { useAppStore } from "../../store/useAppStore";
import { cn } from "../../lib/utils";

const ICONS: Record<TabKey, LucideIcon> = {
  dashboard: LayoutDashboard,
  projects: FolderKanban,
  geometry: Ruler,
  coefficients: Sigma,
  coefficient_detail: Table2,
  air: Wind,
  pressure: Gauge,
  forms: FileText,
  field: MapIcon,
  reports: FileText,
  ocr: ScanLine,
  settings: Settings,
};

function BackendDot({ backend }: { backend: BackendMode }) {
  return (
    <span
      className={cn(
        "status-dot",
        backend === "online" && "tone-pass",
        backend === "demo" && "tone-warning",
        backend === "checking" && "tone-pending",
      )}
      aria-hidden
    />
  );
}

function FormStatusBadge({ status }: { status: string }) {
  if (status === "passed") {
    return (
      <span className="inline-flex size-4 shrink-0 items-center justify-center rounded-full bg-[var(--success-bg)] text-[var(--success)]" title="Kontrolden geçti">
        <Check size={10} strokeWidth={2.8} aria-hidden />
      </span>
    );
  }
  if (status === "failed") {
    return (
      <span className="inline-flex size-4 shrink-0 items-center justify-center rounded-full bg-[var(--danger-bg)] text-[var(--danger)]" title="Bulgu / Hata var">
        <XCircle size={10} strokeWidth={2.5} aria-hidden />
      </span>
    );
  }
  if (status === "warning") {
    return (
      <span className="inline-flex size-4 shrink-0 items-center justify-center rounded-full bg-[var(--warning-bg)] text-[var(--warning)]" title="Uyarı / İnceleme gerekli">
        <AlertTriangle size={10} strokeWidth={2.5} aria-hidden />
      </span>
    );
  }
  if (status === "filled") {
    return (
      <span className="inline-flex size-4 shrink-0 items-center justify-center rounded-full bg-[var(--primary-soft)] text-[var(--primary)]" title="Dolduruldu">
        <Circle size={8} fill="currentColor" aria-hidden />
      </span>
    );
  }
  return (
    <span className="inline-flex size-4 shrink-0 items-center justify-center rounded-full bg-[var(--surface-3)] text-[var(--text-faint)]" title="Boş">
      <Circle size={8} aria-hidden />
    </span>
  );
}

export function Sidebar() {
  const tab = useAppStore((state) => state.tab);
  const setTab = useAppStore((state) => state.setTab);
  const activeFormCode = useAppStore((state) => state.activeFormCode);
  const openForm = useAppStore((state) => state.openForm);
  const sessionId = useAppStore((state) => state.sessionId);
  const sessionName = useAppStore((state) => state.sessionName);
  const projectId = useAppStore((state) => state.projectId);
  const projectName = useAppStore((state) => state.projectName);
  const sidebarOpen = useAppStore((state) => state.sidebarOpen);
  const desktopSidebarOpen = useAppStore((state) => state.desktopSidebarOpen);
  const setSidebarOpen = useAppStore((state) => state.setSidebarOpen);
  const setUpdateModalOpen = useAppStore((state) => state.setUpdateModalOpen);
  const backend = useAppStore((state) => state.backend);
  const sessionApiReady = useAppStore((state) => state.sessionApiReady);

  const { data: meta } = useMeta();
  const { data: projectSessions } = useSessions(projectId);
  const openSession = useOpenSession();
  const { data: formsPayload } = useSessionForms(sessionId);
  const { data: updateStatus } = useUpdateStatus();
  const checkUpdates = useCheckUpdates();
  const silentCheckFired = useRef(false);

  const [formsExpanded, setFormsExpanded] = useState(true);
  const [extrasExpanded, setExtrasExpanded] = useState(false);

  useEffect(() => {
    if (backend === "online" && !silentCheckFired.current) {
      silentCheckFired.current = true;
      checkUpdates.mutate({ force: false, silent: true });
    }
  }, [backend, checkUpdates]);

  const mandatoryForms = BOTAS_FORM_NAV_ITEMS.filter((item) => item.required);
  const extraForms = BOTAS_FORM_NAV_ITEMS.filter((item) => !item.required);
  const formByCode = new Map(
    (formsPayload?.forms ?? []).map((row) => [row.form_code, row]),
  );
  const summary = formsPayload?.summary;

  function renderFormNavRow(item: (typeof BOTAS_FORM_NAV_ITEMS)[number]) {
    const rec = formByCode.get(item.code);
    const st = rec?.status ?? "empty";
    const isActive = tab === "forms" && activeFormCode === item.code;
    return (
      <button
        key={item.code}
        type="button"
        onClick={() => {
          openForm(item.code as BotasFormCode);
          setSidebarOpen(false);
        }}
        title={`${item.botasCode} — ${item.title}`}
        aria-current={isActive ? "page" : undefined}
        className={cn(
          "flex w-full items-center justify-between gap-1.5 rounded-lg border px-2 py-1 text-left text-[11px] transition-colors",
          isActive
            ? "border-[var(--primary-border)] bg-[var(--primary-soft)] font-semibold text-[var(--text)]"
            : "border-transparent text-[var(--text-soft)] hover:bg-[var(--surface-3)] hover:text-[var(--text)]",
        )}
      >
        <span className="flex min-w-0 items-center gap-1.5">
          <span
            className={cn(
              "shrink-0 font-mono text-[9.5px] font-bold",
              isActive ? "text-[var(--primary)]" : "text-[var(--text-faint)]",
            )}
          >
            {item.shortCode}
          </span>
          <span className="truncate">{item.shortTitle}</span>
        </span>
        <span className="flex shrink-0 items-center gap-1">
          {item.hasDetailCalc ? (
            <span className="rounded bg-[var(--surface-3)] px-1 py-0.5 text-[8.5px] font-bold uppercase text-[var(--primary)]">
              Hesap
            </span>
          ) : null}
          <FormStatusBadge status={st} />
        </span>
      </button>
    );
  }

  const nav = (
    <nav className="flex h-full flex-col gap-3">
      <div className="flex items-center justify-between px-1">
        <div className="flex items-center gap-2.5">
          <span className="grid size-9 place-items-center rounded-xl border border-[color-mix(in_srgb,var(--primary)_35%,transparent)] bg-[var(--primary-soft)] text-[var(--primary-strong)]">
            <Droplet size={18} strokeWidth={2} aria-hidden />
          </span>
          <div>
            <p className="text-[17px] font-bold leading-none tracking-[-0.02em] text-[var(--text)]">HYDRO</p>
            <p className="mt-1 text-[10.5px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
              Test Platformu
            </p>
          </div>
        </div>
        <button
          type="button"
          className="btn btn-icon lg:hidden"
          aria-label="Menüyü kapat"
          onClick={() => setSidebarOpen(false)}
        >
          <X size={16} />
        </button>
      </div>

      {/* Aktif Proje & Test Bölümü Seçicisi */}
      <div className="rounded-xl border border-[var(--primary-border)] bg-[color-mix(in_srgb,var(--primary-soft)_38%,var(--surface-2))] p-2.5">
        <p className="text-[9.5px] font-bold uppercase tracking-[0.11em] text-[var(--primary)]">
          Aktif Proje &amp; Test Bölümü
        </p>
        <p className="mt-0.5 truncate text-[11px] font-semibold text-[var(--text)]" title={projectName || "Proje seçilmedi"}>
          {projectName || "Genel Çalışma Alanı"}
        </p>
        {projectSessions && projectSessions.length > 0 ? (
          <select
            aria-label="Aktif Test Bölümü"
            value={sessionId ?? ""}
            onChange={(e) => {
              const nextId = e.target.value;
              if (nextId && nextId !== sessionId) {
                openSession.mutate(nextId);
              }
            }}
            className="mt-1.5 h-7 w-full rounded-lg border border-[var(--border)] bg-[var(--canvas)] px-2 text-[11px] font-medium text-[var(--text)] focus:border-[var(--primary)] focus:outline-none"
          >
            {!projectSessions.some((s) => s.id === sessionId) && sessionId ? (
              <option value={sessionId}>{sessionName}</option>
            ) : null}
            {projectSessions.map((sec) => (
              <option key={sec.id} value={sec.id}>
                {sec.section_meta?.section_no ? `${sec.section_meta.section_no} · ` : ""}
                {sec.name}
              </option>
            ))}
          </select>
        ) : (
          <button
            type="button"
            onClick={() => setTab("projects")}
            className="mt-1.5 block w-full truncate rounded-lg border border-[var(--border)] bg-[var(--canvas)] px-2 py-1 text-left text-[10.5px] text-[var(--text-muted)] hover:border-[var(--primary)]"
          >
            {sessionName || "Kesit seçin →"}
          </button>
        )}
      </div>

      <div className="flex-1 space-y-3.5 overflow-y-auto pr-0.5 scroll-thin">
        {/* Çalışma grubu */}
        <div>
          <p className="px-2 pb-1 text-[10.5px] font-bold uppercase tracking-[0.14em] text-[var(--text-muted)]">
            Çalışma
          </p>
          <div className="space-y-0.5">
            {VISIBLE_TABS.filter((item) => item.group === "calisma").map((item) => {
              const Icon = ICONS[item.key];
              return (
                <button
                  key={item.key}
                  type="button"
                  className="nav-item"
                  aria-current={tab === item.key ? "page" : undefined}
                  title={`${item.label} · Alt+${item.index}`}
                  onClick={() => {
                    setTab(item.key);
                    setSidebarOpen(false);
                  }}
                >
                  <Icon size={16} strokeWidth={1.9} aria-hidden />
                  <span>{item.label}</span>
                  <span className="nav-index">{item.index}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Seçenek 1: Kesite Bağlı Açılır Test Bölümü Formları Ağacı */}
        <div className="rounded-xl border border-[var(--border)] bg-[color-mix(in_srgb,var(--surface-2)_65%,transparent)] p-1.5">
          <button
            type="button"
            onClick={() => setFormsExpanded((prev) => !prev)}
            aria-expanded={formsExpanded}
            className="flex w-full items-center justify-between gap-1.5 rounded-lg px-1.5 py-1 text-left hover:bg-[var(--surface-3)]"
          >
            <span className="flex items-center gap-1 text-[10px] font-extrabold uppercase tracking-[0.09em] text-[var(--text-soft)]">
              {formsExpanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
              Test Bölümü Formları
            </span>
            <span
              className={cn(
                "rounded-full px-1.5 py-0.5 font-mono text-[9.5px] font-bold",
                summary?.failed_forms?.length
                  ? "bg-[var(--danger-bg)] text-[var(--danger)]"
                  : summary?.complete
                    ? "bg-[var(--success-bg)] text-[var(--success)]"
                    : "bg-[var(--surface-3)] text-[var(--text-muted)]",
              )}
            >
              {summary?.filled_required ?? 0}/{summary?.required_total ?? 11}
            </span>
          </button>

          {formsExpanded ? (
            <div className="mt-1 space-y-0.5">
              {mandatoryForms.map((item) => renderFormNavRow(item))}

              <div className="pt-1">
                <button
                  type="button"
                  onClick={() => setExtrasExpanded((prev) => !prev)}
                  aria-expanded={extrasExpanded}
                  className="flex w-full items-center justify-between rounded-lg border border-dashed border-[var(--border-strong)] bg-[var(--surface)] px-2 py-1 text-[10px] font-semibold text-[var(--text-muted)] hover:text-[var(--text)]"
                >
                  <span className="flex items-center gap-1">
                    {extrasExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                    Ek Raporlar (5 doküman)
                  </span>
                  <span className="font-mono text-[9.5px] text-[var(--primary)]">
                    {summary?.supplementary_filled ?? 0} dolu
                  </span>
                </button>
                {extrasExpanded ? (
                  <div className="mt-1 space-y-0.5 pl-1">
                    {extraForms.map((item) => renderFormNavRow(item))}
                  </div>
                ) : null}
              </div>
            </div>
          ) : null}
        </div>

        {/* Çıktı & Sistem grubu */}
        <div>
          <p className="px-2 pb-1 text-[10.5px] font-bold uppercase tracking-[0.14em] text-[var(--text-muted)]">
            Çıktı &amp; Sistem
          </p>
          <div className="space-y-0.5">
            {VISIBLE_TABS.filter((item) => item.group === "cikti").map((item) => {
              const Icon = ICONS[item.key];
              return (
                <button
                  key={item.key}
                  type="button"
                  className="nav-item"
                  aria-current={tab === item.key ? "page" : undefined}
                  title={`${item.label} · Alt+${item.index}`}
                  onClick={() => {
                    setTab(item.key);
                    setSidebarOpen(false);
                  }}
                >
                  <Icon size={16} strokeWidth={1.9} aria-hidden />
                  <span>{item.label}</span>
                  <span className="nav-index">{item.index}</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Alt Sunucu & Güncelleme Yöneticisi Kartı */}
      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-2.5">
        <div className="flex items-center justify-between gap-2 text-[10.5px] font-semibold text-[var(--text-muted)]">
          <span className="flex items-center gap-1.5">
            <BackendDot backend={backend} />
            {backend === "online"
              ? sessionApiReady === false
                ? "Sunucu kısmi"
                : "Sunucu bağlı"
              : backend === "demo"
                ? "Çevrimdışı mod"
                : "Kontrol ediliyor"}
          </span>
          <span className="font-mono text-[10px]">v{meta?.app.version ?? "1.9.0"}</span>
        </div>
        <button
          type="button"
          onClick={() => {
            setUpdateModalOpen(true);
            setSidebarOpen(false);
          }}
          className={cn(
            "mt-2 flex w-full items-center justify-between rounded-lg border px-2 py-1 text-[10.5px] font-semibold transition-colors",
            updateStatus?.update_available
              ? "border-[var(--success-border)] bg-[var(--success-bg)] text-[var(--success)]"
              : "border-[var(--border)] bg-[var(--surface)] text-[var(--text-muted)] hover:border-[var(--primary)] hover:text-[var(--text)]",
          )}
        >
          <span className="flex items-center gap-1.5">
            {updateStatus?.update_available ? (
              <ArrowUpCircle size={12} aria-hidden />
            ) : (
              <RefreshCw size={11} aria-hidden />
            )}
            {updateStatus?.update_available && updateStatus.latest_version
              ? `Yeni sürüm v${updateStatus.latest_version}`
              : "Güncelleme Yöneticisi"}
          </span>
          <span>İncele →</span>
        </button>
      </div>
    </nav>
  );

  return (
    <>
      <aside
        className={cn(
          "hidden w-[264px] shrink-0 border-r border-[var(--border)] bg-[color-mix(in_srgb,var(--surface-2)_72%,transparent)] px-3 py-3.5",
          desktopSidebarOpen && "lg:block",
        )}
      >
        <div className="sticky top-3.5 h-[calc(100vh-1.75rem)]">{nav}</div>
      </aside>

      {sidebarOpen ? (
        <div className="fixed inset-0 z-[60] lg:hidden">
          <button
            type="button"
            className="absolute inset-0"
            style={{ background: "var(--overlay)" }}
            aria-label="Menüyü kapat"
            onClick={() => setSidebarOpen(false)}
          />
          <aside className="relative h-full w-[274px] border-r border-[var(--border)] bg-[var(--surface)] px-3 py-4 shadow-2xl">
            {nav}
          </aside>
        </div>
      ) : null}
    </>
  );
}
