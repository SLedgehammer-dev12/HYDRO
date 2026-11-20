import { useId } from "react";
import { AlertTriangle, Plus, Trash2 } from "lucide-react";
import { num } from "../../lib/format";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { InlineNotice } from "../../components/ui/State";
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
import {
  parseCellNum,
  parseFillingPaste,
  parseMonitoringPaste,
  parsePressurizationPaste,
} from "./pasteUtils";

export function MonitoringFormEditor({
  formCode,
  draft,
  onChange,
  setNestedKey,
  addRow,
  updateRow,
  removeRow,
}: {
  formCode: "filling" | "leak_stabilization" | "pressure_test" | "strength" | "pressurization";
  draft: DraftData;
  onChange: (next: DraftData) => void;
  setNestedKey: (sectionKey: string, fieldKey: string, value: unknown) => void;
  addRow: (listKey: string, template: Record<string, unknown>, nestedParent?: string) => void;
  updateRow: (
    listKey: string,
    index: number,
    patch: Record<string, unknown>,
    nestedParent?: string,
  ) => void;
  removeRow: (listKey: string, index: number, nestedParent?: string) => void;
}) {
  const monId = useId();
  const rows = toList(draft.rows);

  function applyPastedRows(newRows: Array<Record<string, unknown>>, replace: boolean) {
    onChange({
      ...draft,
      rows: replace ? newRows : [...rows, ...newRows],
    });
  }

  const onPasteFilling = useTableClipboardPaste(parseFillingPaste, (r) =>
    applyPastedRows(r, false),
  );
  const onPasteMonitoring = useTableClipboardPaste(parseMonitoringPaste, (r) =>
    applyPastedRows(r, false),
  );
  const onPastePressurization = useTableClipboardPaste(parsePressurizationPaste, (r) =>
    applyPastedRows(r, false),
  );

  /* ---------------------------------------------------------------- */
  /* 017 — SU DOLUM RAPORU                                             */
  /* ---------------------------------------------------------------- */
  if (formCode === "filling") {
    const filling = toRecord(draft.filling);
    const fillingCold = typeof filling.min_temp_c === "number" && filling.min_temp_c < 2;
    return (
      <div className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap gap-2 text-[11px]">
            <Badge tone="info">
              Toplam Dolum:{" "}
              {typeof filling.total_filled_m3 === "number"
                ? `${num(filling.total_filled_m3, 2)} m³`
                : "—"}
            </Badge>
            <Badge tone={fillingCold ? "fail" : "neutral"}>
              Su Sıcaklığı:{" "}
              {typeof filling.min_temp_c === "number"
                ? `${num(filling.min_temp_c, 1)}–${num(filling.max_temp_c as number, 1)} °C`
                : "—"}
            </Badge>
            <Badge tone="neutral">Satır: {rows.length}</Badge>
          </div>
          <Button
            size="sm"
            variant="ghost"
            icon={<Plus size={12} />}
            onClick={() =>
              addRow("rows", {
                time_str: "08:00",
                meter_reading_m3: null,
                delta_volume_m3: null,
                total_volume_m3: null,
                water_inlet_temp_c: null,
                water_pressure_bar: null,
                note: "",
              })
            }
          >
            Saat Satırı Ekle
          </Button>
        </div>

        {fillingCold ? (
          <InlineNotice tone="danger" title="Şartname 10.1 — +2 °C dolum kısıtı" icon={AlertTriangle}>
            Form 017 su dolum kayıtlarında minimum sıcaklık ({num(filling.min_temp_c as number, 1)} °C)
            +2 °C sınırının altında görünüyor. Dolum öncesi ortam ve su sıcaklığını doğrulayın.
          </InlineNotice>
        ) : null}

        <PasteRowsTray
          hint="Saat | Sayaç (m³) | Hacim Farkı (m³) | Toplam Hacim (m³) | Su Sıcaklığı (°C) | Su Basıncı (Bar)"
          parser={parseFillingPaste}
          hasExistingRows={rows.length > 0}
          onApplyRows={applyPastedRows}
        />

        <div
          role="region"
          aria-label="Su Dolum Saatlik İzleme Tablosu"
          onPaste={onPasteFilling}
          className="table-wrap table-sticky max-h-[360px] overflow-auto scroll-thin"
        >
          <table className="data">
            <thead>
              <tr>
                <th className="sticky-col">Okuma Saati</th>
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
                    Saatlik su dolum satırı yok. Doküman tarayın, Excel&apos;den yapıştırın veya satır ekleyin.
                  </td>
                </tr>
              ) : (
                rows.map((row, idx) => (
                  <tr key={idx}>
                    <td className="sticky-col">
                      <CellInput
                        value={strVal(row, "time_str")}
                        onChange={(v) => updateRow("rows", idx, { time_str: v })}
                        ariaLabel={`Saat ${idx + 1}`}
                        align="left"
                        className="w-16"
                      />
                    </td>
                    <td className="num">
                      <CellInput
                        type="number"
                        value={numVal(row, "meter_reading_m3")}
                        onChange={(v) =>
                          updateRow("rows", idx, { meter_reading_m3: parseCellNum(v) })
                        }
                        ariaLabel={`Sayaç ${idx + 1}`}
                        className="w-24"
                      />
                    </td>
                    <td className="num">
                      <CellInput
                        type="number"
                        value={numVal(row, "delta_volume_m3")}
                        onChange={(v) =>
                          updateRow("rows", idx, { delta_volume_m3: parseCellNum(v) })
                        }
                        ariaLabel={`Hacim farkı ${idx + 1}`}
                        className="w-20"
                      />
                    </td>
                    <td className="num">
                      <CellInput
                        type="number"
                        value={numVal(row, "total_volume_m3")}
                        onChange={(v) =>
                          updateRow("rows", idx, { total_volume_m3: parseCellNum(v) })
                        }
                        ariaLabel={`Toplam ${idx + 1}`}
                        className="w-24"
                      />
                    </td>
                    <td className="num">
                      <CellInput
                        type="number"
                        value={numVal(row, "water_inlet_temp_c")}
                        onChange={(v) =>
                          updateRow("rows", idx, { water_inlet_temp_c: parseCellNum(v) })
                        }
                        ariaLabel={`Sıcaklık ${idx + 1}`}
                        className="w-16"
                      />
                    </td>
                    <td className="num">
                      <CellInput
                        type="number"
                        value={numVal(row, "water_pressure_bar")}
                        onChange={(v) =>
                          updateRow("rows", idx, { water_pressure_bar: parseCellNum(v) })
                        }
                        ariaLabel={`Basınç ${idx + 1}`}
                        className="w-16"
                      />
                    </td>
                    <td>
                      <CellInput
                        value={strVal(row, "note")}
                        onChange={(v) => updateRow("rows", idx, { note: v })}
                        ariaLabel={`Not ${idx + 1}`}
                        align="left"
                        className="w-24"
                      />
                    </td>
                    <td className="num">
                      <button
                        type="button"
                        onClick={() => removeRow("rows", idx)}
                        className="rounded p-1 text-[var(--text-faint)] hover:bg-[var(--danger-bg)] hover:text-[var(--danger)]"
                        aria-label={`Satır ${idx + 1} sil`}
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
    );
  }

  /* ---------------------------------------------------------------- */
  /* 018 & 021 — DENGELEME KAÇAK / BASINÇ TESTİ (24 SAATLİK İZLEME)    */
  /* ---------------------------------------------------------------- */
  if (formCode === "leak_stabilization" || formCode === "pressure_test") {
    const mon = toRecord(draft.monitoring);
    const tlog = toRecord(draft.time_log);
    return (
      <div className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap gap-2 text-[11px]">
            <Badge tone="info">
              Süre:{" "}
              {typeof tlog.duration_hours === "number"
                ? `${num(tlog.duration_hours, 1)} sa`
                : `${rows.length} satır`}
            </Badge>
            <Badge tone="neutral">
              Basınç:{" "}
              {typeof mon.p_start_bar === "number"
                ? `${num(mon.p_start_bar, 2)} → ${num(mon.p_end_bar as number, 2)} Bar`
                : "—"}
            </Badge>
            <Badge
              tone={
                typeof mon.last_4h_delta_c === "number"
                  ? mon.last_4h_delta_c <= 0.5
                    ? "pass"
                    : "fail"
                  : "neutral"
              }
            >
              Son 4s ΔT:{" "}
              {typeof mon.last_4h_delta_c === "number"
                ? `${num(mon.last_4h_delta_c, 3)} °C`
                : "—"}
            </Badge>
          </div>
          <Button
            size="sm"
            variant="ghost"
            icon={<Plus size={12} />}
            onClick={() =>
              addRow("rows", {
                time_str: "08:00",
                pressure_bar: null,
                ambient_temp_c: null,
                soil_1_c: null,
                pipe_1_c: null,
                soil_2_c: null,
                pipe_2_c: null,
                avg_soil_c: null,
                avg_pipe_c: null,
              })
            }
          >
            Saat Satırı Ekle
          </Button>
        </div>

        <PasteRowsTray
          hint="Zaman | Basınç (Bar) | Çevre (°C) | Toprak 1 | Boru 1 | Toprak 2 | Boru 2 | Ort. Toprak | Ort. Boru"
          parser={parseMonitoringPaste}
          hasExistingRows={rows.length > 0}
          onApplyRows={applyPastedRows}
        />

        <div
          role="region"
          aria-label="Saatlik Basınç ve Sıcaklık İzleme Tablosu"
          onPaste={onPasteMonitoring}
          className="table-wrap table-sticky max-h-[360px] overflow-auto scroll-thin"
        >
          <table className="data">
            <thead>
              <tr>
                <th className="sticky-col">Zaman</th>
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
                    Saatlik izleme kaydı yok. Özet: {rows.length} satır, P=
                    {strVal(mon, "p_start_bar") || "—"}→{strVal(mon, "p_end_bar") || "—"} bar.
                  </td>
                </tr>
              ) : (
                rows.map((row, idx) => (
                  <tr key={idx}>
                    <td className="sticky-col">
                      <CellInput
                        value={strVal(row, "time_str")}
                        onChange={(v) => updateRow("rows", idx, { time_str: v })}
                        ariaLabel={`Saat ${idx + 1}`}
                        align="left"
                        className="w-16"
                      />
                    </td>
                    <td className="num">
                      <CellInput
                        type="number"
                        value={numVal(row, "pressure_bar")}
                        onChange={(v) =>
                          updateRow("rows", idx, { pressure_bar: parseCellNum(v) })
                        }
                        ariaLabel={`Basınç ${idx + 1}`}
                        className="w-20"
                      />
                    </td>
                    <td className="num">
                      <CellInput
                        type="number"
                        value={numVal(row, "ambient_temp_c")}
                        onChange={(v) =>
                          updateRow("rows", idx, { ambient_temp_c: parseCellNum(v) })
                        }
                        ariaLabel={`Çevre T ${idx + 1}`}
                        className="w-16"
                      />
                    </td>
                    <td className="num">
                      <CellInput
                        type="number"
                        value={numVal(row, "soil_1_c")}
                        onChange={(v) => updateRow("rows", idx, { soil_1_c: parseCellNum(v) })}
                        ariaLabel={`Toprak 1 ${idx + 1}`}
                        className="w-16"
                      />
                    </td>
                    <td className="num">
                      <CellInput
                        type="number"
                        value={numVal(row, "pipe_1_c")}
                        onChange={(v) => updateRow("rows", idx, { pipe_1_c: parseCellNum(v) })}
                        ariaLabel={`Boru 1 ${idx + 1}`}
                        className="w-16"
                      />
                    </td>
                    <td className="num">
                      <CellInput
                        type="number"
                        value={numVal(row, "soil_2_c")}
                        onChange={(v) => updateRow("rows", idx, { soil_2_c: parseCellNum(v) })}
                        ariaLabel={`Toprak 2 ${idx + 1}`}
                        className="w-16"
                      />
                    </td>
                    <td className="num">
                      <CellInput
                        type="number"
                        value={numVal(row, "pipe_2_c")}
                        onChange={(v) => updateRow("rows", idx, { pipe_2_c: parseCellNum(v) })}
                        ariaLabel={`Boru 2 ${idx + 1}`}
                        className="w-16"
                      />
                    </td>
                    <td className="num">
                      <CellInput
                        type="number"
                        value={numVal(row, "avg_soil_c")}
                        onChange={(v) => updateRow("rows", idx, { avg_soil_c: parseCellNum(v) })}
                        ariaLabel={`Ort toprak ${idx + 1}`}
                        className="w-16"
                      />
                    </td>
                    <td className="num">
                      <CellInput
                        type="number"
                        value={numVal(row, "avg_pipe_c")}
                        onChange={(v) => updateRow("rows", idx, { avg_pipe_c: parseCellNum(v) })}
                        ariaLabel={`Ort boru ${idx + 1}`}
                        className="w-16"
                      />
                    </td>
                    <td className="num">
                      <button
                        type="button"
                        onClick={() => removeRow("rows", idx)}
                        className="rounded p-1 text-[var(--text-faint)] hover:bg-[var(--danger-bg)] hover:text-[var(--danger)]"
                        aria-label={`Satır ${idx + 1} sil`}
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
    );
  }

  /* ---------------------------------------------------------------- */
  /* 019 & EK-014 — MUKAVEMET / BASINÇLANDIRMA TEST RAPORU             */
  /* ---------------------------------------------------------------- */
  const pr = toRecord(draft.pressurization);
  return (
    <div className="space-y-3">
      <div className="grid gap-2 sm:grid-cols-3">
        <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-2">
          <label
            htmlFor={`${monId}-vp`}
            className="block text-[10px] font-medium text-[var(--text-muted)]"
          >
            Hava Testi Teorik Vp (m³)
          </label>
          <CellInput
            id={`${monId}-vp`}
            type="number"
            value={numVal(pr, "vp_m3")}
            onChange={(v) => setNestedKey("pressurization", "vp_m3", parseCellNum(v))}
            ariaLabel="Vp (m3)"
            align="left"
            className="mt-1 w-full"
          />
        </div>
        <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-2">
          <label
            htmlFor={`${monId}-vpa`}
            className="block text-[10px] font-medium text-[var(--text-muted)]"
          >
            Ölçülen VpA (m³)
          </label>
          <CellInput
            id={`${monId}-vpa`}
            type="number"
            value={numVal(pr, "vpa_m3")}
            onChange={(v) => setNestedKey("pressurization", "vpa_m3", parseCellNum(v))}
            ariaLabel="VpA (m3)"
            align="left"
            className="mt-1 w-full"
          />
        </div>
        <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-2">
          <label
            htmlFor={`${monId}-water`}
            className="block text-[10px] font-medium text-[var(--text-muted)]"
          >
            İlave Test Suyu Toplam (m³)
          </label>
          <CellInput
            id={`${monId}-water`}
            type="number"
            value={numVal(pr, "total_added_water_m3")}
            onChange={(v) =>
              setNestedKey("pressurization", "total_added_water_m3", parseCellNum(v))
            }
            ariaLabel="İlave su (m3)"
            align="left"
            className="mt-1 w-full"
          />
        </div>
      </div>

      <div className="flex items-center justify-between">
        <span className="text-[11px] font-bold uppercase tracking-wider text-[var(--primary)]">
          Basınç Artışı (P-V) Adımları
        </span>
        <Button
          size="sm"
          variant="ghost"
          icon={<Plus size={12} />}
          onClick={() =>
            addRow("rows", {
              time_str: "10:00",
              p_initial_bar: null,
              p_final_bar: null,
              step_water_m3: null,
              total_water_m3: null,
              water_temp_c: null,
              note: "",
            })
          }
        >
          Adım Ekle
        </Button>
      </div>

      <PasteRowsTray
        hint="Saat | İlk Basınç (Bar) | Son Basınç (Bar) | Kullanılan Su (m³) | Toplam Su (m³) | Su Sıcaklığı (°C)"
        parser={parsePressurizationPaste}
        hasExistingRows={rows.length > 0}
        onApplyRows={applyPastedRows}
      />

      <div
        role="region"
        aria-label="Basınç Artışı P-V Adımları Tablosu"
        onPaste={onPastePressurization}
        className="table-wrap table-sticky max-h-[320px] overflow-auto scroll-thin"
      >
        <table className="data">
          <thead>
            <tr>
              <th className="sticky-col">Saat</th>
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
                  <td className="sticky-col">
                    <CellInput
                      value={strVal(row, "time_str")}
                      onChange={(v) => updateRow("rows", idx, { time_str: v })}
                      ariaLabel={`Saat ${idx + 1}`}
                      align="left"
                      className="w-16"
                    />
                  </td>
                  <td className="num">
                    <CellInput
                      type="number"
                      value={numVal(row, "p_initial_bar")}
                      onChange={(v) =>
                        updateRow("rows", idx, { p_initial_bar: parseCellNum(v) })
                      }
                      ariaLabel={`İlk basınç ${idx + 1}`}
                      className="w-20"
                    />
                  </td>
                  <td className="num">
                    <CellInput
                      type="number"
                      value={numVal(row, "p_final_bar")}
                      onChange={(v) => updateRow("rows", idx, { p_final_bar: parseCellNum(v) })}
                      ariaLabel={`Son basınç ${idx + 1}`}
                      className="w-20"
                    />
                  </td>
                  <td className="num">
                    <CellInput
                      type="number"
                      value={numVal(row, "step_water_m3")}
                      onChange={(v) =>
                        updateRow("rows", idx, { step_water_m3: parseCellNum(v) })
                      }
                      ariaLabel={`Adım su ${idx + 1}`}
                      className="w-20"
                    />
                  </td>
                  <td className="num">
                    <CellInput
                      type="number"
                      value={numVal(row, "total_water_m3")}
                      onChange={(v) =>
                        updateRow("rows", idx, { total_water_m3: parseCellNum(v) })
                      }
                      ariaLabel={`Toplam su ${idx + 1}`}
                      className="w-20"
                    />
                  </td>
                  <td className="num">
                    <CellInput
                      type="number"
                      value={numVal(row, "water_temp_c")}
                      onChange={(v) => updateRow("rows", idx, { water_temp_c: parseCellNum(v) })}
                      ariaLabel={`Su T ${idx + 1}`}
                      className="w-16"
                    />
                  </td>
                  <td className="num">
                    <button
                      type="button"
                      onClick={() => removeRow("rows", idx)}
                      className="rounded p-1 text-[var(--text-faint)] hover:bg-[var(--danger-bg)] hover:text-[var(--danger)]"
                      aria-label={`Adım ${idx + 1} sil`}
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
  );
}
