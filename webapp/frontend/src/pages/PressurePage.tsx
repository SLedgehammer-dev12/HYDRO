import { useState } from "react";
import { AlertTriangle, ArrowLeftRight, ArrowRight, CheckCircle2, Gauge, History, Info, Lock, Sigma } from "lucide-react";
import { PageHeader } from "../components/layout/PageHeader";
import { SectionCard, ResultTile } from "../components/ui/Card";
import { Badge, CoefficientBadge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { NumberField, FieldGrid, ReadonlyValue } from "../components/ui/Field";
import { DecisionCard } from "../components/ui/DecisionCard";
import { MarginGauge } from "../components/ui/Gauge";
import { EmptyState, InlineNotice } from "../components/ui/State";
import {
  useCalculatePressure,
  useCoefficientA,
  useCoefficientB,
  useSaveTestResult,
  useTablePoint,
} from "../hooks/queries";
import { OperationsPanel } from "../features/operations/OperationsPanel";
import { useAppStore } from "../store/useAppStore";
import { useEvaluateShortcut } from "../hooks/useEvaluateShortcut";
import { STEEL_MODEL_OPTIONS } from "../lib/constants";
import { fmt, num, relativeTime } from "../lib/format";
import {
  computeB,
  computePressure,
  geometryForInputs,
  sectionsFromInputs,
} from "../lib/mock";
import type { PressureVariationRequest } from "../lib/types";

const round = (value: number, digits = 6) => {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
};

export function PressurePage({ embedded = false }: { embedded?: boolean } = {}) {
  const inputs = useAppStore((state) => state.inputs);
  const results = useAppStore((state) => state.results);
  const history = useAppStore((state) => state.history);
  const patchInputs = useAppStore((state) => state.patchInputs);
  const setTab = useAppStore((state) => state.setTab);
  const pushToast = useAppStore((state) => state.pushToast);

  const calculate = useCalculatePressure();
  const coefficientA = useCoefficientA();
  const coefficientB = useCoefficientB();
  const tablePoint = useTablePoint();
  const saveResult = useSaveTestResult();
  const [aPrepError, setAPrepError] = useState<string | null>(null);
  const [bPrepError, setBPrepError] = useState<string | null>(null);
  useEvaluateShortcut(evaluate);

  function prepareAB() {
    setAPrepError(null);
    setBPrepError(null);
    const tempC = inputs.pressure.temperature_c ?? inputs.air.temperature_c ?? 20;
    const pressBar =
      inputs.pressure.pressure_bar ??
      inputs.air.pressure_bar ??
      inputs.field.monitored_pressure_bar ??
      (inputs.section_profile.design_pressure_bar
        ? Number((inputs.section_profile.design_pressure_bar * 1.25).toFixed(2))
        : 80);

    if (inputs.pressure.temperature_c === null || inputs.pressure.pressure_bar === null) {
      patchInputs({
        pressure: {
          ...(inputs.pressure.temperature_c === null ? { temperature_c: tempC } : {}),
          ...(inputs.pressure.pressure_bar === null ? { pressure_bar: pressBar } : {}),
        },
      });
    }

    coefficientB.mutate(
      {
        source: inputs.modes.pressure_b_source,
        temperature_c: tempC,
        pressure_bar: pressBar,
        steel_alpha_micro_per_c: inputs.helper.steel_alpha_micro_per_c,
        steel_model: inputs.modes.steel_model,
        backend: inputs.water_backend || "table_v1",
      },
      {
        onSuccess: ({ data }) => {
          patchInputs({ pressure: { b_micro_per_c: data.b_micro_per_c } });
          if (data.water_beta_micro_per_c !== null) {
            patchInputs({ helper: { water_beta_micro_per_c: data.water_beta_micro_per_c } });
          }
          pushToast("success", "B katsayısı hazırlandı", fmt.b(data.b_micro_per_c));
        },
        onError: (error) => {
          setBPrepError(error.message);
          pushToast("error", "B hazırlanamadı", error.message);
        },
      },
    );

    if (inputs.pressure.a_micro_per_bar === null) {
      if (inputs.air.a_micro_per_bar !== null) {
        patchInputs({ pressure: { a_micro_per_bar: inputs.air.a_micro_per_bar } });
      } else if (inputs.modes.pressure_a_mode === "table") {
        tablePoint.mutate(
          {
            table: inputs.modes.pressure_a_reference.includes("GAIL") ? "gail" : "institutional",
            temperature_c: tempC,
            pressure_bar: pressBar,
          },
          {
            onSuccess: ({ data }) => {
              patchInputs({ pressure: { a_micro_per_bar: data.a_micro_per_bar } });
              pushToast("success", "A tablodan alındı", fmt.a(data.a_micro_per_bar));
            },
            onError: (error) => {
              setAPrepError(error.message);
              pushToast("error", "A hazırlanamadı", error.message);
            },
          },
        );
      } else if (inputs.modes.pressure_a_mode !== "manual") {
        coefficientA.mutate(
          {
            temperature_c: tempC,
            pressure_bar: pressBar,
            backend: inputs.water_backend || "table_v1",
          },
          {
            onSuccess: ({ data }) => {
              patchInputs({ pressure: { a_micro_per_bar: data.a_micro_per_bar } });
              pushToast("success", "A hesaplandı", fmt.a(data.a_micro_per_bar));
            },
            onError: (error) => {
              setAPrepError(error.message);
              pushToast("error", "A hazırlanamadı", error.message);
            },
          },
        );
      }
    }
  }

  const pressure = results.pressure;
  const geometry = results.geometry ?? geometryForInputs(inputs);
  const sections = sectionsFromInputs(inputs);
  const aValue = inputs.pressure.a_micro_per_bar;
  const bValue = inputs.pressure.b_micro_per_c;
  const deltaT = inputs.pressure.delta_t_c;
  const pa = inputs.pressure.actual_pressure_change_bar;

  const deltaError =
    deltaT !== null && (deltaT < -20 || deltaT > 20)
      ? "ΔT −20…+20 °C aralığında olmalı."
      : null;
  const paError =
    pa !== null && (pa < -50 || pa > 50)
      ? "Pa −50…+50 bar aralığında olmalı."
      : null;
  const aError =
    aValue !== null && (aValue <= 0 || aValue > 200)
      ? "A 0'dan büyük ve 200'den küçük olmalı."
      : null;
  const bError =
    bValue !== null && (bValue < -200 || bValue > 500)
      ? "B −200…+500 aralığında olmalı."
      : null;

  const missing: string[] = [];
  if (!sections.length) missing.push("Geometri");
  if (!aValue) missing.push("A");
  if (bValue === null) missing.push("B");
  if (deltaT === null) missing.push("ΔT");
  if (pa === null) missing.push("Pa");
  if (deltaError || paError || aError || bError) missing.push("geçerli aralık");

  const deltaHint =
    inputs.pressure.t_initial_c !== null && inputs.pressure.t_final_c !== null
      ? `Tilk ${num(inputs.pressure.t_initial_c, 1)} °C − Tson ${num(inputs.pressure.t_final_c, 1)} °C = ${num(
          round(inputs.pressure.t_initial_c - inputs.pressure.t_final_c, 3),
          3,
        )} °C`
      : "Tilk ve Tson girilirse ΔT otomatik türetilir.";

  function setTemperatures(initial: number | null, final: number | null, derive: boolean) {
    const derived = derive
      ? initial !== null && final !== null
        ? round(initial - final, 3)
        : null
      : inputs.pressure.delta_t_c;
    patchInputs({
      pressure: {
        t_initial_c: initial,
        t_final_c: final,
        derive_delta_t: derive,
        delta_t_c: derived,
      },
    });
  }

  function buildRequest(): PressureVariationRequest | null {
    if (!sections.length || !aValue || bValue === null || deltaT === null || pa === null) return null;
    return {
      geometry: { sections },
      a_micro_per_bar: aValue,
      b_micro_per_c: bValue,
      delta_t_c: deltaT,
      actual_pressure_change_bar: pa,
    };
  }

  function evaluate() {
    const request = buildRequest();
    if (!request || missing.length > 0) {
      pushToast("error", "Basınç testi değerlendirilemedi", `Eksik veya geçersiz: ${missing.join(", ")}`);
      return;
    }
    calculate.mutate(request, {
      onSuccess: ({ data }) => {
        pushToast(
          data.passed ? "success" : "error",
          data.passed ? "Basınç değişim testi başarılı" : "Basınç değişim testi başarısız",
          `Marj ${fmt.bar(data.margin_bar)} · Pt ${fmt.bar(data.theoretical_pressure_change_bar)}`,
        );
        saveResult.mutate({ testType: "pressure", payload: request as unknown as Record<string, unknown> });
      },
      onError: (error) => pushToast("error", "Basınç testi değerlendirilemedi", error.message),
    });
  }

  const sensitivity = sections.length && aValue && deltaT !== null && pa !== null
    ? (["institutional", "gail", "auto"] as const).map((source) => {
        const b = computeB({
          source,
          temperature_c: inputs.pressure.temperature_c ?? 20,
          pressure_bar: inputs.pressure.pressure_bar ?? 80,
          steel_alpha_micro_per_c: inputs.helper.steel_alpha_micro_per_c,
          steel_model: inputs.modes.steel_model,
          backend: inputs.water_backend || "table_v1",
        });
        const result = computePressure({
          geometry: { sections },
          a_micro_per_bar: aValue,
          b_micro_per_c: b.b_micro_per_c,
          delta_t_c: deltaT,
          actual_pressure_change_bar: pa,
        });
        return {
          source,
          b: b.b_micro_per_c,
          label:
            source === "institutional" ? "Kurum içi" : source === "gail" ? "GAIL" : "Otomatik",
          fullLabel: b.label,
          result,
        };
      })
    : [];

  const pressureHistory = history.filter((entry) => entry.testType === "pressure");

  return (
    <div className="space-y-5">
      {embedded ? (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] px-3.5 py-2.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-bold text-[var(--text)]">
              Detay Hesaplama — Basınç Değişim Testi (Şartname 15)
            </span>
            <Badge tone={pressure?.passed ? "pass" : pressure ? "fail" : "pending"}>
              {pressure ? (pressure.passed ? "Kabul" : "Red") : "Değerlendirme bekliyor"}
            </Badge>
            <span className="text-[10.5px] text-[var(--text-faint)]">
              Kural: (Pa − Pt) ≤ 0,3 bar
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
              loading={calculate.isPending}
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
          kicker="Basınç Değişim Testi"
          title="Basınç değişim değerlendirmesi"
          description="Pt teorik basınç değişimidir. Kabul kuralı (Pa − Pt) ≤ 0,3 bar; negatif B geçerlidir ve dP işareti döner."
          meta={
            <>
              <Badge tone={pressure?.passed ? "pass" : pressure ? "fail" : "pending"}>
                {pressure ? (pressure.passed ? "Kabul" : "Red") : "Değerlendirme bekliyor"}
              </Badge>
              <span className="text-[10.5px] text-[var(--text-faint)]">
                Kural: (Pa − Pt) ≤ 0,3 bar
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
                loading={calculate.isPending}
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
          {missing.join(", ")}. Değerlendirme bu alanlar tamamlanmadan çalışmaz.
        </InlineNotice>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
        <div className="space-y-4">
          <SectionCard
            title="Girdiler"
            description="A ve B katsayıları ile sıcaklık/basınç değişimi."
            icon={ArrowLeftRight}
            action={<CoefficientBadge state={pressure ? "computed" : "empty"} />}
          >
            <FieldGrid cols={2}>
              <NumberField
                label="Su sıcaklığı"
                unit="°C"
                value={inputs.pressure.temperature_c}
                onChange={(value) => patchInputs({ pressure: { temperature_c: value } })}
              />
              <NumberField
                label="Su basıncı"
                unit="bar"
                value={inputs.pressure.pressure_bar}
                onChange={(value) => patchInputs({ pressure: { pressure_bar: value } })}
              />
            </FieldGrid>

            <div className="mt-3 grid grid-cols-2 gap-2">
              <NumberField
                label="A katsayısı"
                unit="10⁻⁶/bar"
                value={aValue}
                onChange={(value) => patchInputs({ pressure: { a_micro_per_bar: value } })}
                error={aError}
                help="Katsayılar sekmesinden hazırlanır."
              />
              <NumberField
                label="B katsayısı"
                unit="10⁻⁶/°C"
                value={bValue}
                onChange={(value) => patchInputs({ pressure: { b_micro_per_c: value } })}
                error={bError}
                help="Kurum içi varsayılan; negatif olabilir."
              />
            </div>

            <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-2">
              <span className="text-[10.5px] leading-relaxed text-[var(--text-faint)]">
                B kaynağı:{" "}
                <span className="font-semibold text-[var(--text-soft)]">
                  {inputs.modes.pressure_b_source === "institutional"
                    ? "Kurum içi"
                    : inputs.modes.pressure_b_source === "gail"
                      ? "GAIL"
                      : "Otomatik"}
                </span>{" "}
                · {STEEL_MODEL_OPTIONS.find((model) => model.value === inputs.modes.steel_model)?.label ?? inputs.modes.steel_model}
              </span>
              <div className="flex flex-wrap items-center gap-1.5">
                <Button
                  size="sm"
                  variant="default"
                  icon={<Sigma size={12} />}
                  loading={coefficientB.isPending || coefficientA.isPending || tablePoint.isPending}
                  onClick={prepareAB}
                >
                  A &amp; B'yi Otomatik Doldur
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setTab("coefficients")}>
                  Katsayılar
                </Button>
              </div>
            </div>

            {aPrepError ? (
              <div className="mt-2">
                <InlineNotice tone="danger" title="A hazırlanamadı" icon={AlertTriangle}>
                  {aPrepError}
                </InlineNotice>
              </div>
            ) : null}

            {bPrepError ? (
              <div className="mt-2">
                <InlineNotice tone="danger" title="B hazırlanamadı" icon={AlertTriangle}>
                  {bPrepError}
                </InlineNotice>
              </div>
            ) : null}

            {(bValue !== null && bValue < 0) ||
            (inputs.pressure.temperature_c !== null &&
              inputs.pressure.temperature_c >= 0 &&
              inputs.pressure.temperature_c <= 4) ? (
              <div className="mt-2">
                <InlineNotice tone="info" title="0–4 °C bölgesi / negatif B" icon={Info}>
                  0–4 °C aralığında suyun yoğunluk anomalisi nedeniyle <span className="font-mono">β</span>{" "}
                  ve <span className="font-mono">B</span> sıfır veya negatif olabilir;{" "}
                  <span className="font-mono">Pt</span> işaretinin ters dönmesi fiziksel olarak geçerlidir.
                </InlineNotice>
              </div>
            ) : null}

            <div className="mt-4 border-t border-[var(--border)] pt-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <span className="field-label">Sıcaklık değişimi</span>
                  <p className="mt-0.5 text-[10.5px] text-[var(--text-faint)]">
                    ΔT = Tilk − Tson. Tilk/Tson girilirse ΔT otomatik hesaplanır ve kilitlenir.
                  </p>
                </div>
                <div className="seg-control" role="group" aria-label="Sıcaklık değişimi modu">
                  <button
                    type="button"
                    className="seg-btn"
                    aria-pressed={!inputs.pressure.derive_delta_t}
                    onClick={() =>
                      setTemperatures(
                        inputs.pressure.t_initial_c,
                        inputs.pressure.t_final_c,
                        false,
                      )
                    }
                  >
                    ΔT doğrudan gir
                  </button>
                  <button
                    type="button"
                    className="seg-btn"
                    aria-pressed={inputs.pressure.derive_delta_t}
                    onClick={() =>
                      setTemperatures(
                        inputs.pressure.t_initial_c,
                        inputs.pressure.t_final_c,
                        true,
                      )
                    }
                  >
                    Tilk − Tson ile türet
                  </button>
                </div>
              </div>

              <FieldGrid cols={2} className="mt-2">
                <NumberField
                  label="Başlangıç sıcaklığı Tilk"
                  unit="°C"
                  value={inputs.pressure.t_initial_c}
                  onChange={(value) =>
                    setTemperatures(value, inputs.pressure.t_final_c, inputs.pressure.derive_delta_t)
                  }
                  help="İsteğe bağlı; girilirse ΔT = Tilk − Tson otomatik hesaplanır."
                />
                <NumberField
                  label="Bitiş sıcaklığı Tson"
                  unit="°C"
                  value={inputs.pressure.t_final_c}
                  onChange={(value) =>
                    setTemperatures(inputs.pressure.t_initial_c, value, inputs.pressure.derive_delta_t)
                  }
                  help="İsteğe bağlı; girilirse ΔT = Tilk − Tson otomatik hesaplanır."
                />
              </FieldGrid>

              <div className="mt-3 grid grid-cols-2 gap-2">
                {inputs.pressure.derive_delta_t ? (
                  <div>
                    <ReadonlyValue
                      label="ΔT (türetilmiş)"
                      unit="°C"
                      value={
                        <span className="flex items-center justify-end gap-1.5">
                          <Lock size={11} className="text-[var(--text-faint)]" aria-hidden />
                          {num(deltaT, 3)}
                        </span>
                      }
                      hint={deltaHint}
                    />
                    {deltaError ? (
                      <p className="mt-1 text-[10.5px] font-medium text-[var(--danger)]" role="alert">
                        {deltaError}
                      </p>
                    ) : null}
                  </div>
                ) : (
                  <NumberField
                    label="ΔT = Tilk − Tson"
                    unit="°C"
                    value={deltaT}
                    onChange={(value) => patchInputs({ pressure: { delta_t_c: value } })}
                    error={deltaError}
                    help="-20…+20 °C"
                  />
                )}
                <NumberField
                  label="Fiili basınç değişimi Pa"
                  unit="bar"
                  value={pa}
                  onChange={(value) => patchInputs({ pressure: { actual_pressure_change_bar: value } })}
                  error={paError}
                  help="Pa = Pilk − Pson"
                />
              </div>

              <div className="mt-2 rounded-lg border border-[var(--info-border)] bg-[var(--info-bg)] px-2.5 py-2">
                <p className="flex items-start gap-1.5 text-[10.5px] leading-relaxed text-[var(--text-muted)]">
                  <Info size={12} className="mt-0.5 shrink-0 text-[var(--info)]" aria-hidden />
                  <span>
                    <span className="font-mono">ΔT = Tilk − Tson</span>,{" "}
                    <span className="font-mono">Pa = Pilk − Pson</span>. Örnek: Tilk 22 °C, Tson 20 °C →
                    ΔT = +2 °C; Pilk 82 bar, Pson 76,05 bar → Pa = +5,95 bar.
                  </span>
                </p>
              </div>
            </div>

            <div className="mt-4 grid grid-cols-3 gap-2 border-t border-[var(--border)] pt-3">
              <ResultTile label="İç hacim" value={geometry ? num(geometry.internal_volume_m3, 3) : "—"} unit="m³" />
              <ResultTile label="Elastisite" value={geometry ? num(geometry.elasticity_term, 3) : "—"} hint="0,884·ri/s" />
              <ResultTile
                label="Payda"
                value={geometry && aValue ? num(geometry.elasticity_term + aValue, 3) : "—"}
                hint="elastisite + A"
              />
            </div>
          </SectionCard>

          <SectionCard
            title="Geçmiş"
            description="Bu oturumdaki basınç değişim değerlendirmeleri."
            icon={History}
            bodyClassName="pt-2"
          >
            {pressureHistory.length === 0 ? (
              <EmptyState title="Basınç testi kaydı yok" description="İlk değerlendirmeden sonra burada listelenir." icon={History} />
            ) : (
              <ul className="space-y-1.5">
                {pressureHistory.map((entry) => (
                  <li key={entry.id} className="flex items-start gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-2">
                    <span className="mt-0.5 font-mono text-[10px] text-[var(--text-faint)]">{relativeTime(entry.at)}</span>
                    <span className="min-w-0 flex-1 truncate text-[11px] text-[var(--text-muted)]">{entry.summary}</span>
                    <Badge tone={entry.status === "BASARILI" ? "pass" : entry.status === "BASARISIZ" ? "fail" : "pending"}>
                      {entry.status}
                    </Badge>
                  </li>
                ))}
              </ul>
            )}
          </SectionCard>
        </div>

        <div className="space-y-4">
          <SectionCard
            title="Sonuç"
            description="Pt, üst sınır, Pa ve marj."
            icon={Gauge}
            action={pressure ? <Badge tone={pressure.passed ? "pass" : "fail"}>{pressure.passed ? "Kabul" : "Red"}</Badge> : null}
          >
            <div className="grid grid-cols-2 gap-2">
              <ResultTile label="Teorik Pt" value={num(pressure?.theoretical_pressure_change_bar, 3)} unit="bar" />
              <ResultTile label="Üst sınır" value={num(pressure?.allowable_upper_pressure_change_bar, 3)} unit="bar" hint="Pt + 0,3 bar" />
              <ResultTile label="Fiili Pa" value={num(pa, 3)} unit="bar" />
              <ResultTile
                label="Marj (Pa − Pt)"
                value={num(pressure?.margin_bar, 3)}
                unit="bar"
                tone={pressure ? (pressure.passed ? "pass" : "fail") : undefined}
              />
            </div>

            <div className="mt-4">
              <MarginGauge
                margin={pressure?.margin_bar}
                tolerance={0.3}
                passed={pressure?.passed}
              />
            </div>

            {pressure?.negative_b ? (
              <InlineNotice tone="info" title="B negatif" icon={Info}>
                B negatif; dP işareti döner ve bu fiziksel olarak geçerlidir. Kabul kuralı yine
                (Pa − Pt) ≤ 0,3 bar olarak uygulanır.
              </InlineNotice>
            ) : null}
          </SectionCard>

          <DecisionCard
            decision={pressure?.decision}
            testName="Basınç Değişim Testi"
            marginUnit="bar"
            why={
              <>
                <p className="font-mono">Pt = (B · ΔT) / (0,884·ri/s + A)</p>
                <p className="font-mono">marj = Pa − Pt; kabul marj ≤ 0,3 bar</p>
                <p>
                  B = {fmt.b(bValue)} · ΔT = {fmt.c(deltaT)} · A = {fmt.a(aValue)} · Pa = {fmt.bar(pa)}
                </p>
                <p>Negatif B’de dP işareti döner; sonuç geçerlidir ve ayrıca bilgi notu gösterilir.</p>
              </>
            }
            actions={
              <>
                <Button size="lg" variant="primary" icon={<ArrowRight size={15} />} onClick={() => setTab("reports")}>
                  Raporlara geç
                </Button>
                <Button size="lg" variant="ghost" onClick={() => setTab("coefficients")}>
                  Katsayı detayını gör
                </Button>
              </>
            }
          />

          <SectionCard
            title="B kaynağına göre duyarlılık"
            description="Aynı T/P ve ΔT/Pa için üç B kaynağının ürettiği Pt."
            icon={Sigma}
          >
            {sensitivity.length === 0 ? (
              <p className="text-[11.5px] leading-relaxed text-[var(--text-faint)]">
                Duyarlılık için geometri, A, ΔT ve Pa gerekli.
              </p>
            ) : (
              <div
                role="region"
                aria-label="B kaynağına göre duyarlılık tablosu"
                className="table-wrap scroll-thin"
              >
                <table className="data compact">
                  <caption>Yerel önizleme; resmi karar domain/API hesabından gelir.</caption>
                  <thead>
                    <tr>
                      <th scope="col">Kaynak</th>
                      <th scope="col" className="num">B</th>
                      <th scope="col" className="num">Pt (bar)</th>
                      <th scope="col" className="num">Marj (bar)</th>
                      <th scope="col">Durum</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sensitivity.map((row) => (
                      <tr key={row.source}>
                        <th scope="row" className="whitespace-nowrap font-normal" title={row.fullLabel}>
                          {row.label}
                        </th>
                        <td className="num">{num(row.b, 1)}</td>
                        <td className="num">{num(row.result.theoretical_pressure_change_bar, 3)}</td>
                        <td className="num">{num(row.result.margin_bar, 3)}</td>
                        <td className="whitespace-nowrap">
                          <Badge tone={row.result.passed ? "pass" : "fail"}>
                            {row.result.passed ? "uygun" : "ret"}
                          </Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p className="mt-2 text-[10px] leading-relaxed text-[var(--text-faint)]">
              Kaynak değişimi B’yi ve dolayısıyla Pt’yi değiştirir; marj hesabı Pa sabitken yeniden
              yapılmalıdır.
            </p>
          </SectionCard>
        </div>
      </div>
      {embedded ? null : <OperationsPanel />}
    </div>
  );
}
