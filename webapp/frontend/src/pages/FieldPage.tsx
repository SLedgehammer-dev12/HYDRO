import { ArrowDown, ArrowRight, CheckCircle2, ClipboardCheck, Gauge, Layers, Mountain, MoveRight, Waves } from "lucide-react";
import { PageHeader } from "../components/layout/PageHeader";
import { SectionCard, KpiCard, ResultTile } from "../components/ui/Card";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { NumberField, SelectField, FieldGrid, ReadonlyValue, CheckboxRow } from "../components/ui/Field";
import { DecisionCard } from "../components/ui/DecisionCard";
import { ProgressBar } from "../components/ui/Gauge";
import { EmptyState, InlineNotice } from "../components/ui/State";
import { PressureWindowChart, ElevationProfileChart } from "../components/charts/Charts";
import PipelineScene from "../components/three/PipelineScene";
import { useCalculatePig, useCalculateProfile, useMeta, useSaveTestResult } from "../hooks/queries";
import { useAppStore } from "../store/useAppStore";
import { useEvaluateShortcut } from "../hooks/useEvaluateShortcut";
import { CHECK_DEFINITIONS, FALLBACK_PIG_MODES, PUMP_LABELS } from "../lib/constants";
import { fmt, num, parseNumber } from "../lib/format";
import { buildSceneData, sectionsFromInputs } from "../lib/mock";
import type { PressureProfileRequest } from "../lib/types";
import { cn } from "../lib/utils";

function WindowBar({
  min,
  max,
  monitored,
}: {
  min: number;
  max: number;
  monitored: number | null;
}) {
  const span = Math.max(max - min, 0.001);
  const low = min - span * 0.25;
  const high = max + span * 0.25;
  const fraction = (value: number) => Math.min(100, Math.max(0, ((value - low) / (high - low)) * 100));
  const inWindow = monitored !== null && monitored >= min && monitored <= max;

  return (
    <div>
      <div className="relative h-9 overflow-hidden rounded-lg border border-[var(--border)] bg-[var(--surface-2)]">
        <div
          className="absolute inset-y-0 bg-[var(--danger-bg)]"
          style={{ left: 0, width: `${fraction(min)}%` }}
          aria-hidden
        />
        <div
          className="absolute inset-y-0 bg-[var(--success-bg)]"
          style={{ left: `${fraction(min)}%`, width: `${fraction(max) - fraction(min)}%` }}
          aria-hidden
        />
        <div className="absolute inset-y-0 w-px bg-[var(--warning)]" style={{ left: `${fraction(min)}%` }} aria-hidden />
        <div className="absolute inset-y-0 w-px bg-[var(--danger)]" style={{ left: `${fraction(max)}%` }} aria-hidden />
        {monitored !== null ? (
          <div
            className={cn(
              "absolute top-1/2 h-5 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full",
              inWindow ? "bg-[var(--success)]" : "bg-[var(--danger)]",
            )}
            style={{ left: `${fraction(monitored)}%` }}
            aria-hidden
          />
        ) : null}
      </div>
      <div className="mt-1 flex justify-between font-mono text-[9.5px] text-[var(--text-faint)]">
        <span>{num(low, 1)} bar</span>
        <span className="text-[var(--warning)]">min {num(min, 1)}</span>
        <span className="text-[var(--danger)]">max {num(max, 1)}</span>
        <span>{num(high, 1)} bar</span>
      </div>
    </div>
  );
}

export function FieldPage() {
  const inputs = useAppStore((state) => state.inputs);
  const results = useAppStore((state) => state.results);
  const patchInputs = useAppStore((state) => state.patchInputs);
  const toggleCheck = useAppStore((state) => state.toggleCheck);
  const pushToast = useAppStore((state) => state.pushToast);

  const { data: meta } = useMeta();
  const calculateProfile = useCalculateProfile();
  const calculatePig = useCalculatePig();
  const saveResult = useSaveTestResult();
  useEvaluateShortcut(evaluateProfile);

  const profile = results.profile;
  const pig = results.pig;
  const sections = sectionsFromInputs(inputs);
  const sp = inputs.section_profile;
  const checked = CHECK_DEFINITIONS.filter((check) => inputs.checks[check.key]).length;
  const scene = buildSceneData(inputs, results);
  const monitored = inputs.field.monitored_pressure_bar;

  const limits = meta?.limits;
  const maxLength = limits?.max_test_section_length_m ?? 20_000;
  const maxVolume = limits?.max_test_section_volume_m3 ?? 12_500;

  const elevationError =
    sp.highest_elevation_m !== null &&
    sp.lowest_elevation_m !== null &&
    sp.highest_elevation_m < sp.lowest_elevation_m
      ? "En yüksek kot, en düşük kottan küçük olamaz."
      : null;

  const missing: string[] = [];
  if (!sections.length) missing.push("Geometri");
  if (sp.highest_elevation_m === null) missing.push("en yüksek kot");
  if (sp.lowest_elevation_m === null) missing.push("en düşük kot");
  if (sp.start_elevation_m === null) missing.push("başlangıç kotu");
  if (sp.end_elevation_m === null) missing.push("bitiş kotu");
  if (!sp.design_pressure_bar) missing.push("dizayn basıncı");
  if (!sp.smys_mpa) missing.push("SMYS / malzeme");
  if (!inputs.pump_location) missing.push("pompa konumu");
  if (elevationError) missing.push("geçerli kot aralığı");

  function buildProfileRequest(): PressureProfileRequest | null {
    if (
      !sections.length ||
      sp.highest_elevation_m === null ||
      sp.lowest_elevation_m === null ||
      sp.start_elevation_m === null ||
      sp.end_elevation_m === null ||
      !sp.design_pressure_bar ||
      !sp.smys_mpa ||
      !inputs.pump_location
    ) {
      return null;
    }
    return {
      geometry: { sections },
      design_pressure_bar: sp.design_pressure_bar,
      smys_mpa: sp.smys_mpa,
      location_class: inputs.location_class,
      highest_elevation_m: sp.highest_elevation_m,
      lowest_elevation_m: sp.lowest_elevation_m,
      start_elevation_m: sp.start_elevation_m,
      end_elevation_m: sp.end_elevation_m,
      pump_location: inputs.pump_location,
      monitored_pressure_bar: monitored,
    };
  }

  function evaluateProfile() {
    const request = buildProfileRequest();
    if (!request || missing.length > 0) {
      pushToast("error", "Profil doğrulanamadı", `Eksik: ${missing.join(", ")}`);
      return;
    }
    calculateProfile.mutate(request, {
      onSuccess: ({ data, mode }) => {
        pushToast(
          data.feasible ? "success" : "error",
          data.feasible ? "Basınç penceresi uygun" : "Basınç penceresi uygun değil",
          `${fmt.bar(data.selected_window.minimum_required_pressure_bar)} – ${fmt.bar(
            data.selected_window.maximum_allowable_pressure_bar,
          )}${mode === "demo" ? " (demo)" : ""}`,
        );
        saveResult.mutate({ testType: "profile", payload: request as unknown as Record<string, unknown> });
      },
      onError: (error) => pushToast("error", "Profil doğrulanamadı", error.message),
    });
  }

  function runPig() {
    if (!inputs.field.pig_distance_m || !inputs.field.pig_travel_time_min) {
      pushToast("error", "Pig hesabı yapılamadı", "Mesafe ve süre girilmelidir.");
      return;
    }
    calculatePig.mutate(
      {
        mode: inputs.modes.pig_mode,
        distance_m: inputs.field.pig_distance_m,
        travel_time_min: inputs.field.pig_travel_time_min,
      },
      {
        onSuccess: ({ data, mode }) => {
          patchInputs({
            field: {
              pig_speed_m_per_s: data.speed_m_per_s,
              pig_speed_km_per_h: data.speed_km_per_h,
            },
          });
          pushToast(
            data.passed === false ? "error" : "success",
            `Pig hızı ${data.status}`,
            `${fmt.ms(data.speed_m_per_s)} · ${fmt.kmh(data.speed_km_per_h)}${mode === "demo" ? " (demo)" : ""}`,
          );
          saveResult.mutate({
            testType: "pig",
            payload: {
              mode: inputs.modes.pig_mode,
              distance_m: inputs.field.pig_distance_m,
              travel_time_min: inputs.field.pig_travel_time_min,
            },
          });
        },
        onError: (error) => pushToast("error", "Pig hesabı başarısız", error.message),
      },
    );
  }

  const selectedMin = profile?.selected_window.minimum_required_pressure_bar;
  const selectedMax = profile?.selected_window.maximum_allowable_pressure_bar;
  const pigMode = (meta?.pig_modes ?? FALLBACK_PIG_MODES).find((mode) => mode.label === inputs.modes.pig_mode);
  const pigLimit = pig?.limit.max_speed_m_per_s ?? pigMode?.max_speed_m_per_s ?? null;

  return (
    <div className="space-y-5">
      <PageHeader
        kicker="Profil / Saha"
        title="Basınç penceresi, saha kontrolü ve pig"
        description="Test bölümünün hidrolik penceresi; 20.000 m uzunluk, 12.500 m³ hacim ve %100 SMYS limitleri birlikte değerlendirilir."
        meta={
          <>
            <Badge tone={profile ? (profile.feasible ? "pass" : "fail") : "pending"}>
              {profile ? (profile.feasible ? "Pencere uygun" : "Pencere uygun değil") : "Profil bekliyor"}
            </Badge>
            <span className="text-[10.5px] text-[var(--text-faint)]">
              {checked}/{CHECK_DEFINITIONS.length} saha kontrolü
            </span>
            <span className="chip">{PUMP_LABELS[inputs.pump_location] ?? inputs.pump_location ?? "pompa seçilmedi"}</span>
          </>
        }
        actions={
          <Button
            variant="primary"
            icon={<CheckCircle2 size={14} />}
            loading={calculateProfile.isPending}
            disabled={missing.length > 0}
            title={missing.length ? `Eksik: ${missing.join(", ")}` : "Profili doğrula"}
            onClick={evaluateProfile}
          >
            Profili doğrula
          </Button>
        }
      />

      {missing.length > 0 ? (
        <InlineNotice tone="warning" title="Profil için eksik alanlar">
          {missing.join(", ")}.
        </InlineNotice>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-3">
        <SectionCard
          title="Profil girdileri"
          description="Kotlar ve basınç limitleri."
          icon={Mountain}
        >
          <FieldGrid cols={2}>
            <NumberField
              label="En yüksek kot"
              unit="m"
              value={sp.highest_elevation_m}
              onChange={(value) => patchInputs({ section_profile: { highest_elevation_m: value } })}
              error={elevationError}
            />
            <NumberField
              label="En düşük kot"
              unit="m"
              value={sp.lowest_elevation_m}
              onChange={(value) => patchInputs({ section_profile: { lowest_elevation_m: value } })}
            />
            <NumberField
              label="Başlangıç kotu"
              unit="m"
              value={sp.start_elevation_m}
              onChange={(value) => patchInputs({ section_profile: { start_elevation_m: value } })}
            />
            <NumberField
              label="Bitiş kotu"
              unit="m"
              value={sp.end_elevation_m}
              onChange={(value) => patchInputs({ section_profile: { end_elevation_m: value } })}
            />
            <NumberField
              label="Dizayn basıncı"
              unit="bar"
              value={sp.design_pressure_bar}
              onChange={(value) => patchInputs({ section_profile: { design_pressure_bar: value } })}
            />
            <ReadonlyValue
              label="SMYS"
              unit="MPa"
              value={sp.smys_mpa !== null ? num(sp.smys_mpa, 0) : "—"}
              hint="Malzeme kalitesinden türetilir."
            />
          </FieldGrid>

          <div className="mt-3">
            <SelectField
              label="Location Class"
              value={inputs.location_class}
              onChange={(value) => patchInputs({ location_class: value })}
              options={(meta?.location_classes ?? []).map((rule) => ({
                value: rule.label,
                label: `${rule.label} · ×${rule.minimum_test_factor}`,
              }))}
            />
          </div>
          <div className="mt-3">
            <SelectField
              label="Pompa konumu"
              value={inputs.pump_location}
              onChange={(value) => patchInputs({ pump_location: value })}
              options={(meta?.pump_locations ?? ["Baslangic noktasi", "Bitis noktasi"]).map((value) => ({
                value,
                label: PUMP_LABELS[value] ?? value,
              }))}
            />
          </div>

          <div className="mt-4 border-t border-[var(--border)] pt-3">
            <div className="flex items-center justify-between">
              <span className="field-label">İzlenen basınç</span>
              <span className="font-mono text-[12px] text-[var(--text-soft)]">{fmt.bar(monitored, 1)}</span>
            </div>
            <input
              type="range"
              min={0}
              max={220}
              step={0.5}
              value={monitored ?? 0}
              aria-label="İzlenen basınç kaydırıcısı"
              className="mt-2 w-full accent-[var(--primary)]"
              onChange={(event) => {
                const parsed = parseNumber(event.target.value);
                patchInputs({ field: { monitored_pressure_bar: parsed } });
              }}
            />
            <NumberField
              label="Sayısal değer"
              unit="bar"
              value={monitored}
              onChange={(value) => patchInputs({ field: { monitored_pressure_bar: value } })}
              help="Pencere içinde olup olmadığı kararı etkiler."
            />
          </div>

          <div className="mt-3 grid grid-cols-2 gap-2">
            <ResultTile label="Kot farkı" value={sp.highest_elevation_m !== null && sp.lowest_elevation_m !== null ? num(sp.highest_elevation_m - sp.lowest_elevation_m, 0) : "—"} unit="m" />
            <ResultTile label="Test faktörü" value={profile ? `×${num(profile.location_class.minimum_test_factor, 2)}` : "—"} hint={inputs.location_class} />
          </div>
        </SectionCard>

        <div className="space-y-4 xl:col-span-2">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <KpiCard
              label="Pencere alt"
              value={num(selectedMin, 1)}
              unit="bar"
              icon={ArrowDown}
              hint="Yüksek noktada min test basıncı"
            />
            <KpiCard
              label="Pencere üst"
              value={num(selectedMax, 1)}
              unit="bar"
              icon={ArrowDown}
              hint="Düşük noktada %100 SMYS"
            />
            <KpiCard
              label="İzlenen"
              value={num(monitored, 1)}
              unit="bar"
              icon={Gauge}
              tone={profile ? (profile.monitored_meets_minimum && profile.monitored_under_maximum ? "pass" : "fail") : "default"}
              hint={profile?.monitored_meets_minimum === false ? "Alt sınırın altında" : profile?.monitored_under_maximum === false ? "Üst sınırın üstünde" : "Pencere içinde"}
            />
            <KpiCard
              label="100% SMYS"
              value={num(profile?.limiting_pressure_at_100_smys_bar, 1)}
              unit="bar"
              icon={Layers}
              hint={profile?.limiting_pipe_description ?? "Kritik kesit"}
            />
          </div>

          <SectionCard
            title="Basınç penceresi"
            description="Yeşil bant kabul aralığı; mavi çizgi izlenen basınç."
            icon={Gauge}
            action={
              profile ? (
                <Badge tone={profile.feasible ? "pass" : "fail"}>
                  {profile.feasible ? "Uygun" : "Uygun değil"}
                </Badge>
              ) : null
            }
          >
            {selectedMin !== undefined && selectedMax !== undefined ? (
              <>
                <WindowBar min={selectedMin} max={selectedMax} monitored={monitored} />
                <PressureWindowChart inputs={inputs} profile={profile} height={240} />
              </>
            ) : (
              <EmptyState
                title="Pencere hesaplanmadı"
                description="Kotlar, dizayn basıncı ve SMYS girildikten sonra “Profili doğrula” ile pencere üretilir."
                icon={Gauge}
              />
            )}
          </SectionCard>

          <div className="grid gap-3 sm:grid-cols-3">
            <div className="panel-soft p-3">
              <p className="eyebrow">Uzunluk limiti</p>
              <p className="mt-1 font-mono text-[15px]">{profile ? fmt.m(profile.total_length_m, 0) : "—"}</p>
              <p className="mt-0.5 text-[10px] text-[var(--text-faint)]">≤ {num(maxLength, 0)} m</p>
              <ProgressBar
                value={profile?.total_length_m ?? 0}
                max={maxLength}
                tone={profile && !profile.within_length_limit ? "fail" : "pass"}
                className="mt-2"
              />
            </div>
            <div className="panel-soft p-3">
              <p className="eyebrow">Hacim limiti</p>
              <p className="mt-1 font-mono text-[15px]">{profile ? fmt.m3Short(profile.total_internal_volume_m3) : "—"}</p>
              <p className="mt-0.5 text-[10px] text-[var(--text-faint)]">≤ {num(maxVolume, 0)} m³</p>
              <ProgressBar
                value={profile?.total_internal_volume_m3 ?? 0}
                max={maxVolume}
                tone={profile && !profile.within_volume_limit ? "fail" : "pass"}
                className="mt-2"
              />
            </div>
            <div className="panel-soft p-3">
              <p className="eyebrow">SMYS span</p>
              <p className="mt-1 font-mono text-[15px]">
                {profile ? `${num(profile.required_pressure_with_span_bar, 1)} / ${num(profile.maximum_allowable_pressure_at_low_point_bar, 1)}` : "—"}
              </p>
              <p className="mt-0.5 text-[10px] text-[var(--text-faint)]">gerekli / izin verilen bar</p>
              <ProgressBar
                value={profile?.required_pressure_with_span_bar ?? 0}
                max={profile?.maximum_allowable_pressure_at_low_point_bar ?? 1}
                tone={profile && !profile.within_100_smys_span_limit ? "fail" : "pass"}
                className="mt-2"
              />
            </div>
          </div>

          <DecisionCard
            decision={profile?.decision}
            testName="Test Bölümü Basınç Penceresi"
            marginUnit="bar"
            compact
            why={
              <>
                <p className="font-mono">P_min = dizayn × class faktörü + hidrolik kot farkı</p>
                <p className="font-mono">P_max = 20 · SMYS · t / OD − hidrolik kot farkı</p>
                <p>Hidrolik kotta 15 °C su yoğunluğu (999,1 kg/m³) kullanılır.</p>
              </>
            }
          />
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
        <SectionCard
          title={`Operasyon kontrol noktaları (${checked}/${CHECK_DEFINITIONS.length})`}
          description="Her satırı operatör tek tek onaylar; “tümünü tamamla” yoktur."
          icon={ClipboardCheck}
          action={<Badge tone={checked === 11 ? "pass" : "info"}>{Math.round((checked / 11) * 100)}%</Badge>}
        >
          <ProgressBar value={checked} max={CHECK_DEFINITIONS.length} tone={checked === 11 ? "pass" : "info"} className="mb-3" />
          <div className="grid gap-2">
            {CHECK_DEFINITIONS.map((check) => (
              <CheckboxRow
                key={check.key}
                checked={inputs.checks[check.key]}
                onChange={() => toggleCheck(check.key)}
                label={check.label}
                badge={<span className="chip">{check.ref}</span>}
              />
            ))}
          </div>
        </SectionCard>

        <div className="space-y-4">
          <SectionCard
            title="Pig hızı"
            description={pigMode ? `${pigMode.spec_reference} · limit ${pigLimit !== null ? `${num(pigLimit, 3)} m/s` : "yok"}` : "Mod seçin"}
            icon={MoveRight}
            action={pig ? <Badge tone={pig.status === "UYGUN" ? "pass" : pig.status === "LIMIT ASILDI" ? "fail" : "info"}>{pig.status}</Badge> : null}
          >
            <SelectField
              label="Pig modu"
              value={inputs.modes.pig_mode}
              onChange={(value) => patchInputs({ modes: { pig_mode: value } })}
              options={(meta?.pig_modes ?? FALLBACK_PIG_MODES).map((mode) => ({
                value: mode.label,
                label: mode.label,
              }))}
            />
            <FieldGrid cols={2} className="mt-3">
              <NumberField
                label="Mesafe"
                unit="m"
                value={inputs.field.pig_distance_m}
                onChange={(value) => patchInputs({ field: { pig_distance_m: value } })}
                min={0.1}
              />
              <NumberField
                label="Varış süresi"
                unit="dk"
                value={inputs.field.pig_travel_time_min}
                onChange={(value) => patchInputs({ field: { pig_travel_time_min: value } })}
                min={0.1}
              />
            </FieldGrid>
            <div className="mt-3 flex items-center justify-between">
              <span className="text-[10.5px] text-[var(--text-faint)]">
                {pigLimit === null ? "Bu modda hız limiti tanımlı değildir (bilgi)." : "Limit aşılırsa durum kırmızıya döner."}
              </span>
              <Button
                size="sm"
                variant="primary"
                icon={<Waves size={12} />}
                loading={calculatePig.isPending}
                onClick={runPig}
              >
                Hesapla
              </Button>
            </div>

            <div className="mt-3 grid grid-cols-2 gap-2">
              <ResultTile
                label="Hız"
                value={num(pig?.speed_m_per_s ?? inputs.field.pig_speed_m_per_s, 3)}
                unit="m/s"
                tone={pig ? (pig.passed === false ? "fail" : "pass") : undefined}
              />
              <ResultTile
                label="Hız"
                value={num(pig?.speed_km_per_h ?? inputs.field.pig_speed_km_per_h, 2)}
                unit="km/sa"
              />
            </div>
            {pigLimit !== null ? (
              <div className="mt-3">
                <ProgressBar
                  value={(pig?.speed_m_per_s ?? 0) / pigLimit}
                  max={1}
                  tone={pig?.passed === false ? "fail" : "pass"}
                />
                <div className="mt-1 flex justify-between font-mono text-[9.5px] text-[var(--text-faint)]">
                  <span>0</span>
                  <span>limit {num(pigLimit, 2)} m/s</span>
                </div>
              </div>
            ) : null}
            {pig ? <p className="mt-2 text-[10.5px] leading-relaxed text-[var(--text-muted)]">{pig.summary}</p> : null}
          </SectionCard>

          <SectionCard
            title="Eğilim"
            description="Kot profili ve izlenen basınç."
            icon={Mountain}
          >
            <ElevationProfileChart inputs={inputs} height={170} />
          </SectionCard>
        </div>
      </div>

      <SectionCard
        title="3D tam saha"
        description="Kamera ve kesit kontrolleri 3D bileşeninde. Sahne yüklenemezse aşağıdaki tablo eşdeğer bilgiyi verir."
        icon={Layers}
        action={
          <Button size="sm" variant="ghost" onClick={() => document.getElementById("scene-table")?.scrollIntoView({ block: "center" })}>
            3D’yi atla → tablo
          </Button>
        }
        bodyClassName="pt-2"
      >
        {scene.warnings?.length ? (
          <div className="mb-2">
            <InlineNotice tone="warning" title="Yaklaşık sahne">
              {scene.warnings.join(" ")}
            </InlineNotice>
          </div>
        ) : null}
        <div className="scene-shell">
          <PipelineScene data={scene} className="min-h-[480px]" />
        </div>

        <div id="scene-table" className="mt-3 table-wrap scroll-thin">
          <table className="data">
            <caption>3D sahne eşdeğer veri tablosu</caption>
            <thead>
              <tr>
                <th scope="col">#</th>
                <th scope="col">Segment</th>
                <th scope="col" className="num">Başlangıç (m)</th>
                <th scope="col" className="num">Bitiş (m)</th>
                <th scope="col" className="num">Kot başlangıç</th>
                <th scope="col" className="num">Kot bitiş</th>
                <th scope="col" className="num">OD / WT</th>
                <th scope="col" className="num">P (bar)</th>
              </tr>
            </thead>
            <tbody>
              {scene.segments.length === 0 ? (
                <tr>
                  <td colSpan={8} className="text-center text-[var(--text-faint)]">Segment yok</td>
                </tr>
              ) : (
                scene.segments.map((segment, index) => (
                  <tr key={segment.id}>
                    <td className="font-mono text-[11px]">{index + 1}</td>
                    <td>{segment.label}</td>
                    <td className="num">{num(segment.start_m, 0)}</td>
                    <td className="num">{num(segment.end_m, 0)}</td>
                    <td className="num">{num(segment.start_elevation_m, 1)}</td>
                    <td className="num">{num(segment.end_elevation_m, 1)}</td>
                    <td className="num">{num(segment.outside_diameter_mm, 1)} / {num(segment.wall_thickness_mm, 2)}</td>
                    <td className="num">{num(segment.pressure_bar, 1)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </SectionCard>

      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] px-3.5 py-2.5">
        <p className="text-[10.5px] text-[var(--text-faint)]">
          Basınç penceresi kararı ASME B31.8 ve proje prosedürüyle birlikte değerlendirilmelidir.
        </p>
        <Button size="sm" variant="ghost" icon={<ArrowRight size={12} />} onClick={() => window.scrollTo({ top: 0 })}>
          Başa dön
        </Button>
      </div>
    </div>
  );
}
