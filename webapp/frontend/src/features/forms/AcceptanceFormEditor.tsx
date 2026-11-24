import { Info } from "lucide-react";
import { num } from "../../lib/format";
import { Badge } from "../../components/ui/Badge";
import { CellInput, numVal, toRecord, type DraftData } from "./FormTablePrimitives";
import { parseCellNum } from "./pasteUtils";

function ComparisonBadge({
  reported,
  program,
  unit,
  relTol = 0.02,
  absTol = 0,
  digits = 4,
}: {
  reported: number | null;
  program: number | null;
  unit?: string;
  relTol?: number;
  absTol?: number;
  digits?: number;
}) {
  if (reported === null || program === null) {
    return <span className="text-[10.5px] text-[var(--text-faint)]">—</span>;
  }
  const diff = reported - program;
  const tol = Math.max(absTol, Math.abs(program) * relTol);
  const ok = Math.abs(diff) <= tol;
  const suffix = unit ? ` ${unit}` : "";
  return (
    <Badge tone={ok ? "pass" : "warning"}>
      {ok ? "Uyumlu" : `Fark ${diff > 0 ? "+" : ""}${num(diff, digits)}${suffix}`}
    </Badge>
  );
}

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
    const repVt = parseCellNum(numVal(airRaw, "vt_m3"));
    const repA = parseCellNum(numVal(airRaw, "a_micro_per_bar"));
    const repRatio =
      repVp && repVpa !== null && repVp > 0
        ? repVpa / repVp - 1
        : parseCellNum(numVal(airRaw, "excess_ratio"));
    const calcVp = typeof airCalc.vp_m3 === "number" ? airCalc.vp_m3 : null;
    const calcVt =
      typeof airCalc.vt_m3 === "number"
        ? airCalc.vt_m3
        : typeof mergedHeader.section_volume_m3 === "number"
          ? mergedHeader.section_volume_m3
          : null;
    const calcA = typeof airCalc.a_micro_per_bar === "number" ? airCalc.a_micro_per_bar : null;
    const aSource = typeof airCalc.a_source === "string" ? airCalc.a_source : null;
    const vpSource = typeof airCalc.vp_source === "string" ? airCalc.vp_source : null;
    const stateT = typeof airCalc.state_temp_c === "number" ? airCalc.state_temp_c : null;
    const stateP = typeof airCalc.state_pressure_bar === "number" ? airCalc.state_pressure_bar : null;
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
          role="region"
          aria-label="Hava İçerik Testi Okunan Girdi Değerleri"
          className="table-wrap table-sticky scroll-thin"
        >
          <table className="data">
            <thead>
              <tr>
                <th>2a. Okunan Girdi Değerleri (Formdan)</th>
                <th className="num">Formdan Okunan (OCR)</th>
                <th className="num">Not / Şartname</th>
                <th className="num">Birim</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>
                  <strong>VpA</strong> · Basıncı 1 Bar değiştirmek için kullanılan fiili su miktarı
                  <span className="mt-0.5 block font-mono text-[10px] text-[var(--text-faint)]">
                    Ölçülen saha girdisi · Kabul kuralı: VpA &lt; 1,06 × Vp
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
                <td className="num text-[10.5px] text-[var(--text-faint)]">Girdi (Formdan)</td>
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
                <td className="num font-mono text-[10.5px] text-[var(--text-faint)]">
                  Şartname: 1,00 Bar
                </td>
                <td className="num font-mono">Bar</td>
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
                <td className="num text-[10.5px] text-[var(--text-faint)]">Girdi (Formdan)</td>
                <td className="num font-mono">—</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div
          role="region"
          aria-label="Hava İçerik Testi Hesaplanan ve Karşılaştırılan Değerler"
          className="table-wrap table-sticky scroll-thin"
        >
          <table className="data">
            <thead>
              <tr>
                <th>2b. Hesaplanan Değerler (Form vs Program Hesabı)</th>
                <th className="num">Formdan Okunan (OCR)</th>
                <th className="num">Program Hesabı</th>
                <th className="num">Karşılaştırma</th>
                <th className="num">Birim</th>
              </tr>
            </thead>
            <tbody>
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
                <td className="num font-mono">{calcVt !== null ? num(calcVt, 2) : "—"}</td>
                <td className="num">
                  <ComparisonBadge reported={repVt} program={calcVt} unit="m³" relTol={0.01} digits={2} />
                </td>
                <td className="num font-mono">m³</td>
              </tr>
              <tr>
                <td>
                  <strong>A</strong> · Suyun izotermal sıkıştırılabilirlik katsayısı (×10⁻⁶)
                  {aSource === "program" && stateT !== null && stateP !== null ? (
                    <span className="mt-0.5 block font-mono text-[10px] text-[var(--text-faint)]">
                      Program hesabı (IAPWS-95 EOS): T = {num(stateT, 1)} °C, P = {num(stateP, 1)} bar
                    </span>
                  ) : aSource === "form_fallback" ? (
                    <span className="mt-0.5 block font-mono text-[10px] text-[var(--warning)]">
                      T veya P eksik — bağımsız A hesaplanamadı, form değeri kullanıldı
                    </span>
                  ) : null}
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
                  {aSource === "program" && calcA !== null ? (
                    num(calcA, 3)
                  ) : (
                    <span className="text-[10.5px] text-[var(--text-faint)]">T/P eksik</span>
                  )}
                </td>
                <td className="num">
                  {aSource === "program" ? (
                    <ComparisonBadge reported={repA} program={calcA} relTol={0.02} digits={3} />
                  ) : (
                    <Badge tone="warning">Form A</Badge>
                  )}
                </td>
                <td className="num font-mono">1/Bar</td>
              </tr>
              <tr>
                <td>
                  <strong>Vp</strong> · Basıncı 1 Bar değiştirmek için gerekli teorik su miktarı
                  {vpSource === "form_fallback" ? (
                    <span className="mt-0.5 block font-mono text-[10px] text-[var(--warning)]">
                      Geometri veya A eksik — program Vp hesaplayamadı
                    </span>
                  ) : null}
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
                  {vpSource === "program" && calcVp !== null ? (
                    num(calcVp, 5)
                  ) : (
                    <span className="text-[10.5px] text-[var(--text-faint)]">Hesaplanamadı</span>
                  )}
                </td>
                <td className="num">
                  {vpSource === "program" ? (
                    <ComparisonBadge reported={repVp} program={calcVp} unit="m³" relTol={0.025} digits={5} />
                  ) : (
                    <span className="text-[10.5px] text-[var(--text-faint)]">—</span>
                  )}
                </td>
                <td className="num font-mono">m³</td>
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
                <td className="num">
                  <ComparisonBadge reported={repRatio} program={calcRatio} absTol={0.005} digits={4} />
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
  const repA = parseCellNum(numVal(prRaw, "a_micro_per_bar"));
  const repB = parseCellNum(numVal(prRaw, "b_micro_per_c"));
  const repMargin =
    repPa !== null && repPt !== null ? repPa - repPt : parseCellNum(numVal(prRaw, "pa_minus_pt_bar"));
  const calcPt = typeof prCalc.pt_bar === "number" ? prCalc.pt_bar : null;
  const calcA = typeof prCalc.a_micro_per_bar === "number" ? prCalc.a_micro_per_bar : null;
  const calcB = typeof prCalc.b_micro_per_c === "number" ? prCalc.b_micro_per_c : null;
  const coeffSource = typeof prCalc.coeff_source === "string" ? prCalc.coeff_source : null;
  const ptSource = typeof prCalc.pt_source === "string" ? prCalc.pt_source : null;
  const stateT = typeof prCalc.state_temp_c === "number" ? prCalc.state_temp_c : null;
  const stateP = typeof prCalc.state_pressure_bar === "number" ? prCalc.state_pressure_bar : null;
  const pa021 = typeof prCalc.pa_from_021_bar === "number" ? prCalc.pa_from_021_bar : null;
  const dt021 = typeof prCalc.delta_t_from_021_c === "number" ? prCalc.delta_t_from_021_c : null;

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
        role="region"
        aria-label="Basınç Testi Okunan Girdi Değerleri"
        className="table-wrap table-sticky scroll-thin"
      >
        <table className="data">
          <thead>
            <tr>
              <th>2a. Okunan Girdi Değerleri (Formdan)</th>
              <th className="num">Formdan Okunan (OCR)</th>
              <th className="num">021 Saatlik Kayıt Çapraz Kontrolü</th>
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
              <td className="num font-mono text-[10.5px]">
                {pa021 !== null ? (
                  <span title="021 formundaki başlangıç - bitiş basıncı">
                    021: {num(pa021, 3)}
                  </span>
                ) : (
                  <span className="text-[var(--text-faint)]">Girdi (Formdan)</span>
                )}
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
              <td className="num font-mono text-[10.5px]">
                {dt021 !== null ? (
                  <span title="021 formundaki başlangıç - bitiş boru sıcaklığı">
                    021: {num(dt021, 2)} °C
                  </span>
                ) : (
                  <span className="text-[var(--text-faint)]">Girdi (Formdan)</span>
                )}
              </td>
              <td className="num font-mono">°C</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div
        role="region"
        aria-label="Basınç Testi Hesaplanan ve Karşılaştırılan Değerler"
        className="table-wrap table-sticky scroll-thin"
      >
        <table className="data">
          <thead>
            <tr>
              <th>2b. Hesaplanan Değerler (Form vs Program Hesabı)</th>
              <th className="num">Formdan Okunan (OCR)</th>
              <th className="num">Program Hesabı</th>
              <th className="num">Karşılaştırma</th>
              <th className="num">Birim</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>
                <strong>B</strong> · Su ve çeliğin hacimsel ısıl genleşme farkı (βw − 3α, ×10⁻⁶)
                {coeffSource === "program" && stateT !== null && stateP !== null ? (
                  <span className="mt-0.5 block font-mono text-[10px] text-[var(--text-faint)]">
                    Program hesabı (T = {num(stateT, 1)} °C, P = {num(stateP, 1)} bar · 3α = 35,1)
                  </span>
                ) : coeffSource === "form_fallback" ? (
                  <span className="mt-0.5 block font-mono text-[10px] text-[var(--warning)]">
                    T veya P eksik — bağımsız B hesaplanamadı, form değeri kullanıldı
                  </span>
                ) : null}
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
                {coeffSource === "program" && calcB !== null ? (
                  num(calcB, 2)
                ) : (
                  <span className="text-[10.5px] text-[var(--text-faint)]">T/P eksik</span>
                )}
              </td>
              <td className="num">
                {coeffSource === "program" ? (
                  <ComparisonBadge reported={repB} program={calcB} relTol={0.05} absTol={5} digits={2} />
                ) : (
                  <Badge tone="warning">Form B</Badge>
                )}
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
                {coeffSource === "program" && calcA !== null ? (
                  num(calcA, 3)
                ) : (
                  <span className="text-[10.5px] text-[var(--text-faint)]">T/P eksik</span>
                )}
              </td>
              <td className="num">
                {coeffSource === "program" ? (
                  <ComparisonBadge reported={repA} program={calcA} relTol={0.02} digits={3} />
                ) : (
                  <Badge tone="warning">Form A</Badge>
                )}
              </td>
              <td className="num font-mono">1/Bar</td>
            </tr>
            <tr>
              <td>
                <strong>PT (ΔP)</strong> · Sıcaklık değişiminden kaynaklanan teorik basınç değişimi
                {ptSource === "form_fallback" ? (
                  <span className="mt-0.5 block font-mono text-[10px] text-[var(--warning)]">
                    Geometri veya A/B eksik — program PT hesaplayamadı
                  </span>
                ) : null}
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
                {ptSource === "program" && calcPt !== null ? (
                  num(calcPt, 4)
                ) : (
                  <span className="text-[10.5px] text-[var(--text-faint)]">Hesaplanamadı</span>
                )}
              </td>
              <td className="num">
                {ptSource === "program" ? (
                  <ComparisonBadge reported={repPt} program={calcPt} unit="bar" absTol={0.05} digits={3} />
                ) : (
                  <span className="text-[10.5px] text-[var(--text-faint)]">—</span>
                )}
              </td>
              <td className="num font-mono">Bar</td>
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
              <td className="num">
                <ComparisonBadge
                  reported={repMargin}
                  program={typeof prCalc.margin_bar === "number" ? prCalc.margin_bar : null}
                  unit="bar"
                  absTol={0.05}
                  digits={3}
                />
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
