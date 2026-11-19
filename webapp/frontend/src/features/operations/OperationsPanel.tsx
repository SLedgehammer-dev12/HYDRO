import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Droplets, ListChecks, Timer, TrendingUp } from "lucide-react";
import { SectionCard } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { CheckboxRow, FieldGrid, NumberField, SelectField, TextField } from "../../components/ui/Field";
import { DecisionCard } from "../../components/ui/DecisionCard";
import { InlineNotice, OfflineNotice } from "../../components/ui/State";
import { api, apiErrorMessage } from "../../lib/api";
import { num, parseNumber } from "../../lib/format";
import { useAppStore } from "../../store/useAppStore";
import type {
  DepressurizationRequest,
  DischargeRequest,
  OperationCheckResponse,
  PressureHoldResponse,
  PressurizationRampResponse,
} from "../../lib/types";

type OpTab = "ramp" | "hold" | "depressurize" | "discharge";

const TABS: Array<{ key: OpTab; label: string; icon: typeof Timer }> = [
  { key: "ramp", label: "Basınçlandırma (14.1–14.2)", icon: TrendingUp },
  { key: "hold", label: "2 saatlik bekleme (14.3)", icon: Timer },
  { key: "depressurize", label: "Basınç düşürme (16)", icon: ListChecks },
  { key: "discharge", label: "Boşaltma (17)", icon: Droplets },
];

type Tri = "" | "yes" | "no";
const TRI_OPTIONS = [
  { value: "", label: "Belirtilmedi" },
  { value: "yes", label: "Evet" },
  { value: "no", label: "Hayır" },
];
const toTri = (value: Tri): boolean | null => (value === "" ? null : value === "yes");

const DESTINATIONS = [
  { value: "", label: "Seçiniz" },
  { value: "other_section", label: "Başka test bölümüne aktarım" },
  { value: "watercourse", label: "Akar/durağan su mecrası" },
  { value: "public_land", label: "Devlet arazisi" },
  { value: "private_land", label: "Özel mülkiyet arazi" },
];

/** Satırlardan (sekme/noktalı virgül/boşluk ayrımlı) sayı demetleri okur. */
function parseRows(text: string, columns: number): { rows: number[][]; error: string | null } {
  const rows: number[][] = [];
  const lines = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  for (const [index, line] of lines.entries()) {
    const parts = line.split(/[\t;]+|\s{2,}|\s+(?=[-+\d])/).filter(Boolean);
    const values = parts.map((part) => parseNumber(part));
    if (values.length !== columns || values.some((value) => value === null || Number.isNaN(value))) {
      return { rows: [], error: `${index + 1}. satır ${columns} sayısal değer içermeli.` };
    }
    rows.push(values as number[]);
  }
  return { rows, error: null };
}

function Findings({ result }: { result: OperationCheckResponse }) {
  if (result.violations.length === 0 && result.missing.length === 0) return null;
  return (
    <div className="space-y-2">
      {result.violations.length > 0 ? (
        <InlineNotice tone="danger" title="İhlaller">
          <ul className="list-disc pl-4">
            {result.violations.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </InlineNotice>
      ) : null}
      {result.missing.length > 0 ? (
        <InlineNotice tone="warning" title="Eksik bilgiler">
          <ul className="list-disc pl-4">
            {result.missing.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </InlineNotice>
      ) : null}
    </div>
  );
}

function RampSection({ online }: { online: boolean }) {
  const volume = useAppStore((state) => state.results.geometry?.internal_volume_m3 ?? null);
  const [p100, setP100] = useState<number | null>(null);
  const [total, setTotal] = useState<number | null>(null);
  const [text, setText] = useState("");
  const mutation = useMutation<PressurizationRampResponse, Error, void>({
    mutationFn: async () => {
      const { rows, error } = parseRows(text, 3);
      if (error) throw new Error(error);
      const totalVolume = total ?? volume;
      if (p100 === null || totalVolume === null) {
        throw new Error("%100 SMYS test basıncı ve doldurulan toplam hacim gerekli.");
      }
      return api.pressurizationRamp({
        readings: rows.map(([t, p, v]) => ({
          elapsed_min: t,
          pressure_bar: p,
          cumulative_added_volume_m3: v,
        })),
        test_pressure_100_smys_bar: p100,
        total_filled_volume_m3: totalVolume,
      });
    },
  });
  const result = mutation.data;
  return (
    <div className="space-y-3">
      <FieldGrid cols={2}>
        <NumberField label="%100 SMYS test basıncı" unit="bar" value={p100} onChange={setP100} min={0} step={0.1} />
        <NumberField
          label="Doldurulan toplam su hacmi"
          unit="m³"
          value={total ?? volume}
          onChange={setTotal}
          min={0}
          help={volume !== null && total === null ? "Geometri hesabından alındı." : undefined}
        />
      </FieldGrid>
      <label className="block text-[11.5px] font-medium text-[var(--text-soft)]" htmlFor="ramp-readings">
        Okumalar (dakika · basınç bar · kümülatif basılan su m³; satır başına bir okuma, Excel’den yapıştırılabilir)
      </label>
      <textarea
        id="ramp-readings"
        className="input min-h-32 font-mono text-[11.5px]"
        value={text}
        onChange={(event) => setText(event.target.value)}
        placeholder={"0\t80\t0\n10\t90\t0,5\n20\t95\t0,8"}
      />
      <Button
        variant="primary"
        disabled={!online}
        loading={mutation.isPending}
        onClick={() => mutation.mutate()}
      >
        Değerlendir
      </Button>
      {mutation.isError ? <InlineNotice tone="danger">{apiErrorMessage(mutation.error)}</InlineNotice> : null}
      {result ? (
        <>
          <DecisionCard decision={result.decision} testName="Basınçlandırma izleme" compact />
          <p className="text-[11px] text-[var(--text-faint)]">
            Azami artış hızı {num(result.max_ramp_rate_bar_per_min, 3)} bar/dk · %95 SMYS sonrası basılan su{" "}
            {num(result.pumped_since_95_smys_m3, 4)} m³ (limit {num(result.excess_volume_limit_m3, 4)} m³)
          </p>
        </>
      ) : null}
    </div>
  );
}

function HoldSection({ online }: { online: boolean }) {
  const [target, setTarget] = useState<number | null>(null);
  const [text, setText] = useState("");
  const mutation = useMutation<PressureHoldResponse, Error, void>({
    mutationFn: async () => {
      const { rows, error } = parseRows(text, 3);
      if (error) throw new Error(error);
      if (target === null) throw new Error("Hedef (izlenen) basınç gerekli.");
      return api.pressureHold({
        readings: rows.map(([t, p, c]) => ({ elapsed_min: t, pressure_bar: p, temperature_c: c })),
        target_pressure_bar: target,
      });
    },
  });
  const result = mutation.data;
  return (
    <div className="space-y-3">
      <FieldGrid cols={2}>
        <NumberField label="Hedef (izlenen) basınç" unit="bar" value={target} onChange={setTarget} min={0} step={0.1} />
      </FieldGrid>
      <label className="block text-[11.5px] font-medium text-[var(--text-soft)]" htmlFor="hold-readings">
        Okumalar (dakika · basınç bar · sıcaklık °C; 15 dakikalık kayıt)
      </label>
      <textarea
        id="hold-readings"
        className="input min-h-32 font-mono text-[11.5px]"
        value={text}
        onChange={(event) => setText(event.target.value)}
        placeholder={"0\t100\t12,5\n15\t100\t12,4"}
      />
      <Button variant="primary" disabled={!online} loading={mutation.isPending} onClick={() => mutation.mutate()}>
        Değerlendir
      </Button>
      {mutation.isError ? <InlineNotice tone="danger">{apiErrorMessage(mutation.error)}</InlineNotice> : null}
      {result ? <DecisionCard decision={result.decision} testName="2 saatlik bekleme" compact /> : null}
    </div>
  );
}

function DepressurizeSection({ online }: { online: boolean }) {
  const [testPassed, setTestPassed] = useState<Tri>("");
  const [valve, setValve] = useState<number | null>(null);
  const [pipeChecked, setPipeChecked] = useState<Tri>("");
  const [envChecked, setEnvChecked] = useState<Tri>("");
  const mutation = useMutation<OperationCheckResponse, Error, DepressurizationRequest>({
    mutationFn: (body) => api.depressurization(body),
  });
  const result = mutation.data;
  return (
    <div className="space-y-3">
      <FieldGrid cols={2}>
        <SelectField label="Hidrostatik test başarıyla tamamlandı" value={testPassed} onChange={(v) => setTestPassed(v as Tri)} options={TRI_OPTIONS} />
        <NumberField label="Basınç düşürme vanası çapı" unit="inç" value={valve} onChange={setValve} min={0} step={0.5} help='En fazla 2".' />
        <SelectField label="Boru ve ekipman kontrolü yapıldı" value={pipeChecked} onChange={(v) => setPipeChecked(v as Tri)} options={TRI_OPTIONS} />
        <SelectField label="Çevresel etki önlemleri alındı" value={envChecked} onChange={(v) => setEnvChecked(v as Tri)} options={TRI_OPTIONS} />
      </FieldGrid>
      <Button
        variant="primary"
        disabled={!online}
        loading={mutation.isPending}
        onClick={() =>
          mutation.mutate({
            test_passed: toTri(testPassed),
            release_valve_diameter_in: valve,
            pipe_equipment_checked: toTri(pipeChecked),
            environmental_impact_checked: toTri(envChecked),
          })
        }
      >
        Değerlendir
      </Button>
      {mutation.isError ? <InlineNotice tone="danger">{apiErrorMessage(mutation.error)}</InlineNotice> : null}
      {result ? (
        <>
          <DecisionCard decision={result.decision} testName="Basınç düşürme" compact />
          <Findings result={result} />
        </>
      ) : null}
    </div>
  );
}

function DischargeSection({ online }: { online: boolean }) {
  const [destination, setDestination] = useState("");
  const [pig, setPig] = useState<Tri>("");
  const [hydraulic, setHydraulic] = useState<Tri>("");
  const [approvals, setApprovals] = useState<Tri>("");
  const [erosion, setErosion] = useState<Tri>("");
  const [treatmentRequested, setTreatmentRequested] = useState(false);
  const [treatmentDone, setTreatmentDone] = useState<Tri>("");
  const [analysisRequested, setAnalysisRequested] = useState(false);
  const [analysisDone, setAnalysisDone] = useState<Tri>("");
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");
  const [pigName, setPigName] = useState("");
  const [location, setLocation] = useState("");
  const [duration, setDuration] = useState<number | null>(null);
  const mutation = useMutation<OperationCheckResponse, Error, DischargeRequest>({
    mutationFn: (body) => api.discharge(body),
  });
  const result = mutation.data;
  return (
    <div className="space-y-3">
      <FieldGrid cols={2}>
        <SelectField label="Boşaltma yeri" value={destination} onChange={setDestination} options={DESTINATIONS} />
        <SelectField label="Boşaltma pigi kullanıldı (17)" value={pig} onChange={(v) => setPig(v as Tri)} options={TRI_OPTIONS} />
        <SelectField label="Hidrolik yük önlemleri alındı (17.1)" value={hydraulic} onChange={(v) => setHydraulic(v as Tri)} options={TRI_OPTIONS} />
        <SelectField label="Gerekli onaylar alındı (17.3)" value={approvals} onChange={(v) => setApprovals(v as Tri)} options={TRI_OPTIONS} help="Başka bölüme aktarımda gerekmez." />
        <SelectField label="Erozyon/silitasyon önlendi (17.5)" value={erosion} onChange={(v) => setErosion(v as Tri)} options={TRI_OPTIONS} help="Yalnızca su mecrası için." />
      </FieldGrid>
      <CheckboxRow checked={treatmentRequested} onChange={setTreatmentRequested} label="İdare su arıtma istedi (17.4)" />
      {treatmentRequested ? (
        <SelectField label="Arıtma tamamlandı" value={treatmentDone} onChange={(v) => setTreatmentDone(v as Tri)} options={TRI_OPTIONS} />
      ) : null}
      <CheckboxRow checked={analysisRequested} onChange={setAnalysisRequested} label="İdare numune analizi istedi (17.4)" />
      {analysisRequested ? (
        <SelectField label="Numune analizi yapıldı" value={analysisDone} onChange={(v) => setAnalysisDone(v as Tri)} options={TRI_OPTIONS} />
      ) : null}
      <p className="text-[11.5px] font-semibold text-[var(--text-soft)]">Boşaltma raporu (17.6)</p>
      <FieldGrid cols={2}>
        <TextField label="Tarih" value={date} onChange={setDate} placeholder="YYYY-AA-GG" />
        <TextField label="Saat" value={time} onChange={setTime} placeholder="SS:DD" />
        <TextField label="Kullanılan pig" value={pigName} onChange={setPigName} />
        <TextField label="Boşaltma yeri" value={location} onChange={setLocation} />
        <NumberField label="İşlem süresi" unit="dk" value={duration} onChange={setDuration} min={0} />
      </FieldGrid>
      <Button
        variant="primary"
        disabled={!online}
        loading={mutation.isPending}
        onClick={() =>
          mutation.mutate({
            destination: destination || null,
            used_discharge_pig: toTri(pig),
            hydraulic_load_measures_taken: toTri(hydraulic),
            approvals_obtained: toTri(approvals),
            treatment_requested: treatmentRequested,
            treatment_done: toTri(treatmentDone),
            sample_analysis_requested: analysisRequested,
            sample_analysis_done: toTri(analysisDone),
            erosion_prevented: toTri(erosion),
            report_date: date,
            report_time: time,
            pig_name: pigName,
            discharge_location: location,
            duration_min: duration,
          })
        }
      >
        Değerlendir
      </Button>
      {mutation.isError ? <InlineNotice tone="danger">{apiErrorMessage(mutation.error)}</InlineNotice> : null}
      {result ? (
        <>
          <DecisionCard decision={result.decision} testName="Boşaltma" compact />
          <Findings result={result} />
        </>
      ) : null}
    </div>
  );
}

/** Şartname 14–17 operasyon kontrolleri (sunucu karar metni gösterilir). */
export function OperationsPanel() {
  const backend = useAppStore((state) => state.backend);
  const online = backend === "online";
  const [tab, setTab] = useState<OpTab>("ramp");
  return (
    <SectionCard
      title="Basınçlandırma ve test sonrası operasyonlar"
      description="Şartname 14.1–14.3, 16 ve 17 kontrolleri. Karar metinleri sunucudan gelir."
      icon={ListChecks}
    >
      <div className="space-y-3">
        {!online ? (
          <OfflineNotice>Bu kontroller yalnızca sunucu bağlıyken değerlendirilir.</OfflineNotice>
        ) : null}
        <div role="tablist" aria-label="Operasyon kontrolleri" className="flex flex-wrap gap-1.5">
          {TABS.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={tab === key}
              className={tab === key ? "btn btn-primary" : "btn btn-ghost"}
              onClick={() => setTab(key)}
            >
              <Icon size={13} aria-hidden /> {label}
            </button>
          ))}
        </div>
        {tab === "ramp" ? <RampSection online={online} /> : null}
        {tab === "hold" ? <HoldSection online={online} /> : null}
        {tab === "depressurize" ? <DepressurizeSection online={online} /> : null}
        {tab === "discharge" ? <DischargeSection online={online} /> : null}
      </div>
    </SectionCard>
  );
}
