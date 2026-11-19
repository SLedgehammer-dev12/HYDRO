import { Info } from "lucide-react";
import { num } from "../../lib/format";
import { Badge } from "../../components/ui/Badge";
import { CellInput, numVal, toRecord, type DraftData } from "./FormTablePrimitives";
import { parseCellNum } from "./pasteUtils";

export function AcceptanceFormEditor({
  formCode,
  draft,
  setNestedKey,
  calculations,
  mergedHeader,
}: {
  formCode: "air_acceptance" | "pressure_acceptance";
  draft: DraftData;
  setNestedKey: (sectionKey: string, fieldKey: string, value: unknown) => void;
  calculations: Record<string, Record<string, unknown>>;
  mergedHeader: Record<string, unknown>;
}) {
  /* ---------------------------------------------------------------- */
  /* 020 — HAVA İÇERİK TESTİ KABUL RAPORU                              */
  /* ---------------------------------------------------------------- */
  if (formCode === "air_acceptance") {
    const airRaw = toRecord(draft.air_acceptance);
    const airCalc = calculations.air ?? {};
    const repVp = parseCellNum(numVal(airRaw, "vp_m3"));
    const repVpa = parseCellNum(numVal(airRaw, "vpa_m3"));
    const repRatio =
      repVp && repVpa !== null && repVp > 0
        ? repVpa / repVp - 1
        : parseCellNum(numVal(airRaw, "excess_ratio"));
    const calcRatio = typeof airCalc.ratio === "number" ? airCalc.ratio - 1 : null;

    return (
      <div className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2 border-y border-[var(--border)] bg-[var(--surface-2)] px-3 py-2">
          <span className="text-[10.5px] font-bold uppercase tracking-wider text-[var(--primary)]">
            1. Kullanılacak Formül
          </span>
          <code className="font-mono text-[11.5px] font-bold text-[var(--text)]">
            Vp = (0,884 × ri / S + A) × 10⁻⁶ × Vt × ΔP × K
          </code>
        </div>

        <div
          tabIndex={0}
          role="region"
          aria-label="Hava İçerik Testi Kabul Parametreleri"
          className="table-wrap table-sticky scroll-thin"
        >
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
                <td>
                  <strong>Vp</strong> · Basıncı 1 Bar değiştirmek için gerekli teorik su miktarı
                </td>
                <td className="num">
                  <CellInput
                    type="number"
                    value={numVal(airRaw, "vp_m3")}
                    onChange={(v) => setNestedKey("air_acceptance", "vp_m3", parseCellNum(v))}
                    ariaLabel="Vp (m3)"
                    className="w-28"
                  />
                </td>
                <td className="num font-mono">
                  {typeof airCalc.vp_m3 === "number" ? num(airCalc.vp_m3, 5) : "—"}
                </td>
                <td className="num font-mono">m³</td>
              </tr>
              <tr>
                <td>
                  <strong>VpA</strong> · Basıncı 1 Bar değiştirmek için kullanılan su miktarı
                  <span className="mt-0.5 block font-mono text-[10px] text-[var(--text-faint)]">
                    Kabul kuralı: VpA &lt; 1,06 × Vp (tam 1,06 sınır değeri RED)
                  </span>
                </td>
                <td className="num">
                  <CellInput
                    type="number"
                    value={numVal(airRaw, "vpa_m3")}
                    onChange={(v) => setNestedKey("air_acceptance", "vpa_m3", parseCellNum(v))}
                    ariaLabel="VpA (m3)"
                    className="w-28"
                  />
                </td>
                <td className="num font-mono">
                  {typeof airCalc.vpa_m3 === "number" ? num(airCalc.vpa_m3, 5) : "—"}
                </td>
                <td className="num font-mono">m³</td>
              </tr>
              <tr>
                <td>
                  <strong>Vt</strong> · Test bölümünün geometrik hacmi
                </td>
                <td className="num">
                  <CellInput
                    type="number"
                    value={numVal(airRaw, "vt_m3")}
                    onChange={(v) => setNestedKey("air_acceptance", "vt_m3", parseCellNum(v))}
                    ariaLabel="Vt (m3)"
                    className="w-28"
                  />
                </td>
                <td className="num font-mono">
                  {typeof mergedHeader.section_volume_m3 === "number"
                    ? num(mergedHeader.section_volume_m3, 2)
                    : "—"}
                </td>
                <td className="num font-mono">m³</td>
              </tr>
              <tr>
                <td>
                  <strong>ΔP</strong> · Ölçülen basınç değişimi
                  <span className="mt-0.5 block font-mono text-[10px] text-[var(--text-faint)]">
                    Şartname 13: Hava içerik testi tam ΔP = 1,00 Bar artışla yapılır
                  </span>
                </td>
                <td className="num">
                  <CellInput
                    type="number"
                    value={numVal(airRaw, "pressure_rise_bar")}
                    placeholder="1"
                    onChange={(v) =>
                      setNestedKey("air_acceptance", "pressure_rise_bar", parseCellNum(v))
                    }
                    ariaLabel="Basınç değişimi (Bar)"
                    className="w-28"
                  />
                </td>
                <td className="num font-mono">1,00</td>
                <td className="num font-mono">Bar</td>
              </tr>
              <tr>
                <td>
                  <strong>A</strong> · Suyun izotermal sıkıştırılabilirlik katsayısı (×10⁻⁶)
                </td>
                <td className="num">
                  <CellInput
                    type="number"
                    value={numVal(airRaw, "a_micro_per_bar")}
                    onChange={(v) =>
                      setNestedKey("air_acceptance", "a_micro_per_bar", parseCellNum(v))
                    }
                    ariaLabel="A katsayısı"
                    className="w-28"
                  />
                </td>
                <td className="num font-mono">
                  {typeof airCalc.a_micro_per_bar === "number"
                    ? num(airCalc.a_micro_per_bar, 2)
                    : "—"}
                </td>
                <td className="num font-mono">1/Bar</td>
              </tr>
              <tr>
                <td>
                  <strong>K</strong> · Boru faktörü (Dikişsiz: 1,00 · Kaynaklı: 1,02)
                </td>
                <td className="num">
                  <CellInput
                    type="number"
                    value={numVal(airRaw, "k_factor")}
                    placeholder="1.02"
                    onChange={(v) => setNestedKey("air_acceptance", "k_factor", parseCellNum(v))}
                    ariaLabel="K faktörü"
                    className="w-28"
                  />
                </td>
                <td className="num font-mono">
                  {typeof airCalc.k_factor === "number" ? num(airCalc.k_factor, 2) : "—"}
                </td>
                <td className="num font-mono">—</td>
              </tr>
              <tr>
                <td>
                  <strong>(VpA / Vp) − 1</strong> · Kabul Koşulu (&lt; 0,06)
                </td>
                <td className="num font-mono font-bold">
                  {repRatio !== null ? num(repRatio, 4) : "—"}
                </td>
                <td className="num font-mono font-bold">
                  {calcRatio !== null ? (
                    <Badge tone={airCalc.passed ? "pass" : "fail"}>
                      {num(calcRatio, 4)} ({airCalc.passed ? "KABUL" : "RED"})
                    </Badge>
                  ) : (
                    "—"
                  )}
                </td>
                <td className="num font-mono">&lt; 0,06</td>
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
  const prRaw = toRecord(draft.pressure_acceptance);
  const prCalc = calculations.pressure ?? {};
  const repPa = parseCellNum(numVal(prRaw, "pa_bar"));
  const repPt = parseCellNum(numVal(prRaw, "pt_bar"));
  const repMargin =
    repPa !== null && repPt !== null ? repPa - repPt : parseCellNum(numVal(prRaw, "pa_minus_pt_bar"));

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2 border-y border-[var(--border)] bg-[var(--surface-2)] px-3 py-2">
        <span className="text-[10.5px] font-bold uppercase tracking-wider text-[var(--primary)]">
          1. Kullanılacak Formül
        </span>
        <code className="font-mono text-[11.5px] font-bold text-[var(--text)]">
          PT = (B / (0,884 × ri / S + A)) × ΔT
        </code>
      </div>

      <div
        tabIndex={0}
        role="region"
        aria-label="Basınç Testi Kabul Parametreleri"
        className="table-wrap table-sticky scroll-thin"
      >
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
              <td>
                <strong>PA</strong> · Ölçülen basınç değişimi
                <span className="mt-0.5 block font-mono text-[10px] text-[var(--text-faint)]">
                  İşaret kuralı: PA = Pilk − Pson (basınç düşüşü pozitif)
                </span>
              </td>
              <td className="num">
                <CellInput
                  type="number"
                  value={numVal(prRaw, "pa_bar")}
                  onChange={(v) => setNestedKey("pressure_acceptance", "pa_bar", parseCellNum(v))}
                  ariaLabel="PA (Bar)"
                  className="w-28"
                />
              </td>
              <td className="num font-mono">
                {typeof prCalc.pa_bar === "number" ? num(prCalc.pa_bar, 4) : "—"}
              </td>
              <td className="num font-mono">Bar</td>
            </tr>
            <tr>
              <td>
                <strong>PT (ΔP)</strong> · Sıcaklık değişiminden kaynaklanan basınç değişimi
              </td>
              <td className="num">
                <CellInput
                  type="number"
                  value={numVal(prRaw, "pt_bar")}
                  onChange={(v) => setNestedKey("pressure_acceptance", "pt_bar", parseCellNum(v))}
                  ariaLabel="PT (Bar)"
                  className="w-28"
                />
              </td>
              <td className="num font-mono">
                {typeof prCalc.pt_bar === "number" ? num(prCalc.pt_bar, 4) : "—"}
              </td>
              <td className="num font-mono">Bar</td>
            </tr>
            <tr>
              <td>
                <strong>ΔT</strong> · Testin başı ve sonunda su sıcaklığında oluşan değişim
                <span className="mt-0.5 block font-mono text-[10px] text-[var(--text-faint)]">
                  İşaret kuralı: ΔT = Tilk − Tson (soğuma pozitif)
                </span>
              </td>
              <td className="num">
                <CellInput
                  type="number"
                  value={numVal(prRaw, "delta_t_c")}
                  onChange={(v) =>
                    setNestedKey("pressure_acceptance", "delta_t_c", parseCellNum(v))
                  }
                  ariaLabel="ΔT (°C)"
                  className="w-28"
                />
              </td>
              <td className="num font-mono">
                {typeof prCalc.delta_t_c === "number" ? num(prCalc.delta_t_c, 3) : "—"}
              </td>
              <td className="num font-mono">°C</td>
            </tr>
            <tr>
              <td>
                <strong>B</strong> · Su ve çeliğin ısıl genleşme katsayıları farkı (×10⁻⁶)
              </td>
              <td className="num">
                <CellInput
                  type="number"
                  value={numVal(prRaw, "b_micro_per_c")}
                  onChange={(v) =>
                    setNestedKey("pressure_acceptance", "b_micro_per_c", parseCellNum(v))
                  }
                  ariaLabel="B katsayısı"
                  className="w-28"
                />
              </td>
              <td className="num font-mono">
                {typeof prCalc.b_micro_per_c === "number" ? num(prCalc.b_micro_per_c, 2) : "—"}
              </td>
              <td className="num font-mono">1/K</td>
            </tr>
            <tr>
              <td>
                <strong>A</strong> · Suyun izotermal sıkıştırılabilirlik katsayısı (×10⁻⁶)
              </td>
              <td className="num">
                <CellInput
                  type="number"
                  value={numVal(prRaw, "a_micro_per_bar")}
                  onChange={(v) =>
                    setNestedKey("pressure_acceptance", "a_micro_per_bar", parseCellNum(v))
                  }
                  ariaLabel="A katsayısı"
                  className="w-28"
                />
              </td>
              <td className="num font-mono">
                {typeof prCalc.a_micro_per_bar === "number" ? num(prCalc.a_micro_per_bar, 2) : "—"}
              </td>
              <td className="num font-mono">1/Bar</td>
            </tr>
            <tr>
              <td>
                <strong>(PA − PT)</strong> · İzin Verilebilir Fark PL ≤ 0,30 Bar
              </td>
              <td className="num font-mono font-bold">
                {repMargin !== null ? num(repMargin, 4) : "—"}
              </td>
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

      <div className="flex items-start gap-2 rounded-lg border border-[var(--info-border)] bg-[var(--info-bg)] px-3 py-2 text-[10.5px] leading-relaxed text-[var(--text-muted)]">
        <Info size={13} className="mt-0.5 shrink-0 text-[var(--info)]" aria-hidden />
        <span>
          <strong>Şartname 15:</strong> İzin verilebilir fark sınırı sabittir (
          <code className="font-mono">PL = 0,30 Bar</code>). Negatif <code className="font-mono">B</code>{" "}
          değerlerinde ısınma/soğuma yönü tersine döner.
        </span>
      </div>
    </div>
  );
}
