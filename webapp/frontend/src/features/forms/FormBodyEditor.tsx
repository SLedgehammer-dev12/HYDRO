import { Plus, Trash2 } from "lucide-react";
import type { BotasFormCode } from "../../lib/types";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { AcceptanceFormEditor } from "./AcceptanceFormEditor";
import {
  CellInput,
  PasteRowsTray,
  numVal,
  strVal,
  toList,
  toRecord,
  useTableClipboardPaste,
  type DraftData,
} from "./FormTablePrimitives";
import { MonitoringFormEditor } from "./MonitoringFormEditor";
import {
  parseCellNum,
  parseMeasurementsPaste,
  parsePigRunsPaste,
} from "./pasteUtils";

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

  const onPasteMeasurements = useTableClipboardPaste(parseMeasurementsPaste, (newRows) => {
    const td = toRecord(draft.test_data);
    const existing = toList(td.test_measurements);
    onChange({ ...draft, test_data: { ...td, test_measurements: [...existing, ...newRows] } });
  });

  const onPastePigRuns = useTableClipboardPaste(parsePigRunsPaste, (newRows) => {
    const existing = toList(draft.pig_runs);
    onChange({ ...draft, pig_runs: [...existing, ...newRows] });
  });

  if (formCode === "air_acceptance" || formCode === "pressure_acceptance") {
    return (
      <AcceptanceFormEditor
        formCode={formCode}
        draft={draft}
        setNestedKey={setNestedKey}
        calculations={calculations}
        mergedHeader={mergedHeader}
      />
    );
  }

  if (
    formCode === "filling" ||
    formCode === "leak_stabilization" ||
    formCode === "pressure_test" ||
    formCode === "strength" ||
    formCode === "pressurization"
  ) {
    return (
      <MonitoringFormEditor
        formCode={formCode}
        draft={draft}
        onChange={onChange}
        setNestedKey={setNestedKey}
        addRow={addRow}
        updateRow={updateRow}
        removeRow={removeRow}
      />
    );
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
              onClick={() =>
                addRow(
                  "volume_segments",
                  { wall_thickness_mm: null, length_m: null, volume_m3: null },
                  "test_data",
                )
              }
            >
              Segment Ekle
            </Button>
          </div>
          <div
            tabIndex={0}
            role="region"
            aria-label="Test Bölümü Segment Hacimleri"
            className="table-wrap table-sticky scroll-thin"
          >
            <table className="data">
              <thead>
                <tr>
                  <th className="sticky-col">Boru Et Kalınlığı (mm)</th>
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
                      <td className="sticky-col">
                        <CellInput
                          value={numVal(row, "wall_thickness_mm")}
                          onChange={(v) =>
                            updateRow(
                              "volume_segments",
                              idx,
                              { wall_thickness_mm: parseCellNum(v) },
                              "test_data",
                            )
                          }
                          ariaLabel={`Segment ${idx + 1} et kalınlığı`}
                          className="w-24"
                          type="number"
                        />
                      </td>
                      <td className="num">
                        <CellInput
                          value={numVal(row, "length_m")}
                          onChange={(v) =>
                            updateRow(
                              "volume_segments",
                              idx,
                              { length_m: parseCellNum(v) },
                              "test_data",
                            )
                          }
                          ariaLabel={`Segment ${idx + 1} uzunluk`}
                          className="w-28"
                          type="number"
                        />
                      </td>
                      <td className="num">
                        <CellInput
                          value={numVal(row, "volume_m3")}
                          onChange={(v) =>
                            updateRow(
                              "volume_segments",
                              idx,
                              { volume_m3: parseCellNum(v) },
                              "test_data",
                            )
                          }
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
            {profCalc.summary ? (
              <Badge tone={profCalc.passed ? "pass" : "fail"}>
                {profCalc.passed ? "Basınç Penceresi Uygun" : "Kontrol Gerekli"}
              </Badge>
            ) : null}
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
              <label
                key={k}
                className="block rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-2"
              >
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

        <div className="space-y-2 border-t border-[var(--border)] pt-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
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

          <PasteRowsTray
            hint="Boru Üst Kotu (m) | Ölçüm Noktası (m) | Maks. Basınç (Bar) | Maks. %SMYS | Min. Basınç (Bar) | Min. %SMYS"
            parser={parseMeasurementsPaste}
            hasExistingRows={meas.length > 0}
            onApplyRows={(newRows, replace) =>
              onChange({
                ...draft,
                test_data: { ...td, test_measurements: replace ? newRows : [...meas, ...newRows] },
              })
            }
          />

          <div
            tabIndex={0}
            role="region"
            aria-label="Test Ölçüm Noktaları Tablosu"
            onPaste={onPasteMeasurements}
            className="table-wrap table-sticky max-h-[320px] overflow-auto scroll-thin"
          >
            <table className="data">
              <thead>
                <tr>
                  <th className="sticky-col num">Boru Üst Kotu (m)</th>
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
                      <td className="sticky-col num">
                        <CellInput
                          value={numVal(row, "pipe_top_elev_m")}
                          onChange={(v) =>
                            updateRow(
                              "test_measurements",
                              idx,
                              { pipe_top_elev_m: parseCellNum(v) },
                              "test_data",
                            )
                          }
                          ariaLabel={`Kot ${idx + 1}`}
                          className="w-20"
                          type="number"
                        />
                      </td>
                      <td className="num">
                        <CellInput
                          value={numVal(row, "station_m")}
                          onChange={(v) =>
                            updateRow(
                              "test_measurements",
                              idx,
                              { station_m: parseCellNum(v) },
                              "test_data",
                            )
                          }
                          ariaLabel={`Nokta ${idx + 1}`}
                          className="w-20"
                          type="number"
                        />
                      </td>
                      <td className="num">
                        <CellInput
                          value={numVal(row, "max_pressure_bar")}
                          onChange={(v) =>
                            updateRow(
                              "test_measurements",
                              idx,
                              { max_pressure_bar: parseCellNum(v) },
                              "test_data",
                            )
                          }
                          ariaLabel={`Maks basınç ${idx + 1}`}
                          className="w-20"
                          type="number"
                        />
                      </td>
                      <td className="num">
                        <CellInput
                          value={numVal(row, "max_smys_pct")}
                          onChange={(v) =>
                            updateRow(
                              "test_measurements",
                              idx,
                              { max_smys_pct: parseCellNum(v) },
                              "test_data",
                            )
                          }
                          ariaLabel={`Maks SMYS ${idx + 1}`}
                          className="w-16"
                          type="number"
                        />
                      </td>
                      <td className="num">
                        <CellInput
                          value={numVal(row, "min_pressure_bar")}
                          onChange={(v) =>
                            updateRow(
                              "test_measurements",
                              idx,
                              { min_pressure_bar: parseCellNum(v) },
                              "test_data",
                            )
                          }
                          ariaLabel={`Min basınç ${idx + 1}`}
                          className="w-20"
                          type="number"
                        />
                      </td>
                      <td className="num">
                        <CellInput
                          value={numVal(row, "min_smys_pct")}
                          onChange={(v) =>
                            updateRow(
                              "test_measurements",
                              idx,
                              { min_smys_pct: parseCellNum(v) },
                              "test_data",
                            )
                          }
                          ariaLabel={`Min SMYS ${idx + 1}`}
                          className="w-16"
                          type="number"
                        />
                      </td>
                      <td className="num">
                        <button
                          type="button"
                          onClick={() => removeRow("test_measurements", idx, "test_data")}
                          className="rounded p-1 text-[var(--text-faint)] hover:bg-[var(--danger-bg)] hover:text-[var(--danger)]"
                          aria-label={`Ölçüm ${idx + 1} sil`}
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
      </div>
    );
  }

  /* ---------------------------------------------------------------- */
  /* 016, 023, KUR-001, KUR-002 — PİG İZLEME & KURUTMA DEW POINT      */
  /* ---------------------------------------------------------------- */
  if (
    formCode === "cleaning" ||
    formCode === "dewatering" ||
    formCode === "pre_drying" ||
    formCode === "final_drying"
  ) {
    const runs = toList(draft.pig_runs);
    const drying = toRecord(draft.drying);
    const isDrying = formCode === "pre_drying" || formCode === "final_drying";

    return (
      <div className="space-y-4">
        {isDrying ? (
          <div className="grid gap-2 sm:grid-cols-3">
            <label className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-2">
              <span className="block text-[10px] font-medium text-[var(--text-muted)]">
                Hedef Çiğlenme Noktası (°C)
              </span>
              <CellInput
                type="number"
                value={numVal(drying, "target_dew_point_c") || "-20"}
                onChange={(v) => setNestedKey("drying", "target_dew_point_c", parseCellNum(v))}
                ariaLabel="Hedef dew point"
                align="left"
                className="mt-1 w-full"
              />
            </label>
            <label className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-2">
              <span className="block text-[10px] font-medium text-[var(--text-muted)]">
                Ölçülen Çiğlenme Noktası (°C)
              </span>
              <CellInput
                type="number"
                value={numVal(drying, "measured_dew_point_c")}
                onChange={(v) => setNestedKey("drying", "measured_dew_point_c", parseCellNum(v))}
                ariaLabel="Ölçülen dew point"
                align="left"
                className="mt-1 w-full"
              />
            </label>
            <label className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-2">
              <span className="block text-[10px] font-medium text-[var(--text-muted)]">
                Kurutma Süresi (Saat)
              </span>
              <CellInput
                type="number"
                value={numVal(drying, "duration_hours")}
                onChange={(v) => setNestedKey("drying", "duration_hours", parseCellNum(v))}
                ariaLabel="Kurutma süresi"
                align="left"
                className="mt-1 w-full"
              />
            </label>
          </div>
        ) : null}

        <div className="space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-[11px] font-bold uppercase tracking-wider text-[var(--primary)]">
              Pig İzleme Tablosu
            </span>
            <Button
              size="sm"
              variant="ghost"
              icon={<Plus size={12} />}
              onClick={() =>
                addRow("pig_runs", {
                  pig_type: "Fırçalı / Köpük Pig",
                  launch_time: "08:00",
                  receive_time: "09:15",
                  duration_min: 75,
                  note: "",
                })
              }
            >
              Pig Seferi Ekle
            </Button>
          </div>

          <PasteRowsTray
            hint="Pig Tipi | Atılış Saati (SS:DD) | Alınış Saati (SS:DD) | Süre (dk) | Not"
            parser={parsePigRunsPaste}
            hasExistingRows={runs.length > 0}
            onApplyRows={(newRows, replace) =>
              onChange({ ...draft, pig_runs: replace ? newRows : [...runs, ...newRows] })
            }
          />

          <div
            tabIndex={0}
            role="region"
            aria-label="Pig İzleme Tablosu"
            onPaste={onPastePigRuns}
            className="table-wrap table-sticky max-h-[300px] overflow-auto scroll-thin"
          >
            <table className="data">
              <thead>
                <tr>
                  <th className="sticky-col">Pig Tipi</th>
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
                      <td className="sticky-col">
                        <CellInput
                          value={strVal(row, "pig_type")}
                          onChange={(v) => updateRow("pig_runs", idx, { pig_type: v })}
                          ariaLabel={`Pig tipi ${idx + 1}`}
                          align="left"
                          className="w-36"
                        />
                      </td>
                      <td>
                        <CellInput
                          value={strVal(row, "launch_time")}
                          onChange={(v) => updateRow("pig_runs", idx, { launch_time: v })}
                          ariaLabel={`Atılış ${idx + 1}`}
                          align="left"
                          className="w-20"
                        />
                      </td>
                      <td>
                        <CellInput
                          value={strVal(row, "receive_time")}
                          onChange={(v) => updateRow("pig_runs", idx, { receive_time: v })}
                          ariaLabel={`Alınış ${idx + 1}`}
                          align="left"
                          className="w-20"
                        />
                      </td>
                      <td className="num">
                        <CellInput
                          type="number"
                          value={numVal(row, "duration_min")}
                          onChange={(v) =>
                            updateRow("pig_runs", idx, { duration_min: parseCellNum(v) })
                          }
                          ariaLabel={`Süre ${idx + 1}`}
                          className="w-20"
                        />
                      </td>
                      <td>
                        <CellInput
                          value={strVal(row, "note")}
                          onChange={(v) => updateRow("pig_runs", idx, { note: v })}
                          ariaLabel={`Pig not ${idx + 1}`}
                          align="left"
                          className="w-28"
                        />
                      </td>
                      <td className="num">
                        <button
                          type="button"
                          onClick={() => removeRow("pig_runs", idx)}
                          className="rounded p-1 text-[var(--text-faint)] hover:bg-[var(--danger-bg)] hover:text-[var(--danger)]"
                          aria-label={`Pig ${idx + 1} sil`}
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
          <label
            key={String(k)}
            className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-2.5"
          >
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
