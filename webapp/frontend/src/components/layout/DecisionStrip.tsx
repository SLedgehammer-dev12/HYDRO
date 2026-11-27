import { ArrowUpRight, CircleDot, FileText } from "lucide-react";
import { BOTAS_FORM_BY_CODE } from "../../lib/constants";
import { decisionLabel, num, statusTone } from "../../lib/format";
import { useSessionForms } from "../../hooks/queries";
import { useAppStore } from "../../store/useAppStore";
import type { BotasFormCode, Decision, TabKey } from "../../lib/types";
import { cn } from "../../lib/utils";

function marginUnit(tab: TabKey): string {
  if (tab === "air") return "m³";
  if (tab === "pressure" || tab === "geometry") return "bar";
  return "";
}

export function DecisionStrip() {
  const tab = useAppStore((state) => state.tab);
  const setTab = useAppStore((state) => state.setTab);
  const activeFormCode = useAppStore((state) => state.activeFormCode);
  const openForm = useAppStore((state) => state.openForm);
  const sessionId = useAppStore((state) => state.sessionId);
  const results = useAppStore((state) => state.results);
  const backend = useAppStore((state) => state.backend);

  const { data: formsPayload } = useSessionForms(sessionId);
  const summary = formsPayload?.summary;

  const air = results.air?.decision;
  const pressure = results.pressure?.decision;
  const profile = results.profile?.decision;

  const activeFormSpec = tab === "forms" ? BOTAS_FORM_BY_CODE[activeFormCode] : undefined;
  const activeFormRec =
    tab === "forms"
      ? formsPayload?.forms.find((f) => f.form_code === activeFormCode)
      : undefined;

  const active: Decision | undefined =
    tab === "pressure" ? pressure : tab === "geometry" ? profile : tab === "air" ? air : air ?? pressure;

  const activeTab: TabKey =
    tab === "pressure" || tab === "geometry" || tab === "air"
      ? tab
      : air
        ? "air"
        : "pressure";

  const formTone = summary?.failed_forms?.length
    ? "fail"
    : (summary?.warning_forms_count ?? 0) > 0
      ? "warning"
      : summary?.complete
        ? "pass"
        : "info";

  const tone =
    tab === "forms" && activeFormRec
      ? activeFormRec.status === "passed"
        ? "pass"
        : activeFormRec.status === "failed"
          ? "fail"
          : activeFormRec.status === "warning"
            ? "warning"
            : "info"
      : statusTone(active?.status);

  const margin = active?.margin;
  const unit = marginUnit(activeTab);

  const issueTargetCode =
    (summary?.first_issue_form_code as BotasFormCode | undefined) || "test_data";

  return (
    <div className="w-full max-w-full overflow-hidden border-b border-[var(--border)] bg-[color-mix(in_srgb,var(--surface-2)_78%,transparent)] backdrop-blur-lg sm:sticky sm:top-[45px] sm:z-30">
      <div className="mx-auto flex w-full max-w-[1500px] flex-nowrap items-center gap-x-2 overflow-x-auto px-3 py-0 scroll-thin sm:px-4 sm:py-0.5">
        <span className="flex shrink-0 items-center gap-1.5 whitespace-nowrap text-[11px] font-bold uppercase tracking-[0.14em] text-[var(--text-muted)]">
          <CircleDot size={11} aria-hidden />
          Aktif karar
        </span>

        <button
          type="button"
          className={cn(
            "badge transition-transform hover:-translate-y-px",
            air ? `badge-${statusTone(air.status)}` : "badge-pending",
            activeTab === "air" && tab !== "forms" && "ring-1 ring-[color-mix(in_srgb,var(--primary)_35%,transparent)]",
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
            activeTab === "pressure" && tab !== "forms" && "ring-1 ring-[color-mix(in_srgb,var(--primary)_35%,transparent)]",
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
              activeTab === "geometry" && tab !== "forms" && "ring-1 ring-[color-mix(in_srgb,var(--primary)_35%,transparent)]",
            )}
            onClick={() => {
              useAppStore.getState().setPendingScrollTarget("saha");
              setTab("geometry");
            }}
            title="Basınç penceresi kararı"
          >
            Profil · {decisionLabel(profile.status)}
          </button>
        ) : null}

        {summary ? (
          <button
            type="button"
            className={cn(
              "badge hidden transition-transform hover:-translate-y-px md:inline-flex",
              `badge-${formTone}`,
              tab === "forms" && "ring-1 ring-[color-mix(in_srgb,var(--primary)_35%,transparent)]",
            )}
            onClick={() => openForm(issueTargetCode)}
            title="BOTAŞ Test Bölümü Formları durum özeti"
          >
            <FileText size={10} aria-hidden />
            Formlar · {summary.filled_required}/{summary.required_total}
          </button>
        ) : null}

        <span className="hidden h-3.5 w-px bg-[var(--border-strong)] sm:block" aria-hidden />

        <span className={cn("hidden items-center gap-1.5 text-[11px] md:flex", `tone-${tone}`)}>
          <span className="status-dot" aria-hidden />
          {tab === "forms" && activeFormSpec ? (
            <>
              <span className="font-semibold">
                {activeFormSpec.shortCode} · {activeFormSpec.shortTitle}
              </span>
              {activeFormRec?.findings?.length ? (
                <span className="font-mono text-[11px] text-[var(--text-faint)]">
                  · {activeFormRec.findings[0].ref || activeFormRec.findings[0].title}
                </span>
              ) : null}
            </>
          ) : (
            <>
              <span className="font-semibold">{active?.title ?? "Değerlendirme bekliyor"}</span>
              {active?.rule ? (
                <span className="font-mono text-[11px] text-[var(--text-faint)]">· {active.rule}</span>
              ) : null}
            </>
          )}
        </span>

        {tab !== "forms" && typeof margin === "number" ? (
          <span className="ml-auto flex items-center gap-1 text-[11px] text-[var(--text-faint)]">
            Marj
            <span className={cn("font-mono font-semibold", `tone-${tone}`)}>
              {num(margin, 4)} {unit}
            </span>
          </span>
        ) : null}

        {backend === "demo" ? (
          <span className="badge badge-warning hidden lg:inline-flex">çevrimdışı</span>
        ) : null}

        <button
          type="button"
          className="ml-auto inline-flex shrink-0 items-center gap-0.5 whitespace-nowrap text-[11px] font-semibold text-[var(--primary)] hover:underline"
          onClick={() => {
            if (tab === "forms" && summary?.first_issue_form_code) {
              openForm(summary.first_issue_form_code as BotasFormCode);
            } else {
              setTab(activeTab);
            }
          }}
        >
          {tab === "forms" && summary?.first_issue_form_code ? "Bulgulu forma git" : "Detaya git"}
          <ArrowUpRight size={11} aria-hidden />
        </button>
      </div>
    </div>
  );
}
