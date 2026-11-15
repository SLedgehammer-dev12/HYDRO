import { AlertTriangle, ArrowRight, CheckCircle2, CircleDashed, Sigma } from "lucide-react";
import { geometryForInputs } from "../../lib/mock";
import { fmt, formatCoefficientState, num } from "../../lib/format";
import { CHECK_DEFINITIONS } from "../../lib/constants";
import { useAppStore } from "../../store/useAppStore";
import { Badge, CoefficientBadge } from "../ui/Badge";
import { ProgressBar } from "../ui/Gauge";

export function RightPanel() {
  const inputs = useAppStore((state) => state.inputs);
  const results = useAppStore((state) => state.results);
  const setTab = useAppStore((state) => state.setTab);

  const geometry = results.geometry ?? geometryForInputs(inputs);
  const checked = CHECK_DEFINITIONS.filter((check) => inputs.checks[check.key]).length;
  const airCoeff = results.coefficients?.airA;
  const pressureB = results.coefficients?.pressureB;

  const missing: string[] = [];
  if (!geometry) missing.push("Geometri: dış çap, et kalınlığı ve uzunluk gerekli.");
  if (!inputs.air.actual_added_water_m3) missing.push("Hava: fiili ilave su (Vpa) girilmedi.");
  if (!inputs.pressure.delta_t_c) missing.push("Basınç: ΔT girilmedi.");
  if (!inputs.pressure.actual_pressure_change_bar)
    missing.push("Basınç: Pa girilmedi.");
  if (!inputs.section_profile.smys_mpa)
    missing.push("Profil: malzeme kalitesi / SMYS seçilmedi.");

  return (
    <aside className="hidden w-[292px] shrink-0 xl:block">
      <div className="sticky top-[104px] max-h-[calc(100vh-120px)] space-y-3 overflow-y-auto pb-6 pr-0.5 scroll-thin">
        <div className="panel p-3.5">
          <div className="flex items-center justify-between">
            <p className="eyebrow">Canlı Özet</p>
            <span className="chip">{results.source === "demo" ? "demo" : "canlı"}</span>
          </div>

          <div className="mt-3 space-y-2">
            <button
              type="button"
              className="flex w-full items-center justify-between rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-2 text-left hover:border-[var(--border-strong)]"
              onClick={() => setTab("geometry")}
            >
              <span className="text-[11px] text-[var(--text-muted)]">Geometri</span>
              <span className="font-mono text-[11px] text-[var(--text-soft)]">
                {geometry ? `${geometry.section_count} kesit` : "—"}
              </span>
            </button>
            <div className="grid grid-cols-2 gap-2">
              <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-2">
                <p className="text-[9.5px] uppercase tracking-wide text-[var(--text-faint)]">Uzunluk</p>
                <p className="mt-0.5 font-mono text-[12px]">{geometry ? fmt.m(geometry.total_length_m, 0) : "—"}</p>
              </div>
              <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-2">
                <p className="text-[9.5px] uppercase tracking-wide text-[var(--text-faint)]">Hacim</p>
                <p className="mt-0.5 font-mono text-[12px]">{geometry ? fmt.m3Short(geometry.internal_volume_m3) : "—"}</p>
              </div>
            </div>
          </div>

          <div className="mt-3 border-t border-[var(--border)] pt-2.5">
            <p className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--text-faint)]">
              <Sigma size={11} aria-hidden /> Katsayılar
            </p>
            <div className="mt-1.5 space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="text-[11px] text-[var(--text-muted)]">A · hava</span>
                <span className="flex items-center gap-1.5">
                  <span className="font-mono text-[10.5px]">{airCoeff ? num(airCoeff.a_micro_per_bar, 4) : "—"}</span>
                  <CoefficientBadge state={airCoeff?.state ?? "empty"} />
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[11px] text-[var(--text-muted)]">B · basınç</span>
                <span className="flex items-center gap-1.5">
                  <span className="font-mono text-[10.5px]">{pressureB ? num(pressureB.b_micro_per_c, 3) : "—"}</span>
                  <CoefficientBadge state={pressureB ? "reference" : "empty"} />
                </span>
              </div>
            </div>
            <button
              type="button"
              className="mt-2 inline-flex items-center gap-0.5 text-[10.5px] font-semibold text-[var(--primary)] hover:underline"
              onClick={() => setTab("coefficients")}
            >
              A/B hazırla <ArrowRight size={11} />
            </button>
          </div>

          <div className="mt-3 border-t border-[var(--border)] pt-2.5">
            <div className="flex items-center justify-between">
              <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--text-faint)]">
                Saha kontrolü
              </p>
              <span className="font-mono text-[10.5px] text-[var(--text-muted)]">
                {checked}/{CHECK_DEFINITIONS.length}
              </span>
            </div>
            <ProgressBar value={checked} max={CHECK_DEFINITIONS.length} tone={checked === 11 ? "pass" : "info"} className="mt-1.5" />
            <button
              type="button"
              className="mt-2 inline-flex items-center gap-0.5 text-[10.5px] font-semibold text-[var(--primary)] hover:underline"
              onClick={() => setTab("field")}
            >
              Checklist’i aç <ArrowRight size={11} />
            </button>
          </div>
        </div>

        <div className="panel p-3.5">
          <p className="eyebrow">Uyarılar</p>
          {missing.length === 0 ? (
            <div className="mt-2 flex items-start gap-2 text-[11px] text-[var(--text-muted)]">
              <CheckCircle2 size={14} className="mt-0.5 shrink-0 tone-pass" aria-hidden />
              Zorunlu alanlar tamam görünüyor. Değerlendirme yapmadan önce birimleri kontrol edin.
            </div>
          ) : (
            <ul className="mt-2 space-y-1.5">
              {missing.slice(0, 4).map((item) => (
                <li key={item} className="flex items-start gap-1.5 text-[10.5px] leading-snug text-[var(--text-muted)]">
                  <AlertTriangle size={12} className="mt-0.5 shrink-0 tone-warning" aria-hidden />
                  {item}
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="panel-soft p-3">
          <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--text-faint)]">
            <CircleDashed size={11} aria-hidden /> Sıradaki adım
          </div>
          <p className="mt-1.5 text-[11px] leading-relaxed text-[var(--text-muted)]">
            {!geometry
              ? "Geometriyi tamamlayın."
              : !inputs.pressure.b_micro_per_c
                ? "B katsayısını hazırlayın."
                : !results.air
                  ? "Hava içerik testini değerlendirin."
                  : !results.pressure
                    ? "Basınç değişim testini değerlendirin."
                    : "Raporu önizleyip dışa aktarın."}
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <Badge tone={inputs.material_grade ? "pass" : "warning"}>
              {inputs.material_grade ? "Malzeme seçili" : "Malzeme eksik"}
            </Badge>
            <Badge tone={formatCoefficientState(airCoeff?.state) === "BEKLİYOR" ? "pending" : "pass"}>
              A {formatCoefficientState(airCoeff?.state)}
            </Badge>
          </div>
        </div>
      </div>
    </aside>
  );
}
