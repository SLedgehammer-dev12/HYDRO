import { Plus, Trash2 } from "lucide-react";
import { num } from "../../lib/format";
import type { BotasFormCode } from "../../lib/types";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";

type DraftData = Record<string, unknown>;

function toRecord(val: unknown): Record<string, unknown> {
  return val && typeof val === "object" && !Array.isArray(val) ? (val as Record<string, unknown>) : {};
}

function toList(val: unknown): Array<Record<string, unknown>> {
  return Array.isArray(val) ? (val.filter((item) => item && typeof item === "object") as Array<Record<string, unknown>>) : [];
}

function numVal(obj: Record<string, unknown>, key: string): string {
  const v = obj[key];
  if (v === null || v === undefined || v === "") return "";
  return String(v);
}

function parseCellNum(raw: string): number | null {
  const trimmed = raw.trim().replace(",", ".");
  if (!trimmed) return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

function strVal(obj: Record<string, unknown>, key: string): string {
  const v = obj[key];
  return v === null || v === undefined ? "" : String(v);
}

function CellInput({
  value,
  onChange,
  placeholder = "—",
  type = "text",
  align = "right",
  ariaLabel,
  className = "",
}: {
  value: string;
  onChange: (next: string) => void;
  placeholder?: string;
  type?: "text" | "number";
  align?: "left" | "right";
  ariaLabel: string;
  className?: string;
}) {
  return (
    <input
      type={type === "number" ? "text" : type}
      inputMode={type === "number" ? "decimal" : undefined}
      value={value}
      placeholder={placeholder}
      aria-label={ariaLabel}
      onChange={(e) => onChange(e.target.value)}
      className={`h-7 rounded border border-[var(--border)] bg-[var(--canvas)] px-2 font-mono text-[11px] text-[var(--text)] focus:border-[var(--primary)] focus:outline-none ${
        align === "right" ? "text-right" : "text-left"
      } ${className}`}
    />
  );
}

export function FormBodyEditor({
  formCode,
  draft,
  onChange,
  calculations,
  mergedHeader,
}: {
  formCode: BotasFormCode;
  draft: DraftData;
  onChange: (next: DraftData) => void;
  calculations: Record<string, Record<string, unknown>>;
  mergedHeader: Record<string, unknown>;
}) {
  function setNestedKey(sectionKey: string, fieldKey: string, value: unknown) {
    const cur = toRecord(draft[sectionKey]);
    onChange({
      ...draft,
      [sectionKey]: {
        ...cur,
        [fieldKey]: value,
      },
    });
  }

  function updateRow(
    listKey: string,
    index: number,
    patch: Record<string, unknown>,
    nestedParent?: string,
  ) {
    if (nestedParent) {
      const parent = toRecord(draft[nestedParent]);
      const rows = toList(parent[listKey]);
      const nextRows = rows.map((r, i) => (i === index ? { ...r, ...patch } : r));
      onChange({ ...draft, [nestedParent]: { ...parent, [listKey]: nextRows } });
      return;
    }
    const rows = toList(draft[listKey]);
    const nextRows = rows.map((r, i) => (i === index ? { ...r, ...patch } : r));
    onChange({ ...draft, [listKey]: nextRows });
  }

  function addRow(listKey: string, template: Record<string, unknown>, nestedParent?: string) {
    if (nestedParent) {
      const parent = toRecord(draft[nestedParent]);
      const rows = toList(parent[listKey]);
      onChange({ ...draft, [nestedParent]: { ...parent, [listKey]: [...rows, template] } });
      return;
    }
    const rows = toList(draft[listKey]);
    onChange({ ...draft, [listKey]: [...rows, template] });
  }

  function removeRow(listKey: string, index: number, nestedParent?: string) {
    if (nestedParent) {
      const parent = toRecord(draft[nestedParent]);
      const rows = toList(parent[listKey]).filter((_, i) => i !== index);
      onChange({ ...draft, [nestedParent]: { ...parent, [listKey]: rows } });
      return;
    }
    const rows = toList(draft[listKey]).filter((_, i) => i !== index);
    onChange({ ...draft, [listKey]: rows });
  }

  /* ---------------------------------------------------------------- */
  /* 015 — HİDROSTATİK TEST VERİLERİ                                   */
  /* ---------------------------------------------------------------- */
  if (formCode === "test_data") {
    const hdr = toRecord(draft.header);
    const td = toRecord(draft.test_data);
    const segs = toList(td.volume_segments);
    const meas = toList(td.test_measurements);
    const profCalc = calculations.profile ?? {};

    return (
      <div className="space-y-4">
        <div className="border-t border-[var(--border)] pt-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-[11px] font-bold uppercase tracking-wider text-[var(--primary)]">
              1. Test Bölümü Hacmi &amp; Segmentleri
            </span>
            <Button
              size="sm"
              variant="ghost"
              icon={<Plus size={12} />}
              onClick={() => addRow("volume_segments", { wall_thickness_mm: null, length_m: null, volume_m3: null }, "test_data")}
            >
              Segment Ekle
            </Button>
          </div>
          <div className="table-wrap scroll-thin">
            <table className="data">
              <thead>
                <tr>
                  <th>Boru Et Kalınlığı (mm)</th>
                  <th className="num">Uzunluk (m)</th>
                  <th className="num">Hacim (m³)</th>
                  <th className="num">İşlem</th>
                </tr>
              </thead>
              <tbody>
                {segs.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="py-3 text-center text-[11px] text-[var(--text-faint)]">
                      Segment hacim satırı yok; yukarıdan ekleyebilirsiniz.
                    </td>
                  </tr>
                ) : (
                  segs.map((row, idx) => (
                    <tr key={idx}>
                      <td>
                        <CellInput
                          value={numVal(row, "wall_thickness_mm")}
                          onChange={(v) => updateRow("volume_segments", idx, { wall_thickness_mm: parseCellNum(v) }, "test_data")}
                          ariaLabel={`Segment ${idx + 1} et kalınlığı`}
                          className="w-24"
                          type="number"
                        />
                      </td>
                      <td className="num">
                        <CellInput
                          value={numVal(row, "length_m")}
                          onChange={(v) => updateRow("volume_segments", idx, { length_m: parseCellNum(v) }, "test_data")}
                          ariaLabel={`Segment ${idx + 1} uzunluk`}
                          className="w-28"
                          type="number"
                        />
                      </td>
                      <td className="num">
                        <CellInput
                          value={numVal(row, "volume_m3")}
                          onChange={(v) => updateRow("volume_segments", idx, { volume_m3: parseCellNum(v) }, "test_data")}
                          ariaLabel={`Segment ${idx + 1} hacim`}
                          className="w-28"
                          type="number"
                        />
                      </td>
                      <td className="num">
                        <button
                          type="button"
                          onClick={() => removeRow("volume_segments", idx, "test_data")}
                          className="rounded p-1 text-[var(--text-faint)] hover:bg-[var(--danger-bg)] hover:text-[var(--danger)]"
                          aria-label={`Segment ${idx + 1} sil`}
                        >
                          <Trash2 size={12} />
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="border-t border-[var(--border)] pt-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-[11px] font-bold uppercase tracking-wider text-[var(--primary)]">
              2. Test Bölümü Parametreleri
            </span>
            {profCalc.summary ? <Badge tone={profCalc.passed ? "pass" : "fail"}>{profCalc.passed ? "Basınç Penceresi Uygun" : "Kontrol Gerekli"}</Badge> : null}
          </div>
          <div className="grid gap-2 sm:grid-cols-3">
            {[
              ["design_pressure_bar", "Maks. İşletme Basıncı (Bar)"],
              ["smys_mpa", "Boru Akma Dayanımı SMYS (MPa)"],
              ["test_pressure_bar", "Maks. Test Basıncı (Bar)"],
              ["lowest_elevation_m", "En Düşük Kot (m)"],
              ["highest_elevation_m", "En Yüksek Kot (m)"],
              ["start_elevation_m", "Başlangıç Kotu (m)"],
              ["end_elevation_m", "Bitiş Kotu (m)"],
              ["monitored_pressure_bar", "Test İzleme Basıncı Ps (Bar)"],
            ].map(([k, lbl]) => (
              <label key={k} className="block rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-2">
                <span className="block text-[10px] font-medium text-[var(--text-muted)]">{lbl}</span>
                <CellInput
                  value={numVal(hdr, k) || numVal(mergedHeader, k)}
                  onChange={(v) => setNestedKey("header", k, parseCellNum(v))}
                  ariaLabel={lbl}
                  align="left"
                  type="number"
                  className="mt-1 w-full"
                />
              </label>
            ))}
          </div>
        </div>

        <div className="border-t border-[var(--border)] pt-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-[11px] font-bold uppercase tracking-wider text-[var(--primary)]">
              3. Test Ölçüm Noktaları (Kot / Basınç / %SMYS)
            </span>
            <Button
              size="sm"
              variant="ghost"
              icon={<Plus size={12} />}
              onClick={() =>
                addRow(
                  "test_measurements",
                  {
                    pipe_top_elev_m: null,
                    station_m: null,
                    max_pressure_bar: null,
                    max_smys_pct: null,
                    min_pressure_bar: null,
                    min_smys_pct: null,
                    note: "",
                  },
                  "test_data",
                )
              }
            >
              Ölçüm Ekle
            </Button>
          </div>
          <div className="table-wrap scroll-thin">
            <table className="data">
              <thead>
                <tr>
                  <th className="num">Boru Üst Kotu (m)</th>
                  <th className="num">Ölçüm Noktası (m)</th>
                  <th className="num">Maks. Basınç (Bar)</th>
                  <th className="num">Maks. %SMYS</th>
                  <th className="num">Min. Basınç (Bar)</th>
                  <th className="num">Min. %SMYS</th>
                  <th className="num">Sil</th>
                </tr>
              </thead>
              <tbody>
                {meas.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="py-3 text-center text-[11px] text-[var(--text-faint)]">
                      Test ölçüm satırı yok.
                    </td>
                  </tr>
                ) : (
                  meas.map((row, idx) => (
                    <tr key={idx}>
                      <td className="num"><CellInput value={numVal(row, "pipe_top_elev_m")} onChange={(v) => updateRow("test_measurements", idx, { pipe_top_elev_m: parseCellNum(v) }, "test_data")} ariaLabel={`Kot ${idx + 1}`} className="w-20" type="number" /></td>
                      <td className="num"><CellInput value={numVal(row, "station_m")} onChange={(v) => updateRow("test_measurements", idx, { station_m: parseCellNum(v) }, "test_data")} ariaLabel={`Nokta ${idx + 1}`} className="w-20" type="number" /></td>
                      <td className="num"><CellInput value={numVal(row, "max_pressure_bar")} onChange={(v) => updateRow("test_measurements", idx, { max_pressure_bar: parseCellNum(v) }, "test_data")} ariaLabel={`Maks basınç ${idx + 1}`} className="w-20" type="number" /></td>
                      <td className="num"><CellInput value={numVal(row, "max_smys_pct")} onChange={(v) => updateRow("test_measurements", idx, { max_smys_pct: parseCellNum(v) }, "test_data")} ariaLabel={`Maks SMYS ${idx + 1}`} className="w-16" type="number" /></td>
                      <td className="num"><CellInput value={numVal(row, "min_pressure_bar")} onChange={(v) => updateRow("test_measurements", idx, { min_pressure_bar: parseCellNum(v) }, "test_data")} ariaLabel={`Min basınç ${idx + 1}`} className="w-20" type="number" /></td>
                      <td className="num"><CellInput value={numVal(row, "min_smys_pct")} onChange={(v) => updateRow("test_measurements", idx, { min_smys_pct: parseCellNum(v) }, "test_data")} ariaLabel={`Min SMYS ${idx + 1}`} className="w-16" type="number" /></td>
                      <td className="num">
                        <button type="button" onClick={() => removeRow("test_measurements", idx, "test_data")} className="rounded p-1 text-[var(--text-faint)] hover:bg-[var(--danger-bg)] hover:text-[var(--danger)]" aria-label={`Ölçüm ${idx + 1} sil`}>
                          <Trash2 size={12} />
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    );
  }

  /* ---------------------------------------------------------------- */
  /* 020 — HAVA İÇERİK TESTİ KABUL RAPORU                              */
  /* ---------------------------------------------------------------- */
  if (formCode === "air_acceptance") {
    const airRaw = toRecord(draft.air_acceptance);
    const airCalc = calculations.air ?? {};
    const repVp = parseCellNum(numVal(airRaw, "vp_m3"));
    const repVpa = parseCellNum(numVal(airRaw, "vpa_m3"));
    const repRatio = repVp && repVpa !== null && repVp > 0 ? repVpa / repVp - 1 : parseCellNum(numVal(airRaw, "excess_ratio"));
    const calcRatio = typeof airCalc.ratio === "number" ? airCalc.ratio - 1 : null;

    return (
      <div className="space-y-3">
        <div className="border-y border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 flex flex-wrap items-center justify-between gap-2">
          <span className="text-[10.5px] font-bold uppercase tracking-wider text-[var(--primary)]">
            1. Kullanılacak Formül
          </span>
          <code className="font-mono text-[11.5px] font-bold text-[var(--text)]">
            Vp = (0,884 × ri / S + A) × 10⁻⁶ × Vt × ΔP × K
          </code>
        </div>

        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>2. Parametreler ve Veriler</th>
                <th className="num">OCR / Düzenlenebilir Değer</th>
                <th className="num">Program Hesabı</th>
                <th className="num">Birim</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td><strong>Vp</strong> · Basıncı 1 Bar değiştirmek için gerekli teorik su miktarı</td>
                <td className="num"><CellInput type="number" value={numVal(airRaw, "vp_m3")} onChange={(v) => setNestedKey("air_acceptance", "vp_m3", parseCellNum(v))} ariaLabel="Vp (m3)" className="w-28" /></td>
                <td className="num font-mono">{typeof airCalc.vp_m3 === "number" ? num(airCalc.vp_m3, 5) : "—"}</td>
                <td className="num font-mono">m³</td>
              </tr>
              <tr>
                <td><strong>VpA</strong> · Basıncı 1 Bar değiştirmek için kullanılan su miktarı</td>
                <td className="num"><CellInput type="number" value={numVal(airRaw, "vpa_m3")} onChange={(v) => setNestedKey("air_acceptance", "vpa_m3", parseCellNum(v))} ariaLabel="VpA (m3)" className="w-28" /></td>
                <td className="num font-mono">{typeof airCalc.vpa_m3 === "number" ? num(airCalc.vpa_m3, 5) : "—"}</td>
                <td className="num font-mono">m³</td>
              </tr>
              <tr>
                <td><strong>Vt</strong> · Test bölümünün geometrik hacmi</td>
                <td className="num"><CellInput type="number" value={numVal(airRaw, "vt_m3")} onChange={(v) => setNestedKey("air_acceptance", "vt_m3", parseCellNum(v))} ariaLabel="Vt (m3)" className="w-28" /></td>
                <td className="num font-mono">{typeof mergedHeader.section_volume_m3 === "number" ? num(mergedHeader.section_volume_m3, 2) : "—"}</td>
                <td className="num font-mono">m³</td>
              </tr>
              <tr>
                <td><strong>ΔP</strong> · Ölçülen basınç değişimi</td>
                <td className="num"><CellInput type="number" value={numVal(airRaw, "pressure_rise_bar") || "1"} onChange={(v) => setNestedKey("air_acceptance", "pressure_rise_bar", parseCellNum(v))} ariaLabel="Basınç değişimi (Bar)" className="w-28" /></td>
                <td className="num font-mono">1,00</td>
                <td className="num font-mono">Bar</td>
              </tr>
              <tr>
                <td><strong>A</strong> · Suyun izotermal sıkıştırılabilirlik katsayısı (×10⁻⁶)</td>
                <td className="num"><CellInput type="number" value={numVal(airRaw, "a_micro_per_bar")} onChange={(v) => setNestedKey("air_acceptance", "a_micro_per_bar", parseCellNum(v))} ariaLabel="A katsayısı" className="w-28" /></td>
                <td className="num font-mono">{typeof airCalc.a_micro_per_bar === "number" ? num(airCalc.a_micro_per_bar, 2) : "—"}</td>
                <td className="num font-mono">1/Bar</td>
              </tr>
              <tr>
                <td><strong>K</strong> · Boru faktörü (Dikişsiz: 1,00 · Kaynaklı: 1,02)</td>
                <td className="num"><CellInput type="number" value={numVal(airRaw, "k_factor") || "1.02"} onChange={(v) => setNestedKey("air_acceptance", "k_factor", parseCellNum(v))} ariaLabel="K faktörü" className="w-28" /></td>
                <td className="num font-mono">{typeof airCalc.k_factor === "number" ? num(airCalc.k_factor, 2) : "—"}</td>
                <td className="num font-mono">—</td>
              </tr>
              <tr>
                <td><strong>(VpA / Vp) − 1</strong> · Kabul Koşulu (≤ 0,06)</td>
                <td className="num font-mono font-bold">{repRatio !== null ? num(repRatio, 4) : "—"}</td>
                <td className="num font-mono font-bold">
                  {calcRatio !== null ? (
                    <Badge tone={airCalc.passed ? "pass" : "fail"}>
                      {num(calcRatio, 4)} ({airCalc.passed ? "KABUL" : "RED"})
                    </Badge>
                  ) : (
                    "—"
                  )}
                </td>
                <td className="num font-mono">≤ 0,06</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  /* ---------------------------------------------------------------- */
  /* 022 — BASINÇ TESTİ KABUL RAPORU                                   */
  /* ---------------------------------------------------------------- */
  if (formCode === "pressure_acceptance") {
    const prRaw = toRecord(draft.pressure_acceptance);
    const prCalc = calculations.pressure ?? {};
    const repPa = parseCellNum(numVal(prRaw, "pa_bar"));
    const repPt = parseCellNum(numVal(prRaw, "pt_bar"));
    const repMargin = repPa !== null && repPt !== null ? repPa - repPt : parseCellNum(numVal(prRaw, "pa_minus_pt_bar"));

    return (
      <div className="space-y-3">
        <div className="border-y border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 flex flex-wrap items-center justify-between gap-2">
          <span className="text-[10.5px] font-bold uppercase tracking-wider text-[var(--primary)]">
            1. Kullanılacak Formül
          </span>
          <code className="font-mono text-[11.5px] font-bold text-[var(--text)]">
            PT = (B / (0,884 × ri / S + A)) × ΔT
          </code>
        </div>

        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>2. Parametreler ve Veriler</th>
                <th className="num">OCR / Düzenlenebilir Değer</th>
                <th className="num">Program Hesabı</th>
                <th className="num">Birim</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td><strong>PA</strong> · Ölçülen basınç değişimi</td>
                <td className="num"><CellInput type="number" value={numVal(prRaw, "pa_bar")} onChange={(v) => setNestedKey("pressure_acceptance", "pa_bar", parseCellNum(v))} ariaLabel="PA (Bar)" className="w-28" /></td>
                <td className="num font-mono">{typeof prCalc.pa_bar === "number" ? num(prCalc.pa_bar, 4) : "—"}</td>
                <td className="num font-mono">Bar</td>
              </tr>
              <tr>
                <td><strong>PT (ΔP)</strong> · Sıcaklık değişiminden kaynaklanan basınç değişimi</td>
                <td className="num"><CellInput type="number" value={numVal(prRaw, "pt_bar")} onChange={(v) => setNestedKey("pressure_acceptance", "pt_bar", parseCellNum(v))} ariaLabel="PT (Bar)" className="w-28" /></td>
                <td className="num font-mono">{typeof prCalc.pt_bar === "number" ? num(prCalc.pt_bar, 4) : "—"}</td>
                <td className="num font-mono">Bar</td>
              </tr>
              <tr>
                <td><strong>ΔT</strong> · Testin başı ve sonunda su sıcaklığında oluşan değişim</td>
                <td className="num"><CellInput type="number" value={numVal(prRaw, "delta_t_c")} onChange={(v) => setNestedKey("pressure_acceptance", "delta_t_c", parseCellNum(v))} ariaLabel="ΔT (°C)" className="w-28" /></td>
                <td className="num font-mono">{typeof prCalc.delta_t_c === "number" ? num(prCalc.delta_t_c, 3) : "—"}</td>
                <td className="num font-mono">°C</td>
              </tr>
              <tr>
                <td><strong>B</strong> · Su ve çeliğin ısıl genleşme katsayıları farkı (×10⁻⁶)</td>
                <td className="num"><CellInput type="number" value={numVal(prRaw, "b_micro_per_c")} onChange={(v) => setNestedKey("pressure_acceptance", "b_micro_per_c", parseCellNum(v))} ariaLabel="B katsayısı" className="w-28" /></td>
                <td className="num font-mono">{typeof prCalc.b_micro_per_c === "number" ? num(prCalc.b_micro_per_c, 2) : "—"}</td>
                <td className="num font-mono">1/K</td>
              </tr>
              <tr>
                <td><strong>A</strong> · Suyun izotermal sıkıştırılabilirlik katsayısı (×10⁻⁶)</td>
                <td className="num"><CellInput type="number" value={numVal(prRaw, "a_micro_per_bar")} onChange={(v) => setNestedKey("pressure_acceptance", "a_micro_per_bar", parseCellNum(v))} ariaLabel="A katsayısı" className="w-28" /></td>
                <td className="num font-mono">{typeof prCalc.a_micro_per_bar === "number" ? num(prCalc.a_micro_per_bar, 2) : "—"}</td>
                <td className="num font-mono">1/Bar</td>
              </tr>
              <tr>
                <td><strong>(PA − PT)</strong> · İzin Verilebilir Fark PL ≤ 0,30 Bar</td>
                <td className="num font-mono font-bold">{repMargin !== null ? num(repMargin, 4) : "—"}</td>
                <td className="num font-mono font-bold">
                  {typeof prCalc.margin_bar === "number" ? (
                    <Badge tone={prCalc.passed ? "pass" : "fail"}>
                      {num(prCalc.margin_bar, 4)} Bar ({prCalc.passed ? "KABUL" : "RED"})
                    </Badge>
                  ) : (
                    "—"
                  )}
                </td>
                <td className="num font-mono">≤ 0,30</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  /* ---------------------------------------------------------------- */
  /* 017 — SU DOLUM RAPORU                                             */
  /* ---------------------------------------------------------------- */
  if (formCode === "filling") {
    const rows = toList(draft.rows);
    const filling = toRecord(draft.filling);
    return (
      <div className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap gap-2 text-[11px]">
            <Badge tone="info">Toplam Dolum: {typeof filling.total_filled_m3 === "number" ? `${num(filling.total_filled_m3, 2)} m³` : "—"}</Badge>
            <Badge tone="neutral">Su Sıcaklığı: {typeof filling.min_temp_c === "number" ? `${num(filling.min_temp_c, 1)}–${num(filling.max_temp_c as number, 1)} °C` : "—"}</Badge>
            <Badge tone="neutral">Satır: {rows.length}</Badge>
          </div>
          <Button
            size="sm"
            variant="ghost"
            icon={<Plus size={12} />}
            onClick={() => addRow("rows", { time_str: "08:00", meter_reading_m3: null, delta_volume_m3: null, total_volume_m3: null, water_inlet_temp_c: null, water_pressure_bar: null, note: "" })}
          >
            Saat Satırı Ekle
          </Button>
        </div>

        <div className="table-wrap max-h-[340px] overflow-y-auto scroll-thin">
          <table className="data">
            <thead>
              <tr>
                <th>Okuma Saati</th>
                <th className="num">Sayaç Okuması (m³)</th>
                <th className="num">Hacim Değişimi (m³)</th>
                <th className="num">Toplam Hacim (m³)</th>
                <th className="num">Su Giriş Sıcaklığı (°C)</th>
                <th className="num">Su Basıncı (Bar)</th>
                <th>Not</th>
                <th className="num">Sil</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-4 text-center text-[11px] text-[var(--text-faint)]">
                    Saatlik su dolum satırı yok. Doküman tarayın veya satır ekleyin.
                  </td>
                </tr>
              ) : (
                rows.map((row, idx) => (
                  <tr key={idx}>
                    <td><CellInput value={strVal(row, "time_str")} onChange={(v) => updateRow("rows", idx, { time_str: v })} ariaLabel={`Saat ${idx + 1}`} align="left" className="w-16" /></td>
                    <td className="num"><CellInput type="number" value={numVal(row, "meter_reading_m3")} onChange={(v) => updateRow("rows", idx, { meter_reading_m3: parseCellNum(v) })} ariaLabel={`Sayaç ${idx + 1}`} className="w-24" /></td>
                    <td className="num"><CellInput type="number" value={numVal(row, "delta_volume_m3")} onChange={(v) => updateRow("rows", idx, { delta_volume_m3: parseCellNum(v) })} ariaLabel={`Hacim farkı ${idx + 1}`} className="w-20" /></td>
                    <td className="num"><CellInput type="number" value={numVal(row, "total_volume_m3")} onChange={(v) => updateRow("rows", idx, { total_volume_m3: parseCellNum(v) })} ariaLabel={`Toplam ${idx + 1}`} className="w-24" /></td>
                    <td className="num"><CellInput type="number" value={numVal(row, "water_inlet_temp_c")} onChange={(v) => updateRow("rows", idx, { water_inlet_temp_c: parseCellNum(v) })} ariaLabel={`Sıcaklık ${idx + 1}`} className="w-16" /></td>
                    <td className="num"><CellInput type="number" value={numVal(row, "water_pressure_bar")} onChange={(v) => updateRow("rows", idx, { water_pressure_bar: parseCellNum(v) })} ariaLabel={`Basınç ${idx + 1}`} className="w-16" /></td>
                    <td><CellInput value={strVal(row, "note")} onChange={(v) => updateRow("rows", idx, { note: v })} ariaLabel={`Not ${idx + 1}`} align="left" className="w-24" /></td>
                    <td className="num">
                      <button type="button" onClick={() => removeRow("rows", idx)} className="rounded p-1 text-[var(--text-faint)] hover:bg-[var(--danger-bg)] hover:text-[var(--danger)]" aria-label={`Satır ${idx + 1} sil`}>
                        <Trash2 size={12} />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  /* ---------------------------------------------------------------- */
  /* 018 & 021 — DENGELEME KAÇAK / BASINÇ TESTİ (24 SAATLİK İZLEME)    */
  /* ---------------------------------------------------------------- */
  if (formCode === "leak_stabilization" || formCode === "pressure_test") {
    const rows = toList(draft.rows);
    const mon = toRecord(draft.monitoring);
    const tlog = toRecord(draft.time_log);
    return (
      <div className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap gap-2 text-[11px]">
            <Badge tone="info">Süre: {typeof tlog.duration_hours === "number" ? `${num(tlog.duration_hours, 1)} sa` : `${rows.length} satır`}</Badge>
            <Badge tone="neutral">Basınç: {typeof mon.p_start_bar === "number" ? `${num(mon.p_start_bar, 2)} → ${num(mon.p_end_bar as number, 2)} Bar` : "—"}</Badge>
            <Badge tone="neutral">Son 4s ΔT: {typeof mon.last_4h_delta_c === "number" ? `${num(mon.last_4h_delta_c, 3)} °C` : "—"}</Badge>
          </div>
          <Button
            size="sm"
            variant="ghost"
            icon={<Plus size={12} />}
            onClick={() => addRow("rows", { time_str: "08:00", pressure_bar: null, ambient_temp_c: null, soil_1_c: null, pipe_1_c: null, avg_soil_c: null, avg_pipe_c: null })}
          >
            Saat Satırı Ekle
          </Button>
        </div>

        <div className="table-wrap max-h-[340px] overflow-y-auto scroll-thin">
          <table className="data">
            <thead>
              <tr>
                <th>Zaman</th>
                <th className="num">Basınç (Bar)</th>
                <th className="num">Çevre (°C)</th>
                <th className="num">Toprak 1 (°C)</th>
                <th className="num">Boru 1 (°C)</th>
                <th className="num">Toprak 2 (°C)</th>
                <th className="num">Boru 2 (°C)</th>
                <th className="num">Ort. Toprak</th>
                <th className="num">Ort. Boru</th>
                <th className="num">Sil</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={10} className="py-4 text-center text-[11px] text-[var(--text-faint)]">
                    Saatlik izleme kaydı yok. Özet: {rows.length} satır, P={strVal(mon, "p_start_bar") || "—"}→{strVal(mon, "p_end_bar") || "—"} bar.
                  </td>
                </tr>
              ) : (
                rows.map((row, idx) => (
                  <tr key={idx}>
                    <td><CellInput value={strVal(row, "time_str")} onChange={(v) => updateRow("rows", idx, { time_str: v })} ariaLabel={`Saat ${idx + 1}`} align="left" className="w-16" /></td>
                    <td className="num"><CellInput type="number" value={numVal(row, "pressure_bar")} onChange={(v) => updateRow("rows", idx, { pressure_bar: parseCellNum(v) })} ariaLabel={`Basınç ${idx + 1}`} className="w-20" /></td>
                    <td className="num"><CellInput type="number" value={numVal(row, "ambient_temp_c")} onChange={(v) => updateRow("rows", idx, { ambient_temp_c: parseCellNum(v) })} ariaLabel={`Çevre T ${idx + 1}`} className="w-16" /></td>
                    <td className="num"><CellInput type="number" value={numVal(row, "soil_1_c")} onChange={(v) => updateRow("rows", idx, { soil_1_c: parseCellNum(v) })} ariaLabel={`Toprak 1 ${idx + 1}`} className="w-16" /></td>
                    <td className="num"><CellInput type="number" value={numVal(row, "pipe_1_c")} onChange={(v) => updateRow("rows", idx, { pipe_1_c: parseCellNum(v) })} ariaLabel={`Boru 1 ${idx + 1}`} className="w-16" /></td>
                    <td className="num"><CellInput type="number" value={numVal(row, "soil_2_c")} onChange={(v) => updateRow("rows", idx, { soil_2_c: parseCellNum(v) })} ariaLabel={`Toprak 2 ${idx + 1}`} className="w-16" /></td>
                    <td className="num"><CellInput type="number" value={numVal(row, "pipe_2_c")} onChange={(v) => updateRow("rows", idx, { pipe_2_c: parseCellNum(v) })} ariaLabel={`Boru 2 ${idx + 1}`} className="w-16" /></td>
                    <td className="num"><CellInput type="number" value={numVal(row, "avg_soil_c")} onChange={(v) => updateRow("rows", idx, { avg_soil_c: parseCellNum(v) })} ariaLabel={`Ort toprak ${idx + 1}`} className="w-16" /></td>
                    <td className="num"><CellInput type="number" value={numVal(row, "avg_pipe_c")} onChange={(v) => updateRow("rows", idx, { avg_pipe_c: parseCellNum(v) })} ariaLabel={`Ort boru ${idx + 1}`} className="w-16" /></td>
                    <td className="num">
                      <button type="button" onClick={() => removeRow("rows", idx)} className="rounded p-1 text-[var(--text-faint)] hover:bg-[var(--danger-bg)] hover:text-[var(--danger)]" aria-label={`Satır ${idx + 1} sil`}>
                        <Trash2 size={12} />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  /* ---------------------------------------------------------------- */
  /* 019 & EK-014 — MUKAVEMET / BASINÇLANDIRMA TEST RAPORU             */
  /* ---------------------------------------------------------------- */
  if (formCode === "strength" || formCode === "pressurization") {
    const rows = toList(draft.rows);
    const pr = toRecord(draft.pressurization);
    return (
      <div className="space-y-3">
        <div className="grid gap-2 sm:grid-cols-3">
          <label className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-2">
            <span className="block text-[10px] font-medium text-[var(--text-muted)]">Hava Testi Teorik Vp (m³)</span>
            <CellInput type="number" value={numVal(pr, "vp_m3")} onChange={(v) => setNestedKey("pressurization", "vp_m3", parseCellNum(v))} ariaLabel="Vp (m3)" align="left" className="mt-1 w-full" />
          </label>
          <label className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-2">
            <span className="block text-[10px] font-medium text-[var(--text-muted)]">Ölçülen VpA (m³)</span>
            <CellInput type="number" value={numVal(pr, "vpa_m3")} onChange={(v) => setNestedKey("pressurization", "vpa_m3", parseCellNum(v))} ariaLabel="VpA (m3)" align="left" className="mt-1 w-full" />
          </label>
          <label className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-2">
            <span className="block text-[10px] font-medium text-[var(--text-muted)]">İlave Test Suyu Toplam (m³)</span>
            <CellInput type="number" value={numVal(pr, "total_added_water_m3")} onChange={(v) => setNestedKey("pressurization", "total_added_water_m3", parseCellNum(v))} ariaLabel="İlave su (m3)" align="left" className="mt-1 w-full" />
          </label>
        </div>

        <div className="flex items-center justify-between">
          <span className="text-[11px] font-bold uppercase tracking-wider text-[var(--primary)]">
            Basınç Artışı (P-V) Adımları
          </span>
          <Button
            size="sm"
            variant="ghost"
            icon={<Plus size={12} />}
            onClick={() => addRow("rows", { time_str: "10:00", p_initial_bar: null, p_final_bar: null, step_water_m3: null, total_water_m3: null, water_temp_c: null, note: "" })}
          >
            Adım Ekle
          </Button>
        </div>

        <div className="table-wrap max-h-[300px] overflow-y-auto scroll-thin">
          <table className="data">
            <thead>
              <tr>
                <th>Saat</th>
                <th className="num">İlk Basınç (Bar)</th>
                <th className="num">Son Basınç (Bar)</th>
                <th className="num">Kullanılan Su (m³)</th>
                <th className="num">Toplam Su (m³)</th>
                <th className="num">Su Sıcaklığı (°C)</th>
                <th className="num">Sil</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-4 text-center text-[11px] text-[var(--text-faint)]">
                    P-V basınç adımı kaydı yok.
                  </td>
                </tr>
              ) : (
                rows.map((row, idx) => (
                  <tr key={idx}>
                    <td><CellInput value={strVal(row, "time_str")} onChange={(v) => updateRow("rows", idx, { time_str: v })} ariaLabel={`Saat ${idx + 1}`} align="left" className="w-16" /></td>
                    <td className="num"><CellInput type="number" value={numVal(row, "p_initial_bar")} onChange={(v) => updateRow("rows", idx, { p_initial_bar: parseCellNum(v) })} ariaLabel={`İlk basınç ${idx + 1}`} className="w-20" /></td>
                    <td className="num"><CellInput type="number" value={numVal(row, "p_final_bar")} onChange={(v) => updateRow("rows", idx, { p_final_bar: parseCellNum(v) })} ariaLabel={`Son basınç ${idx + 1}`} className="w-20" /></td>
                    <td className="num"><CellInput type="number" value={numVal(row, "step_water_m3")} onChange={(v) => updateRow("rows", idx, { step_water_m3: parseCellNum(v) })} ariaLabel={`Adım su ${idx + 1}`} className="w-20" /></td>
                    <td className="num"><CellInput type="number" value={numVal(row, "total_water_m3")} onChange={(v) => updateRow("rows", idx, { total_water_m3: parseCellNum(v) })} ariaLabel={`Toplam su ${idx + 1}`} className="w-20" /></td>
                    <td className="num"><CellInput type="number" value={numVal(row, "water_temp_c")} onChange={(v) => updateRow("rows", idx, { water_temp_c: parseCellNum(v) })} ariaLabel={`Su T ${idx + 1}`} className="w-16" /></td>
                    <td className="num">
                      <button type="button" onClick={() => removeRow("rows", idx)} className="rounded p-1 text-[var(--text-faint)] hover:bg-[var(--danger-bg)] hover:text-[var(--danger)]" aria-label={`Adım ${idx + 1} sil`}>
                        <Trash2 size={12} />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  /* ---------------------------------------------------------------- */
  /* 016, 023, KUR-001, KUR-002 — PİG İZLEME & KURUTMA DEW POINT      */
  /* ---------------------------------------------------------------- */
  if (formCode === "cleaning" || formCode === "dewatering" || formCode === "pre_drying" || formCode === "final_drying") {
    const runs = toList(draft.pig_runs);
    const drying = toRecord(draft.drying);
    const isDrying = formCode === "pre_drying" || formCode === "final_drying";

    return (
      <div className="space-y-4">
        {isDrying ? (
          <div className="grid gap-2 sm:grid-cols-3">
            <label className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-2">
              <span className="block text-[10px] font-medium text-[var(--text-muted)]">Hedef Çiğlenme Noktası (°C)</span>
              <CellInput type="number" value={numVal(drying, "target_dew_point_c") || "-20"} onChange={(v) => setNestedKey("drying", "target_dew_point_c", parseCellNum(v))} ariaLabel="Hedef dew point" align="left" className="mt-1 w-full" />
            </label>
            <label className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-2">
              <span className="block text-[10px] font-medium text-[var(--text-muted)]">Ölçülen Çiğlenme Noktası (°C)</span>
              <CellInput type="number" value={numVal(drying, "measured_dew_point_c")} onChange={(v) => setNestedKey("drying", "measured_dew_point_c", parseCellNum(v))} ariaLabel="Ölçülen dew point" align="left" className="mt-1 w-full" />
            </label>
            <label className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-2">
              <span className="block text-[10px] font-medium text-[var(--text-muted)]">Kurutma Süresi (Saat)</span>
              <CellInput type="number" value={numVal(drying, "duration_hours")} onChange={(v) => setNestedKey("drying", "duration_hours", parseCellNum(v))} ariaLabel="Kurutma süresi" align="left" className="mt-1 w-full" />
            </label>
          </div>
        ) : null}

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold uppercase tracking-wider text-[var(--primary)]">
              Pig İzleme Tablosu
            </span>
            <Button
              size="sm"
              variant="ghost"
              icon={<Plus size={12} />}
              onClick={() => addRow("pig_runs", { pig_type: "Fırçalı / Köpük Pig", launch_time: "08:00", receive_time: "09:15", duration_min: 75, note: "" })}
            >
              Pig Seferi Ekle
            </Button>
          </div>

          <div className="table-wrap scroll-thin">
            <table className="data">
              <thead>
                <tr>
                  <th>Pig Tipi</th>
                  <th>Atılış Saati</th>
                  <th>Alınış Saati</th>
                  <th className="num">Süre (dk)</th>
                  <th>Not</th>
                  <th className="num">Sil</th>
                </tr>
              </thead>
              <tbody>
                {runs.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="py-4 text-center text-[11px] text-[var(--text-faint)]">
                      Pig atılış/alınış satırı yok; yukarıdan ekleyebilirsiniz.
                    </td>
                  </tr>
                ) : (
                  runs.map((row, idx) => (
                    <tr key={idx}>
                      <td><CellInput value={strVal(row, "pig_type")} onChange={(v) => updateRow("pig_runs", idx, { pig_type: v })} ariaLabel={`Pig tipi ${idx + 1}`} align="left" className="w-36" /></td>
                      <td><CellInput value={strVal(row, "launch_time")} onChange={(v) => updateRow("pig_runs", idx, { launch_time: v })} ariaLabel={`Atılış ${idx + 1}`} align="left" className="w-20" /></td>
                      <td><CellInput value={strVal(row, "receive_time")} onChange={(v) => updateRow("pig_runs", idx, { receive_time: v })} ariaLabel={`Alınış ${idx + 1}`} align="left" className="w-20" /></td>
                      <td className="num"><CellInput type="number" value={numVal(row, "duration_min")} onChange={(v) => updateRow("pig_runs", idx, { duration_min: parseCellNum(v) })} ariaLabel={`Süre ${idx + 1}`} className="w-20" /></td>
                      <td><CellInput value={strVal(row, "note")} onChange={(v) => updateRow("pig_runs", idx, { note: v })} ariaLabel={`Pig not ${idx + 1}`} align="left" className="w-28" /></td>
                      <td className="num">
                        <button type="button" onClick={() => removeRow("pig_runs", idx)} className="rounded p-1 text-[var(--text-faint)] hover:bg-[var(--danger-bg)] hover:text-[var(--danger)]" aria-label={`Pig ${idx + 1} sil`}>
                          <Trash2 size={12} />
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    );
  }

  /* ---------------------------------------------------------------- */
  /* EK FORMLAR (SPOOL, HESAP TABLOSU, CHART, KALİPER PİG)            */
  /* ---------------------------------------------------------------- */
  const params = toRecord(draft.parameters);
  const paramKeys =
    formCode === "chart_recorder"
      ? [
          ["chart_no", "Chart No", false],
          ["range_bar", "Basınç Skalası (Bar)", true],
          ["duration_hours", "Kayıt Süresi (Saat)", true],
        ]
      : formCode === "caliper_pig"
        ? [
            ["plate_diameter_mm", "Kalibre Plakası Çapı (mm)", true],
            ["max_dent_pct", "Maks. Göçük / Ovalite (%)", true],
          ]
        : [
            ["p_min_bar", "Pmin (Bar)", true],
            ["p_max_bar", "Pmax (Bar)", true],
            ["v_sec_m3", "Vsec Hacim (m³)", true],
            ["hoop_stress_pct", "Çevresel Gerilme (%SMYS)", true],
          ];

  return (
    <div className="space-y-3">
      <div className="grid gap-2 sm:grid-cols-2">
        {paramKeys.map(([k, lbl, isNum]) => (
          <label key={String(k)} className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-2.5">
            <span className="block text-[10px] font-medium text-[var(--text-muted)]">{lbl}</span>
            <CellInput
              type={isNum ? "number" : "text"}
              value={strVal(params, String(k))}
              onChange={(v) => setNestedKey("parameters", String(k), isNum ? parseCellNum(v) : v)}
              ariaLabel={String(lbl)}
              align="left"
              className="mt-1 w-full"
            />
          </label>
        ))}
      </div>
    </div>
  );
}
