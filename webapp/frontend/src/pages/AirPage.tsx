import { AlertTriangle, ArrowRight, CheckCircle2, ChevronRight, Gauge, Lock, Sigma, Wind } from "lucide-react";
import { PageHeader } from "../components/layout/PageHeader";
import { SectionCard, ResultTile } from "../components/ui/Card";
import { Badge, CoefficientBadge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { NumberField, SelectField, FieldGrid, ReadonlyValue } from "../components/ui/Field";
import { DecisionCard } from "../components/ui/DecisionCard";
import { RatioGauge } from "../components/ui/Gauge";
import { InlineNotice } from "../components/ui/State";
import {
  useCalculateAir,
  useCoefficientA,
  useMeta,
  useSaveTestResult,
} from "../hooks/queries";
import { useAppStore } from "../store/useAppStore";
import { useEvaluateShortcut } from "../hooks/useEvaluateShortcut";
import { K_PRESETS } from "../lib/constants";
import { fmt, num, relativeTime } from "../lib/format";
import { geometryForInputs, sectionsFromInputs } from "../lib/mock";
import type { AirContentRequest } from "../lib/types";

export function AirPage({ embedded = false }: { embedded?: boolean } = {}) {
  const inputs = useAppStore((state) => state.inputs);
  const results = useAppStore((state) => state.results);
  const history = useAppStore((state) => state.history);
  const patchInputs = useAppStore((state) => state.patchInputs);
  const setTab = useAppStore((state) => state.setTab);
  const pushToast = useAppStore((state) => state.pushToast);

  const calculateAir = useCalculateAir();
  const coefficientA = useCoefficientA();
  const { data: meta } = useMeta();
  const saveResult = useSaveTestResult();
  useEvaluateShortcut(evaluate);

  const air = results.air;
  const mode = inputs.modes.air_a_mode;
  const activeWaterBackend = inputs.water_backend || meta?.water_backends[0]?.key || "table_v1";
  const geometry = results.geometry ?? geometryForInputs(inputs);
  const sections = sectionsFromInputs(inputs);
  const aValue = inputs.air.a_micro_per_bar;

  const temperatureWarning =
    inputs.air.temperature_c !== null &&
    (inputs.air.temperature_c < -5 || inputs.air.temperature_c > 60)
      ? "Sıcaklık −5…60 °C aralığının dışında; sonucu kontrol edin."
      : null;
  const pressureError =
    inputs.air.pressure_bar !== null && inputs.air.pressure_bar <= 0
      ? "Su basıncı 0'dan büyük olmalı."
      : null;
  const kError =
    inputs.air.k_factor < 1 || inputs.air.k_factor > 1.1
      ? "K faktörü 1,00 – 1,10 aralığında olmalı."
      : null;
  const vpaError =
    inputs.air.actual_added_water_m3 !== null && inputs.air.actual_added_water_m3 < 0
      ? "Vpa negatif olamaz."
      : null;
  const effectiveAmbient =
    inputs.air.ambient_temperature_c ?? inputs.field.ambient_temperature_c;
  const ambientError =
    effectiveAmbient !== null && effectiveAmbient < 2
      ? "Şartname 10.1: dolum sırasında ortam sıcaklığı +2 °C altında olmamalı."
      : null;

  const missing: string[] = [];
  if (!sections.length) missing.push("Geometri");
  if (!aValue) missing.push("A katsayısı");
  if (inputs.air.actual_added_water_m3 === null) missing.push("Vpa");
  if (kError) missing.push("geçerli K");
  if (pressureError) missing.push("geçerli basınç");
  if (Math.abs(inputs.air.pressure_rise_bar - 1) > 1e-9) missing.push("P = 1,0 bar");

  function buildRequest(): AirContentRequest | null {
    if (!sections.length || !aValue || inputs.air.actual_added_water_m3 === null) return null;
    return {
      geometry: { sections },
      a_micro_per_bar: aValue,
      pressure_rise_bar: inputs.air.pressure_rise_bar,
      k_factor: inputs.air.k_factor,
      actual_added_water_m3: inputs.air.actual_added_water_m3,
    };
  }

  function evaluate() {
    const request = buildRequest();
    if (!request) {
      pushToast("error", "Hava testi değerlendirilemedi", `Eksik: ${missing.join(", ")}`);
      return;
    }
    if (missing.length > 0) {
      pushToast("error", "Girdiler geçersiz", `Düzeltin: ${missing.join(", ")}`);
      return;
    }
    calculateAir.mutate(request, {
      onSuccess: ({ data }) => {
        const passed = data.passed;
        pushToast(
          passed ? "success" : "error",
          passed ? "Hava içerik testi başarılı" : "Hava içerik testi başarısız",
          `Vpa/Vp = ${num(data.ratio, 6)} · marj ${fmt.m3(data.decision.margin ?? 0)}`,
        );
        saveResult.mutate({
          testType: "air",
          payload: request as unknown as Record<string, unknown>,
        });
      },
      onError: (error) => pushToast("error", "Hava testi değerlendirilemedi", error.message),
    });
  }

  function prepareA() {
    const effectivePressure =
      inputs.air.pressure_bar ??
      inputs.field.monitored_pressure_bar ??
      (inputs.section_profile.design_pressure_bar
        ? Number((inputs.section_profile.design_pressure_bar * 1.25).toFixed(2))
        : null);
    if (inputs.air.temperature_c === null || effectivePressure === null) {
      pushToast("error", "A hazırlanamadı", "Su sıcaklığı ve basıncı gerekli.");
      return;
    }
    if (inputs.air.pressure_bar === null) {
      patchInputs({ air: { pressure_bar: effectivePressure } });
    }
    if (mode === "manual") {
      pushToast("info", "Manuel A", "Manuel modda A değeri doğrudan kullanılır.");
      return;
    }
    coefficientA.mutate(
      {
        temperature_c: inputs.air.temperature_c,
        pressure_bar: effectivePressure,
        backend: activeWaterBackend,
      },
      {
        onSuccess: ({ data }) => {
          patchInputs({ air: { a_micro_per_bar: data.a_micro_per_bar } });
          pushToast(
            "success",
            data.state === "reference" ? "A tablodan alındı" : "A hesaplandı",
            `${fmt.a(data.a_micro_per_bar)} · ${data.backend.label}`,
          );
        },
      },
    );
  }

  const airHistory = history.filter((entry) => entry.testType === "air");

  return (
    <div className="space-y-5">
      {embedded ? (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] px-3.5 py-2.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-bold text-[var(--text)]">
              Detay Hesaplama — Hava İçerik Testi (Şartname 13)
            </span>
            <Badge tone={air?.passed ? "pass" : air ? "fail" : "pending"}>
              {air ? (air.passed ? "Kabul" : "Red") : "Değerlendirme bekliyor"}
            </Badge>
            <span className="text-[10.5px] text-[var(--text-faint)]">
              Kural: Vpa &lt; 1,06 × Vp
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="ghost" icon={<Sigma size={14} />} onClick={() => setTab("coefficients")}>
              Katsayılar & Detay
            </Button>
            <Button
              size="sm"
              variant="primary"
              icon={<CheckCircle2 size={14} />}
              loading={calculateAir.isPending}
              disabled={missing.length > 0}
              title={missing.length ? `Eksik: ${missing.join(", ")}` : "Testi değerlendir"}
              onClick={evaluate}
            >
              Testi değerlendir
            </Button>
          </div>
        </div>
      ) : (
        <PageHeader
          kicker="Hava İçerik Testi"
          title="Hava içerik değerlendirmesi"
          description="Şartname 13: tam 1,0 bar basınç artışıyla yapılır ve Vpa < 1,06 × Vp kuralı uygulanır. Tam sınır değeri başarısızdır."
          meta={
            <>
              <Badge tone={air?.passed ? "pass" : air ? "fail" : "pending"}>
                {air ? (air.passed ? "Kabul" : "Red") : "Değerlendirme bekliyor"}
              </Badge>
              <span className="text-[10.5px] text-[var(--text-faint)]">
                Kural: Vpa &lt; 1,06 × Vp
              </span>
            </>
          }
          actions={
            <>
              <Button size="lg" variant="ghost" icon={<Sigma size={15} />} onClick={() => setTab("coefficients")}>
                Katsayılar & Detay
              </Button>
              <Button
                size="lg"
                variant="primary"
                icon={<CheckCircle2 size={15} />}
                loading={calculateAir.isPending}
                disabled={missing.length > 0}
                title={missing.length ? `Eksik: ${missing.join(", ")}` : "Testi değerlendir"}
                onClick={evaluate}
              >
                Testi değerlendir
              </Button>
            </>
          }
        />
      )}

      {missing.length > 0 ? (
        <InlineNotice tone="warning" title="Eksik alanlar" icon={Lock}>
          {missing.join(", ")}. “Değerlendir” bu alanlar tamamlanmadan çalışmaz.
        </InlineNotice>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
        <div className="space-y-4">
          <SectionCard
            title="Girdiler"
            description="Su sıcaklığı/basıncı A katsayısını belirler; Vpa sahadan gelir."
            icon={Wind}
            action={<CoefficientBadge state={air ? "computed" : aValue ? "manual" : "empty"} />}
          >
            <FieldGrid cols={2}>
              <NumberField
                label="Su sıcaklığı"
                unit="°C"
                value={inputs.air.temperature_c}
                onChange={(value) => patchInputs({ air: { temperature_c: value } })}
                help="A hesabı için gerekli."
                error={temperatureWarning}
                min={-5}
                max={60}
              />
              <NumberField
                label="Su basıncı"
                unit="bar"
                value={inputs.air.pressure_bar}
                onChange={(value) => patchInputs({ air: { pressure_bar: value } })}
                error={pressureError}
                min={1}
                max={150}
              />
            </FieldGrid>

            <div className="mt-3">
              <span className="field-label">A modu</span>
              <div className="mt-1.5 seg-control" role="group" aria-label="A modu">
                {(["auto", "manual"] as const).map((option) => (
                  <button
                    key={option}
                    type="button"
                    className="seg-btn"
                    aria-pressed={option === "auto" ? mode !== "manual" : mode === "manual"}
                    onClick={() => patchInputs({ modes: { air_a_mode: option } })}
                  >
                    {option === "auto" ? "Otomatik" : "Manuel"}
                  </button>
                ))}
              </div>
            </div>

            {mode !== "manual" ? (
              <div className="mt-3">
                <SelectField
                  label="Su özelliği backend'i"
                  value={activeWaterBackend}
                  onChange={(value) => patchInputs({ water_backend: value })}
                  options={(meta?.water_backends ?? []).map((backend) => ({
                    value: backend.key,
                    label: `${backend.label}${backend.distribution_ready ? "" : " (dağıtım dışı)"}`,
                  }))}
                  placeholder="Backend seçin"
                />
              </div>
            ) : null}

            <div className="mt-3 grid grid-cols-[1fr_auto] items-end gap-2">
              <NumberField
                label="A katsayısı"
                unit="10⁻⁶/bar"
                value={aValue}
                onChange={(value) => patchInputs({ air: { a_micro_per_bar: value } })}
                readOnly={mode !== "manual"}
                help={
                  mode === "manual"
                    ? "Manuel mod: 1,0 – 200,0"
                    : "Otomatik modda salt okunur; A’yı hazırla ile doldurun."
                }
                min={1}
                max={200}
              />
              <Button
                size="sm"
                variant="default"
                icon={<Sigma size={12} />}
                loading={coefficientA.isPending}
                disabled={mode === "manual"}
                onClick={prepareA}
              >
                T &amp; P'den A'yı Doldur
              </Button>
            </div>

            <FieldGrid cols={2} className="mt-3">
              <div>
                <ReadonlyValue
                  label="Basınç artışı P"
                  unit="bar"
                  value={
                    <span className="flex items-center justify-end gap-1.5">
                      <Lock size={11} className="text-[var(--text-faint)]" aria-hidden />
                      {num(inputs.air.pressure_rise_bar, 1)}
                    </span>
                  }
                  hint="Şartname 13: tam 1,0 bar. Değiştirilemez."
                />
              </div>
              <NumberField
                label="Fiili ilave su Vpa"
                unit="m³"
                value={inputs.air.actual_added_water_m3}
                onChange={(value) => patchInputs({ air: { actual_added_water_m3: value } })}
                error={vpaError}
                help="Sahada ölçülen ilave su hacmi."
                min={0}
              />
            </FieldGrid>

            <div className="mt-3 grid grid-cols-[1fr_1fr] gap-2">
              <SelectField
                label="K preset"
                value={inputs.modes.k_preset}
                onChange={(value) => {
                  const preset = K_PRESETS.find((item) => item.label === value);
                  patchInputs({
                    modes: { k_preset: value },
                    air: { k_factor: preset?.value ?? inputs.air.k_factor },
                  });
                }}
                options={K_PRESETS.map((preset) => ({ value: preset.label, label: preset.label }))}
              />
              <NumberField
                label="K faktörü"
                value={inputs.air.k_factor}
                onChange={(value) => patchInputs({ air: { k_factor: value ?? 1.02 } })}
                error={kError}
                min={1}
                max={1.1}
                digits={3}
                disabled={inputs.modes.k_preset !== "Özel"}
              />
            </div>

            <div className="mt-3 space-y-2">
              <NumberField
                label="Ortam hava sıcaklığı (10.1)"
                unit="°C"
                value={effectiveAmbient}
                onChange={(value) =>
                  patchInputs({
                    air: { ambient_temperature_c: value },
                    field: { ambient_temperature_c: value },
                  })
                }
                error={ambientError}
                help={ambientError ? undefined : "Saha kontrolünde +2 °C limiti ayrıca işaretlenir."}
              />
              {ambientError ? (
                <InlineNotice tone="danger" title="Şartname 10.1 — +2 °C dolum kısıtı" icon={AlertTriangle}>
                  Ölçülen ortam/dolum sıcaklığı ({num(effectiveAmbient, 1)} °C) +2 °C sınırının
                  altında. Donma riskine karşı dolum durdurulmalı veya önlem alınmalıdır.
                </InlineNotice>
              ) : null}
            </div>

            <div className="mt-4 grid grid-cols-3 gap-2 border-t border-[var(--border)] pt-3">
              <ResultTile label="İç hacim Vt" value={geometry ? num(geometry.internal_volume_m3, 3) : "—"} unit="m³" />
              <ResultTile label="Elastisite" value={geometry ? num(geometry.elasticity_term, 3) : "—"} hint="0,884·ri/s" />
              <ResultTile label="Segment" value={geometry ? num(geometry.section_count, 0) : "—"} unit="kesit" />
            </div>
          </SectionCard>
        </div>

        <div className="space-y-4">
          <SectionCard
            title="Sonuç"
            description="Teorik ilave su, kabul limiti ve fiili değer."
            icon={Gauge}
            action={air ? <Badge tone={air.passed ? "pass" : "fail"}>{air.passed ? "Kabul" : "Red"}</Badge> : null}
          >
            <RatioGauge
              ratio={air?.ratio}
              passed={air?.passed}
              title="Vpa / Vp"
              valueLabel="Fiili / teorik"
              thresholdLabel="kabul 1,06"
            />

            <div className="mt-3 grid grid-cols-2 gap-2">
              <ResultTile label="Teorik Vp" value={num(air?.theoretical_added_water_m3, 6)} unit="m³" hint="Hesaplanan ilave su" />
              <ResultTile label="Kabul limiti" value={num(air?.acceptance_limit_m3, 6)} unit="m³" hint="1,06 × Vp" tone="info" />
              <ResultTile label="Fiili Vpa" value={num(inputs.air.actual_added_water_m3, 6)} unit="m³" hint="Saha ölçümü" />
              <ResultTile
                label="Marj"
                value={num(air?.decision.margin, 6)}
                unit="m³"
                hint="limit − Vpa"
                tone={air ? (air.passed ? "pass" : "fail") : undefined}
              />
            </div>
          </SectionCard>

          <DecisionCard
            decision={air?.decision}
            testName="Hava İçerik Testi"
            marginUnit="m³"
            why={
              <>
                <p className="font-mono">Vp = ((0,884·ri/s) + A) · 10⁻⁶ · Vt · P · K</p>
                <p className="font-mono">limit = 1,06 · Vp; oran = Vpa / Vp</p>
                <p>
                  A = {fmt.a(aValue)} · ri = {geometry ? fmt.mm(geometry.internal_radius_mm) : "—"} · Vt ={" "}
                  {geometry ? fmt.m3Short(geometry.internal_volume_m3) : "—"} · K = {num(inputs.air.k_factor, 3)}
                </p>
                <p>Tam 1,06 sınırı başarısız sayılır; domain karşılaştırması kesin kabul kullanır.</p>
              </>
            }
            actions={
              <>
                <Button size="lg" variant="primary" icon={<ArrowRight size={15} />} onClick={() => setTab("pressure")}>
                  Basınç testine geç
                </Button>
                <Button size="lg" variant="ghost" onClick={() => setTab("coefficients")}>
                  Katsayı detayını gör
                </Button>
              </>
            }
          />
        </div>
      </div>

      <div className="space-y-3">
        <details className="disclosure-card">
          <summary className="disclosure-summary">
            <ChevronRight size={15} className="disclosure-chevron shrink-0" aria-hidden />
            <span>A Katsayısı Özeti &amp; Kaynak</span>
            <span className="ml-auto text-[11px] font-normal text-[var(--text-faint)]">
              A = {num(aValue, 4)} · {mode === "auto" ? "Backend hesabı" : mode === "table" ? "Referans tablo" : "Manuel"}
            </span>
          </summary>
          <div className="disclosure-body space-y-3">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[11.5px] text-[var(--text-muted)]">A değeri ve kaynağı</span>
              <CoefficientBadge state={mode === "manual" ? "manual" : mode === "table" ? "reference" : "computed"} />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <ResultTile label="A" value={num(aValue, 6)} unit="10⁻⁶/bar" />
              <ResultTile
                label="Kaynak"
                value={
                  <span className="text-[13px]">
                    {mode === "auto" ? "Backend hesabı" : mode === "table" ? "Referans tablo" : "Manuel"}
                  </span>
                }
                hint={mode === "table" && results.tablePoint?.repaired ? "Onarılmış hücre" : "Provenance"}
              />
            </div>
            {results.tablePoint ? (
              <p className="text-[10.5px] leading-relaxed text-[var(--text-muted)]">
                Son tablo okuması: A = {fmt.a(results.tablePoint.a_micro_per_bar)} · B ={" "}
                {fmt.b(results.tablePoint.b_micro_per_c)}
                {results.tablePoint.repaired ? " (onarılmış)" : ""}
              </p>
            ) : null}
            <InlineNotice tone="info" title="Birim" icon={Sigma}>
              A değeri 10⁻⁶/bar ölçeğindedir; 44,97 değeri 44,97 × 10⁻⁶ /bar anlamına gelir.
            </InlineNotice>
          </div>
        </details>

        <details className="disclosure-card">
          <summary className="disclosure-summary">
            <ChevronRight size={15} className="disclosure-chevron shrink-0" aria-hidden />
            <span>Hava Testi Geçmişi</span>
            <span className="ml-auto text-[11px] font-normal text-[var(--text-faint)]">
              {airHistory.length} kayıt
            </span>
          </summary>
          <div className="disclosure-body">
            {airHistory.length === 0 ? (
              <p className="text-[11.5px] text-[var(--text-faint)]">
                Henüz hava testi kaydı yok. İlk değerlendirmeden sonra burada listelenir.
              </p>
            ) : (
              <ul className="space-y-1.5">
                {airHistory.map((entry) => (
                  <li key={entry.id} className="flex items-start gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-2.5 py-2">
                    <span className="mt-0.5 font-mono text-[10px] text-[var(--text-faint)]">{relativeTime(entry.at)}</span>
                    <span className="min-w-0 flex-1 truncate text-[11px] text-[var(--text-muted)]">{entry.summary}</span>
                    <Badge tone={entry.status === "BASARILI" ? "pass" : entry.status === "BASARISIZ" ? "fail" : "pending"}>
                      {entry.status}
                    </Badge>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </details>
      </div>
    </div>
  );
}
