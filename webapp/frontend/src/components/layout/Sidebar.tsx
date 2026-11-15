import {
  Droplet,
  FileText,
  FolderKanban,
  Gauge,
  LayoutDashboard,
  Map,
  Ruler,
  ScanLine,
  Settings,
  Sigma,
  Table2,
  Wind,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { VISIBLE_TABS } from "../../lib/constants";
import type { BackendMode, TabKey } from "../../lib/types";
import { useMeta } from "../../hooks/queries";
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
  field: Map,
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

export function Sidebar() {
  const tab = useAppStore((state) => state.tab);
  const setTab = useAppStore((state) => state.setTab);
  const sidebarOpen = useAppStore((state) => state.sidebarOpen);
  const setSidebarOpen = useAppStore((state) => state.setSidebarOpen);
  const backend = useAppStore((state) => state.backend);
  const sessionApiReady = useAppStore((state) => state.sessionApiReady);
  const { data: meta } = useMeta();

  const groups = [
    { key: "calisma" as const, label: "Çalışma" },
    { key: "cikti" as const, label: "Çıktı & Sistem" },
  ];

  const nav = (
    <nav className="flex h-full flex-col gap-5">
      <div className="flex items-center justify-between px-1">
        <div className="flex items-center gap-2.5">
          <span className="grid size-9 place-items-center rounded-xl border border-[color-mix(in_srgb,var(--primary)_35%,transparent)] bg-[var(--primary-soft)] text-[var(--primary-strong)]">
            <Droplet size={18} strokeWidth={2} aria-hidden />
          </span>
          <div>
            <p className="text-[15px] font-semibold leading-none tracking-[-0.02em]">HYDRO</p>
            <p className="mt-1 text-[10px] font-medium uppercase tracking-[0.14em] text-[var(--text-faint)]">
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

      <div className="flex-1 space-y-5 overflow-y-auto pr-0.5 scroll-thin">
        {groups.map((group) => (
          <div key={group.key}>
            <p className="px-2 pb-1.5 text-[9.5px] font-semibold uppercase tracking-[0.16em] text-[var(--text-faint)]">
              {group.label}
            </p>
            <div className="space-y-0.5">
              {VISIBLE_TABS.filter((item) => item.group === group.key).map((item) => {
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
                    <Icon size={15} strokeWidth={1.8} aria-hidden />
                    <span>{item.label}</span>
                    <span className="nav-index">{item.index}</span>
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-3">
        <div className="flex items-center gap-2 text-[10.5px] font-semibold text-[var(--text-muted)]">
          <BackendDot backend={backend} />
          {backend === "online"
            ? sessionApiReady === false
              ? "Backend kısmi"
              : "Backend bağlı"
            : backend === "demo"
              ? "Demo modu"
              : "Bağlantı kontrol ediliyor"}
        </div>
        <p className="mt-1.5 text-[10px] leading-relaxed text-[var(--text-faint)]">
          {meta?.spec.code ?? "4-NGTL 0-GN-P-002-5007 R4"}
          <br />
          Sürüm {meta?.app.version ?? "1.7.3"}
        </p>
      </div>
    </nav>
  );

  return (
    <>
      <aside className="hidden w-[228px] shrink-0 border-r border-[var(--border)] bg-[color-mix(in_srgb,var(--surface-2)_72%,transparent)] px-3 py-4 lg:block">
        <div className="sticky top-4 h-[calc(100vh-2rem)]">{nav}</div>
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
          <aside className="relative h-full w-[260px] border-r border-[var(--border)] bg-[var(--surface)] px-3 py-4 shadow-2xl">
            {nav}
          </aside>
        </div>
      ) : null}
    </>
  );
}
