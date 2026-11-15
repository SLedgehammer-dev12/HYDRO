import {
  Activity,
  ArrowRight,
  CheckCircle2,
  Circle,
  Gauge,
  Layers,
  Map,
  Mountain,
  Ruler,
  Sigma,
  Wind,
  XCircle,
} from "lucide-react";
import { motion } from "framer-motion";
import PipelineScene from "../components/three/PipelineScene";
import { PageHeader } from "../components/layout/PageHeader";
import { SectionCard, KpiCard, ResultTile } from "../components/ui/Card";
import { Badge, StatusBadge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { DecisionCard } from "../components/ui/DecisionCard";
import { OfflineNotice, EmptyState, InlineNotice } from "../components/ui/State";
import { ElevationProfileChart, TrendChart } from "../components/charts/Charts";
import { RatioGauge, ProgressBar } from "../components/ui/Gauge";
import { geometryForInputs, buildSceneData } from "../lib/mock";
import { CHECK_DEFINITIONS } from "../lib/constants";
import { dateTime, fmt, num, relativeTime, statusTone } from "../lib/format";
import { useAppStore } from "../store/useAppStore";
import { useMeta } from "../hooks/queries";
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
  const setTab = useAppStore((state) => state.setTab);
  const { data: meta } = useMeta();

  const geometry = results.geometry ?? geometryForInputs(inputs);
  const air = results.air;
  const pressure = results.pressure;
  const profile = results.profile;
  const checked = CHECK_DEFINITIONS.filter((check) => inputs.checks[check.key]).length;
  const scene = buildSceneData(inputs, results);

  const airAReady = Boolean(inputs.air.a_micro_per_bar);
  const bReady = Boolean(inputs.pressure.b_micro_per_c);
  const deltaReady = Boolean(inputs.pressure.delta_t_c !== null && inputs.pressure.actual_pressure_change_bar !== null);

  const nextStep = !projectId
    ? { tab: "projects" as const, label: "Proje ve kesit seç", detail: "Kesit kaydı bir projeye bağlanmadan çalışma başlatılamaz." }
    : !geometry
    ? { tab: "geometry" as const, label: "Geometriyi tamamla", detail: "Dış çap, et kalınlığı ve uzunluk girilmeden hesap yapılamaz." }
    : !airAReady || !bReady
      ? { tab: "coefficients" as const, label: "Katsayıları hazırla", detail: "A ve B katsayıları testlerin temel girdisidir." }
      : !air
        ? { tab: "air" as const, label: "Hava içerik testini değerlendir", detail: "Vpa girildikten sonra tek tıkla karar üretilir." }
        : !pressure
          ? { tab: "pressure" as const, label: "Basınç değişim testini değerlendir", detail: "ΔT ve Pa değerleri hazır." }
          : { tab: "reports" as const, label: "Raporu üret", detail: "Kararlar hazır; PDF, Excel veya TXT olarak dışa aktarın." };

  const prep = [
    {
      label: "Proje ve kesit kimliği",
      ready: Boolean(projectId),
      tab: "projects" as const,
      detail: projectId ? `${projectCode || "proje"} · ${inputs.section_meta.section_no || "kesit"}` : "Proje seçilmedi",
    },
    {
      label: "Geometri (kesit + uzunluk)",
      ready: Boolean(geometry),
      tab: "geometry" as const,
      detail: geometry ? `${geometry.section_count} kesit · ${fmt.m(geometry.total_length_m, 0)}` : "Eksik alan var",
    },
    {
      label: "A katsayısı",
      ready: airAReady,
      tab: "coefficients" as const,
      detail: airAReady ? fmt.a(inputs.air.a_micro_per_bar) : "Hesaplanmadı",
    },
    {
      label: "B katsayısı",
      ready: bReady,
      tab: "coefficients" as const,
      detail: bReady ? fmt.b(inputs.pressure.b_micro_per_c) : "Hesaplanmadı",
    },
    {
      label: "ΔT ve Pa",
      ready: deltaReady,
      tab: "pressure" as const,
      detail: deltaReady ? `ΔT ${fmt.c(inputs.pressure.delta_t_c)} · Pa ${fmt.bar(inputs.pressure.actual_pressure_change_bar)}` : "Eksik",
    },
  ];

  return (
    <div className="space-y-5">
      <PageHeader
        kicker="Dashboard"
        title={`Merhaba, ${inputs.report.operator || "operatör"}`}
        description={
          <>
            <span className="font-medium text-[var(--text-soft)]">{projectName || "Proje seçilmedi"}</span>
            {projectCode ? <span className="font-mono text-[11px] text-[var(--text-faint)]"> · {projectCode}</span> : null}
            <span className="text-[var(--text-faint)]"> · </span>
            <span className="font-medium text-[var(--text-soft)]">{sessionName}</span> kesitinin durumu.
            Kararlar backend’den veya demo motorundan gelir; son kabul her zaman yetkili personel
            tarafından verilir.
          </>
        }
        meta={
          <>
            <Badge tone={sessionStatus === "completed" ? "pass" : "info"}>
              {sessionStatus === "completed" ? "Tamamlandı" : sessionStatus === "draft" ? "Taslak" : "Aktif"}
            </Badge>
            <span className="text-[10.5px] text-[var(--text-faint)]">
              Son hesap: {results.lastComputedAt ? relativeTime(results.lastComputedAt) : "—"}
            </span>
            {meta ? <span className="chip">{meta.spec.code}</span> : null}
          </>
        }
        actions={
          <>
            <Button variant="ghost" icon={<Layers size={14} />} onClick={() => setTab("projects")}>
              Projeler
            </Button>
            <Button variant="ghost" icon={<Map size={14} />} onClick={() => setTab("geometry")}>
              Sahayı gör
            </Button>
            <Button size="lg" variant="primary" icon={<ArrowRight size={15} />} onClick={() => setTab(nextStep.tab)}>
              {nextStep.label}
            </Button>
          </>
        }
      />

      {backend === "demo" ? <OfflineNotice /> : null}

      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <KpiCard
          label="Segment"
          value={geometry ? num(geometry.section_count, 0) : "—"}
          unit="kesit"
          icon={Layers}
          hint={geometry ? `Et kalınlığı ${fmt.mm(inputs.geometry.wall_thickness_mm)}` : "Geometri girilmedi"}
        />
        <KpiCard
          label="Toplam uzunluk"
          value={geometry ? num(geometry.total_length_m, 0) : "—"}
          unit="m"
          icon={Ruler}
          hint={geometry ? `${num(geometry.total_length_m / 1000, 2)} km test bölümü` : "Uzunluk girilmedi"}
        />
        <KpiCard
          label="İç hacim"
          value={geometry ? num(geometry.internal_volume_m3, 2) : "—"}
          unit="m³"
          icon={Layers}
          hint={geometry ? `Limit 12.500 m³ · ${fmt.percentValue((geometry.internal_volume_m3 / 12500) * 100, 1)}` : "Hacim hesaplanamadı"}
          tone={geometry && geometry.internal_volume_m3 > 12500 ? "fail" : "default"}
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

      <div className="grid gap-4 xl:grid-cols-[1fr_1fr_0.9fr]">
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
        <SectionCard
          title="Hazırlık kontrolü"
          description="Eksik satıra tıklayarak ilgili sekmeye gidin."
          icon={CheckCircle2}
          bodyClassName="pt-3"
        >
          <ul className="space-y-1.5">
            {prep.map((item) => (
              <li key={item.label}>
                <button
                  type="button"
                  className="flex w-full items-start gap-2 rounded-lg border border-transparent px-1.5 py-1.5 text-left transition-colors hover:border-[var(--border)] hover:bg-[var(--surface-2)]"
                  onClick={() => setTab(item.tab)}
                >
                  {item.ready ? (
                    <CheckCircle2 size={14} className="mt-0.5 shrink-0 tone-pass" aria-hidden />
                  ) : (
                    <Circle size={14} className="mt-0.5 shrink-0 text-[var(--text-faint)]" aria-hidden />
                  )}
                  <span className="min-w-0 flex-1">
                    <span className="block text-[11.5px] font-medium text-[var(--text-soft)]">{item.label}</span>
                    <span className="mt-0.5 block truncate text-[10px] text-[var(--text-faint)]">{item.detail}</span>
                  </span>
                  <ArrowRight size={11} className="mt-1 shrink-0 text-[var(--text-faint)]" aria-hidden />
                </button>
              </li>
            ))}
          </ul>
          <div className="mt-2.5 border-t border-[var(--border)] pt-2.5">
            <div className="flex items-center justify-between text-[10.5px]">
              <span className="text-[var(--text-faint)]">Saha kontrol listesi</span>
              <span className="font-mono text-[var(--text-soft)]">{checked}/{CHECK_DEFINITIONS.length}</span>
            </div>
            <ProgressBar value={checked} max={CHECK_DEFINITIONS.length} tone={checked === 11 ? "pass" : "info"} className="mt-1.5" />
          </div>
        </SectionCard>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.25fr_1fr]">
        <SectionCard
          title="Kot profili"
          description="4 kot noktasından türetilen yaklaşık profil. Gerçek ölçüm noktaları eklendiğinde 3D sahne güncellenir."
          icon={Mountain}
          action={
            <Button size="sm" variant="ghost" icon={<ArrowRight size={12} />} onClick={() => setTab("geometry")}>
              Sahaya git
            </Button>
          }
        >
          <ElevationProfileChart inputs={inputs} height={230} />
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[10.5px] text-[var(--text-faint)]">
            <span>Başlangıç {fmt.m(inputs.section_profile.start_elevation_m, 0)}</span>
            <span>En yüksek {fmt.m(inputs.section_profile.highest_elevation_m, 0)}</span>
            <span>En düşük {fmt.m(inputs.section_profile.lowest_elevation_m, 0)}</span>
            <span>Bitiş {fmt.m(inputs.section_profile.end_elevation_m, 0)}</span>
          </div>
        </SectionCard>

        <SectionCard
          title="Karar göstergesi"
          description="Hava testi oranı ve kabul sınırı."
          icon={Sigma}
          bodyClassName="pt-2"
        >
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-1">
            <RatioGauge
              ratio={air?.ratio}
              passed={air?.passed}
              title="Vpa / Vp"
              valueLabel="Fiili / teorik"
              thresholdLabel="kabul 1,06"
            />
            <div className="grid grid-cols-2 gap-2">
              <ResultTile
                label="Oran"
                value={air ? fmt.ratio(air.ratio, 6) : "—"}
                hint="Vpa / Vp"
                tone={air ? (air.passed ? "pass" : "fail") : undefined}
              />
              <ResultTile
                label="Marj"
                value={air ? num(air.decision.margin ?? 0, 6) : "—"}
                unit="m³"
                hint="limit − Vpa"
                tone={air ? (air.passed ? "pass" : "fail") : undefined}
              />
            </div>
          </div>
        </SectionCard>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.4fr_1fr]">
        <SectionCard
          title="3D saha önizlemesi"
          description="Segmentler, ekipman ve pig konumu. Tam sahne Geometri & Saha sayfasındadır."
          icon={Layers}
          action={
            <Button size="sm" variant="ghost" icon={<ArrowRight size={12} />} onClick={() => setTab("geometry")}>
              Tam sahne
            </Button>
          }
          bodyClassName="pt-2"
        >
          <div className="scene-shell">
            <PipelineScene data={scene} className="min-h-[300px]" />
          </div>
          {scene.warnings?.length ? (
            <p className="mt-2 text-[10.5px] leading-relaxed text-[var(--text-faint)]">{scene.warnings[0]}</p>
          ) : null}
        </SectionCard>

        <SectionCard
          title="Son işlemler"
          description="Bu oturumdaki son hesaplamalar ve katsayı hazırlıkları."
          icon={Activity}
          bodyClassName="pt-2"
        >
          {history.length === 0 ? (
            <EmptyState
              title="Henüz işlem yok"
              description="İlk hesaplamadan sonra burada zaman damgalı bir kayıt listesi görünür."
              action={
                <Button size="sm" variant="primary" onClick={() => setTab("geometry")}>
                  Geometri ile başla
                </Button>
              }
            />
          ) : (
            <ol className="space-y-1.5">
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
        </SectionCard>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_1.15fr]">
        <SectionCard
          title="Son 24 saat eğilimi"
          description="Basınç ve sıcaklık seyri. Demo modunda örnek zaman serisidir."
          icon={Activity}
        >
          <TrendChart
            pressure={inputs.field.monitored_pressure_bar ?? inputs.air.pressure_bar ?? 80}
            temperature={inputs.air.temperature_c ?? 20}
            height={180}
          />
          <div className="mt-1 flex gap-4 text-[10px] text-[var(--text-faint)]">
            <span className="flex items-center gap-1"><span className="legend-dot bg-[var(--chart-1)]" /> Basınç (bar)</span>
            <span className="flex items-center gap-1"><span className="legend-dot bg-[var(--chart-3)]" /> Sıcaklık (°C)</span>
          </div>
        </SectionCard>

        <div className="hero-banner p-4">
          <div className="relative">
            <p className="eyebrow">Sıradaki adım</p>
            <h3 className="mt-1.5 text-[19px] font-semibold tracking-[-0.02em]">{nextStep.label}</h3>
            <p className="mt-1 max-w-[52ch] text-[12px] leading-relaxed text-[var(--text-muted)]">{nextStep.detail}</p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Button variant="primary" icon={<ArrowRight size={14} />} onClick={() => setTab(nextStep.tab)}>
                Devam et
              </Button>
              <Button variant="ghost" icon={<Wind size={13} />} onClick={() => setTab("air")}>
                Hava testi
              </Button>
            </div>
            <div className="mt-4 grid grid-cols-3 gap-2">
              <ResultTile label="Hava" value={<span className={cn("text-[14px]", `tone-${statusTone(air?.decision.status)}`)}>{air?.decision.status ?? "BEKLIYOR"}</span>} />
              <ResultTile label="Basınç" value={<span className={cn("text-[14px]", `tone-${statusTone(pressure?.decision.status)}`)}>{pressure?.decision.status ?? "BEKLIYOR"}</span>} />
              <ResultTile label="Profil" value={<span className={cn("text-[14px]", `tone-${statusTone(profile?.decision.status)}`)}>{profile?.decision.status ?? "BEKLIYOR"}</span>} />
            </div>
            <p className="mt-3 text-[10px] leading-relaxed text-[var(--text-faint)]">
              Son güncelleme {dateTime(results.lastComputedAt)} · Kararlar ASME B31.8 ile birlikte
              değerlendirilmelidir.
            </p>
          </div>
        </div>
      </div>

      {!geometry ? (
        <InlineNotice tone="warning" title="Geometri eksik" icon={Ruler}>
          Hesap üretmek için Geometri sekmesinde dış çap, et kalınlığı ve hat uzunluğunu girin.
        </InlineNotice>
      ) : null}

      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.05, duration: 0.25 }}
        className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] px-3.5 py-2.5 text-[10.5px] text-[var(--text-faint)]"
      >
        <span className="flex items-center gap-1.5">
          <StatusBadge status={air?.decision.status ?? "BEKLIYOR"} dotOnly />
          <span aria-hidden>·</span>
          <StatusBadge status={pressure?.decision.status ?? "BEKLIYOR"} dotOnly />
        </span>
        <span className="font-mono">{meta?.spec.code ?? "4-NGTL 0-GN-P-002-5007 R4"}</span>
      </motion.div>
    </div>
  );
}
