import {
  Activity,
  ArrowRight,
  CheckCircle2,
  ChevronRight,
  Circle,
  FileScan,
  FolderKanban,
  Gauge,
  Layers,
  Map,
  Mountain,
  Ruler,
  XCircle,
} from "lucide-react";
import { PageHeader } from "../components/layout/PageHeader";
import { SectionCard, KpiCard, ResultTile } from "../components/ui/Card";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { DecisionCard } from "../components/ui/DecisionCard";
import { OnboardingWelcomeCard } from "../components/onboarding/OnboardingWelcomeCard";
import { OfflineNotice } from "../components/ui/State";
import { ElevationProfileChart, TrendChart } from "../components/charts/LazyCharts";
import { geometryForInputs } from "../lib/mock";
import { BOTAS_FORM_BY_CODE } from "../lib/constants";
import { fmt, num, relativeTime, statusTone } from "../lib/format";
import type { BotasFormCode } from "../lib/types";
import { useAppStore } from "../store/useAppStore";
import { useMeta, useSessionForms } from "../hooks/queries";
import { cn } from "../lib/utils";

export function DashboardPage() {
  const inputs = useAppStore((state) => state.inputs);
  const results = useAppStore((state) => state.results);
  const history = useAppStore((state) => state.history);
  const backend = useAppStore((state) => state.backend);
  const sessionName = useAppStore((state) => state.sessionName);
  const sessionStatus = useAppStore((state) => state.sessionStatus);
  const projectId = useAppStore((state) => state.projectId);
  const projectName = useAppStore((state) => state.projectName);
  const projectCode = useAppStore((state) => state.projectCode);
  const sessionId = useAppStore((state) => state.sessionId);
  const setTab = useAppStore((state) => state.setTab);
  const setPendingScrollTarget = useAppStore((state) => state.setPendingScrollTarget);
  const openForm = useAppStore((state) => state.openForm);
  const onboardingDismissed = useAppStore((state) => state.onboardingDismissed);
  const tourActive = useAppStore((state) => state.tourActive);
  const { data: meta } = useMeta();
  const { data: formsPayload } = useSessionForms(sessionId);
  const formsSummary = formsPayload?.summary;
  const targetFormCode = (
    formsSummary?.first_issue_form_code ||
    formsPayload?.missing_required_forms?.[0]?.form_code ||
    "test_data"
  ) as BotasFormCode;

  const geometry = results.geometry ?? geometryForInputs(inputs);
  const air = results.air;
  const pressure = results.pressure;
  const profile = results.profile;

  const monSourceForm =
    formsPayload?.forms?.find((f) => f.form_code === "pressure_test" && f.status !== "empty") ??
    formsPayload?.forms?.find((f) => f.form_code === "leak_stabilization" && f.status !== "empty") ??
    formsPayload?.forms?.find((f) => f.form_code === "pressure_test");
  const monExt = monSourceForm?.extracted_data as Record<string, unknown> | undefined;
  const monNested = monExt?.monitoring as Record<string, unknown> | undefined;
  const rawTrendRows = Array.isArray(monNested?.rows)
    ? monNested.rows
    : Array.isArray(monExt?.rows)
      ? monExt.rows
      : [];
  const trendRows = rawTrendRows.filter(
    (r): r is Record<string, unknown> => Boolean(r && typeof r === "object"),
  );

  function open3DScene() {
    setPendingScrollTarget("sahne-3d");
    setTab("geometry");
  }

  const nextStep = !projectId
    ? { tab: "projects" as const, label: "Proje ve kesit seç", detail: "Çalışmaya başlamak için bir proje ve Test Bölümü seçin veya yeni oluşturun." }
    : !geometry
    ? { tab: "geometry" as const, label: "Geometriyi tamamla", detail: "Dış çap, et kalınlığı ve uzunluk girilmeden hesap yapılamaz; dilerseniz mevcut raporu OCR ile okuyabilirsiniz." }
    : !air
      ? { tab: "air" as const, label: "Hava içerik testini değerlendir", detail: "Vpa girildikten sonra tek tıkla karar üretilir." }
      : !pressure
        ? { tab: "pressure" as const, label: "Basınç değişim testini değerlendir", detail: "ΔT ve Pa değerleri hazır." }
        : { tab: "reports" as const, label: "Raporu üret", detail: "Kararlar hazır; PDF, Excel veya TXT olarak dışa aktarın." };

  const testsAndFormsDone = Boolean(
    air && pressure && (formsSummary ? formsSummary.filled_required >= formsSummary.required_total : true),
  );
  const workflowSteps = [
    {
      num: 1,
      label: "Proje & Kesit",
      detail: projectId ? projectCode || projectName || "Seçildi" : "Seçim bekliyor",
      done: Boolean(projectId),
      active: !projectId,
      tab: "projects" as const,
    },
    {
      num: 2,
      label: "Geometri & Kot",
      detail: geometry ? `${geometry.section_count} segment` : "Eksik",
      done: Boolean(geometry),
      active: Boolean(projectId) && !geometry,
      tab: "geometry" as const,
    },
    {
      num: 3,
      label: "Testler & Formlar",
      detail: air && pressure ? "Kararlar üretildi" : formsSummary ? `${formsSummary.filled_required}/${formsSummary.required_total} form` : "Hesap bekliyor",
      done: testsAndFormsDone,
      active: Boolean(geometry) && !testsAndFormsDone,
      tab: air && pressure ? ("forms" as const) : !air ? ("air" as const) : ("pressure" as const),
    },
    {
      num: 4,
      label: "Resmî Rapor",
      detail: air && pressure ? "Çıktıya hazır" : "Test sonrası",
      done: false,
      active: Boolean(air && pressure),
      tab: "reports" as const,
    },
  ];

  const specCode = meta?.spec.code ?? "4-NGTL 0-GN-P-002-5007 R4";

  return (
    <div className="space-y-4">
      <PageHeader
        kicker={projectCode ? `Genel Bakış · ${projectCode}` : "Genel Bakış"}
        title={projectName ? `${projectName} · ${sessionName}` : sessionName || "Test Bölümü"}
        description={`Operatör: ${inputs.report.operator || "belirtilmedi"} · ${specCode}`}
        meta={
          <>
            <Badge tone={sessionStatus === "completed" ? "pass" : "info"}>
              {sessionStatus === "completed" ? "Tamamlandı" : sessionStatus === "draft" ? "Taslak" : "Aktif"}
            </Badge>
            {results.lastComputedAt ? (
              <span className="text-[10.5px] text-[var(--text-faint)]">
                Son hesap: {relativeTime(results.lastComputedAt)}
              </span>
            ) : null}
          </>
        }
        actions={
          <Button size="lg" variant="primary" icon={<ArrowRight size={15} />} onClick={() => setTab(nextStep.tab)}>
            {nextStep.label}
          </Button>
        }
      />

      {backend === "demo" ? <OfflineNotice /> : null}
      {!onboardingDismissed && !tourActive ? <OnboardingWelcomeCard /> : null}

      {/* 4 Adımlı Canlı İlerleme Çubuğu */}
      <nav aria-label="Test değerlendirme adımları" className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {workflowSteps.map((stepItem) => (
          <button
            key={stepItem.num}
            type="button"
            onClick={() => {
              if (stepItem.tab === "forms") openForm(targetFormCode);
              else setTab(stepItem.tab);
            }}
            className={cn(
              "flex items-center gap-2.5 rounded-xl border px-3 py-2 text-left transition-colors",
              stepItem.active
                ? "border-[var(--primary)] bg-[var(--primary-soft)]"
                : stepItem.done
                  ? "border-[var(--success-border)] bg-[var(--surface-2)] hover:border-[var(--border-strong)]"
                  : "border-[var(--border)] bg-[var(--surface-2)] hover:border-[var(--border-strong)]",
            )}
          >
            <span
              className={cn(
                "grid size-6 shrink-0 place-items-center rounded-full font-mono text-[11px] font-bold",
                stepItem.done
                  ? "bg-[var(--success-bg)] text-[var(--success)]"
                  : stepItem.active
                    ? "bg-[var(--primary)] text-[var(--primary-ink)]"
                    : "bg-[var(--surface-3)] text-[var(--text-muted)]",
              )}
            >
              {stepItem.done ? <CheckCircle2 size={13} aria-hidden /> : stepItem.num}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[11.5px] font-semibold text-[var(--text)]">
                {stepItem.label}
              </span>
              <span className="block truncate text-[10px] text-[var(--text-muted)]">
                {stepItem.detail}
              </span>
            </span>
          </button>
        ))}
      </nav>

      {geometry ? (
        <>
          <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
            <KpiCard
              label="Boru Segmenti"
              value={num(geometry.section_count, 0)}
              unit="segment"
              icon={Layers}
              hint={`Et kalınlığı ${fmt.mm(inputs.geometry.wall_thickness_mm)}`}
            />
            <KpiCard
              label="Toplam uzunluk"
              value={num(geometry.total_length_m, 0)}
              unit="m"
              icon={Ruler}
              hint={`${num(geometry.total_length_m / 1000, 2)} km test bölümü`}
            />
            <KpiCard
              label="İç hacim"
              value={num(geometry.internal_volume_m3, 2)}
              unit="m³"
              icon={Layers}
              hint={`Limit 12.500 m³ · ${fmt.percentValue((geometry.internal_volume_m3 / 12500) * 100, 1)}`}
              tone={geometry.internal_volume_m3 > 12500 ? "fail" : "default"}
            />
            <KpiCard
              label="Test basıncı"
              value={num(inputs.field.monitored_pressure_bar ?? inputs.air.pressure_bar, 1)}
              unit="bar"
              icon={Gauge}
              hint={`Dizayn ${fmt.bar(inputs.section_profile.design_pressure_bar, 1)} · pencere ${
                profile ? `${num(profile.selected_window.minimum_required_pressure_bar, 0)}–${num(profile.selected_window.maximum_allowable_pressure_bar, 0)}` : "—"
              }`}
              tone={profile && !profile.feasible ? "fail" : "default"}
            />
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <DecisionCard
              decision={air?.decision}
              testName="Hava İçerik Testi"
              marginUnit="m³"
              actions={
                <Button size="sm" variant="ghost" icon={<ArrowRight size={12} />} onClick={() => setTab("air")}>
                  Detaya git
                </Button>
              }
              why={
                <>
                  <p>Vp = ((0,884·ri/s) + A) · 10⁻⁶ · Vt · P · K</p>
                  <p>
                    A = {fmt.a(inputs.air.a_micro_per_bar)} · P = {fmt.bar(inputs.air.pressure_rise_bar)} · K ={" "}
                    {num(inputs.air.k_factor, 3)} · Vpa = {fmt.m3(inputs.air.actual_added_water_m3)}
                  </p>
                </>
              }
              extra={
                air ? (
                  <div className="mt-3 grid grid-cols-3 gap-2">
                    <ResultTile label="Vp" value={num(air.theoretical_added_water_m3, 5)} unit="m³" />
                    <ResultTile label="Limit" value={num(air.acceptance_limit_m3, 5)} unit="m³" />
                    <ResultTile label="Vpa" value={num(air.actual_added_water_m3, 5)} unit="m³" />
                  </div>
                ) : null
              }
            />
            <DecisionCard
              decision={pressure?.decision}
              testName="Basınç Değişim Testi"
              marginUnit="bar"
              actions={
                <Button size="sm" variant="ghost" icon={<ArrowRight size={12} />} onClick={() => setTab("pressure")}>
                  Detaya git
                </Button>
              }
              why={
                <>
                  <p>Pt = (B · ΔT) / (0,884·ri/s + A)</p>
                  <p>
                    B = {fmt.b(inputs.pressure.b_micro_per_c)} · ΔT = {fmt.c(inputs.pressure.delta_t_c)} · Pa ={" "}
                    {fmt.bar(inputs.pressure.actual_pressure_change_bar)}
                  </p>
                </>
              }
              extra={
                pressure ? (
                  <div className="mt-3 grid grid-cols-3 gap-2">
                    <ResultTile label="Pt" value={num(pressure.theoretical_pressure_change_bar, 3)} unit="bar" />
                    <ResultTile label="Üst sınır" value={num(pressure.allowable_upper_pressure_change_bar, 3)} unit="bar" />
                    <ResultTile label="Marj" value={num(pressure.margin_bar, 2)} unit="bar" tone={pressure.passed ? "pass" : "fail"} />
                  </div>
                ) : null
              }
            />
          </div>
        </>
      ) : (
        <div className="panel flex flex-col justify-between gap-3 p-4 sm:flex-row sm:items-center">
          <div className="min-w-0">
            <p className="text-[13px] font-semibold text-[var(--text)]">{nextStep.label}</p>
            <p className="mt-0.5 text-[12px] text-[var(--text-muted)]">{nextStep.detail}</p>
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            <Button size="sm" variant="default" icon={<Ruler size={14} />} onClick={() => setTab("geometry")}>
              Geometriyi Gir
            </Button>
            <Button size="sm" variant="default" icon={<FileScan size={14} />} onClick={() => setTab("ocr")}>
              OCR Rapor Yükle
            </Button>
            {projectId ? (
              <Button size="sm" variant="ghost" icon={<FolderKanban size={14} />} onClick={() => openForm(targetFormCode)}>
                Formlar ({BOTAS_FORM_BY_CODE[targetFormCode]?.shortCode ?? "015"})
              </Button>
            ) : null}
          </div>
        </div>
      )}

      <details className="disclosure-card">
        <summary className="disclosure-summary">
          <ChevronRight size={15} className="disclosure-chevron shrink-0" aria-hidden />
          <span>Grafikler ve Son İşlemler</span>
          <span className="ml-auto text-[11px] font-normal text-[var(--text-faint)]">
            Kot profili · 24s eğilim · {history.length} kayıt
          </span>
        </summary>
        <div className="disclosure-body space-y-4">
          <div className="grid gap-4 xl:grid-cols-[1.2fr_1fr]">
            <SectionCard
              title="Kot profili"
              description={inputs.profile_points.length >= 2 ? "Plan-profil paftasından aktarılan gerçek arazi kot profili." : "Kesit kot değerlerinden oluşturulan boykesit profili."}
              icon={Mountain}
              action={
                <Button size="sm" variant="ghost" icon={<Map size={12} />} onClick={open3DScene}>
                  3D saha görünümü
                </Button>
              }
            >
              <ElevationProfileChart inputs={inputs} height={210} />
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[10.5px] text-[var(--text-faint)]">
                <span>Başlangıç {fmt.m(inputs.section_profile.start_elevation_m, 0)}</span>
                <span>En yüksek {fmt.m(inputs.section_profile.highest_elevation_m, 0)}</span>
                <span>En düşük {fmt.m(inputs.section_profile.lowest_elevation_m, 0)}</span>
                <span>Bitiş {fmt.m(inputs.section_profile.end_elevation_m, 0)}</span>
              </div>
            </SectionCard>

            <SectionCard
              title="Son 24 saat eğilimi"
              description="BOT-FRM-021 / 018 saatlik izleme kayıtlarından basınç ve sıcaklık seyri."
              icon={Activity}
              action={
                <Button size="sm" variant="ghost" icon={<ArrowRight size={12} />} onClick={() => openForm("pressure_test")}>
                  021 Formu
                </Button>
              }
            >
              {trendRows.length < 2 ? (
                <div style={{ height: 180 }}>
                  <div className="grid h-full place-items-center rounded-xl border border-dashed border-[var(--border)] px-4 text-center text-[11.5px] text-[var(--text-faint)]">
                    24 saatlik izleme verisi henüz girilmedi (BOT-FRM-021 / 018)
                  </div>
                </div>
              ) : (
                <TrendChart rows={trendRows} height={180} />
              )}
              <div className="mt-1 flex gap-4 text-[10px] text-[var(--text-faint)]">
                <span className="flex items-center gap-1"><span className="legend-dot bg-[var(--chart-1)]" /> Basınç (bar)</span>
                <span className="flex items-center gap-1"><span className="legend-dot bg-[var(--chart-3)]" /> Sıcaklık (°C)</span>
              </div>
            </SectionCard>
          </div>

          <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-3.5">
            <p className="text-[12px] font-semibold text-[var(--text)]">Son işlemler</p>
            {history.length === 0 ? (
              <p className="mt-1 text-[11.5px] text-[var(--text-faint)]">
                Henüz hesaplama kaydı yok. İlk hesaplamadan sonra kayıtlar burada listelenir.
              </p>
            ) : (
              <ol className="mt-2 space-y-1.5">
                {history.slice(0, 6).map((entry) => (
                  <li
                    key={entry.id}
                    className="flex items-start gap-2.5 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-2"
                  >
                    <span className={cn("mt-1", `tone-${statusTone(entry.status)}`)}>
                      {entry.status === "BASARILI" ? (
                        <CheckCircle2 size={13} aria-hidden />
                      ) : entry.status === "BASARISIZ" ? (
                        <XCircle size={13} aria-hidden />
                      ) : (
                        <Circle size={13} aria-hidden />
                      )}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate text-[11.5px] font-medium">{entry.title}</span>
                        <span className="chip shrink-0">{relativeTime(entry.at)}</span>
                      </div>
                      <p className="mt-0.5 line-clamp-2 text-[10.5px] leading-snug text-[var(--text-faint)]">
                        {entry.summary}
                      </p>
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </div>
        </div>
      </details>
    </div>
  );
}
