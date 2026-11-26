import { useEffect, useId, useMemo, useRef, useState, type FormEvent } from "react";
import {
  Activity,
  ArrowDownToLine,
  ArrowUpFromLine,
  ClipboardPaste,
  Plus,
  Trash2,
} from "lucide-react";
import { TimeSeriesChart } from "../../components/charts/LazyCharts";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { ResultTile } from "../../components/ui/Card";
import { DecisionCard } from "../../components/ui/DecisionCard";
import { InlineNotice, OfflineNotice } from "../../components/ui/State";
import {
  useAddTimeSeries,
  useBatchTimeSeries,
  useClearTimeSeries,
  useDeleteTimeSeries,
  useSyncTimeSeriesForm,
  useThermalBalance,
  useTimeSeries,
  useTimeSeriesSummary,
} from "../../hooks/queries";
import { apiErrorMessage } from "../../lib/api";
import { num, parseNumber, round } from "../../lib/format";
import {
  formatTsShort,
  parseTimeSeriesPaste,
  parseUtcDateTimeInputValue,
  toUtcDateTimeInputValue,
} from "../../lib/timeSeriesParse";
import type {
  ThermalBalanceResponse,
  TimeSeriesRecordInput,
  TimeSeriesRecordItem,
  TimeSeriesSummary,
} from "../../lib/types";
import { useAppStore } from "../../store/useAppStore";
import { SaveResultButton } from "./SaveResultButton";

export interface TimeSeriesPanelProps {
  online: boolean;
  formContext?: "leak_stabilization" | "pressure_test";
  formDirty?: boolean;
}

const VIRTUALIZE_THRESHOLD = 80;
const VIRTUAL_ROW_HEIGHT = 34;
const VIRTUAL_VIEWPORT_ROWS = 12;
const VIRTUAL_OVERSCAN = 8;

interface FieldErrors {
  timestamp?: string;
  pressure?: string;
  temperature?: string;
  volume?: string;
}

function validateTimestampInput(raw: string): string | undefined {
  if (!raw.trim()) return "Zaman damgası gerekli.";
  if (parseUtcDateTimeInputValue(raw) === null) return "Geçerli bir tarih ve saat girin (UTC).";
  return undefined;
}

function validateFiniteInput(
  raw: string,
  label: string,
  required: boolean,
): { value: number | null; error?: string } {
  const trimmed = raw.trim();
  if (!trimmed) {
    return required ? { value: null, error: `${label} gerekli.` } : { value: null };
  }
  const parsed = parseNumber(trimmed);
  if (parsed === null || !Number.isFinite(parsed)) {
    return { value: null, error: `${label} geçerli bir sayı olmalı.` };
  }
  return { value: parsed };
}

export function TimeSeriesPanel({ online, formContext, formDirty = false }: TimeSeriesPanelProps) {
  const uid = useId();
  const addHeadingId = `${uid}-add-heading`;
  const tsId = `${uid}-ts`;
  const tsErrId = `${uid}-ts-err`;
  const pId = `${uid}-p`;
  const pErrId = `${uid}-p-err`;
  const tId = `${uid}-t`;
  const tErrId = `${uid}-t-err`;
  const vId = `${uid}-v`;
  const vErrId = `${uid}-v-err`;
  const notesId = `${uid}-notes`;
  const pastePanelId = `${uid}-paste-panel`;
  const pasteTextId = `${uid}-paste-text`;
  const modeGroupName = `${uid}-paste-mode`;
  const tableCaptionId = `${uid}-table-caption`;

  const tsInputRef = useRef<HTMLInputElement | null>(null);
  const pInputRef = useRef<HTMLInputElement | null>(null);
  const tInputRef = useRef<HTMLInputElement | null>(null);
  const vInputRef = useRef<HTMLInputElement | null>(null);

  const sessionId = useAppStore((state) => state.sessionId);
  const sessionApiReady = useAppStore((state) => state.sessionApiReady);
  const sectionTestDate = useAppStore((state) => state.inputs.section_meta?.test_date);
  const patchInputs = useAppStore((state) => state.patchInputs);
  const pushToast = useAppStore((state) => state.pushToast);

  const persistedMode = online && sessionApiReady !== false && Boolean(sessionId);
  const listQuery = useTimeSeries(persistedMode ? sessionId : null);
  const summaryQuery = useTimeSeriesSummary(persistedMode ? sessionId : null);
  const addMutation = useAddTimeSeries(sessionId);
  const batchMutation = useBatchTimeSeries(sessionId);
  const deleteMutation = useDeleteTimeSeries(sessionId);
  const clearMutation = useClearTimeSeries(sessionId);
  const syncFormMutation = useSyncTimeSeriesForm(sessionId);
  const {
    mutate: mutateThermal,
    reset: resetThermal,
  } = useThermalBalance();

  const [localRecords, setLocalRecords] = useState<TimeSeriesRecordItem[]>([]);
  const [adHocSummary, setAdHocSummary] = useState<ThermalBalanceResponse | null>(null);
  const [tableScrollTop, setTableScrollTop] = useState<number>(0);

  const [timestampInput, setTimestampInput] = useState<string>(() => toUtcDateTimeInputValue());
  const [pressureInput, setPressureInput] = useState<string>("");
  const [tempInput, setTempInput] = useState<string>("");
  const [volumeInput, setVolumeInput] = useState<string>("");
  const [notesInput, setNotesInput] = useState<string>("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [formStatus, setFormStatus] = useState<string>("");

  const [showPaste, setShowPaste] = useState<boolean>(false);
  const [pasteText, setPasteText] = useState<string>("");
  const [pasteMode, setPasteMode] = useState<"append" | "replace">("append");
  const [pasteError, setPasteError] = useState<string | null>(null);
  const [confirmClear, setConfirmClear] = useState<boolean>(false);
  const [pendingOverwriteForm, setPendingOverwriteForm] = useState<
    "leak_stabilization" | "pressure_test" | null
  >(null);

  const lastEvaluatedKeyRef = useRef<string>("");

  useEffect(() => {
    setConfirmClear(false);
    setPendingOverwriteForm(null);
    setFieldErrors({});
    setFormStatus("");
    setPasteError(null);
    setShowPaste(false);
    setPasteText("");
    setLocalRecords([]);
    setAdHocSummary(null);
    setTableScrollTop(0);
    setTimestampInput(toUtcDateTimeInputValue());
    lastEvaluatedKeyRef.current = "";
    resetThermal();
  }, [sessionId, resetThermal]);

  useEffect(() => {
    if (persistedMode || !online || localRecords.length === 0) {
      lastEvaluatedKeyRef.current = "";
      return;
    }
    const key = JSON.stringify(
      localRecords.map((r) => [r.timestamp, r.pressure_bar, r.temperature_c, r.volume_m3]),
    );
    if (lastEvaluatedKeyRef.current === key) return;
    lastEvaluatedKeyRef.current = key;
    const payload: TimeSeriesRecordInput[] = localRecords.map((row) => ({
      timestamp: row.timestamp,
      pressure_bar: row.pressure_bar,
      temperature_c: row.temperature_c,
      volume_m3: row.volume_m3,
      notes: row.notes,
    }));
    mutateThermal(payload, {
      onSuccess: (res) => setAdHocSummary(res),
      onError: (err) => pushToast("error", "Termal denge hesaplanamadı", apiErrorMessage(err)),
    });
  }, [persistedMode, online, localRecords, mutateThermal, pushToast]);

  const records = useMemo(() => {
    const raw = persistedMode ? (listQuery.data?.items ?? []) : localRecords;
    return [...raw].sort(
      (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
    );
  }, [persistedMode, listQuery.data?.items, localRecords]);

  const isVirtualized = records.length > VIRTUALIZE_THRESHOLD;
  const { visibleRecords, topSpacerHeight, bottomSpacerHeight } = useMemo(() => {
    if (!isVirtualized) {
      return { visibleRecords: records, topSpacerHeight: 0, bottomSpacerHeight: 0 };
    }
    const startIdx = Math.max(
      0,
      Math.floor(tableScrollTop / VIRTUAL_ROW_HEIGHT) - VIRTUAL_OVERSCAN,
    );
    const endIdx = Math.min(
      records.length,
      startIdx + VIRTUAL_VIEWPORT_ROWS + VIRTUAL_OVERSCAN * 2,
    );
    return {
      visibleRecords: records.slice(startIdx, endIdx),
      topSpacerHeight: startIdx * VIRTUAL_ROW_HEIGHT,
      bottomSpacerHeight: Math.max(0, (records.length - endIdx) * VIRTUAL_ROW_HEIGHT),
    };
  }, [isVirtualized, records, tableScrollTop]);

  const summary: TimeSeriesSummary | undefined = persistedMode
    ? summaryQuery.data
    : (adHocSummary ?? undefined);

  const savePayload = useMemo(() => {
    if (records.length === 0) return null;
    return {
      records: records.map((row) => ({
        timestamp: row.timestamp,
        pressure_bar: row.pressure_bar,
        temperature_c: row.temperature_c,
        volume_m3: row.volume_m3,
        notes: row.notes,
      })),
    };
  }, [records]);

  const canApplyToPressure =
    summary !== undefined &&
    summary.initial_temperature_c !== null &&
    summary.final_temperature_c !== null &&
    summary.pressure_change_pa_bar !== null;

  function handleAddSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const tsErr = validateTimestampInput(timestampInput);
    const pCheck = validateFiniteInput(pressureInput, "Basınç", true);
    const tCheck = validateFiniteInput(tempInput, "Sıcaklık", true);
    const vCheck = validateFiniteInput(volumeInput, "Hacim", false);
    const nextErrors: FieldErrors = {
      timestamp: tsErr,
      pressure: pCheck.error,
      temperature: tCheck.error,
      volume: vCheck.error,
    };
    setFieldErrors(nextErrors);

    if (tsErr) {
      tsInputRef.current?.focus();
      setFormStatus(`Okuma eklenemedi: ${tsErr}`);
      return;
    }
    if (pCheck.error || pCheck.value === null) {
      pInputRef.current?.focus();
      setFormStatus(`Okuma eklenemedi: ${pCheck.error ?? "Basınç gerekli."}`);
      return;
    }
    if (tCheck.error || tCheck.value === null) {
      tInputRef.current?.focus();
      setFormStatus(`Okuma eklenemedi: ${tCheck.error ?? "Sıcaklık gerekli."}`);
      return;
    }
    if (vCheck.error) {
      vInputRef.current?.focus();
      setFormStatus(`Okuma eklenemedi: ${vCheck.error}`);
      return;
    }

    const isoTs = parseUtcDateTimeInputValue(timestampInput);
    if (!isoTs) {
      tsInputRef.current?.focus();
      setFormStatus("Okuma eklenemedi: Geçerli bir tarih ve saat girin (UTC).");
      return;
    }
    const recordInput: TimeSeriesRecordInput = {
      timestamp: isoTs,
      pressure_bar: pCheck.value,
      temperature_c: tCheck.value,
      volume_m3: vCheck.value,
      notes: notesInput.trim().slice(0, 500),
      source: "manual",
    };

    if (persistedMode) {
      addMutation.mutate(recordInput, {
        onSuccess: (res) => {
          setFormStatus(`Okuma kaydedildi (${formatTsShort(res.record.timestamp)}).`);
          setNotesInput("");
          setConfirmClear(false);
          pushToast("success", "Zaman serisi okuması eklendi");
        },
        onError: (err) => {
          const msg = apiErrorMessage(err);
          setFormStatus(msg);
          pushToast("error", "Okuma eklenemedi", msg);
        },
      });
      return;
    }

    const nextItem: TimeSeriesRecordItem = {
      id: `local-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      timestamp: isoTs,
      pressure_bar: recordInput.pressure_bar,
      temperature_c: recordInput.temperature_c,
      volume_m3: recordInput.volume_m3 ?? null,
      notes: recordInput.notes ?? "",
      source: "manual",
    };
    const nextList = [...localRecords, nextItem].sort(
      (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
    );
    setLocalRecords(nextList);
    setNotesInput("");
    setConfirmClear(false);
    setFormStatus(`Okuma listeye eklendi (${formatTsShort(nextItem.timestamp)}).`);
  }

  function handleApplyPaste() {
    const parsed = parseTimeSeriesPaste(pasteText, sectionTestDate || undefined);
    if (parsed.error) {
      setPasteError(parsed.error);
      return;
    }
    setPasteError(null);

    if (persistedMode) {
      batchMutation.mutate(
        { records: parsed.records, mode: pasteMode, source: "batch" },
        {
          onSuccess: (res) => {
            setPasteText("");
            setShowPaste(false);
            setConfirmClear(false);
            setFormStatus(`${res.inserted} okuma içe aktarıldı.`);
            pushToast("success", `${res.inserted} zaman serisi okuması içe aktarıldı`);
          },
          onError: (err) => {
            const msg = apiErrorMessage(err);
            setPasteError(msg);
            pushToast("error", "Toplu aktarım başarısız", msg);
          },
        },
      );
      return;
    }

    const newItems: TimeSeriesRecordItem[] = parsed.records.map((rec, idx) => ({
      id: `local-${Date.now()}-${idx}-${Math.random().toString(36).slice(2, 6)}`,
      timestamp: rec.timestamp ?? new Date().toISOString(),
      pressure_bar: rec.pressure_bar,
      temperature_c: rec.temperature_c,
      volume_m3: rec.volume_m3 ?? null,
      notes: rec.notes ?? "",
      source: rec.source ?? "batch",
    }));
    const nextList = (pasteMode === "replace" ? newItems : [...localRecords, ...newItems]).sort(
      (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
    );
    setLocalRecords(nextList);
    setPasteText("");
    setShowPaste(false);
    setConfirmClear(false);
    setFormStatus(`${newItems.length} okuma içe aktarıldı.`);
  }

  function handleDeleteRow(row: TimeSeriesRecordItem) {
    if (persistedMode) {
      deleteMutation.mutate(row.id, {
        onSuccess: () => pushToast("info", "Zaman serisi kaydı silindi"),
        onError: (err) => pushToast("error", "Kayıt silinemedi", apiErrorMessage(err)),
      });
      return;
    }
    const nextList = localRecords.filter((item) => item.id !== row.id);
    setLocalRecords(nextList);
    if (nextList.length === 0) {
      setAdHocSummary(null);
      resetThermal();
    }
  }

  function handleClearAll() {
    if (persistedMode) {
      clearMutation.mutate(undefined, {
        onSuccess: (res) => {
          setConfirmClear(false);
          setFormStatus(`${res.deleted} kayıt temizlendi.`);
          pushToast("info", "Zaman serisi temizlendi", `${res.deleted} kayıt silindi.`);
        },
        onError: (err) => pushToast("error", "Temizlenemedi", apiErrorMessage(err)),
      });
      return;
    }
    setLocalRecords([]);
    setAdHocSummary(null);
    setTableScrollTop(0);
    resetThermal();
    setConfirmClear(false);
    setFormStatus("Yerel okumalar temizlendi.");
  }

  function handleApplyToPressure() {
    if (
      !summary ||
      summary.initial_temperature_c === null ||
      summary.final_temperature_c === null ||
      summary.pressure_change_pa_bar === null
    ) {
      return;
    }
    const tInit = round(summary.initial_temperature_c, 3);
    const tFin = round(summary.final_temperature_c, 3);
    const dT = round(tInit - tFin, 3);
    const paVal = round(summary.pressure_change_pa_bar, 3);
    patchInputs({
      pressure: {
        t_initial_c: tInit,
        t_final_c: tFin,
        derive_delta_t: true,
        delta_t_c: dT,
        actual_pressure_change_bar: paVal,
      },
    });
    pushToast(
      "success",
      "Basınç testi girdilerine aktarıldı",
      `Tilk=${num(tInit, 2)} °C · Tson=${num(tFin, 2)} °C · Pa=${num(paVal, 3)} bar`,
    );
  }

  function handleSyncForm(
    formCode: "leak_stabilization" | "pressure_test",
    direction: "from_form" | "to_form",
    confirmedOverwrite = false,
  ) {
    if (direction === "to_form" && formDirty && !confirmedOverwrite) {
      setPendingOverwriteForm(formCode);
      return;
    }
    setPendingOverwriteForm(null);
    const label = formCode === "leak_stabilization" ? "Form 018" : "Form 021";
    syncFormMutation.mutate(
      { form_code: formCode, direction, mode: "replace" },
      {
        onSuccess: (res) => {
          if (direction === "from_form") {
            const skipText = res.skipped_rows > 0 ? ` (${res.skipped_rows} eksik satır atlandı)` : "";
            pushToast(
              "success",
              `${label} senkronizasyonu tamamlandı`,
              `${res.synced_count} okuma zaman serisine alındı${skipText}.`,
            );
          } else {
            const truncText =
              res.skipped_rows > 0
                ? ` (${res.skipped_rows} okuma 300 satır form sınırı nedeniyle atlandı)`
                : "";
            pushToast(
              res.skipped_rows > 0 ? "warning" : "success",
              `${label} senkronizasyonu tamamlandı`,
              `${res.synced_count} okuma ${label} satırlarına yazıldı ve kontroller güncellendi${truncText}.`,
            );
          }
        },
        onError: (err) => {
          pushToast("error", `${label} senkronizasyonu başarısız`, apiErrorMessage(err));
        },
      },
    );
  }

  const syncFormsOrder: Array<{
    code: "leak_stabilization" | "pressure_test";
    shortLabel: string;
  }> =
    formContext === "pressure_test"
      ? [
          { code: "pressure_test", shortLabel: "Form 021" },
          { code: "leak_stabilization", shortLabel: "Form 018" },
        ]
      : [
          { code: "leak_stabilization", shortLabel: "Form 018" },
          { code: "pressure_test", shortLabel: "Form 021" },
        ];

  const listTruncated = Boolean(
    persistedMode && listQuery.data && listQuery.data.total > records.length,
  );

  return (
    <div className="space-y-4">
      {!online ? (
        <OfflineNotice>
          Resmî Şartname Bölüm 12 (termal dengeleme) ve Bölüm 15.1 (24 saatlik test kaydı) kararları
          yalnızca sunucu bağlıyken hesaplanır.
        </OfflineNotice>
      ) : null}

      {persistedMode && (listQuery.isError || summaryQuery.isError) ? (
        <InlineNotice tone="danger" title="Zaman serisi verisi yüklenemedi">
          {apiErrorMessage((listQuery.error ?? summaryQuery.error) as Error)}
        </InlineNotice>
      ) : null}

      {listTruncated ? (
        <InlineNotice tone="warning" title="Tablo görüntüleme sınırı (1000 kayıt)">
          Sunucuda toplam {listQuery.data?.total} kayıt bulunuyor; tabloda ve grafikte ilk 1000 kayıt
          gösteriliyor. Özet KPI’lar tüm kayıtlar üzerinden hesaplanır.
        </InlineNotice>
      ) : null}

      {pendingOverwriteForm ? (
        <InlineNotice tone="warning" title="Formda kaydedilmemiş değişiklikler var">
          <span>
            {pendingOverwriteForm === "leak_stabilization" ? "Form 018" : "Form 021"} üzerinde
            kaydedilmemiş taslak değişiklikler zaman serisinden gelen satırlarla değiştirilecek.
          </span>
          <div className="mt-2 flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="primary"
              disabled={syncFormMutation.isPending}
              onClick={() => handleSyncForm(pendingOverwriteForm, "to_form", true)}
            >
              Evet, form satırlarını güncelle
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setPendingOverwriteForm(null)}>
              Vazgeç
            </Button>
          </div>
        </InlineNotice>
      ) : null}

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        <ResultTile
          label="İzleme süresi"
          value={summary ? num(summary.duration_hours, 2) : "—"}
          unit="sa"
          hint="Hedef ≥ 24,0 sa"
          tone={
            summary && summary.record_count >= 2
              ? summary.thermal_duration_ok
                ? "pass"
                : "fail"
              : undefined
          }
        />
        <ResultTile
          label="Son 4s ΔT"
          value={summary?.temp_diff_c !== null && summary?.temp_diff_c !== undefined ? num(summary.temp_diff_c, 3) : "—"}
          unit="°C"
          hint="Hedef ≤ 0,50 °C"
          tone={
            summary && summary.temp_diff_c !== null
              ? summary.balanced
                ? "pass"
                : "fail"
              : undefined
          }
        />
        <ResultTile
          label="Fiili Pa"
          value={
            summary?.pressure_change_pa_bar !== null && summary?.pressure_change_pa_bar !== undefined
              ? num(summary.pressure_change_pa_bar, 3)
              : "—"
          }
          unit="bar"
          hint={
            summary?.initial_pressure_bar !== null && summary?.final_pressure_bar !== null && summary
              ? `${num(summary.initial_pressure_bar, 2)} → ${num(summary.final_pressure_bar, 2)} bar`
              : "Pilk − Pson"
          }
        />
        <ResultTile
          label="Sıcaklık ΔT"
          value={
            summary?.temperature_change_dt_c !== null && summary?.temperature_change_dt_c !== undefined
              ? num(summary.temperature_change_dt_c, 3)
              : "—"
          }
          unit="°C"
          hint={
            summary?.initial_temperature_c !== null && summary?.final_temperature_c !== null && summary
              ? `${num(summary.initial_temperature_c, 2)} → ${num(summary.final_temperature_c, 2)} °C`
              : "Tilk − Tson"
          }
        />
        <ResultTile
          label="Maks. aralık"
          value={
            summary?.max_gap_hours !== null && summary?.max_gap_hours !== undefined
              ? num(summary.max_gap_hours, 2)
              : "—"
          }
          unit="sa"
          hint="Hedef ≤ 2,00 sa"
          tone={
            summary && summary.max_gap_hours !== null
              ? summary.recording_interval_ok
                ? "pass"
                : "fail"
              : undefined
          }
        />
        <ResultTile
          label="Kayıt sayısı"
          value={String(summary?.record_count ?? records.length)}
          unit="adet"
          hint={
            summary?.first_timestamp
              ? `${formatTsShort(summary.first_timestamp)} → ${formatTsShort(summary.last_timestamp)}`
              : "Veri bekleniyor"
          }
        />
      </div>

      {summary ? (
        <div className="grid gap-3 lg:grid-cols-2">
          <DecisionCard
            decision={summary.decision}
            testName="Termal Denge (Bölüm 12)"
            marginUnit="°C"
            compact
          />
          <DecisionCard
            decision={summary.recording_decision}
            testName="24 Saatlik Test Kaydı (Bölüm 15.1)"
            marginUnit="sa"
            compact
          />
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          variant="primary"
          disabled={!canApplyToPressure}
          icon={<Activity size={13} />}
          onClick={handleApplyToPressure}
        >
          Tilk, Tson ve Pa’yı Basınç Testine Aktar
        </Button>

        {persistedMode ? (
          <SaveResultButton
            testType="thermal_balance"
            payload={savePayload}
            decision={summary?.decision}
          />
        ) : null}

        {persistedMode
          ? syncFormsOrder.map(({ code, shortLabel }) => {
              const primaryContext = formContext === code;
              const variant = primaryContext ? "primary" : "ghost";
              return (
                <div key={code} className="inline-flex flex-wrap items-center gap-1">
                  <Button
                    size="sm"
                    variant={variant}
                    disabled={syncFormMutation.isPending}
                    icon={<ArrowDownToLine size={12} />}
                    onClick={() => handleSyncForm(code, "from_form")}
                  >
                    {`${shortLabel}'den çek`}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={records.length === 0 || syncFormMutation.isPending}
                    icon={<ArrowUpFromLine size={12} />}
                    onClick={() => handleSyncForm(code, "to_form")}
                  >
                    {`${shortLabel}'e yaz`}
                  </Button>
                </div>
              );
            })
          : null}
      </div>

      <TimeSeriesChart records={records} height={210} />

      <form
        onSubmit={handleAddSubmit}
        aria-labelledby={addHeadingId}
        noValidate
        className="space-y-3 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-3"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h4 id={addHeadingId} className="text-[12.5px] font-semibold text-[var(--text)]">
            Tekil Okuma Ekle (Bölüm 12 &amp; 15)
          </h4>
          <button
            type="button"
            aria-expanded={showPaste}
            aria-controls={pastePanelId}
            className="btn btn-ghost"
            onClick={() => setShowPaste((open) => !open)}
          >
            <ClipboardPaste size={13} aria-hidden />
            Toplu yapıştır (Excel / CSV)
          </button>
        </div>

        <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-5">
          <div className="flex flex-col gap-1">
            <label htmlFor={tsId} className="text-[11px] font-medium text-[var(--text-soft)]">
              Zaman (UTC) <span aria-hidden="true">*</span>
            </label>
            <input
              ref={tsInputRef}
              id={tsId}
              name="timestamp"
              type="datetime-local"
              required
              value={timestampInput}
              aria-invalid={Boolean(fieldErrors.timestamp)}
              aria-describedby={fieldErrors.timestamp ? tsErrId : undefined}
              onChange={(e) => {
                setTimestampInput(e.target.value);
                if (fieldErrors.timestamp) {
                  setFieldErrors((prev) => ({ ...prev, timestamp: undefined }));
                }
              }}
              onBlur={() =>
                setFieldErrors((prev) => ({
                  ...prev,
                  timestamp: validateTimestampInput(timestampInput),
                }))
              }
              className="input font-mono text-[12px]"
            />
            {fieldErrors.timestamp ? (
              <p id={tsErrId} className="text-[11px] text-[var(--danger)]">
                {fieldErrors.timestamp}
              </p>
            ) : null}
          </div>

          <div className="flex flex-col gap-1">
            <label htmlFor={pId} className="text-[11px] font-medium text-[var(--text-soft)]">
              Basınç (bar) <span aria-hidden="true">*</span>
            </label>
            <input
              ref={pInputRef}
              id={pId}
              name="pressure_bar"
              type="text"
              inputMode="decimal"
              autoComplete="off"
              required
              value={pressureInput}
              placeholder="80,25"
              aria-invalid={Boolean(fieldErrors.pressure)}
              aria-describedby={fieldErrors.pressure ? pErrId : undefined}
              onChange={(e) => {
                setPressureInput(e.target.value);
                if (fieldErrors.pressure) {
                  setFieldErrors((prev) => ({ ...prev, pressure: undefined }));
                }
              }}
              onBlur={() =>
                setFieldErrors((prev) => ({
                  ...prev,
                  pressure: validateFiniteInput(pressureInput, "Basınç", true).error,
                }))
              }
              className="input font-mono text-[12px]"
            />
            {fieldErrors.pressure ? (
              <p id={pErrId} className="text-[11px] text-[var(--danger)]">
                {fieldErrors.pressure}
              </p>
            ) : null}
          </div>

          <div className="flex flex-col gap-1">
            <label htmlFor={tId} className="text-[11px] font-medium text-[var(--text-soft)]">
              Sıcaklık (°C) <span aria-hidden="true">*</span>
            </label>
            <input
              ref={tInputRef}
              id={tId}
              name="temperature_c"
              type="text"
              inputMode="decimal"
              autoComplete="off"
              required
              value={tempInput}
              placeholder="15,4"
              aria-invalid={Boolean(fieldErrors.temperature)}
              aria-describedby={fieldErrors.temperature ? tErrId : undefined}
              onChange={(e) => {
                setTempInput(e.target.value);
                if (fieldErrors.temperature) {
                  setFieldErrors((prev) => ({ ...prev, temperature: undefined }));
                }
              }}
              onBlur={() =>
                setFieldErrors((prev) => ({
                  ...prev,
                  temperature: validateFiniteInput(tempInput, "Sıcaklık", true).error,
                }))
              }
              className="input font-mono text-[12px]"
            />
            {fieldErrors.temperature ? (
              <p id={tErrId} className="text-[11px] text-[var(--danger)]">
                {fieldErrors.temperature}
              </p>
            ) : null}
          </div>

          <div className="flex flex-col gap-1">
            <label htmlFor={vId} className="text-[11px] font-medium text-[var(--text-soft)]">
              Hacim (m³, isteğe bağlı)
            </label>
            <input
              ref={vInputRef}
              id={vId}
              name="volume_m3"
              type="text"
              inputMode="decimal"
              autoComplete="off"
              value={volumeInput}
              placeholder="10,5"
              aria-invalid={Boolean(fieldErrors.volume)}
              aria-describedby={fieldErrors.volume ? vErrId : undefined}
              onChange={(e) => {
                setVolumeInput(e.target.value);
                if (fieldErrors.volume) {
                  setFieldErrors((prev) => ({ ...prev, volume: undefined }));
                }
              }}
              onBlur={() =>
                setFieldErrors((prev) => ({
                  ...prev,
                  volume: validateFiniteInput(volumeInput, "Hacim", false).error,
                }))
              }
              className="input font-mono text-[12px]"
            />
            {fieldErrors.volume ? (
              <p id={vErrId} className="text-[11px] text-[var(--danger)]">
                {fieldErrors.volume}
              </p>
            ) : null}
          </div>

          <div className="flex flex-col gap-1">
            <label htmlFor={notesId} className="text-[11px] font-medium text-[var(--text-soft)]">
              Not (isteğe bağlı)
            </label>
            <input
              id={notesId}
              name="notes"
              type="text"
              maxLength={500}
              value={notesInput}
              placeholder="Ölçüm notu"
              onChange={(e) => setNotesInput(e.target.value)}
              className="input text-[12px]"
            />
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="submit"
              disabled={addMutation.isPending}
              className="btn btn-primary"
            >
              <Plus size={13} aria-hidden />
              {addMutation.isPending ? "Ekleniyor..." : "Okuma ekle"}
            </button>
            <p role="status" aria-live="polite" className="text-[11.5px] text-[var(--text-muted)]">
              {formStatus}
            </p>
          </div>
          {records.length > 0 ? (
            <div className="flex items-center gap-1.5">
              {confirmClear ? (
                <>
                  <button
                    type="button"
                    disabled={clearMutation.isPending}
                    className="btn btn-danger"
                    onClick={handleClearAll}
                  >
                    Tümünü silmeyi onayla
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost"
                    onClick={() => setConfirmClear(false)}
                  >
                    Vazgeç
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={() => setConfirmClear(true)}
                >
                  <Trash2 size={13} aria-hidden />
                  Tümünü temizle
                </button>
              )}
            </div>
          ) : null}
        </div>
      </form>

      <div
        id={pastePanelId}
        hidden={!showPaste}
        className="space-y-3 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-3"
      >
        <div className="flex flex-col gap-1">
          <label htmlFor={pasteTextId} className="text-[11.5px] font-medium text-[var(--text-soft)]">
            Toplu okuma satırları (Zaman · Basınç bar · Sıcaklık °C · [Hacim m³] · [Not]; sekme veya noktalı virgül ayrımlı)
          </label>
          <textarea
            id={pasteTextId}
            name="bulk_paste"
            rows={4}
            value={pasteText}
            onChange={(e) => {
              setPasteText(e.target.value);
              if (pasteError) setPasteError(null);
            }}
            placeholder={"2026-11-14T08:00Z\t80,50\t15,2\t10,0\tBaşlangıç\n2026-11-14T12:00Z\t80,48\t15,1"}
            className="w-full rounded-lg border border-[var(--border)] bg-[var(--surface)] px-2.5 py-2 font-mono text-[11.5px] text-[var(--text)]"
          />
        </div>

        <fieldset className="space-y-1">
          <legend className="text-[11px] font-semibold text-[var(--text-soft)]">
            İçe aktarma modu
          </legend>
          <div className="flex flex-wrap gap-4 text-[12px] text-[var(--text)]">
            <label className="inline-flex items-center gap-1.5">
              <input
                type="radio"
                name={modeGroupName}
                value="append"
                checked={pasteMode === "append"}
                onChange={() => setPasteMode("append")}
              />
              <span>Mevcut kayıtlara ekle</span>
            </label>
            <label className="inline-flex items-center gap-1.5">
              <input
                type="radio"
                name={modeGroupName}
                value="replace"
                checked={pasteMode === "replace"}
                onChange={() => setPasteMode("replace")}
              />
              <span>Mevcut kayıtları değiştir</span>
            </label>
          </div>
        </fieldset>

        {pasteError ? <InlineNotice tone="danger">{pasteError}</InlineNotice> : null}

        <button
          type="button"
          disabled={batchMutation.isPending || !pasteText.trim()}
          className="btn btn-primary"
          onClick={handleApplyPaste}
        >
          {batchMutation.isPending ? "Aktarılıyor..." : "Yapıştırılan satırları içe aktar"}
        </button>
      </div>

      <div
        tabIndex={0}
        role="region"
        aria-labelledby={tableCaptionId}
        onScroll={(e) => {
          if (isVirtualized) setTableScrollTop(e.currentTarget.scrollTop);
        }}
        className="table-wrap table-sticky diff-table-wrap max-h-[340px] overflow-auto scroll-thin"
      >
        <table className="data compact">
          <caption id={tableCaptionId}>
            24 Saatlik Basınç ve Sıcaklık Zaman Serisi Kayıtları ({records.length})
          </caption>
          <thead>
            <tr>
              <th scope="col" className="sticky-col">
                Zaman (UTC)
              </th>
              <th scope="col" className="num">
                Basınç (bar)
              </th>
              <th scope="col" className="num">
                Sıcaklık (°C)
              </th>
              <th scope="col" className="num">
                Hacim (m³)
              </th>
              <th scope="col">Kaynak</th>
              <th scope="col">Not</th>
              <th scope="col" className="num">
                İşlem
              </th>
            </tr>
          </thead>
          <tbody>
            {records.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-5 text-center text-[11.5px] text-[var(--text-faint)]">
                  Henüz zaman serisi kaydı yok. Tekil okuma ekleyin, Excel’den yapıştırın veya Form
                  018 / 021’den veri aktarın.
                </td>
              </tr>
            ) : (
              <>
                {topSpacerHeight > 0 ? (
                  <tr aria-hidden="true" data-virtual-spacer="top">
                    <td colSpan={7} style={{ height: `${topSpacerHeight}px`, padding: 0, border: 0 }} />
                  </tr>
                ) : null}
                {visibleRecords.map((row) => {
                  const shortTs = formatTsShort(row.timestamp);
                  return (
                    <tr key={row.id}>
                      <th scope="row" className="sticky-col whitespace-nowrap font-mono" title={row.timestamp}>
                        {shortTs}
                      </th>
                      <td className="num font-mono" data-label="Basınç (bar)">
                        {num(row.pressure_bar, 3)}
                      </td>
                      <td className="num font-mono" data-label="Sıcaklık (°C)">
                        {num(row.temperature_c, 2)}
                      </td>
                      <td className="num font-mono" data-label="Hacim (m³)">
                        {row.volume_m3 !== null ? num(row.volume_m3, 3) : "—"}
                      </td>
                      <td data-label="Kaynak">
                        <Badge tone="neutral">{row.source || "manual"}</Badge>
                      </td>
                      <td className="max-w-[200px] truncate" data-label="Not" title={row.notes}>
                        {row.notes || "—"}
                      </td>
                      <td className="num" data-label="İşlem">
                        <button
                          type="button"
                          disabled={deleteMutation.isPending}
                          onClick={() => handleDeleteRow(row)}
                          aria-label={`Okumayı sil (${shortTs})`}
                          className="rounded p-1 text-[var(--text-faint)] hover:bg-[var(--danger-bg)] hover:text-[var(--danger)]"
                        >
                          <Trash2 size={13} aria-hidden />
                        </button>
                      </td>
                    </tr>
                  );
                })}
                {bottomSpacerHeight > 0 ? (
                  <tr aria-hidden="true" data-virtual-spacer="bottom">
                    <td colSpan={7} style={{ height: `${bottomSpacerHeight}px`, padding: 0, border: 0 }} />
                  </tr>
                ) : null}
              </>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
