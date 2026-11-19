import { useId, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Database,
  Download,
  FlaskConical,
  Info,
  RefreshCw,
  Sigma,
  Sparkles,
  Table2,
  Wrench,
} from "lucide-react";
import { PageHeader } from "../components/layout/PageHeader";
import { SectionCard, ResultTile } from "../components/ui/Card";
import { Badge, CoefficientBadge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { NumberField, SelectField, FieldGrid } from "../components/ui/Field";
import { InlineNotice } from "../components/ui/State";
import {
  useBackendComparison,
  useCoefficientA,
  useCoefficientB,
  useCoefficientCompare,
  useMeta,
  useReferenceTables,
  useTablePoint,
} from "../hooks/queries";
import { useAppStore } from "../store/useAppStore";
import { STEEL_MODEL_OPTIONS, STEEL_PRESETS } from "../lib/constants";
import { fmt, num } from "../lib/format";
import {
  buildBackendComparisonCsv,
  buildBackendComparisonReportText,
  downloadBlob,
  reportFileName,
} from "../lib/report";
import type { AMode, BackendComparisonItem, BSource } from "../lib/types";
import { cn } from "../lib/utils";

const A_MODES: Array<{ value: AMode; label: string; note: string }> = [
  { value: "auto", label: "Otomatik", note: "Su özelliği backend'inden hesaplanır." },
  { value: "table", label: "Tablo", note: "Referans tablosundan A okunur (onarım uygulanır)." },
  { value: "manual", label: "Manuel", note: "Kullanıcı değeri; aralık kontrolü yapılır." },
];

const B_SOURCES: Array<{ value: BSource; label: string; note: string }> = [
  { value: "institutional", label: "Kurum içi", note: "Varsayılan · BOTAŞ A/B kontrol tablosu" },
  { value: "gail", label: "GAIL", note: "GAIL referans tablosu" },
  { value: "auto", label: "Otomatik", note: "β − çelik genleşmesi" },
];

export function CoefficientsPage() {
  const inputs = useAppStore((state) => state.inputs);
  const results = useAppStore((state) => state.results);
  const patchInputs = useAppStore((state) => state.patchInputs);
  const setTab = useAppStore((state) => state.setTab);
  const pushToast = useAppStore((state) => state.pushToast);

  const { data: meta } = useMeta();
  const { data: referenceTables } = useReferenceTables();
  const coefficientA = useCoefficientA();
  const coefficientB = useCoefficientB();
  const compare = useCoefficientCompare();
  const backendCompare = useBackendComparison();
  const tablePoint = useTablePoint();

  const backendTableCaptionId = useId();
  const [aTarget, setATarget] = useState<"air" | "pressure">("pressure");
  const [aError, setAError] = useState<string | null>(null);
  const [bError, setBError] = useState<string | null>(null);
  const [compareError, setCompareError] = useState<string | null>(null);

  const activeWaterBackend = inputs.water_backend || meta?.water_backends[0]?.key || "table_v1";
  const context = aTarget === "air" ? inputs.air : inputs.pressure;
  const aMode = aTarget === "air" ? inputs.modes.air_a_mode : inputs.modes.pressure_a_mode;
  const aResult =
    aTarget === "air" ? results.coefficients?.airA : results.coefficients?.pressureA;
  const bResult = results.coefficients?.pressureB;
  const bCompare = results.bCompare;

  const effectiveB = inputs.pressure.b_micro_per_c ?? bResult?.b_micro_per_c ?? null;
  const effectiveBeta = bResult?.water_beta_micro_per_c ?? inputs.helper.water_beta_micro_per_c ?? null;
  const bTemp = inputs.pressure.temperature_c;
  const inDensityAnomalyBand = bTemp !== null && bTemp >= 0 && bTemp <= 4;
  const showNegativeBetaOrBNotice =
    inDensityAnomalyBand ||
    (effectiveBeta !== null && effectiveBeta < 0) ||
    (effectiveB !== null && effectiveB < 0);

  const institutional = referenceTables?.items.find((table) => table.key === "institutional");
  const gail = referenceTables?.items.find((table) => table.key === "gail");

  function setContextValues(temperature: number | null, pressure: number | null) {
    if (aTarget === "air") {
      patchInputs({ air: { temperature_c: temperature, pressure_bar: pressure } });
    } else {
      patchInputs({ pressure: { temperature_c: temperature, pressure_bar: pressure } });
    }
  }

  function setAModeValue(mode: AMode) {
    if (aTarget === "air") {
      patchInputs({ modes: { air_a_mode: mode } });
    } else {
      patchInputs({ modes: { pressure_a_mode: mode } });
    }
  }

  function setAValue(value: number | null) {
    if (aTarget === "air") {
      patchInputs({ air: { a_micro_per_bar: value } });
    } else {
      patchInputs({ pressure: { a_micro_per_bar: value } });
    }
  }

  function computeA() {
    setAError(null);
    if (context.temperature_c === null || context.pressure_bar === null) {
      const msg = "Sıcaklık ve basınç girilmelidir.";
      setAError(msg);
      pushToast("error", "A hesaplanamadı", msg);
      return;
    }
    if (aMode === "manual") {
      pushToast("info", "Manuel A", "Manuel modda değer doğrudan kullanılır; hesap çalıştırılmaz.");
      return;
    }
    if (aMode === "table") {
      tablePoint.mutate(
        {
          table: (aTarget === "air" ? inputs.modes.air_a_reference : inputs.modes.pressure_a_reference).includes("GAIL")
            ? "gail"
            : "institutional",
          temperature_c: context.temperature_c,
          pressure_bar: context.pressure_bar,
        },
        {
          onSuccess: ({ data }) => {
            setAValue(data.a_micro_per_bar);
            pushToast(
              "success",
              "A tablodan okundu",
              `${fmt.a(data.a_micro_per_bar)}${data.repaired ? " · onarılmış hücre" : ""}`,
            );
          },
          onError: (error) => {
            setAError(error.message);
            pushToast("error", "A okunamadı", error.message);
          },
        },
      );
      return;
    }
    coefficientA.mutate(
      {
        temperature_c: context.temperature_c,
        pressure_bar: context.pressure_bar,
        backend: activeWaterBackend,
      },
      {
        onSuccess: ({ data }) => {
          setAValue(data.a_micro_per_bar);
          pushToast(
            "success",
            "A katsayısı hesaplandı",
            `${fmt.a(data.a_micro_per_bar)} · ${data.backend.label}`,
          );
        },
        onError: (error) => {
          setAError(error.message);
          pushToast("error", "A hesaplanamadı", error.message);
        },
      },
    );
  }

  function computeB() {
    setBError(null);
    if (inputs.pressure.temperature_c === null || inputs.pressure.pressure_bar === null) {
      const msg = "Sıcaklık ve basınç girilmelidir.";
      setBError(msg);
      pushToast("error", "B hesaplanamadı", msg);
      return;
    }
    coefficientB.mutate(
      {
        source: inputs.modes.pressure_b_source,
        temperature_c: inputs.pressure.temperature_c,
        pressure_bar: inputs.pressure.pressure_bar,
        steel_alpha_micro_per_c: inputs.helper.steel_alpha_micro_per_c,
        steel_model: inputs.modes.steel_model,
        backend: activeWaterBackend,
      },
      {
        onSuccess: ({ data }) => {
          patchInputs({ pressure: { b_micro_per_c: data.b_micro_per_c } });
          if (data.water_beta_micro_per_c !== null) {
            patchInputs({ helper: { water_beta_micro_per_c: data.water_beta_micro_per_c } });
          }
          pushToast(
            "success",
            "B katsayısı hazır",
            `${fmt.b(data.b_micro_per_c)} · ${data.label}`,
          );
        },
        onError: (error) => {
          setBError(error.message);
          pushToast("error", "B hesaplanamadı", error.message);
        },
      },
    );
  }

  function runCompare() {
    if (inputs.pressure.temperature_c === null || inputs.pressure.pressure_bar === null) {
      pushToast("error", "Karşılaştırma yapılamadı", "Sıcaklık ve basınç girilmelidir.");
      return;
    }
    setCompareError(null);
    compare.mutate(
      {
        temperature_c: inputs.pressure.temperature_c,
        pressure_bar: inputs.pressure.pressure_bar,
        steel_alpha_micro_per_c: inputs.helper.steel_alpha_micro_per_c,
        steel_model: inputs.modes.steel_model,
        backend: activeWaterBackend,
      },
      {
        onError: (error) => setCompareError(error.message),
      },
    );
  }

  function runBackendCompare() {
    if (inputs.pressure.temperature_c === null || inputs.pressure.pressure_bar === null) {
      pushToast("error", "Backend karşılaştırması yapılamadı", "Sıcaklık ve basınç girilmelidir.");
      return;
    }
    backendCompare.mutate({
      temperature_c: inputs.pressure.temperature_c,
      pressure_bar: inputs.pressure.pressure_bar,
    });
  }

  function exportBackendComparison(format: "txt" | "csv") {
    const cmp = results.backendCompare;
    if (!cmp || !meta) return;
    const baseName = reportFileName(format, inputs.report.report_no ? `${inputs.report.report_no}_backend` : "backend_karsilastirma");
    if (format === "csv") {
      const csv = buildBackendComparisonCsv(cmp, activeWaterBackend);
      downloadBlob(new Blob([`\uFEFF${csv}`], { type: "text/csv;charset=utf-8" }), baseName);
    } else {
      const txt = buildBackendComparisonReportText(cmp, activeWaterBackend, meta);
      downloadBlob(new Blob([txt], { type: "text/plain;charset=utf-8" }), baseName);
    }
    pushToast("success", "Karşılaştırma raporu indirildi", baseName);
  }

  function getRefItem(items: BackendComparisonItem[]): BackendComparisonItem | undefined {
    return (
      items.find((item) => item.backend.key === "table_v1" && !item.error) ??
      items.find((item) => !item.error)
    );
  }

  const activeA = aMode === "manual" ? context.a_micro_per_bar : aResult?.a_micro_per_bar ?? context.a_micro_per_bar;

  return (
    <div className="space-y-5">
      <PageHeader
        kicker="Katsayılar & Detay"
        title="A/B hazırlama, üç kaynak ve backend karşılaştırması"
        description="A su sıkıştırılabilirliği ve B ısıl genleşme farkı burada hazırlanır; aynı sayfada kurum içi tablo, GAIL, otomatik β−3α, su özelliği backend'leri ve A tablosu onarım bilgisi karşılaştırılır."
        meta={
          <>
            <span className="flex items-center gap-1.5 text-[11px] text-[var(--text-muted)]">
              A <CoefficientBadge state={aResult?.state ?? (activeA !== null ? "manual" : "empty")} />
            </span>
            <span className="flex items-center gap-1.5 text-[11px] text-[var(--text-muted)]">
              B <CoefficientBadge state={bResult ? "reference" : inputs.pressure.b_micro_per_c !== null ? "manual" : "empty"} />
            </span>
            <span className="chip">{inputs.modes.steel_model}</span>
            <Badge tone={bCompare ? "pass" : "pending"}>
              {bCompare ? "karşılaştırma hazır" : "karşılaştırma bekliyor"}
            </Badge>
          </>
        }
        actions={
          <>
            <Button
              size="lg"
              icon={<RefreshCw size={15} />}
              loading={compare.isPending}
              onClick={runCompare}
            >
              Üç kaynağı karşılaştır
            </Button>
            <Button size="lg" icon={<ArrowRight size={15} />} onClick={() => setTab("air")}>
              Hava testine git
            </Button>
            <Button size="lg" variant="primary" icon={<ArrowRight size={15} />} onClick={() => setTab("pressure")}>
              Basınç testine git
            </Button>
          </>
        }
      />

      <div className="grid gap-4 xl:grid-cols-2">
        <SectionCard
          title="A — su sıkıştırılabilirliği"
          description="10⁻⁶/bar mertebesinde; test sıcaklığı ve basıncına bağlıdır."
          icon={FlaskConical}
          action={<CoefficientBadge state={aResult?.state ?? (activeA ? "manual" : "empty")} />}
        >
          <div className="mb-3 seg-control" role="group" aria-label="A hedef testi">
            <button type="button" className="seg-btn" aria-pressed={aTarget === "air"} onClick={() => setATarget("air")}>
              Hava testi
            </button>
            <button
              type="button"
              className="seg-btn"
              aria-pressed={aTarget === "pressure"}
              onClick={() => setATarget("pressure")}
            >
              Basınç testi
            </button>
          </div>

          <FieldGrid cols={2}>
            <NumberField
              label="Su sıcaklığı"
              unit="°C"
              value={context.temperature_c}
              onChange={(value) => setContextValues(value, context.pressure_bar)}
              min={0}
              max={60}
            />
            <NumberField
              label="Su basıncı"
              unit="bar"
              value={context.pressure_bar}
              onChange={(value) => setContextValues(context.temperature_c, value)}
              min={1}
              max={150}
            />
          </FieldGrid>

          <div className="mt-3">
            <span className="field-label">A modu</span>
            <div className="mt-1.5 seg-control" role="group" aria-label="A modu">
              {A_MODES.map((mode) => (
                <button
                  key={mode.value}
                  type="button"
                  className="seg-btn"
                  aria-pressed={aMode === mode.value}
                  title={mode.note}
                  onClick={() => setAModeValue(mode.value)}
                >
                  {mode.label}
                </button>
              ))}
            </div>
          </div>

          {aMode === "table" ? (
            <div className="mt-3">
              <SelectField
                label="Referans tablosu"
                value={aTarget === "air" ? inputs.modes.air_a_reference : inputs.modes.pressure_a_reference}
                onChange={(value) => {
                  if (aTarget === "air") patchInputs({ modes: { air_a_reference: value } });
                  else patchInputs({ modes: { pressure_a_reference: value } });
                }}
                options={(referenceTables?.items ?? []).map((table) => ({
                  value: table.option_label,
                  label: `${table.label} · ${table.temperature.min}–${table.temperature.max} °C`,
                }))}
                placeholder="Tablo seçin"
              />
            </div>
          ) : null}

          {aMode === "auto" ? (
            <div className="mt-3">
              <SelectField
                label="Su özelliği backend'i"
                value={activeWaterBackend}
                onChange={(value) => patchInputs({ water_backend: value })}
                options={(meta?.water_backends ?? []).map((backend) => ({
                  value: backend.key,
                  label: `${backend.label}${backend.distribution_ready ? "" : " (dağıtım dışı)"}`,
                }))}
              />
            </div>
          ) : null}

          {aMode === "manual" ? (
            <div className="mt-3">
              <NumberField
                label="Manuel A"
                unit="10⁻⁶/bar"
                value={context.a_micro_per_bar}
                onChange={setAValue}
                min={1}
                max={200}
                help="Aralık: 1,0 – 200,0. Değer doğrudan testlerde kullanılır."
              />
            </div>
          ) : null}

          <div className="mt-3 flex items-center justify-between gap-2">
            <span className="text-[10.5px] text-[var(--text-faint)]">
              {aMode === "manual" ? "Manuel modda hesap çalışmaz." : "Seçili sıcaklık ve basınç için katsayı hesaplanır."}
            </span>
            <Button
              size="lg"
              variant="primary"
              icon={<Sigma size={15} />}
              loading={coefficientA.isPending || tablePoint.isPending}
              onClick={computeA}
            >
              A’yı hazırla
            </Button>
          </div>

          <div className="mt-3 grid grid-cols-2 gap-2">
            <ResultTile
              label="A"
              value={num(activeA, 6)}
              unit="10⁻⁶/bar"
              tone={activeA !== null ? (aMode === "manual" ? "info" : "pass") : undefined}
              hint={aResult?.backend.label ?? (aMode === "manual" ? "Manuel değer" : "Henüz hesaplanmadı")}
            />
            <ResultTile
              label="Backend"
              value={
                <span className="text-[13px]">{aResult?.backend.key ?? (aMode === "table" ? "referans tablo" : aMode === "manual" ? "manuel" : activeWaterBackend)}</span>
              }
              hint={
                aResult?.backend.label ??
                (aMode === "table" ? "Onarım bilgisi aşağıda" : "API coefficients/a")
              }
            />
          </div>
          {aError ? (
            <div className="mt-3">
              <InlineNotice tone="danger" title="A hazırlanamadı" icon={AlertTriangle}>
                {aError}
              </InlineNotice>
            </div>
          ) : null}
        </SectionCard>

        <SectionCard
          title="B — basınç değişim katsayısı"
          description="Varsayılan kurum içi tablodur. Otomatik modda β − 3α (hacimsel) kullanılır."
          icon={Sparkles}
          action={<CoefficientBadge state={bResult?.source === "auto" ? "computed" : bResult ? "reference" : inputs.pressure.b_micro_per_c !== null ? "manual" : "empty"} />}
        >
          <div className="mb-3 seg-control" role="group" aria-label="B kaynağı">
            {B_SOURCES.map((source) => (
              <button
                key={source.value}
                type="button"
                className="seg-btn"
                aria-pressed={inputs.modes.pressure_b_source === source.value}
                title={source.note}
                onClick={() => {
                  patchInputs({
                    modes: {
                      pressure_b_source: source.value,
                      pressure_b_reference:
                        source.value === "gail"
                          ? "GAIL referans tablosu - aktif T/P"
                          : source.value === "institutional"
                            ? "BOTAŞ referans tablosu - aktif T/P"
                            : "",
                    },
                    pressure: { b_micro_per_c: null },
                  });
                }}
              >
                {source.label}
              </button>
            ))}
          </div>

          <p className="text-[10.5px] leading-relaxed text-[var(--text-faint)]">
            {B_SOURCES.find((source) => source.value === inputs.modes.pressure_b_source)?.note}
            {inputs.modes.pressure_b_source !== "auto" ? " · Tablo B değeri ham hücreden alınır." : ""}
          </p>

          <FieldGrid cols={2} className="mt-3">
            <NumberField
              label="Su sıcaklığı (B)"
              unit="°C"
              value={inputs.pressure.temperature_c}
              onChange={(value) => patchInputs({ pressure: { temperature_c: value } })}
            />
            <NumberField
              label="Su basıncı (B)"
              unit="bar"
              value={inputs.pressure.pressure_bar}
              onChange={(value) => patchInputs({ pressure: { pressure_bar: value } })}
            />
          </FieldGrid>

          <div className="mt-3 grid grid-cols-2 gap-3">
            <SelectField
              label="Çelik modeli"
              value={inputs.modes.steel_model}
              onChange={(value) =>
                patchInputs({
                  modes: { steel_model: value as typeof inputs.modes.steel_model },
                })
              }
              options={STEEL_MODEL_OPTIONS.map((model) => ({
                value: model.value,
                label: model.label,
              }))}
              disabled={inputs.modes.pressure_b_source !== "auto"}
              help={
                inputs.modes.pressure_b_source === "auto"
                  ? STEEL_MODEL_OPTIONS.find((model) => model.value === inputs.modes.steel_model)?.note
                  : "Yalnızca otomatik kaynakta etkilidir."
              }
            />
            <NumberField
              label="Çelik α"
              unit="10⁻⁶/°C"
              value={inputs.helper.steel_alpha_micro_per_c}
              onChange={(value) =>
                patchInputs({ helper: { steel_alpha_micro_per_c: value ?? 12 } })
              }
              min={0.1}
              disabled={inputs.modes.pressure_b_source !== "auto"}
              help="Karbon çelik varsayılanı 12,0."
            />
          </div>

          <div className="mt-2 grid gap-2 sm:grid-cols-2">
            <SelectField
              label="Çelik preset"
              value={inputs.modes.steel_preset}
              onChange={(value) => {
                const preset = STEEL_PRESETS.find((item) => item.label === value);
                patchInputs({
                  modes: { steel_preset: value },
                  helper: {
                    steel_alpha_micro_per_c:
                      preset?.value ?? inputs.helper.steel_alpha_micro_per_c,
                  },
                });
              }}
              options={STEEL_PRESETS.map((preset) => ({ value: preset.label, label: preset.label }))}
            />
            {inputs.modes.pressure_b_source === "auto" ? (
              <SelectField
                label="Su özelliği backend'i (auto β)"
                value={activeWaterBackend}
                onChange={(value) => patchInputs({ water_backend: value })}
                options={(meta?.water_backends ?? []).map((backend) => ({
                  value: backend.key,
                  label: `${backend.label}${backend.distribution_ready ? "" : " (dağıtım dışı)"}`,
                }))}
              />
            ) : null}
          </div>

          <div className="mt-3 flex items-center justify-between gap-2">
            <span className="text-[10.5px] text-[var(--text-faint)]">
              {inputs.modes.pressure_b_source === "auto"
                ? "β otomatik hesaplanır; α çelik modeline göre düşülür."
                : "Tablo aralığı: kurum içi 1–25 °C / 30–120 bar."}
            </span>
            <Button
              size="lg"
              variant="primary"
              icon={<Sigma size={15} />}
              loading={coefficientB.isPending}
              onClick={computeB}
            >
              B’yi hazırla
            </Button>
          </div>

          <div className="mt-3 grid grid-cols-2 gap-2">
            <ResultTile
              label="B"
              value={num(inputs.pressure.b_micro_per_c ?? bResult?.b_micro_per_c, 6)}
              unit="10⁻⁶/°C"
              tone={
                effectiveB !== null
                  ? effectiveB < 0
                    ? "info"
                    : "pass"
                  : undefined
              }
              hint={bResult?.label ?? B_SOURCES.find((s) => s.value === inputs.modes.pressure_b_source)?.note}
            />
            <ResultTile
              label="Su β"
              value={num(inputs.helper.water_beta_micro_per_c, 6)}
              unit="10⁻⁶/°C"
              tone={
                inputs.helper.water_beta_micro_per_c !== null && inputs.helper.water_beta_micro_per_c < 0
                  ? "info"
                  : undefined
              }
              hint="Otomatik kaynakta dolar"
            />
          </div>

          {bError ? (
            <div className="mt-3">
              <InlineNotice tone="danger" title="B hesaplanamadı" icon={AlertTriangle}>
                <p>{bError}</p>
                {inputs.modes.pressure_b_source !== "auto" && bTemp !== null && bTemp < 1 ? (
                  <Button
                    size="sm"
                    variant="default"
                    className="mt-2"
                    onClick={() => {
                      setBError(null);
                      patchInputs({
                        modes: { pressure_b_source: "auto", pressure_b_reference: "" },
                        pressure: { b_micro_per_c: null },
                      });
                    }}
                  >
                    Otomatik β − 3α kaynağına geç
                  </Button>
                ) : null}
              </InlineNotice>
            </div>
          ) : null}

          {showNegativeBetaOrBNotice ? (
            <div className="mt-3">
              <InlineNotice
                tone="info"
                title="0–4 °C yoğunluk anomalisi / negatif β veya B"
                icon={Info}
              >
                0–4 °C bölgesinde suyun maksimum yoğunluk noktası nedeniyle suyun ısıl genleşme
                katsayısı (<span className="font-mono">β</span>) sıfırın altına inebilir ve{" "}
                <span className="font-mono">B = β − 3α</span> negatif olur. Negatif{" "}
                <span className="font-mono">B</span> ile teorik{" "}
                <span className="font-mono">Pt</span> işareti ters döner ve fiziksel olarak
                geçerlidir. Kurum içi/GAIL tabloları 1–25 °C aralığını kapsar; 1 °C altında{" "}
                <span className="font-semibold">Otomatik</span> kaynak (0–40 °C) kullanılmalıdır.
              </InlineNotice>
            </div>
          ) : null}

          {bResult?.note ? (
            <p className="mt-2 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-2 text-[10.5px] leading-relaxed text-[var(--text-muted)]">
              {bResult.note}
            </p>
          ) : null}
          {bResult?.repaired_table ? (
            <div className="mt-2">
              <Badge tone="warning">
                <Wrench size={11} /> Onarılmış tablo hücresi
              </Badge>
            </div>
          ) : null}
        </SectionCard>
      </div>

      <SectionCard
        title="Üç kaynak karşılaştırması"
        description="Aynı T/P düğümünde kurum içi, GAIL ve otomatik B değerleri."
        icon={Table2}
        action={
          <Button size="lg" variant="primary" icon={<RefreshCw size={15} />} loading={compare.isPending} onClick={runCompare}>
            Karşılaştır
          </Button>
        }
      >
        {compareError ? <InlineNotice tone="danger" title="Karşılaştırma başarısız">{compareError}</InlineNotice> : null}
        {bCompare ? (
          <>
            <div className="table-wrap scroll-thin mt-1">
              <table className="data">
                <caption>
                  T = {fmt.c(bCompare.temperature_c)} · P = {fmt.bar(bCompare.pressure_bar)}
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Kaynak</th>
                    <th scope="col" className="num">B (10⁻⁶/°C)</th>
                    <th scope="col" className="num">Kurum içi farkı</th>
                    <th scope="col">Durum</th>
                    <th scope="col">Not</th>
                  </tr>
                </thead>
                <tbody>
                  {[
                    { key: "institutional", row: bCompare.institutional },
                    { key: "gail", row: bCompare.gail },
                    { key: "auto", row: bCompare.auto },
                  ].map(({ key, row }) => {
                    const delta =
                      key === "institutional"
                        ? 0
                        : row.b_micro_per_c - bCompare.institutional.b_micro_per_c;
                    return (
                      <tr key={key} className={cn(key === inputs.modes.pressure_b_source && "bg-[var(--primary-soft)]")}>
                        <td>
                          <div className="flex items-center gap-2">
                            <span className="font-medium text-[var(--text)]">{row.label}</span>
                            {key === inputs.modes.pressure_b_source ? <Badge tone="info">seçili</Badge> : null}
                          </div>
                        </td>
                        <td className="num">{num(row.b_micro_per_c, 6)}</td>
                        <td className={cn("num", delta === 0 ? "text-[var(--text-faint)]" : "tone-warning")}>
                          {delta === 0 ? "—" : `${delta > 0 ? "+" : ""}${num(delta, 6)}`}
                        </td>
                        <td>
                          {row.repaired_table ? <Badge tone="warning">onarıldı</Badge> : <Badge tone="pass">ham</Badge>}
                        </td>
                        <td className="max-w-[320px] text-[10.5px] leading-snug text-[var(--text-muted)]">
                          {row.note}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
              <ResultTile label="Kurum içi ↔ GAIL" value={num(bCompare.deltas.institutional_vs_gail, 6)} unit="10⁻⁶/°C" />
              <ResultTile label="Otomatik ↔ kurum içi" value={num(bCompare.deltas.auto_vs_institutional, 6)} unit="10⁻⁶/°C" />
              <ResultTile label="Otomatik ↔ GAIL" value={num(bCompare.deltas.auto_vs_gail, 6)} unit="10⁻⁶/°C" />
            </div>
          </>
        ) : (
          <p className="text-[11.5px] leading-relaxed text-[var(--text-faint)]">
            Henüz karşılaştırma yapılmadı. “Karşılaştır” üç kaynağı aynı düğümde çözer ve farkları
            gösterir.
          </p>
        )}
      </SectionCard>

      <div className="grid gap-4 xl:grid-cols-2">
        <SectionCard
          title="Backend karşılaştırması"
          description="Kurulu su özelliği backend'leri için A, β, yoğunluk ve referansa göre fark."
          icon={Database}
          action={
            <div className="flex flex-wrap items-center gap-1.5">
              {results.backendCompare?.items.length ? (
                <>
                  <Button
                    size="sm"
                    variant="ghost"
                    icon={<Download size={12} />}
                    onClick={() => exportBackendComparison("txt")}
                  >
                    TXT
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    icon={<Download size={12} />}
                    onClick={() => exportBackendComparison("csv")}
                  >
                    CSV
                  </Button>
                </>
              ) : null}
              <Button
                size="lg"
                icon={<RefreshCw size={15} />}
                loading={backendCompare.isPending}
                onClick={runBackendCompare}
              >
                Çalıştır
              </Button>
            </div>
          }
        >
          {results.backendCompare ? (
            (() => {
              const items = results.backendCompare.items;
              const refItem = getRefItem(items);
              return (
                <div
                  role="region"
                  aria-labelledby={backendTableCaptionId}
                  className="table-wrap scroll-thin"
                >
                  <table className="data compact">
                    <caption id={backendTableCaptionId}>
                      T = {fmt.c(results.backendCompare.temperature_c)} · P ={" "}
                      {fmt.bar(results.backendCompare.pressure_bar)}
                      {refItem ? ` · Referans: ${refItem.backend.label}` : ""}
                    </caption>
                    <thead>
                      <tr>
                        <th scope="col">Backend</th>
                        <th scope="col" className="num">A</th>
                        <th scope="col" className="num">ΔA</th>
                        <th scope="col" className="num">β</th>
                        <th scope="col" className="num">Δβ</th>
                        <th scope="col" className="num">ρ (kg/m³)</th>
                        <th scope="col">Seçim</th>
                      </tr>
                    </thead>
                    <tbody>
                      {items.map((item) => {
                        const isSelected = item.backend.key === activeWaterBackend;
                        const deltaA =
                          refItem?.a_micro_per_bar != null && item.a_micro_per_bar != null
                            ? item.a_micro_per_bar - refItem.a_micro_per_bar
                            : null;
                        const deltaBeta =
                          refItem?.beta_micro_per_c != null && item.beta_micro_per_c != null
                            ? item.beta_micro_per_c - refItem.beta_micro_per_c
                            : null;
                        return (
                          <tr key={item.backend.key} className={cn(isSelected && "bg-[var(--primary-soft)]")}>
                            <th scope="row">
                              <div className="flex flex-wrap items-center gap-1.5 font-normal">
                                <span className="font-medium text-[var(--text)]">{item.backend.label}</span>
                                {isSelected ? <Badge tone="info">seçili</Badge> : null}
                                {!item.backend.distribution_ready ? (
                                  <Badge tone="warning">dağıtım dışı</Badge>
                                ) : null}
                              </div>
                            </th>
                            {item.error ? (
                              <td colSpan={6} className="text-[11px] font-medium tone-danger">
                                Hata: {item.error}
                              </td>
                            ) : (
                              <>
                                <td className="num">{num(item.a_micro_per_bar, 6)}</td>
                                <td className="num text-[var(--text-faint)]">
                                  {deltaA === null || deltaA === 0
                                    ? "—"
                                    : `${deltaA > 0 ? "+" : ""}${num(deltaA, 6)}`}
                                </td>
                                <td className="num">{num(item.beta_micro_per_c, 6)}</td>
                                <td className="num text-[var(--text-faint)]">
                                  {deltaBeta === null || deltaBeta === 0
                                    ? "—"
                                    : `${deltaBeta > 0 ? "+" : ""}${num(deltaBeta, 6)}`}
                                </td>
                                <td className="num">{num(item.density_kg_per_m3, 2)}</td>
                                <td>
                                  {isSelected ? (
                                    <Badge tone="pass">Aktif</Badge>
                                  ) : (
                                    <Button
                                      size="sm"
                                      variant="ghost"
                                      onClick={() => patchInputs({ water_backend: item.backend.key })}
                                    >
                                      Seç
                                    </Button>
                                  )}
                                </td>
                              </>
                            )}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              );
            })()
          ) : (
            <p className="text-[11.5px] leading-relaxed text-[var(--text-faint)]">
              Backend listesi meta uçtan gelir. Karşılaştırma, A ve β değerlerinin backend’e göre
              farkını gösterir ve TXT/CSV rapor olarak indirilebilir.
            </p>
          )}
        </SectionCard>

        <SectionCard
          title="A onarım bilgisi"
          description="Kurum içi tablodaki 7 °C / 81–100 bar anomalisi çalışma zamanında onarılır."
          icon={Wrench}
          action={
            <Button
              size="lg"
              icon={<Table2 size={15} />}
              loading={tablePoint.isPending}
              onClick={() => tablePoint.mutate({ table: "institutional", temperature_c: 7, pressure_bar: 90 })}
            >
              7 °C / 90 bar örneği
            </Button>
          }
        >
          <div className="grid gap-2 sm:grid-cols-2">
            <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-2.5">
              <p className="eyebrow">Kurum içi / BOTAŞ</p>
              <p className="mt-1 font-mono text-[11px] text-[var(--text-soft)]">
                {institutional
                  ? `${institutional.temperature.min}–${institutional.temperature.max} °C · ${institutional.pressure.min}–${institutional.pressure.max} bar`
                  : "—"}
              </p>
              <p className="mt-1 text-[10px] text-[var(--text-faint)]">
                {institutional?.source_note ?? "Kaynak bilgisi meta uçtan gelir."}
              </p>
            </div>
            <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-2.5">
              <p className="eyebrow">GAIL</p>
              <p className="mt-1 font-mono text-[11px] text-[var(--text-soft)]">
                {gail ? `${gail.temperature.min}–${gail.temperature.max} °C · ${gail.pressure.min}–${gail.pressure.max} bar` : "—"}
              </p>
              <p className="mt-1 text-[10px] text-[var(--text-faint)]">
                {gail?.source_note ?? "Kaynak bilgisi meta uçtan gelir."}
              </p>
            </div>
          </div>

          {results.tablePoint ? (
            <div className="mt-3 rounded-lg border border-[var(--warning-border)] bg-[var(--warning-bg)] px-3 py-2.5">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={results.tablePoint.repaired ? "warning" : "pass"}>
                  {results.tablePoint.repaired ? "Onarılmış A" : "Ham hücre"}
                </Badge>
                <span className="font-mono text-[11px] text-[var(--text-soft)]">
                  T={num(results.tablePoint.requested.temperature_c, 1)} °C · P={num(results.tablePoint.requested.pressure_bar, 1)} bar
                </span>
              </div>
              <div className="mt-2 grid grid-cols-2 gap-2">
                <ResultTile label="A" value={num(results.tablePoint.a_micro_per_bar, 6)} unit="10⁻⁶/bar" />
                <ResultTile label="B" value={num(results.tablePoint.b_micro_per_c, 6)} unit="10⁻⁶/°C" />
              </div>
              {results.tablePoint.repair_note ? (
                <p className="mt-2 text-[10.5px] leading-relaxed text-[var(--text-muted)]">
                  {results.tablePoint.repair_note}
                </p>
              ) : null}
            </div>
          ) : (
            <p className="mt-3 text-[11px] leading-relaxed text-[var(--text-faint)]">
              “7 °C / 90 bar örneği” düğmesi onarım davranışını ve kaynak notunu gösterir. Resmi
              karar için onarılmış A değerinin denetim izi kontrol edilmelidir.
            </p>
          )}
        </SectionCard>
      </div>

      <InlineNotice tone="info" title="Provenance" icon={Info}>
        HESAP = backend hesabı, TABLO = referans hücre, MANUEL = kullanıcı değeri, BAYAT = girdi
        değiştiği için yenilenmesi gereken katsayı. Mod değişince eski değer temizlenir; yeni modun
        değeri yeniden üretilmelidir.
      </InlineNotice>

      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] px-3.5 py-2.5">
        <p className="text-[10.5px] text-[var(--text-faint)]">
          Hazırlanan A ve B değerleri Hava İçerik ve Basınç Değişim sekmelerine anında yansır.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <Button size="lg" icon={<ArrowRight size={15} />} onClick={() => setTab("air")}>
            Hava testine git
          </Button>
          <Button size="lg" variant="primary" icon={<ArrowRight size={15} />} onClick={() => setTab("pressure")}>
            Basınç testine git
          </Button>
        </div>
      </div>
    </div>
  );
}
