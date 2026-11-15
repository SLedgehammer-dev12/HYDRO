import { useState } from "react";
import {
  ArrowRight,
  FlaskConical,
  Info,
  Sigma,
  Sparkles,
  Table2,
  Wrench,
} from "lucide-react";
import { PageHeader } from "../components/layout/PageHeader";
import { SectionCard, ResultTile } from "../components/ui/Card";
import { Badge, CoefficientBadge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { NumberField, SelectField, FieldGrid, ReadonlyValue } from "../components/ui/Field";
import { InlineNotice } from "../components/ui/State";
import {
  useCoefficientA,
  useCoefficientB,
  useMeta,
  useReferenceTables,
  useTablePoint,
} from "../hooks/queries";
import { useAppStore } from "../store/useAppStore";
import { STEEL_MODEL_OPTIONS, STEEL_PRESETS } from "../lib/constants";
import { fmt, num } from "../lib/format";
import type { AMode, BSource } from "../lib/types";
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
  const tablePoint = useTablePoint();

  const [aTarget, setATarget] = useState<"air" | "pressure">("pressure");

  const context = aTarget === "air" ? inputs.air : inputs.pressure;
  const aMode = aTarget === "air" ? inputs.modes.air_a_mode : inputs.modes.pressure_a_mode;
  const aResult =
    aTarget === "air" ? results.coefficients?.airA : results.coefficients?.pressureA;
  const bResult = results.coefficients?.pressureB;
  const bCompare = results.bCompare;

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
    if (context.temperature_c === null || context.pressure_bar === null) {
      pushToast("error", "A hesaplanamadı", "Sıcaklık ve basınç girilmelidir.");
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
          onSuccess: ({ data, mode }) => {
            setAValue(data.a_micro_per_bar);
            pushToast(
              "success",
              "A tablodan okundu",
              `${fmt.a(data.a_micro_per_bar)}${data.repaired ? " · onarılmış hücre" : ""}${mode === "demo" ? " (demo)" : ""}`,
            );
          },
          onError: (error) => pushToast("error", "A okunamadı", error.message),
        },
      );
      return;
    }
    coefficientA.mutate(
      {
        temperature_c: context.temperature_c,
        pressure_bar: context.pressure_bar,
        backend:
          (aTarget === "air" ? inputs.modes.air_a_reference : inputs.modes.pressure_a_reference) ||
          meta?.water_backends[0]?.key ||
          "table_v1",
      },
      {
        onSuccess: ({ data, mode }) => {
          setAValue(data.a_micro_per_bar);
          pushToast(
            "success",
            "A katsayısı hesaplandı",
            `${fmt.a(data.a_micro_per_bar)} · ${data.backend.label}${mode === "demo" ? " (demo)" : ""}`,
          );
        },
        onError: (error) => pushToast("error", "A hesaplanamadı", error.message),
      },
    );
  }

  function computeB() {
    if (inputs.pressure.temperature_c === null || inputs.pressure.pressure_bar === null) {
      pushToast("error", "B hesaplanamadı", "Sıcaklık ve basınç girilmelidir.");
      return;
    }
    coefficientB.mutate(
      {
        source: inputs.modes.pressure_b_source,
        temperature_c: inputs.pressure.temperature_c,
        pressure_bar: inputs.pressure.pressure_bar,
        steel_alpha_micro_per_c: inputs.helper.steel_alpha_micro_per_c,
        steel_model: inputs.modes.steel_model,
      },
      {
        onSuccess: ({ data, mode }) => {
          patchInputs({ pressure: { b_micro_per_c: data.b_micro_per_c } });
          if (data.water_beta_micro_per_c !== null) {
            patchInputs({ helper: { water_beta_micro_per_c: data.water_beta_micro_per_c } });
          }
          pushToast(
            "success",
            "B katsayısı hazır",
            `${fmt.b(data.b_micro_per_c)} · ${data.label}${mode === "demo" ? " (demo)" : ""}`,
          );
        },
        onError: (error) => pushToast("error", "B hesaplanamadı", error.message),
      },
    );
  }

  const activeA = aMode === "manual" ? context.a_micro_per_bar : aResult?.a_micro_per_bar ?? context.a_micro_per_bar;

  return (
    <div className="space-y-5">
      <PageHeader
        kicker="Katsayılar"
        title="A/B hazırlama ve kaynak doğrulama"
        description="A su sıkıştırılabilirliği, B ise suyun hacimsel genleşmesi ile çeliğin genleşmesinin farkıdır. Kaynak ve provenance karar şeridinde izlenir."
        meta={
          <>
            <span className="flex items-center gap-1.5 text-[11px] text-[var(--text-muted)]">
              A <CoefficientBadge state={aResult?.state ?? (activeA ? "manual" : "empty")} />
            </span>
            <span className="flex items-center gap-1.5 text-[11px] text-[var(--text-muted)]">
              B <CoefficientBadge state={bResult ? "reference" : inputs.pressure.b_micro_per_c ? "manual" : "empty"} />
            </span>
            <span className="chip">{inputs.modes.steel_model}</span>
          </>
        }
        actions={
          <>
            <Button size="lg" icon={<Table2 size={15} />} onClick={() => setTab("coefficient_detail")}>
              Katsayı detayı
            </Button>
            <Button size="lg" variant="primary" icon={<ArrowRight size={15} />} onClick={() => setTab("air")}>
              Hava testine geç
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
                value={
                  (aTarget === "air" ? inputs.modes.air_a_reference : inputs.modes.pressure_a_reference) ||
                  meta?.water_backends[0]?.key ||
                  "table_v1"
                }
                onChange={(value) => {
                  if (aTarget === "air") patchInputs({ modes: { air_a_reference: value } });
                  else patchInputs({ modes: { pressure_a_reference: value } });
                }}
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
              {aMode === "manual" ? "Manuel modda hesap çalışmaz." : "Sunucu hesabı; backend yoksa demo motoru."}
            </span>
            <Button
              size="sm"
              variant="primary"
              icon={<Sigma size={12} />}
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
              tone={activeA ? (aMode === "manual" ? "info" : "pass") : undefined}
              hint={aResult?.backend.label ?? (aMode === "manual" ? "Manuel değer" : "Henüz hesaplanmadı")}
            />
            <ResultTile
              label="Backend"
              value={
                <span className="text-[13px]">{aResult?.backend.key ?? (aMode === "table" ? "referans tablo" : aMode === "manual" ? "manuel" : "—")}</span>
              }
              hint={
                aResult?.backend.label ??
                (aMode === "table" ? "Onarım bilgisi aşağıda" : "API coefficients/a")
              }
            />
          </div>
        </SectionCard>

        <SectionCard
          title="B — basınç değişim katsayısı"
          description="Varsayılan kurum içi tablodur. Otomatik modda β − 3α (hacimsel) kullanılır."
          icon={Sparkles}
          action={<CoefficientBadge state={bResult?.source === "auto" ? "computed" : bResult ? "reference" : inputs.pressure.b_micro_per_c ? "manual" : "empty"} />}
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

          <div className="mt-2">
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
          </div>

          <div className="mt-3 flex items-center justify-between gap-2">
            <span className="text-[10.5px] text-[var(--text-faint)]">
              {inputs.modes.pressure_b_source === "auto"
                ? "β otomatik hesaplanır; α çelik modeline göre düşülür."
                : "Tablo aralığı: kurum içi 1–25 °C / 30–120 bar."}
            </span>
            <Button
              size="sm"
              variant="primary"
              icon={<Sigma size={12} />}
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
              tone={inputs.pressure.b_micro_per_c ? "pass" : undefined}
              hint={bResult?.label ?? B_SOURCES.find((s) => s.value === inputs.modes.pressure_b_source)?.note}
            />
            <ResultTile
              label="Su β"
              value={num(inputs.helper.water_beta_micro_per_c, 6)}
              unit="10⁻⁶/°C"
              hint="Otomatik kaynakta dolar"
            />
          </div>

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
        title="Detaylı karşılaştırma ayrı sayfada"
        description="Üç kaynak, backend ve A onarım bilgisi Katsayı Detayı menüsüne taşındı."
        icon={Table2}
        action={
          <Button variant="primary" size="sm" icon={<ArrowRight size={12} />} onClick={() => setTab("coefficient_detail")}>
            Katsayı detayını aç
          </Button>
        }
      >
        <div className="grid gap-2 sm:grid-cols-3">
          <ResultTile label="Kurum içi" value={num(bCompare?.institutional.b_micro_per_c ?? inputs.pressure.b_micro_per_c, 6)} unit="10⁻⁶/°C" />
          <ResultTile label="GAIL" value={num(bCompare?.gail.b_micro_per_c, 6)} unit="10⁻⁶/°C" />
          <ResultTile label="Otomatik" value={num(bCompare?.auto.b_micro_per_c, 6)} unit="10⁻⁶/°C" />
        </div>
        <p className="mt-3 text-[11px] leading-relaxed text-[var(--text-faint)]">
          {bCompare
            ? "Karşılaştırma hazır. Farklar, backend tablosu ve A onarım örneği detay sayfasında."
            : "Detay sayfasında üç kaynağı aynı T/P düğümünde karşılaştırın; backend ve A onarım bilgisini inceleyin."}
        </p>
      </SectionCard>

      <InlineNotice tone="info" title="Provenance" icon={Info}>
        HESAP = backend hesabı, TABLO = referans hücre, MANUEL = kullanıcı değeri, BAYAT = girdi
        değiştiği için yenilenmesi gereken katsayı. Mod değişince eski değer temizlenir; yeni modun
        değeri yeniden üretilmelidir.
      </InlineNotice>
    </div>
  );
}
