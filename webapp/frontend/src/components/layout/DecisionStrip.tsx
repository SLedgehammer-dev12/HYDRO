import { ArrowUpRight, CircleDot } from "lucide-react";
import { decisionLabel, num, statusTone } from "../../lib/format";
import { useAppStore } from "../../store/useAppStore";
import type { Decision, TabKey } from "../../lib/types";
import { cn } from "../../lib/utils";

function marginUnit(tab: TabKey): string {
  if (tab === "air") return "m³";
  if (tab === "pressure" || tab === "geometry") return "bar";
  return "";
}

export function DecisionStrip() {
  const tab = useAppStore((state) => state.tab);
  const setTab = useAppStore((state) => state.setTab);
  const results = useAppStore((state) => state.results);
  const backend = useAppStore((state) => state.backend);

  const air = results.air?.decision;
  const pressure = results.pressure?.decision;
  const profile = results.profile?.decision;

  const active: Decision | undefined =
    tab === "pressure" ? pressure : tab === "geometry" ? profile : tab === "air" ? air : air ?? pressure;

  const activeTab: TabKey =
    tab === "pressure" || tab === "geometry" || tab === "air"
      ? tab
      : air
        ? "air"
        : "pressure";

  const tone = statusTone(active?.status);
  const margin = active?.margin;
  const unit = marginUnit(activeTab);

  return (
    <div className="sticky top-[57px] z-30 border-b border-[var(--border)] bg-[color-mix(in_srgb,var(--surface-2)_78%,transparent)] backdrop-blur-lg">
      <div className="mx-auto flex max-w-[1500px] flex-wrap items-center gap-x-2 gap-y-1.5 px-4 py-1.5">
        <span className="flex items-center gap-1.5 text-[9.5px] font-semibold uppercase tracking-[0.14em] text-[var(--text-faint)]">
          <CircleDot size={11} aria-hidden />
          Aktif karar
        </span>

        <button
          type="button"
          className={cn(
            "badge transition-transform hover:-translate-y-px",
            air ? `badge-${statusTone(air.status)}` : "badge-pending",
            activeTab === "air" && "ring-1 ring-[color-mix(in_srgb,var(--primary)_35%,transparent)]",
          )}
          onClick={() => setTab("air")}
          title="Hava içerik testi kararı"
        >
          Hava · {decisionLabel(air?.status)}
        </button>

        <button
          type="button"
          className={cn(
            "badge transition-transform hover:-translate-y-px",
            pressure ? `badge-${statusTone(pressure.status)}` : "badge-pending",
            activeTab === "pressure" && "ring-1 ring-[color-mix(in_srgb,var(--primary)_35%,transparent)]",
          )}
          onClick={() => setTab("pressure")}
          title="Basınç değişim testi kararı"
        >
          Basınç · {decisionLabel(pressure?.status)}
        </button>

        {profile ? (
          <button
            type="button"
            className={cn(
              "badge hidden transition-transform hover:-translate-y-px sm:inline-flex",
              `badge-${statusTone(profile.status)}`,
              activeTab === "geometry" && "ring-1 ring-[color-mix(in_srgb,var(--primary)_35%,transparent)]",
            )}
            onClick={() => {
              setTab("geometry");
              window.setTimeout(() => {
                document.getElementById("saha")?.scrollIntoView({ behavior: "smooth", block: "start" });
              }, 30);
            }}
            title="Basınç penceresi kararı"
          >
            Profil · {decisionLabel(profile.status)}
          </button>
        ) : null}

        <span className="hidden h-3.5 w-px bg-[var(--border-strong)] sm:block" aria-hidden />

        <span className={cn("hidden items-center gap-1.5 text-[11px] md:flex", `tone-${tone}`)}>
          <span className="status-dot" aria-hidden />
          <span className="font-semibold">{active?.title ?? "Değerlendirme bekliyor"}</span>
          {active?.rule ? (
            <span className="font-mono text-[10.5px] text-[var(--text-faint)]">· {active.rule}</span>
          ) : null}
        </span>

        {typeof margin === "number" ? (
          <span className="ml-auto flex items-center gap-1 text-[10.5px] text-[var(--text-faint)]">
            Marj
            <span className={cn("font-mono font-semibold", `tone-${tone}`)}>
              {num(margin, 4)} {unit}
            </span>
          </span>
        ) : null}

        {backend === "demo" ? (
          <span className="badge badge-warning hidden lg:inline-flex">demo verisi</span>
        ) : null}

        <button
          type="button"
          className="ml-auto inline-flex items-center gap-0.5 text-[10.5px] font-semibold text-[var(--primary)] hover:underline"
          onClick={() => setTab(activeTab)}
        >
          Detaya git
          <ArrowUpRight size={11} aria-hidden />
        </button>
      </div>
    </div>
  );
}
