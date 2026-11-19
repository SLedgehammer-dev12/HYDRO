import { useEffect, useId, useState } from "react";
import { CheckCircle2, FileScan, Plus, Upload, X } from "lucide-react";
import { api } from "../../lib/api";
import { num } from "../../lib/format";
import { mergePlanProfileScans, parseKpMeters } from "../../lib/kp";
import type {
  DraftSectionItem,
  PlanProfileScanResponse,
  Project,
  SessionListItem,
} from "../../lib/types";
import { useCreateDraftSectionsBatch } from "../../hooks/queries";
import { useAppStore } from "../../store/useAppStore";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Dialog";
import { FieldGrid, NumberField } from "../../components/ui/Field";
import { InlineNotice } from "../../components/ui/State";

interface QueuedSheet {
  id: string;
  file: File;
  status: "pending" | "scanning" | "done" | "error";
  sectionCount?: number;
  error?: string;
}

export function PlanProfileScanModal({
  open,
  onClose,
  selected,
  rawSections,
}: {
  open: boolean;
  onClose: () => void;
  selected: Project | null;
  rawSections: SessionListItem[];
}) {
  const pushToast = useAppStore((state) => state.pushToast);
  const createDraftBatch = useCreateDraftSectionsBatch();

  const [scanQueue, setScanQueue] = useState<QueuedSheet[]>([]);
  const [isScanningSheets, setIsScanningSheets] = useState(false);
  const [scanProgressText, setScanProgressText] = useState("");
  const [scannedDoneCount, setScannedDoneCount] = useState(0);
  const [maxSectionLenM, setMaxSectionLenM] = useState<number | null>(12_000);
  const [maxElevDiffM, setMaxElevDiffM] = useState<number | null>(180);
  const [scanResult, setScanResult] = useState<PlanProfileScanResponse | null>(null);
  const [editableDrafts, setEditableDrafts] = useState<DraftSectionItem[]>([]);

  const modalScanInputId = useId();
  const modalAppendInputId = useId();

  useEffect(() => {
    if (open) {
      setScanQueue([]);
      setIsScanningSheets(false);
      setScanProgressText("");
      setScannedDoneCount(0);
      setScanResult(null);
      setEditableDrafts([]);
    }
  }, [open]);

  function addModalScanFiles(files: FileList | File[] | null) {
    if (!files || files.length === 0) return;
    const incoming = Array.from(files);
    setScanQueue((prev) => {
      const seen = new Set(prev.map((q) => q.id));
      const next = [...prev];
      for (const file of incoming) {
        const key = `${file.name}::${file.size}::${file.lastModified}`;
        if (!seen.has(key)) {
          seen.add(key);
          next.push({ id: key, file, status: "pending" });
        }
      }
      return next;
    });
  }

  async function runPlanProfileScan() {
    if (scanQueue.length === 0) {
      pushToast(
        "warning",
        "Pafta seçilmedi",
        "Taranacak Plan-Profil PDF veya CAD paftalarını seçin.",
      );
      return;
    }
    setIsScanningSheets(true);
    setScannedDoneCount(0);
    setScanQueue((prev) =>
      prev.map((item) => ({
        ...item,
        status: "pending",
        sectionCount: undefined,
        error: undefined,
      })),
    );

    const results: PlanProfileScanResponse[] = [];
    for (let idx = 0; idx < scanQueue.length; idx += 1) {
      const item = scanQueue[idx];
      setScanProgressText(
        `Pafta taranıyor: ${idx + 1} / ${scanQueue.length} — ${item.file.name}`,
      );
      setScanQueue((prev) =>
        prev.map((entry, eIdx) => (eIdx === idx ? { ...entry, status: "scanning" } : entry)),
      );
      try {
        const res = await api.scanPlanProfile({
          file: item.file,
          maxSectionLengthM: maxSectionLenM ?? 12_000,
          maxElevationDiffM: maxElevDiffM,
        });
        results.push(res);
        setScanQueue((prev) =>
          prev.map((entry, eIdx) =>
            eIdx === idx
              ? { ...entry, status: "done", sectionCount: res.draft_sections.length }
              : entry,
          ),
        );
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Tarama hatası";
        setScanQueue((prev) =>
          prev.map((entry, eIdx) =>
            eIdx === idx ? { ...entry, status: "error", error: msg } : entry,
          ),
        );
      }
      setScannedDoneCount(idx + 1);
    }

    setIsScanningSheets(false);
    if (results.length === 0) {
      setScanProgressText("Hiçbir pafta okunamadı.");
      pushToast("error", "Paftalar taranamadı", "Yüklenen paftaların hiçbiri çözümlenemedi.");
      return;
    }

    const { mergedScan, drafts } = mergePlanProfileScans(results, rawSections);
    setScanResult(mergedScan);
    setEditableDrafts(drafts);
    setScanProgressText(
      `${results.length} / ${scanQueue.length} pafta tarandı · ${drafts.length} taslak hazır.`,
    );
  }

  function updateDraftRow(index: number, patch: Partial<DraftSectionItem>) {
    setEditableDrafts((current) => {
      const next = current.map((item, idx) => (idx === index ? { ...item, ...patch } : item));
      return next.map((item, idx) => {
        const sM = parseKpMeters(item.start_kp);
        const eM = parseKpMeters(item.end_kp);
        const len =
          sM !== null && eM !== null && eM > sM
            ? Math.round((eM - sM) * 100) / 100
            : item.length_m;
        let continuityOk = true;
        let continuityNote = "Başlangıç kesiti";
        if (idx > 0) {
          const prev = next[idx - 1];
          const prevEndM = parseKpMeters(prev.end_kp);
          if (prevEndM !== null && sM !== null) {
            const diff = Math.round(sM - prevEndM);
            continuityOk = Math.abs(diff) <= 0.5;
            continuityNote = continuityOk
              ? `Önceki (${prev.section_no}) bitiş KP (${prev.end_kp}) ile eşleşiyor.`
              : `${prev.section_no} bitişi (${prev.end_kp}) ile ${
                  diff > 0 ? `+${diff} m boşluk` : `${Math.abs(diff)} m bindirme`
                }`;
          }
        }
        return {
          ...item,
          start_m: sM ?? item.start_m,
          end_m: eM ?? item.end_m,
          length_m: len,
          continuity_ok: continuityOk,
          continuity_note: continuityNote,
        };
      });
    });
  }

  function commitDraftSections() {
    if (!selected || editableDrafts.length === 0) return;
    createDraftBatch.mutate(
      {
        projectId: selected.id,
        sections: editableDrafts,
      },
      {
        onSuccess: () => onClose(),
      },
    );
  }

  return (
    <Modal
      open={open}
      dismissible={!isScanningSheets && !createDraftBatch.isPending}
      onClose={() => {
        if (!isScanningSheets && !createDraftBatch.isPending) onClose();
      }}
      title="Plan-Profil Paftalarından Taslak Kesit (Section) Üret"
      description="Tek bir toplu paftayı veya her test bölümünün ayrı paftalarını sırayla tarayarak uç uca eşleşen taslak kesitler oluşturun."
      className="max-w-4xl max-h-[88vh] overflow-y-auto"
      footer={
        <>
          <Button variant="ghost" disabled={isScanningSheets} onClick={onClose}>
            Kapat
          </Button>
          <Button
            icon={<FileScan size={14} />}
            loading={isScanningSheets}
            disabled={scanQueue.length === 0 || isScanningSheets}
            onClick={() => void runPlanProfileScan()}
          >
            {isScanningSheets
              ? `Taranıyor (${scannedDoneCount}/${scanQueue.length})...`
              : scanQueue.length > 1
                ? `${scanQueue.length} Paftayı Sırayla Tara & Birleştir`
                : "Paftayı Tara ve Taslakları Üret"}
          </Button>
          {editableDrafts.length > 0 ? (
            <Button
              variant="primary"
              icon={<CheckCircle2 size={14} />}
              loading={createDraftBatch.isPending}
              onClick={commitDraftSections}
            >
              Taslakları Projeye Kaydet ({editableDrafts.length} kesit)
            </Button>
          ) : null}
        </>
      }
    >
      <div className="space-y-3">
        <div className="space-y-3 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-3">
          <div className="relative">
            <input
              id={modalScanInputId}
              type="file"
              multiple
              disabled={isScanningSheets}
              accept=".pdf,.dwg,.dxf,.png,.jpg,.jpeg,.tif,.tiff"
              className="visually-hidden"
              onChange={(event) => {
                if (isScanningSheets) return;
                addModalScanFiles(event.target.files);
                event.target.value = "";
              }}
            />
            <label
              htmlFor={modalScanInputId}
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => {
                event.preventDefault();
                if (isScanningSheets) return;
                addModalScanFiles(event.dataTransfer.files);
              }}
              className="flex cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-[var(--border-strong)] bg-[var(--surface-1)] px-4 py-4 text-center transition-colors hover:border-[var(--primary)] [input:focus-visible+&]:outline [input:focus-visible+&]:outline-2 [input:focus-visible+&]:outline-offset-2 [input:focus-visible+&]:outline-[var(--focus)]"
            >
              <Upload size={18} className="mb-1.5 text-[var(--primary)]" aria-hidden />
              <span className="text-[12.5px] font-medium text-[var(--text)]">
                {scanQueue.length > 0
                  ? `${scanQueue.length} pafta seçildi (sürükleyip bırakarak veya tıklayarak ekleyebilirsiniz)`
                  : "Plan-Profil PDF, DWG/DXF veya görsel paftaları seçin (çoklu seçim desteklenir)"}
              </span>
              <span className="mt-0.5 text-[10.5px] text-[var(--text-muted)]">
                Ayrı test bölümü paftalarını tek seferde seçip sırayla taratabilirsiniz.
              </span>
            </label>
          </div>

          {scanQueue.length > 0 ? (
            <div className="space-y-2 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] p-2.5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-[11px] font-semibold text-[var(--text)]">
                  Seçili Paftalar ({scanQueue.length})
                </span>
                <div className="flex items-center gap-2">
                  <div className="relative">
                    <input
                      id={modalAppendInputId}
                      type="file"
                      multiple
                      accept=".pdf,.dwg,.dxf,.png,.jpg,.jpeg,.tif,.tiff"
                      className="visually-hidden"
                      disabled={isScanningSheets}
                      onChange={(event) => {
                        addModalScanFiles(event.target.files);
                        event.target.value = "";
                      }}
                    />
                    <label
                      htmlFor={modalAppendInputId}
                      className="inline-flex cursor-pointer items-center gap-1 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2 py-1 text-[10.5px] font-medium text-[var(--text-soft)] hover:border-[var(--primary)] [input:focus-visible+&]:outline [input:focus-visible+&]:outline-2 [input:focus-visible+&]:outline-offset-2 [input:focus-visible+&]:outline-[var(--focus)]"
                    >
                      <Plus size={11} aria-hidden />
                      Başka Pafta Ekle
                    </label>
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={isScanningSheets}
                    onClick={() => {
                      setScanQueue([]);
                      setScanResult(null);
                      setEditableDrafts([]);
                      setScanProgressText("");
                    }}
                  >
                    Temizle
                  </Button>
                </div>
              </div>

              <ul className="max-h-32 space-y-1 overflow-y-auto scroll-thin pr-1">
                {scanQueue.map((item, idx) => (
                  <li
                    key={item.id}
                    className="flex items-center justify-between gap-2 rounded border border-[var(--border)] px-2 py-1 text-[11px]"
                  >
                    <span className="min-w-0 truncate">
                      <span className="mr-1.5 font-mono text-[10px] text-[var(--text-faint)]">
                        #{idx + 1}
                      </span>
                      {item.file.name}
                    </span>
                    <span className="flex shrink-0 items-center gap-1.5">
                      {item.status === "scanning" ? (
                        <Badge tone="info">Taranıyor...</Badge>
                      ) : item.status === "done" ? (
                        <Badge tone="pass">{item.sectionCount ?? 0} kesit</Badge>
                      ) : item.status === "error" ? (
                        <span title={item.error}>
                          <Badge tone="fail">Hata</Badge>
                        </span>
                      ) : (
                        <Badge tone="neutral">Hazır</Badge>
                      )}
                      <button
                        type="button"
                        disabled={isScanningSheets}
                        aria-label={`${item.file.name} paftasını çıkar`}
                        onClick={() =>
                          setScanQueue((prev) => prev.filter((q) => q.id !== item.id))
                        }
                        className="rounded p-0.5 text-[var(--text-muted)] hover:bg-[var(--danger-bg)] hover:text-[var(--danger)] disabled:opacity-40"
                      >
                        <X size={12} aria-hidden />
                      </button>
                    </span>
                  </li>
                ))}
              </ul>

              {isScanningSheets || scanProgressText ? (
                <div className="space-y-1" role="status" aria-live="polite">
                  {isScanningSheets ? (
                    <progress
                      value={scannedDoneCount}
                      max={scanQueue.length}
                      className="h-1.5 w-full accent-[var(--primary)]"
                    />
                  ) : null}
                  <p className="text-[10.5px] text-[var(--text-muted)]">{scanProgressText}</p>
                </div>
              ) : null}
            </div>
          ) : null}

          <FieldGrid cols={2}>
            <NumberField
              label="Hedef maks. kesit boyu"
              unit="m"
              value={maxSectionLenM}
              onChange={setMaxSectionLenM}
              min={500}
              max={20000}
              help="NGTL 5007 üst sınırı: 20.000 m"
            />
            <NumberField
              label="Maks. kot farkı (opsiyonel)"
              unit="m"
              value={maxElevDiffM}
              onChange={setMaxElevDiffM}
              min={20}
              max={1000}
              help="Kot farkı aşılırsa kesit daha erken bölünür"
            />
          </FieldGrid>
        </div>

        {scanResult ? (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-[11px]">
              <Badge tone="info">{scanResult.page_count} sayfa</Badge>
              <Badge tone="neutral">
                KP {scanResult.min_kp} → {scanResult.max_kp} ({num(scanResult.total_length_m, 0)} m)
              </Badge>
              <Badge tone="neutral">{scanResult.station_count} KP noktası</Badge>
              <Badge tone="neutral">{scanResult.elevation_point_count} kot noktası</Badge>
              {scanResult.pipe_meta.outside_diameter_mm ? (
                <span className="chip">
                  OD {num(scanResult.pipe_meta.outside_diameter_mm, 1)} mm · WT{" "}
                  {num(scanResult.pipe_meta.wall_thickness_mm, 2)} mm
                </span>
              ) : null}
              <Badge tone={editableDrafts.every((d) => d.continuity_ok) ? "pass" : "warning"}>
                {editableDrafts.every((d) => d.continuity_ok)
                  ? "Tüm taslak KP'ler uç uca eşleşiyor"
                  : "KP farkı var"}
              </Badge>
            </div>

            {scanResult.warnings.length > 0 ? (
              <InlineNotice tone="warning" title="Tarama notu">
                {scanResult.warnings.join(" ")}
              </InlineNotice>
            ) : null}

            <div
              role="region"
              aria-label="Üretilen Taslak Kesitler Tablosu"
              className="table-wrap table-sticky max-h-[280px] overflow-auto scroll-thin"
            >
              <table className="data">
                <caption>Üretilen taslak kesitler (kaydetmeden önce düzenleyebilirsiniz)</caption>
                <thead>
                  <tr>
                    <th scope="col" className="sticky-col">
                      Kesit No
                    </th>
                    <th scope="col">Başlangıç KP</th>
                    <th scope="col">Bitiş KP</th>
                    <th scope="col" className="num">
                      Uzunluk (m)
                    </th>
                    <th scope="col" className="num">
                      Kot (Baş/Bit/Min/Max)
                    </th>
                    {scanQueue.length > 1 || editableDrafts.some((d) => Boolean(d.source_file)) ? (
                      <th scope="col">Kaynak Pafta</th>
                    ) : null}
                    <th scope="col">KP Sürekliliği</th>
                  </tr>
                </thead>
                <tbody>
                  {editableDrafts.map((draft, idx) => (
                    <tr key={`${draft.section_no}-${idx}`}>
                      <td className="sticky-col">
                        <input
                          type="text"
                          value={draft.section_no}
                          autoCorrect="off"
                          autoCapitalize="none"
                          spellCheck={false}
                          onChange={(e) => updateDraftRow(idx, { section_no: e.target.value })}
                          className="field-input h-7 w-[78px] px-2 font-mono text-[11px]"
                          aria-label={`Kesit no ${idx + 1}`}
                        />
                      </td>
                      <td>
                        <input
                          type="text"
                          value={draft.start_kp}
                          autoCorrect="off"
                          autoCapitalize="none"
                          spellCheck={false}
                          onChange={(e) => updateDraftRow(idx, { start_kp: e.target.value })}
                          className="field-input h-7 w-[92px] px-2 font-mono text-[11px]"
                          aria-label={`Başlangıç KP ${idx + 1}`}
                        />
                      </td>
                      <td>
                        <input
                          type="text"
                          value={draft.end_kp}
                          autoCorrect="off"
                          autoCapitalize="none"
                          spellCheck={false}
                          onChange={(e) => updateDraftRow(idx, { end_kp: e.target.value })}
                          className="field-input h-7 w-[92px] px-2 font-mono text-[11px]"
                          aria-label={`Bitiş KP ${idx + 1}`}
                        />
                      </td>
                      <td className="num font-mono">{num(draft.length_m, 0)}</td>
                      <td className="num font-mono text-[10.5px]">
                        {draft.start_elevation_m !== null
                          ? `${num(draft.start_elevation_m, 0)} / ${num(
                              draft.end_elevation_m,
                              0,
                            )} (${num(draft.lowest_elevation_m, 0)}–${num(
                              draft.highest_elevation_m,
                              0,
                            )} m)`
                          : "—"}
                      </td>
                      {scanQueue.length > 1 ||
                      editableDrafts.some((d) => Boolean(d.source_file)) ? (
                        <td
                          className="max-w-[140px] truncate text-[10.5px] text-[var(--text-muted)]"
                          title={draft.source_file}
                        >
                          {draft.source_file || "—"}
                        </td>
                      ) : null}
                      <td>
                        <Badge tone={draft.continuity_ok ? "pass" : "warning"}>
                          {idx === 0
                            ? draft.prev_end_kp
                              ? draft.continuity_ok
                                ? "Öncekiyle eşleşiyor"
                                : draft.continuity_note
                              : "Başlangıç"
                            : draft.continuity_ok
                              ? "Eşleşiyor"
                              : draft.continuity_note}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}
      </div>
    </Modal>
  );
}
