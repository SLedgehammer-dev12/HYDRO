import { useEffect, useId, useMemo, useState } from "react";
import { ArrowUpDown, ClipboardPaste, Mountain, Plus, Sparkles, Trash2, Wrench } from "lucide-react";
import { SectionCard } from "../ui/Card";
import { Badge } from "../ui/Badge";
import { Button, IconButton } from "../ui/Button";
import { InlineNotice } from "../ui/State";
import { useAppStore } from "../../store/useAppStore";
import { formatInput, num, parseNumber } from "../../lib/format";
import { formatKp, parseKpMeters } from "../../lib/kp";
import { buildDefaultEquipmentInputs, resolveProfileCurve } from "../../lib/mock";
import type {
  EquipmentInputItem,
  ProfilePointItem,
  SceneEquipmentType,
  SceneStatus,
} from "../../lib/types";

const EQUIPMENT_TYPE_OPTIONS: ReadonlyArray<{ value: SceneEquipmentType; label: string }> = [
  { value: "valve", label: "Hat Vanası" },
  { value: "pump", label: "Pompa" },
  { value: "test-head", label: "Test Başlığı" },
  { value: "pig-launcher", label: "Pig Başlatıcı" },
  { value: "pig-receiver", label: "Pig Alıcı" },
  { value: "gauge", label: "Basınç Göstergesi" },
];

const EQUIPMENT_STATUS_OPTIONS: ReadonlyArray<{ value: SceneStatus; label: string }> = [
  { value: "pass", label: "Hazır" },
  { value: "pending", label: "Bekliyor" },
  { value: "warning", label: "Kontrol" },
  { value: "fail", label: "Hata" },
];

/** Count profile points with at least 0.5 m spacing along the line. */
export function countDistinctProfileStations(points: ReadonlyArray<ProfilePointItem>): number {
  const valid = points
    .filter((pt) => Number.isFinite(pt.station_m) && Number.isFinite(pt.elevation_m))
    .map((pt) => pt.station_m)
    .sort((a, b) => a - b);
  let distinct = 0;
  let last: number | null = null;
  for (const station of valid) {
    if (last === null || Math.abs(station - last) > 0.5) {
      distinct += 1;
      last = station;
    }
  }
  return distinct;
}

function parseLocalizedNumber(token: string): number | null {
  const cleaned = token.trim().replace(/\s+/g, "");
  if (!cleaned) return null;
  if (/^-?\d{1,3}(\.\d{3})+,\d+$/.test(cleaned)) {
    const parsed = Number(cleaned.replace(/\./g, "").replace(",", "."));
    return Number.isFinite(parsed) ? parsed : null;
  }
  if (/^-?\d+,\d+$/.test(cleaned)) {
    const parsed = Number(cleaned.replace(",", "."));
    return Number.isFinite(parsed) ? parsed : null;
  }
  const parsed = Number(cleaned.replace(/,/g, ""));
  return Number.isFinite(parsed) ? parsed : null;
}

function splitSurveyColumns(line: string): string[] {
  if (line.includes("\t")) return line.split("\t").map((c) => c.trim()).filter(Boolean);
  if (line.includes(";")) return line.split(";").map((c) => c.trim()).filter(Boolean);
  if (/,\s+/.test(line)) {
    const parts = line.split(/,\s+/).map((c) => c.trim()).filter(Boolean);
    if (parts.length >= 2) return parts;
  }
  if (line.includes(",")) {
    const commaParts = line.split(",").map((c) => c.trim());
    if (commaParts.length === 2 && (/\s/.test(line) || commaParts[1].includes("."))) {
      return commaParts.filter(Boolean);
    }
  }
  return line.trim().split(/\s+/).filter(Boolean);
}

/**
 * Parse CSV/TSV/whitespace lines containing `(station_m, elevation_m)` or `(KP a+bbb, elevation_m)`.
 */
export function parseSurveyPointsText(
  raw: string,
  startKpM: number | null,
): { points: ProfilePointItem[]; invalidLines: number } {
  const points: ProfilePointItem[] = [];
  let invalidLines = 0;

  for (const rawLine of raw.split(/\r?\n/)) {
    const trimmed = rawLine.trim();
    if (!trimmed) continue;

    const cols = splitSurveyColumns(trimmed);
    if (cols.length < 2) {
      invalidLines += 1;
      continue;
    }

    const firstToken = cols[0].replace(/^kp\s*/i, "").trim();
    const secondToken = cols[1].replace(/\s*m$/i, "").trim();

    let station: number | null = null;
    if (firstToken.includes("+")) {
      const absKp = parseKpMeters(firstToken);
      if (absKp !== null) {
        station = startKpM !== null ? Math.max(0, absKp - startKpM) : absKp;
      }
    } else {
      station = parseLocalizedNumber(firstToken);
    }

    const elevation = parseLocalizedNumber(secondToken);
    if (
      station === null ||
      elevation === null ||
      !Number.isFinite(station) ||
      !Number.isFinite(elevation)
    ) {
      // Skip likely header row ("İstasyon", "Kot") without inflating error count if it has letters only
      const isHeader = /[a-zA-ZğüşöçıİĞÜŞÖÇ]/.test(firstToken) && points.length === 0;
      if (!isHeader) invalidLines += 1;
      continue;
    }

    if (station < 0 || station > 1_000_000 || elevation < -500 || elevation > 10_000) {
      invalidLines += 1;
      continue;
    }

    points.push({
      station_m: Math.round(station * 100) / 100,
      elevation_m: Math.round(elevation * 100) / 100,
    });
  }

  return {
    points: points.sort((a, b) => a.station_m - b.station_m),
    invalidLines,
  };
}

function interpolateCurveY(points: ReadonlyArray<{ x: number; y: number }>, station: number): number | null {
  if (points.length === 0) return null;
  if (station <= points[0].x) return points[0].y;
  for (let i = 1; i < points.length; i += 1) {
    const left = points[i - 1];
    const right = points[i];
    if (station <= right.x) {
      const span = right.x - left.x;
      return span <= 0 ? right.y : left.y + ((right.y - left.y) * (station - left.x)) / span;
    }
  }
  return points[points.length - 1].y;
}

function ValidatedNumberInput({
  value,
  label,
  min,
  max,
  placeholder,
  errorText,
  required = true,
  onCommit,
}: {
  value: number | null;
  label: string;
  min: number;
  max: number;
  placeholder?: string;
  errorText: string;
  required?: boolean;
  onCommit: (next: number | null) => void;
}) {
  const errId = useId();
  const [text, setText] = useState(() => formatInput(value));
  const [interacted, setInteracted] = useState(false);

  useEffect(() => {
    setText(formatInput(value));
    setInteracted(false);
  }, [value]);

  const validateText = (candidate: string): { valid: boolean; parsed: number | null } => {
    const trimmed = candidate.trim();
    if (!trimmed) {
      return { valid: !required, parsed: null };
    }
    const parsed = parseNumber(trimmed);
    if (parsed === null || !Number.isFinite(parsed) || parsed < min || parsed > max) {
      return { valid: false, parsed: null };
    }
    return { valid: true, parsed };
  };

  const check = validateText(text);
  const showError = interacted && !check.valid;

  const commit = () => {
    setInteracted(true);
    const res = validateText(text);
    if (res.valid) {
      onCommit(res.parsed);
    }
  };

  return (
    <div>
      <input
        className="table-input"
        inputMode="decimal"
        aria-label={label}
        aria-invalid={showError ? "true" : "false"}
        aria-describedby={showError ? errId : undefined}
        placeholder={placeholder}
        value={text}
        onChange={(event) => {
          setText(event.target.value);
          if (interacted) {
            const live = validateText(event.target.value);
            if (live.valid) onCommit(live.parsed);
          }
        }}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            commit();
            (event.target as HTMLInputElement).blur();
          }
        }}
      />
      {showError ? (
        <div id={errId} className="survey-field-error">
          <span role="img" aria-label="Hata">!</span> {errorText}
        </div>
      ) : null}
    </div>
  );
}

function ValidatedLabelInput({
  value,
  label,
  errorText,
  onCommit,
}: {
  value: string;
  label: string;
  errorText: string;
  onCommit: (next: string) => void;
}) {
  const errId = useId();
  const [text, setText] = useState(value);
  const [interacted, setInteracted] = useState(false);

  useEffect(() => {
    setText(value);
    setInteracted(false);
  }, [value]);

  const invalid = interacted && text.trim().length === 0;

  return (
    <div>
      <input
        className="table-input text-left font-sans"
        aria-label={label}
        required
        aria-invalid={invalid ? "true" : "false"}
        aria-describedby={invalid ? errId : undefined}
        value={text}
        onChange={(event) => {
          setText(event.target.value);
          if (event.target.value.trim().length > 0) {
            onCommit(event.target.value);
          }
        }}
        onBlur={() => {
          setInteracted(true);
          if (text.trim().length > 0) {
            onCommit(text.trim());
          }
        }}
      />
      {invalid ? (
        <div id={errId} className="survey-field-error">
          <span role="img" aria-label="Hata">!</span> {errorText}
        </div>
      ) : null}
    </div>
  );
}

export function SiteSurveyPanel({ totalLength }: { totalLength: number }) {
  const inputs = useAppStore((state) => state.inputs);
  const setProfilePoints = useAppStore((state) => state.setProfilePoints);
  const setEquipment = useAppStore((state) => state.setEquipment);
  const patchInputs = useAppStore((state) => state.patchInputs);

  const [pasteOpen, setPasteOpen] = useState(false);
  const [pasteText, setPasteText] = useState("");
  const [pasteFeedback, setPasteFeedback] = useState<string | null>(null);

  const profileCaptionId = useId();
  const equipmentCaptionId = useId();

  const maxStation = totalLength > 0 ? Math.max(totalLength, 1_000_000) : 1_000_000;
  const stationLimit = totalLength > 0 ? totalLength : 1_000_000;
  const startKpM = useMemo(() => parseKpMeters(inputs.section_meta.start_kp), [inputs.section_meta.start_kp]);

  const points = useMemo(() => inputs.profile_points ?? [], [inputs.profile_points]);
  const equipment = useMemo(() => inputs.equipment ?? [], [inputs.equipment]);
  const distinctCount = useMemo(() => countDistinctProfileStations(points), [points]);
  const hasRealProfile = distinctCount >= 2;
  const hasCustomEquipment = equipment.some(
    (item) => Number.isFinite(item.station_m) && item.label.trim().length > 0,
  );

  const profileCurve = useMemo(
    () => resolveProfileCurve(inputs, totalLength > 0 ? totalLength : 1_000).points,
    [inputs, totalLength],
  );

  const seedProfileFromFourPoints = () => {
    const sp = inputs.section_profile;
    const len = totalLength > 0 ? totalLength : 1_000;
    const startEl = sp.start_elevation_m ?? sp.lowest_elevation_m ?? 0;
    const endEl = sp.end_elevation_m ?? sp.highest_elevation_m ?? startEl;
    const highest = sp.highest_elevation_m ?? Math.max(startEl, endEl);
    const lowest = sp.lowest_elevation_m ?? Math.min(startEl, endEl);
    setProfilePoints([
      { station_m: 0, elevation_m: Math.round(startEl * 100) / 100 },
      { station_m: Math.round(len * 0.33 * 100) / 100, elevation_m: Math.round(highest * 100) / 100 },
      { station_m: Math.round(len * 0.68 * 100) / 100, elevation_m: Math.round(lowest * 100) / 100 },
      { station_m: Math.round(len * 100) / 100, elevation_m: Math.round(endEl * 100) / 100 },
    ]);
    setPasteFeedback(null);
  };

  const addProfilePoint = () => {
    const last = points[points.length - 1];
    const step = totalLength > 0 ? Math.max(100, Math.round(totalLength / 10)) : 500;
    const nextStation = last
      ? Math.min(stationLimit, Math.round((last.station_m + step) * 100) / 100)
      : 0;
    const nextElev = last
      ? last.elevation_m
      : (inputs.section_profile.start_elevation_m ?? 0);
    setProfilePoints([...points, { station_m: nextStation, elevation_m: nextElev }]);
  };

  const summarizeElevations = () => {
    if (points.length < 2) return;
    const sorted = [...points].sort((a, b) => a.station_m - b.station_m);
    const elevations = sorted.map((p) => p.elevation_m);
    patchInputs({
      section_profile: {
        start_elevation_m: sorted[0].elevation_m,
        end_elevation_m: sorted[sorted.length - 1].elevation_m,
        highest_elevation_m: Math.max(...elevations),
        lowest_elevation_m: Math.min(...elevations),
      },
    });
  };

  const applyPaste = () => {
    const parsed = parseSurveyPointsText(pasteText, startKpM);
    if (parsed.points.length === 0) {
      setPasteFeedback("Geçerli kot noktası bulunamadı. Örnek: 0, 420.5 veya KP 1+500 485.2");
      return;
    }
    setProfilePoints(parsed.points);
    setPasteOpen(false);
    setPasteText("");
    setPasteFeedback(
      parsed.invalidLines > 0
        ? `${parsed.points.length} nokta yüklendi; ${parsed.invalidLines} satır atlandı.`
        : `${parsed.points.length} kot noktası yüklendi.`,
    );
  };

  const addEquipment = () => {
    const idx = equipment.length + 1;
    const defaultStation = totalLength > 0 ? Math.round((totalLength / 2) * 10) / 10 : 0;
    setEquipment([
      ...equipment,
      {
        id: `eq-custom-${Date.now().toString(36)}-${idx}`,
        type: "valve",
        label: `Saha Ekipmanı ${idx}`,
        station_m: defaultStation,
        elevation_m: null,
        status: "pass",
      },
    ]);
  };

  const updateEquipmentRow = (index: number, patch: Partial<EquipmentInputItem>) => {
    setEquipment(equipment.map((item, i) => (i === index ? { ...item, ...patch } : item)));
  };

  return (
    <div id="site-survey-panel" className="grid gap-4 xl:grid-cols-2">
      <SectionCard
        title="Gerçek Kot Profili (profile_points[])"
        description="Topoğrafik etüt / plan-profil koordinatları girildiğinde 3D sahne gerçek güzergahı çizer."
        icon={Mountain}
        action={
          hasRealProfile ? (
            <Badge tone="pass">Gerçek Profil ({points.length} nokta)</Badge>
          ) : (
            <Badge tone="warning">Yaklaşık Profil (4 nokta)</Badge>
          )
        }
      >
        {!hasRealProfile ? (
          <div className="mb-3">
            <InlineNotice tone="warning" title="Yaklaşık kot profili kullanılıyor">
              En az 2 farklı istasyona ait kot noktası girilmediği için 3D ve 2D görünüm başlangıç,
              zirve, çukur ve bitiş değerlerinden yaklaşık çizilir. Plan-Profil taraması veya CSV/TSV
              yapıştırma ile gerçek kotları yükleyebilirsiniz.
            </InlineNotice>
          </div>
        ) : null}

        <div className="mb-2.5 flex flex-wrap items-center gap-1.5">
          <Button size="sm" icon={<Plus size={13} />} onClick={addProfilePoint}>
            Nokta Ekle
          </Button>
          <Button size="sm" variant="ghost" icon={<Sparkles size={13} />} onClick={seedProfileFromFourPoints}>
            4 Kottan Başlat
          </Button>
          <Button
            size="sm"
            variant="ghost"
            icon={<ClipboardPaste size={13} />}
            onClick={() => setPasteOpen((open) => !open)}
          >
            CSV / TSV Yapıştır
          </Button>
          {points.length >= 2 ? (
            <>
              <Button size="sm" variant="ghost" onClick={summarizeElevations}>
                Kotları Özetle
              </Button>
              <Button
                size="sm"
                variant="ghost"
                icon={<ArrowUpDown size={13} />}
                onClick={() => setProfilePoints([...points].sort((a, b) => a.station_m - b.station_m))}
              >
                Sırala
              </Button>
            </>
          ) : null}
          {points.length > 0 ? (
            <Button
              size="sm"
              variant="danger"
              icon={<Trash2 size={13} />}
              onClick={() => {
                setProfilePoints([]);
                setPasteFeedback(null);
              }}
            >
              Temizle
            </Button>
          ) : null}
        </div>

        {pasteFeedback ? (
          <p className="mb-2 text-[11px] text-[var(--text-muted)]" role="status">
            {pasteFeedback}
          </p>
        ) : null}

        {pasteOpen ? (
          <div className="mb-3 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-3">
            <label
              htmlFor="survey-csv-paste"
              className="block text-[11px] font-medium text-[var(--text)]"
            >
              İstasyon (m veya KP) ve Kot (m) satırlarını yapıştırın
            </label>
            <textarea
              id="survey-csv-paste"
              rows={4}
              value={pasteText}
              onChange={(event) => setPasteText(event.target.value)}
              placeholder={"0\t420.5\n1500\t485.2\n3200\t455.0"}
              className="mt-1.5 w-full rounded-lg border border-[var(--border)] bg-[var(--surface)] px-2.5 py-2 font-mono text-xs text-[var(--text)] focus:border-[var(--primary)] focus:outline-none"
            />
            <div className="mt-2 flex items-center justify-end gap-2">
              <Button size="sm" variant="ghost" onClick={() => setPasteOpen(false)}>
                Vazgeç
              </Button>
              <Button size="sm" variant="primary" onClick={applyPaste}>
                Uygula
              </Button>
            </div>
          </div>
        ) : null}

        {points.length === 0 ? (
          <p className="rounded-xl border border-dashed border-[var(--border)] px-3 py-4 text-center text-xs text-[var(--text-muted)]">
            Henüz kot noktası yok. &ldquo;Nokta Ekle&rdquo;, &ldquo;4 Kottan Başlat&rdquo; veya
            &ldquo;CSV / TSV Yapıştır&rdquo; ile ekleyebilirsiniz.
          </p>
        ) : (
          <div
            role="region"
            aria-labelledby={profileCaptionId}
            className="table-wrap table-sticky scroll-thin max-h-[280px] overflow-y-auto"
          >
            <table className="data compact survey-table">
              <caption id={profileCaptionId} className="sr-only">
                Gerçek hat kot profili noktaları; istasyon ve yükseklik değerleri
              </caption>
              <thead>
                <tr>
                  <th scope="col" className="sticky-col">#</th>
                  <th scope="col" className="num">İstasyon (m)</th>
                  <th scope="col" className="num">Kot (m)</th>
                  <th scope="col" className="num">KP</th>
                  <th scope="col"><span className="sr-only">Sil</span></th>
                </tr>
              </thead>
              <tbody>
                {points.map((pt, index) => (
                  <tr key={`pp-${index}`}>
                    <th scope="row" className="sticky-col font-mono text-[11px] text-[var(--text-faint)]">
                      {index + 1}
                    </th>
                    <td data-label="İstasyon (m)">
                      <ValidatedNumberInput
                        label={`Kot noktası ${index + 1} istasyon`}
                        value={pt.station_m}
                        min={0}
                        max={totalLength > 0 ? totalLength : maxStation}
                        errorText={
                          totalLength > 0
                            ? `0 ile ${num(totalLength, 0)} m arasında olmalıdır.`
                            : "0 veya pozitif istasyon girin."
                        }
                        onCommit={(val) => {
                          if (val === null) return;
                          setProfilePoints(
                            points.map((row, i) => (i === index ? { ...row, station_m: val } : row)),
                          );
                        }}
                      />
                    </td>
                    <td data-label="Kot (m)">
                      <ValidatedNumberInput
                        label={`Kot noktası ${index + 1} kot`}
                        value={pt.elevation_m}
                        min={-500}
                        max={10_000}
                        errorText="-500 ile 10.000 m arasında geçerli kot girin."
                        onCommit={(val) => {
                          if (val === null) return;
                          setProfilePoints(
                            points.map((row, i) => (i === index ? { ...row, elevation_m: val } : row)),
                          );
                        }}
                      />
                    </td>
                    <td data-label="KP" className="num font-mono text-[11px] text-[var(--text-faint)]">
                      {startKpM !== null ? formatKp(startKpM + pt.station_m) : "—"}
                    </td>
                    <td className="text-right">
                      <IconButton
                        label={`Kot noktası ${index + 1} sil`}
                        onClick={() => setProfilePoints(points.filter((_, i) => i !== index))}
                      >
                        <Trash2 size={13} />
                      </IconButton>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      <SectionCard
        title="Saha Ekipmanları (equipment[])"
        description="Vana, pompa, test başlığı, pig ve basınç ölçer konumları 3D sahneye yerleştirilir."
        icon={Wrench}
        action={
          hasCustomEquipment ? (
            <Badge tone="pass">Gerçek Ekipman ({equipment.length})</Badge>
          ) : (
            <Badge tone="warning">Varsayılan Yerleşim</Badge>
          )
        }
      >
        {!hasCustomEquipment ? (
          <div className="mb-3">
            <InlineNotice tone="warning" title="Varsayılan ekipman yerleşimi gösteriliyor">
              Özel saha ekipmanı tanımlanmadığı için 3D sahnede hat başı/sonu vanaları, pompa ve pig
              başlatıcı otomatik konumlandırılır. Gerçek saha konumları için liste oluşturabilirsiniz.
            </InlineNotice>
          </div>
        ) : null}

        <div className="mb-2.5 flex flex-wrap items-center gap-1.5">
          <Button size="sm" icon={<Plus size={13} />} onClick={addEquipment}>
            Ekipman Ekle
          </Button>
          <Button
            size="sm"
            variant="ghost"
            icon={<Sparkles size={13} />}
            onClick={() => setEquipment(buildDefaultEquipmentInputs(inputs))}
          >
            Varsayılanlardan Başlat
          </Button>
          {equipment.length > 0 ? (
            <Button
              size="sm"
              variant="danger"
              icon={<Trash2 size={13} />}
              onClick={() => setEquipment([])}
            >
              Temizle
            </Button>
          ) : null}
        </div>

        {equipment.length === 0 ? (
          <p className="rounded-xl border border-dashed border-[var(--border)] px-3 py-4 text-center text-xs text-[var(--text-muted)]">
            Özel saha ekipmanı yok. &ldquo;Ekipman Ekle&rdquo; veya
            &ldquo;Varsayılanlardan Başlat&rdquo; ile saha yerleşimi tanımlayabilirsiniz.
          </p>
        ) : (
          <div
            role="region"
            aria-labelledby={equipmentCaptionId}
            className="table-wrap table-sticky scroll-thin max-h-[280px] overflow-y-auto"
          >
            <table className="data compact survey-table">
              <caption id={equipmentCaptionId} className="sr-only">
                Saha ekipmanları; tip, etiket, istasyon, kot ve durum
              </caption>
              <thead>
                <tr>
                  <th scope="col" className="sticky-col">#</th>
                  <th scope="col">Tip</th>
                  <th scope="col">Etiket</th>
                  <th scope="col" className="num">İstasyon (m)</th>
                  <th scope="col" className="num">Kot (m)</th>
                  <th scope="col">Durum</th>
                  <th scope="col"><span className="sr-only">Sil</span></th>
                </tr>
              </thead>
              <tbody>
                {equipment.map((item, index) => {
                  const autoElev = interpolateCurveY(profileCurve, item.station_m);
                  return (
                    <tr key={item.id || `eq-row-${index}`}>
                      <th scope="row" className="sticky-col font-mono text-[11px] text-[var(--text-faint)]">
                        {index + 1}
                      </th>
                      <td data-label="Tip">
                        <select
                          aria-label={`Ekipman ${index + 1} tipi`}
                          value={item.type}
                          onChange={(event) =>
                            updateEquipmentRow(index, {
                              type: event.target.value as SceneEquipmentType,
                            })
                          }
                          className="table-input text-left font-sans"
                        >
                          {EQUIPMENT_TYPE_OPTIONS.map((opt) => (
                            <option key={opt.value} value={opt.value}>
                              {opt.label}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td data-label="Etiket" className="min-w-[130px]">
                        <ValidatedLabelInput
                          label={`Ekipman ${index + 1} etiketi`}
                          value={item.label}
                          errorText="Ekipman etiketi boş bırakılamaz."
                          onCommit={(val) => updateEquipmentRow(index, { label: val })}
                        />
                      </td>
                      <td data-label="İstasyon (m)">
                        <ValidatedNumberInput
                          label={`Ekipman ${index + 1} istasyon`}
                          value={item.station_m}
                          min={0}
                          max={totalLength > 0 ? totalLength : maxStation}
                          errorText={
                            totalLength > 0
                              ? `0 ile ${num(totalLength, 0)} m arasında olmalıdır.`
                              : "0 veya pozitif istasyon girin."
                          }
                          onCommit={(val) => {
                            if (val !== null) updateEquipmentRow(index, { station_m: val });
                          }}
                        />
                      </td>
                      <td data-label="Kot (m)">
                        <ValidatedNumberInput
                          label={`Ekipman ${index + 1} kot`}
                          value={item.elevation_m}
                          min={-500}
                          max={10_000}
                          required={false}
                          placeholder={autoElev !== null ? `Oto (~${num(autoElev, 1)})` : "Oto"}
                          errorText="-500 ile 10.000 m arasında kot girin veya boş bırakın."
                          onCommit={(val) => updateEquipmentRow(index, { elevation_m: val })}
                        />
                      </td>
                      <td data-label="Durum">
                        <select
                          aria-label={`Ekipman ${index + 1} durumu`}
                          value={item.status ?? "pass"}
                          onChange={(event) =>
                            updateEquipmentRow(index, {
                              status: event.target.value as SceneStatus,
                            })
                          }
                          className="table-input text-left font-sans"
                        >
                          {EQUIPMENT_STATUS_OPTIONS.map((opt) => (
                            <option key={opt.value} value={opt.value}>
                              {opt.label}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="text-right">
                        <IconButton
                          label={`Ekipman ${index + 1} sil`}
                          onClick={() => setEquipment(equipment.filter((_, i) => i !== index))}
                        >
                          <Trash2 size={13} />
                        </IconButton>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>
    </div>
  );
}
