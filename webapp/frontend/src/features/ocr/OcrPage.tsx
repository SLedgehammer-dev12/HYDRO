import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import clsx from "clsx";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clipboard,
  Download,
  FileJson,
  Loader2,
  RefreshCw,
  RotateCcw,
  ScanLine,
  ShieldAlert,
  Square,
  Trash2,
} from "lucide-react";
import Dropzone, { MAX_FILE_BYTES } from "./components/Dropzone";
import SummaryCard from "./components/SummaryCard";
import FieldsTable from "./components/FieldsTable";
import DiscrepanciesTable from "./components/DiscrepanciesTable";
import WarningsPanel from "./components/WarningsPanel";
import MappingPanel from "./components/MappingPanel";
import StatusPanel from "./components/StatusPanel";
import HistoryPanel from "./components/HistoryPanel";
import { PageHeader } from "../../components/layout/PageHeader";
import { flattenReport } from "./fields";
import {
  DEMO_HISTORY,
  DEMO_MAPPING_PROFILES,
  DEMO_RESULT,
  SAMPLE_CALCULATED,
} from "./demoData";
import {
  OcrApiError,
  analyzeOcr,
  cancelOcrAnalysis,
  currentSessionId,
  getMappingProfile,
  getOcrStatus,
  isAbortError,
  listAnalyses,
  listMappingProfiles,
  toOcrApiError,
  waitForAnalysis,
} from "./ocrApi";
import { formatDateTime, formatNumber, shortId } from "./format";
import {
  ANALYSIS_STATUS_LABELS,
  SOURCE_LABELS,
  isBlockingDiscrepancy,
  type MappingProfile,
  type OcrAnalysisResult,
  type OcrAnalysisSummary,
  type OcrErrorDetail,
  type OcrStatus,
} from "./types";

type Phase = "idle" | "analyzing" | "done" | "error";
type TabKey = "fields" | "discrepancies" | "warnings";
type StageKey = "upload" | "extract" | "parse" | "compare";

const STAGES: Array<{ key: StageKey; label: string; detail: string }> = [
  { key: "upload", label: "Yükleniyor", detail: "Dosya sunucuya aktarılıyor" },
  { key: "extract", label: "Metin / OCR çıkarılıyor", detail: "Metin katmanı veya Tesseract" },
  { key: "parse", label: "Alanlar ayrıştırılıyor", detail: "Etiket + regex eşleme" },
  { key: "compare", label: "Karşılaştırılıyor", detail: "Toleranslı hesap kontrolü" },
];

function mapServerStage(raw: string | null | undefined): StageKey {
  const value = (raw ?? "").toLowerCase();
  if (value.includes("queue") || value.includes("upload")) return "upload";
  if (value.includes("compare")) return "compare";
  if (value.includes("pars") || value.includes("field")) return "parse";
  if (value.includes("extract") || value.includes("ocr") || value.includes("text")) return "extract";
  return "extract";
}

function serverStageLabel(raw: string | null | undefined): string {
  const stage = mapServerStage(raw);
  return STAGES.find((item) => item.key === stage)?.label ?? "İşleniyor";
}

function wait(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException("İptal edildi.", "AbortError"));
      return;
    }
    const onAbort = () => {
      window.clearTimeout(timer);
      reject(new DOMException("İptal edildi.", "AbortError"));
    };
    const timer = window.setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

export default function OcrPage() {
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);

  const [phase, setPhase] = useState<Phase>("idle");
  const [stage, setStage] = useState<StageKey>("upload");
  const [stageNote, setStageNote] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);

  const [result, setResult] = useState<OcrAnalysisResult | null>(null);
  const [resultDemo, setResultDemo] = useState(false);
  const [error, setError] = useState<OcrApiError | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [copiedRequestId, setCopiedRequestId] = useState(false);

  const [useCalculated, setUseCalculated] = useState(true);
  const [calculatedJson, setCalculatedJson] = useState("");
  const [calculatedError, setCalculatedError] = useState<string | null>(null);
  const [comparisonRequested, setComparisonRequested] = useState(false);

  const [selectedFields, setSelectedFields] = useState<Set<string>>(new Set());
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [tab, setTab] = useState<TabKey>("fields");

  const [status, setStatus] = useState<OcrStatus | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const [statusError, setStatusError] = useState(false);

  const [history, setHistory] = useState<OcrAnalysisSummary[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState(false);
  const [historyDemo, setHistoryDemo] = useState(false);
  const [openingHistoryId, setOpeningHistoryId] = useState<string | null>(null);

  const [profiles, setProfiles] = useState<MappingProfile[]>([]);
  const [profilesLoading, setProfilesLoading] = useState(true);
  const [profilesError, setProfilesError] = useState<string | null>(null);
  const [profilesDemo, setProfilesDemo] = useState(false);
  const [selectedProfileId, setSelectedProfileId] = useState<string | null>(null);
  const [profileDetail, setProfileDetail] = useState<MappingProfile | null>(null);
  const [profileDetailLoading, setProfileDetailLoading] = useState(false);
  const [profileDetailError, setProfileDetailError] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const startedAtRef = useRef(0);
  const resultHeadingRef = useRef<HTMLHeadingElement>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  const sessionId = useMemo(() => currentSessionId(), []);

  const demoMode = statusError;
  const selectedProfile = useMemo(
    () => profiles.find((profile) => profile.id === selectedProfileId) ?? null,
    [profiles, selectedProfileId],
  );

  const fields = useMemo(() => flattenReport(result?.report), [result]);
  const lowThreshold = status?.thresholds?.low_confidence ?? 0.6;
  const criticalThreshold = status?.thresholds?.critical_confidence ?? 0.4;
  const pendingLowConfidence = useMemo(
    () =>
      fields.filter(
        (item) => item.field.confidence < lowThreshold && !selectedFields.has(item.descriptor.key),
      ),
    [fields, selectedFields, lowThreshold],
  );
  const editedCount = Object.keys(edits).length;
  const allSelected = fields.length > 0 && selectedFields.size === fields.length;

  const loadStatus = useCallback(async () => {
    setStatusLoading(true);
    try {
      const data = await getOcrStatus();
      setStatus(data);
      setStatusError(false);
    } catch {
      setStatus(null);
      setStatusError(true);
    } finally {
      setStatusLoading(false);
    }
  }, []);

  const loadHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const data = await listAnalyses({ limit: 20 });
      setHistory(data.items);
      setHistoryDemo(false);
      setHistoryError(false);
    } catch {
      setHistory(DEMO_HISTORY);
      setHistoryDemo(true);
      setHistoryError(true);
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  const loadProfiles = useCallback(async () => {
    setProfilesLoading(true);
    try {
      const data = await listMappingProfiles();
      if (data.items.length > 0) {
        setProfiles(data.items);
        setProfilesDemo(false);
        setProfilesError(null);
        setSelectedProfileId((current) => {
          if (current && data.items.some((item) => item.id === current)) return current;
          return data.items.find((item) => item.is_default)?.id ?? data.items[0].id;
        });
      } else {
        setProfiles(DEMO_MAPPING_PROFILES);
        setProfilesDemo(true);
        setProfilesError(
          "Sunucuda eşleme profili yok; yerel taslak profiller gösteriliyor. Format geldiğinde profil oluşturun.",
        );
        setSelectedProfileId((current) => current ?? DEMO_MAPPING_PROFILES[0].id);
      }
    } catch {
      setProfiles(DEMO_MAPPING_PROFILES);
      setProfilesDemo(true);
      setProfilesError(
        "Eşleme profilleri yüklenemedi; yerel taslak profiller gösteriliyor. Bu profil analizle gönderilmez.",
      );
      setSelectedProfileId((current) => current ?? DEMO_MAPPING_PROFILES[0].id);
    } finally {
      setProfilesLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadStatus();
    void loadHistory();
    void loadProfiles();
  }, [loadStatus, loadHistory, loadProfiles]);

  useEffect(() => {
    if (phase !== "analyzing") return;
    const timer = window.setInterval(() => {
      setElapsed(Math.max(0, Math.floor((Date.now() - startedAtRef.current) / 1000)));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [phase]);

  useEffect(() => {
    if (phase !== "error") return;
    const timer = window.setTimeout(() => errorRef.current?.focus(), 40);
    return () => window.clearTimeout(timer);
  }, [phase]);

  useEffect(() => {
    const selected = profiles.find((profile) => profile.id === selectedProfileId) ?? null;
    if (!selected) {
      setProfileDetail(null);
      setProfileDetailError(null);
      setProfileDetailLoading(false);
      return;
    }
    if (selected.mapping || profilesDemo) {
      setProfileDetail(selected);
      setProfileDetailError(null);
      setProfileDetailLoading(false);
      return;
    }
    const controller = new AbortController();
    let cancelled = false;
    setProfileDetailLoading(true);
    setProfileDetailError(null);
    getMappingProfile(selected.id, controller.signal)
      .then((detail) => {
        if (!cancelled) setProfileDetail(detail);
      })
      .catch((caught) => {
        if (cancelled || isAbortError(caught)) return;
        setProfileDetail(selected);
        setProfileDetailError(
          "Profil tanımı yüklenemedi; alan listesi varsayılan etiketlerle gösteriliyor.",
        );
      })
      .finally(() => {
        if (!cancelled) setProfileDetailLoading(false);
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [profiles, profilesDemo, selectedProfileId]);

  const applyResult = (analysis: OcrAnalysisResult, demo: boolean) => {
    const flattened = flattenReport(analysis.report);
    setResult(analysis);
    setResultDemo(demo);
    setPhase("done");
    setError(null);
    setEdits({});
    setSelectedFields(
      new Set(
        flattened
          .filter((item) => item.field.confidence >= lowThreshold)
          .map((item) => item.descriptor.key),
      ),
    );
    const nextTab: TabKey = (analysis.discrepancies ?? []).some(isBlockingDiscrepancy)
      ? "discrepancies"
      : "fields";
    setTab(nextTab);
    setComparisonRequested((analysis.discrepancies ?? []).length > 0);
    setStageNote(null);
    window.setTimeout(() => resultHeadingRef.current?.focus(), 40);
  };

  const runDemo = async (signal: AbortSignal) => {
    setStage("upload");
    setStageNote("Demo: dosya yükleniyor (yerel, ağa çıkılmaz).");
    await wait(500, signal);
    setStage("extract");
    setStageNote("Demo: metin katmanı ve OCR çıktısı üretiliyor.");
    await wait(950, signal);
    setStage("parse");
    setStageNote("Demo: alan etiketleri eşleniyor.");
    await wait(800, signal);
    setStage("compare");
    setStageNote("Demo: toleranslar uygulanıyor.");
    await wait(650, signal);
    applyResult(DEMO_RESULT, true);
  };

  const readCalculatedPayload = (): {
    value: Record<string, unknown> | null;
    error: string | null;
  } => {
    if (!useCalculated) return { value: null, error: null };
    const raw = calculatedJson.trim();
    if (!raw) return { value: null, error: null };
    try {
      const parsed: unknown = JSON.parse(raw);
      if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
        return {
          value: null,
          error:
            "Kök değer bir JSON nesnesi olmalı: { \"test_pressure_bar\": 80.0, ... } gibi.",
        };
      }
      return { value: parsed as Record<string, unknown>, error: null };
    } catch (caught) {
      return {
        value: null,
        error: `JSON okunamadı: ${caught instanceof Error ? caught.message : "geçersiz sözdizimi"}`,
      };
    }
  };

  const showFailure = (detail: OcrErrorDetail | null | undefined, fallback: string) => {
    setError(
      new OcrApiError({
        code: detail?.code ?? "ocr_error",
        message: detail?.message ?? fallback,
        details: detail?.detail ? { detail: detail.detail } : {},
        status: 200,
      }),
    );
    setPhase("error");
  };

  const runAnalysis = async () => {
    if (!file) {
      setFileError("Analiz için önce bir dosya seçin.");
      return;
    }
    const parsed = readCalculatedPayload();
    if (parsed.error) {
      setCalculatedError(parsed.error);
      return;
    }
    setCalculatedError(null);
    setFileError(null);
    setResult(null);
    setResultDemo(false);
    setError(null);
    setEdits({});
    setPhase("analyzing");
    setStage("upload");
    setStageNote(demoMode ? "Demo modu: backend kapalı, yerel örnek sonuç üretilecek." : null);
    setElapsed(0);
    startedAtRef.current = Date.now();
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      if (demoMode) {
        await runDemo(controller.signal);
        return;
      }
      const job = await analyzeOcr(
        {
          file,
          calculated: parsed.value,
          mappingProfileId: profilesDemo ? null : selectedProfileId,
          sessionId,
        },
        controller.signal,
      );
      setJobId(job.analysis_id);
      setStage("extract");
      setStageNote(
        job.reused
          ? "Aynı dosya daha önce yüklenmiş; mevcut analiz yeniden kullanılıyor."
          : job.estimated_wait_s
            ? `Tahmini bekleme: ${formatNumber(job.estimated_wait_s, 0)} sn.`
            : "Sunucu analizi başlattı.",
      );
      const final = await waitForAnalysis(job.analysis_id, {
        signal: controller.signal,
        onProgress: (info) => {
          setStage(mapServerStage(info.stage));
          setStageNote(
            info.status === "queued"
              ? "Kuyrukta; önceki analiz bitince başlayacak."
              : `Sunucu aşaması: ${serverStageLabel(info.stage)}`,
          );
        },
      });
      if (final.status === "succeeded") {
        applyResult(final, false);
      } else if (final.status === "failed") {
        showFailure(final.error, "Analiz tamamlanamadı; sunucu hata ayrıntısı göndermedi.");
      } else if (final.status === "cancelled") {
        setPhase("idle");
        setStageNote("Analiz iptal edildi.");
      }
    } catch (caught) {
      if (isAbortError(caught) || controller.signal.aborted) {
        setPhase("idle");
        setStageNote("Analiz iptal edildi.");
      } else {
        setError(toOcrApiError(caught));
        setPhase("error");
      }
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      setJobId(null);
      setElapsed(0);
    }
  };

  const handleCancel = () => {
    abortRef.current?.abort();
    if (jobId) {
      void cancelOcrAnalysis(jobId).catch(() => undefined);
    }
    setPhase("idle");
    setStageNote("Analiz iptal edildi.");
  };

  const openHistoryItem = async (item: OcrAnalysisSummary) => {
    if (phase === "analyzing") return;
    if (historyDemo || item.id.startsWith("demo")) {
      applyResult({ ...DEMO_RESULT, id: item.id }, true);
      return;
    }
    setOpeningHistoryId(item.id);
    setError(null);
    setResult(null);
    setResultDemo(false);
    setEdits({});
    setPhase("analyzing");
    setStage(mapServerStage(item.status));
    setStageNote("Geçmiş analiz yükleniyor…");
    setElapsed(0);
    startedAtRef.current = Date.now();
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const final = await waitForAnalysis(item.id, {
        signal: controller.signal,
        onProgress: (info) => {
          setStage(mapServerStage(info.stage));
          setStageNote(`Sunucu aşaması: ${serverStageLabel(info.stage)}`);
        },
      });
      if (final.status === "succeeded") {
        applyResult(final, false);
      } else if (final.status === "failed") {
        showFailure(final.error, "Geçmiş analiz başarısız; hata ayrıntısı yok.");
      } else if (final.status === "cancelled") {
        setPhase("idle");
        setStageNote("Bu analiz iptal edilmiş.");
      }
    } catch (caught) {
      if (isAbortError(caught) || controller.signal.aborted) {
        setPhase("idle");
      } else {
        setError(toOcrApiError(caught));
        setPhase("error");
      }
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      setOpeningHistoryId(null);
      setElapsed(0);
    }
  };

  const showDemo = () => {
    if (phase === "analyzing") handleCancel();
    applyResult(DEMO_RESULT, true);
    setFileError(null);
  };

  const resetAll = () => {
    if (abortRef.current) {
      abortRef.current.abort();
      if (jobId) void cancelOcrAnalysis(jobId).catch(() => undefined);
    }
    setFile(null);
    setFileError(null);
    setResult(null);
    setResultDemo(false);
    setError(null);
    setEdits({});
    setSelectedFields(new Set());
    setPhase("idle");
    setStage("upload");
    setStageNote(null);
    setElapsed(0);
    setJobId(null);
    setTab("fields");
    setComparisonRequested(false);
  };

  const downloadJson = () => {
    if (!result) return;
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${resultDemo ? "demo-" : ""}ocr-${shortId(result.id).replace("…", "")}.json`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
  };

  const copyRequestId = async () => {
    if (!error?.requestId) return;
    try {
      await navigator.clipboard.writeText(error.requestId);
      setCopiedRequestId(true);
      window.setTimeout(() => setCopiedRequestId(false), 2500);
    } catch {
      setCopiedRequestId(false);
    }
  };

  const toggleField = (key: string, checked: boolean) => {
    setSelectedFields((previous) => {
      const next = new Set(previous);
      if (checked) next.add(key);
      else next.delete(key);
      return next;
    });
  };

  const editField = (key: string, value: string | null) => {
    setEdits((previous) => {
      const next = { ...previous };
      if (value === null) delete next[key];
      else next[key] = value;
      return next;
    });
  };

  const tabs = [
    { key: "fields" as TabKey, label: "Alanlar", count: fields.length },
    {
      key: "discrepancies" as TabKey,
      label: "Uyuşmazlıklar",
      count: result?.discrepancies?.length ?? 0,
    },
    {
      key: "warnings" as TabKey,
      label: "Uyarılar",
      count: (result?.warnings?.length ?? 0) + (result?.issues?.length ?? 0),
    },
  ];

  const activeStageIndex = Math.max(
    0,
    STAGES.findIndex((item) => item.key === stage),
  );

  const analyzeDisabledReason = !file
    ? "Analiz için önce bir dosya seçin."
    : phase === "analyzing"
      ? "Analiz sürüyor; bitmesini bekleyin veya iptal edin."
      : calculatedError
        ? "Hesaplanan değer JSON'unu düzeltin."
        : null;

  const approveBlockedReason =
    pendingLowConfidence.length > 0
      ? `${pendingLowConfidence.length} düşük güvenli alan seçilmedi; onaydan önce her birini işaretleyin.`
      : editedCount > 0
        ? `${editedCount} alan elle düzeltildi; düzeltme onay sayılmaz. Onay uç noktası bağlanınca değerler denetim iziyle gönderilecek.`
        : "Onay uç noktası hazır (POST /api/ocr/analyses/{id}/approve); oturum kimliği ve yetki katmanı bağlanınca etkinleşecek.";

  const handleTabKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const buttons = Array.from(
      event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]'),
    );
    const currentIndex = buttons.findIndex((button) => button.getAttribute("aria-selected") === "true");
    const direction = event.key === "ArrowRight" ? 1 : -1;
    const nextIndex = (currentIndex + direction + buttons.length) % buttons.length;
    const nextTab = tabs[nextIndex];
    if (!nextTab) return;
    setTab(nextTab.key);
    buttons[nextIndex]?.focus();
  };

  return (
    <div className="space-y-5">
      <PageHeader
        kicker="Rapor doğrulama · OCR"
        title="Test Raporu Kontrolü"
        description="PDF veya taranmış test raporunu yükleyin; alanlar çıkarılır, hesaplanan değerlerle toleranslı karşılaştırılır ve insan onayına sunulur."
        actions={
          <div className="flex flex-col items-end gap-1.5 text-right">
            <span
              className={clsx(
                "rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em]",
                statusError
                  ? "border-[var(--warning-border)] bg-[var(--warning-bg)] text-[var(--warning)]"
                  : status?.available
                    ? "border-[var(--success-border)] bg-[var(--success-bg)] text-[var(--success)]"
                    : "border-[var(--border)] bg-[var(--surface-3)] text-[var(--text-soft)]",
              )}
            >
              {statusLoading
                ? "Motor kontrol ediliyor"
                : statusError
                  ? "Backend çevrimdışı · demo"
                  : status?.available
                    ? "OCR hazır"
                    : "OCR kullanılamıyor"}
            </span>
            <p className="numeric text-[10px] text-[var(--text-faint)]" title={sessionId}>
              Oturum: {shortId(sessionId)}
            </p>
          </div>
        }
      />

      <div className="flex items-start gap-2.5 rounded-xl border border-[var(--warning-border)] bg-[var(--warning-bg)] px-3.5 py-3 text-[11px] leading-relaxed text-[var(--warning)]">
        <ShieldAlert size={16} className="mt-0.5 shrink-0 text-[var(--warning)]" aria-hidden="true" />
        <p>
          <strong className="font-semibold text-[var(--warning)]">OCR çıktısı resmi kabul değildir.</strong>{" "}
          Yetkili personel onayı zorunludur; onaylanan değerler ham rapordaki değeri değiştirmez,
          denetim izine yazılır. Rapor dosyası bulut OCR'a gönderilmez.
        </p>
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="min-w-0 space-y-5">
          <section className="panel p-5" aria-labelledby="ocr-upload-title">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="grid h-8 w-8 place-items-center rounded-lg border border-[var(--info-border)] bg-[var(--info-bg)] text-[var(--primary)]">
                  <FileJson size={16} aria-hidden="true" />
                </span>
                <div>
                  <h2 id="ocr-upload-title" className="text-base font-semibold text-[var(--text)]">
                    1 · Rapor dosyası
                  </h2>
                  <p className="text-[11px] text-[var(--text-faint)]">
                    Tek dosya · en fazla {MAX_FILE_BYTES / (1024 * 1024)} MB
                  </p>
                </div>
              </div>
              <span className="rounded-full border border-[var(--border)] bg-[var(--surface-3)] px-2.5 py-1 text-[10px] text-[var(--text-soft)]">
                {demoMode ? "Demo modu" : "Sunucu analizi"}
              </span>
            </div>

            <div className="mt-4">
              <Dropzone
                file={file}
                error={fileError}
                disabled={phase === "analyzing"}
                onSelect={(next) => {
                  setFile(next);
                  setFileError(null);
                  if (phase === "done" || phase === "error") {
                    setResult(null);
                    setPhase("idle");
                    setStageNote(null);
                  }
                }}
                onRemove={() => {
                  setFile(null);
                  setFileError(null);
                }}
                onError={(message) => setFileError(message)}
              />
            </div>

            {demoMode ? (
              <p className="mt-3 rounded-lg border border-[var(--warning-border)] bg-[var(--warning-bg)] px-3 py-2 text-[11px] leading-relaxed text-[var(--warning)]">
                Backend çevrimdışı: <strong>Analiz Et</strong> yerel demo sonucu üretir. Dosya
                yüklenmez, hiçbir veri ağa çıkmaz.
              </p>
            ) : null}

            <div className="panel-soft mt-4 p-4">
              <label className="flex cursor-pointer items-start gap-3">
                <input
                  type="checkbox"
                  className="mt-0.5 h-4 w-4 shrink-0 accent-[var(--primary)]"
                  checked={useCalculated}
                  onChange={(event) => {
                    setUseCalculated(event.target.checked);
                    setCalculatedError(null);
                  }}
                />
                <span>
                  <span className="text-sm font-medium text-[var(--text)]">
                    Hesaplanan değerlerle karşılaştır
                  </span>
                  <span className="mt-0.5 block text-[11px] leading-relaxed text-[var(--text-faint)]">
                    Oturum hesapları bağlanana kadar karşılaştırma payload'ını JSON olarak
                    yapıştırın. Boş bırakılırsa yalnızca alan çıkarımı yapılır.
                  </span>
                </span>
              </label>

              {useCalculated ? (
                <div className="mt-3">
                  <label
                    htmlFor="ocr-calculated"
                    className="text-[10px] font-medium uppercase tracking-[0.16em] text-[var(--text-muted)]"
                  >
                    calculated JSON (opsiyonel)
                  </label>
                  <textarea
                    id="ocr-calculated"
                    value={calculatedJson}
                    onChange={(event) => {
                      setCalculatedJson(event.target.value);
                      setCalculatedError(null);
                    }}
                    rows={4}
                    spellCheck={false}
                    placeholder='{"test_pressure_bar": 80.0, "air_test": {"vpa_m3": 0.00768}}'
                    aria-invalid={calculatedError ? true : undefined}
                    aria-describedby="ocr-calculated-hint"
                    className={clsx(
                      "numeric mt-1.5 w-full resize-y rounded-lg border bg-[var(--surface-2)] px-3 py-2 text-[11px] leading-relaxed text-[var(--text)] placeholder:text-[var(--text-faint)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)]",
                      calculatedError ? "border-[var(--danger-border)]" : "border-[var(--border)]",
                    )}
                  />
                  <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
                    <p id="ocr-calculated-hint" className="text-[10px] text-[var(--text-faint)]">
                      Şema: <span className="numeric">pipe_od_mm</span>,{" "}
                      <span className="numeric">test_pressure_bar</span>,{" "}
                      <span className="numeric">air_test.vpa_m3</span>,{" "}
                      <span className="numeric">pressure_test.pa_bar</span>,{" "}
                      <span className="numeric">result</span>.
                    </p>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          setCalculatedJson(JSON.stringify(SAMPLE_CALCULATED, null, 2));
                          setCalculatedError(null);
                        }}
                        className="rounded-md border border-[var(--border)] px-2.5 py-1 text-[10px] font-medium text-[var(--text-soft)] transition hover:border-[var(--info-border)] hover:text-[var(--primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)]"
                      >
                        Örnek doldur
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setCalculatedJson("");
                          setCalculatedError(null);
                        }}
                        disabled={calculatedJson.length === 0}
                        className="rounded-md border border-[var(--border)] px-2.5 py-1 text-[10px] font-medium text-[var(--text-soft)] transition hover:border-[var(--border-strong)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)] disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        Temizle
                      </button>
                    </div>
                  </div>
                  {calculatedError ? (
                    <p
                      id="ocr-calculated-error"
                      role="alert"
                      className="mt-2 rounded-md border border-[var(--danger-border)] bg-[var(--danger-bg)] px-2.5 py-1.5 text-[11px] text-[var(--danger)]"
                    >
                      {calculatedError}
                    </p>
                  ) : null}
                </div>
              ) : null}
            </div>

            <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t hairline pt-4">
              <div className="min-w-0">
                <p className="text-xs text-[var(--text-soft)]">
                  Eşleme profili:{" "}
                  <span className="font-medium text-[var(--text)]">
                    {selectedProfile?.name ?? "Varsayılan etiket sözlüğü"}
                  </span>
                </p>
                <p className="mt-0.5 text-[10px] text-[var(--text-faint)]">
                  {profilesDemo
                    ? "Yerel taslak profil yalnızca önizleme içindir; analizle gönderilmez."
                    : `Karşılaştırma: ${useCalculated && calculatedJson.trim() ? "JSON payload gönderilecek" : "yalnızca alan çıkarımı"}`}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {phase === "analyzing" ? (
                  <button
                    type="button"
                    onClick={handleCancel}
                    className="inline-flex min-h-10 items-center gap-1.5 rounded-lg border border-[var(--danger-border)] px-3.5 py-2 text-sm font-medium text-[var(--danger)] transition hover:bg-[var(--danger-bg)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)]"
                  >
                    <Square size={14} aria-hidden="true" />
                    İptal
                  </button>
                ) : null}
                <button
                  type="button"
                  onClick={() => {
                    void runAnalysis();
                  }}
                  disabled={!file || phase === "analyzing"}
                  aria-describedby={analyzeDisabledReason ? "ocr-analyze-reason" : undefined}
                  className="inline-flex min-h-10 items-center gap-2 rounded-lg bg-[var(--primary)] px-4 py-2 text-sm font-semibold text-[var(--primary-ink)] transition hover:bg-[var(--primary-strong)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--canvas)] disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {phase === "analyzing" ? (
                    <Loader2 size={16} className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
                  ) : (
                    <ScanLine size={16} aria-hidden="true" />
                  )}
                  Analiz Et
                  {demoMode ? (
                    <span className="rounded border border-current px-1.5 py-0.5 text-[9px] uppercase tracking-wide">
                      demo
                    </span>
                  ) : null}
                </button>
              </div>
            </div>

            {analyzeDisabledReason ? (
              <p id="ocr-analyze-reason" className="mt-2 text-right text-[10px] text-[var(--text-faint)]">
                {analyzeDisabledReason}
              </p>
            ) : null}

            {phase === "analyzing" ? (
              <div
                className="panel-soft mt-4 p-4"
                aria-live="polite"
                aria-busy="true"
                role="status"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="flex items-center gap-2 text-xs font-medium text-[var(--text)]">
                    <Loader2 size={14} className="animate-spin text-[var(--primary)] motion-reduce:animate-none" aria-hidden="true" />
                    Analiz sürüyor · {STAGES[activeStageIndex].label}
                  </p>
                  <p className="numeric text-[10px] text-[var(--text-muted)]">
                    {formatNumber(elapsed, 0)} sn · 300 sn sınırı
                  </p>
                </div>
                <ol className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                  {STAGES.map((item, index) => {
                    const completed = index < activeStageIndex;
                    const active = index === activeStageIndex;
                    return (
                      <li
                        key={item.key}
                        aria-current={active ? "step" : undefined}
                        className={clsx(
                          "rounded-lg border px-2.5 py-2",
                          active
                            ? "border-[var(--info-border)] bg-[var(--info-bg)]"
                            : completed
                              ? "border-[var(--success-border)] bg-[var(--success-bg)]"
                              : "border-[var(--border)] bg-[var(--surface-2)]",
                        )}
                      >
                        <p className="flex items-center gap-1.5 text-[11px] font-medium text-[var(--text-soft)]">
                          {completed ? (
                            <CheckCircle2 size={12} className="text-[var(--success)]" aria-hidden="true" />
                          ) : active ? (
                            <Loader2 size={12} className="animate-spin text-[var(--primary)] motion-reduce:animate-none" aria-hidden="true" />
                          ) : (
                            <span
                              className="h-3 w-3 rounded-full border border-[var(--border-strong)]"
                              aria-hidden="true"
                            />
                          )}
                          {item.label}
                        </p>
                        <p className="mt-0.5 text-[10px] text-[var(--text-faint)]">{item.detail}</p>
                      </li>
                    );
                  })}
                </ol>
                <p className="mt-2 text-[10px] leading-relaxed text-[var(--text-faint)]">
                  {stageNote ?? "Sunucu aşama bilgisi bekleniyor…"} Sayfa sayısı çıkarım bitince
                  gösterilir.
                </p>
              </div>
            ) : null}

            {phase === "idle" && stageNote ? (
              <p
                role="status"
                className="mt-3 rounded-lg border border-[var(--border)] bg-[var(--surface-3)] px-3 py-2 text-[11px] text-[var(--text-soft)]"
              >
                {stageNote}
              </p>
            ) : null}
          </section>

          {error ? (
            <div
              ref={errorRef}
              tabIndex={-1}
              role="alert"
              className="panel border-[var(--danger-border)] p-5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)]"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="flex items-center gap-2 text-sm font-semibold text-[var(--danger)]">
                  <AlertTriangle size={17} aria-hidden="true" />
                  Analiz tamamlanamadı
                </p>
                <span className="numeric rounded border border-[var(--danger-border)] bg-[var(--danger-bg)] px-2 py-0.5 text-[10px] text-[var(--danger)]">
                  {error.code}
                </span>
              </div>
              <p className="mt-2 text-sm leading-relaxed text-[var(--text)]">{error.message}</p>
              <p className="mt-1.5 text-[11px] leading-relaxed text-[var(--warning)]">{error.hint}</p>

              {Object.keys(error.details).length > 0 ? (
                <details className="mt-3">
                  <summary className="cursor-pointer text-[11px] font-medium text-[var(--text-muted)]">
                    Teknik ayrıntı
                  </summary>
                  <pre className="numeric mt-2 max-h-48 overflow-auto rounded-lg border hairline bg-[var(--surface-2)] p-3 text-[10px] leading-relaxed text-[var(--text-soft)]">
                    {JSON.stringify(error.details, null, 2)}
                  </pre>
                </details>
              ) : null}

              {error.requestId ? (
                <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-[var(--text-muted)]">
                  <span>
                    request_id: <span className="numeric text-[var(--text-soft)]">{error.requestId}</span>
                  </span>
                  <button
                    type="button"
                    onClick={() => {
                      void copyRequestId();
                    }}
                    className="inline-flex items-center gap-1 rounded border border-[var(--border)] px-2 py-0.5 text-[10px] text-[var(--text-soft)] hover:border-[var(--info-border)] hover:text-[var(--primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)]"
                  >
                    <Clipboard size={11} aria-hidden="true" />
                    {copiedRequestId ? "Kopyalandı" : "Kopyala"}
                  </button>
                  <span aria-live="polite" className="sr-only">
                    {copiedRequestId ? "request_id panoya kopyalandı" : ""}
                  </span>
                </div>
              ) : null}

              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => {
                    void runAnalysis();
                  }}
                  disabled={!file}
                  className="inline-flex min-h-10 items-center gap-1.5 rounded-lg bg-[var(--primary)] px-3.5 py-2 text-xs font-semibold text-[var(--primary-ink)] hover:bg-[var(--primary-strong)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)] disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <RefreshCw size={13} aria-hidden="true" />
                  Yeniden dene
                </button>
                <button
                  type="button"
                  onClick={showDemo}
                  className="inline-flex min-h-10 items-center gap-1.5 rounded-lg border border-[var(--warning-border)] bg-[var(--warning-bg)] px-3.5 py-2 text-xs font-medium text-[var(--warning)] hover:bg-[var(--warning-bg)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)]"
                >
                  <ScanLine size={13} aria-hidden="true" />
                  Demo sonucu göster
                </button>
                <button
                  type="button"
                  onClick={resetAll}
                  className="inline-flex min-h-10 items-center gap-1.5 rounded-lg border border-[var(--border)] px-3.5 py-2 text-xs font-medium text-[var(--text-soft)] hover:border-[var(--border-strong)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)]"
                >
                  <RotateCcw size={13} aria-hidden="true" />
                  Yeni analiz
                </button>
              </div>
            </div>
          ) : null}

          {!result && phase === "idle" ? (
            <section className="panel p-6" aria-labelledby="ocr-empty-title">
              <div className="flex items-start gap-4">
                <span className="grid h-12 w-12 shrink-0 place-items-center rounded-xl border border-[var(--border)] bg-[var(--surface-3)] text-[var(--text-soft)]">
                  <ArrowRight size={20} aria-hidden="true" />
                </span>
                <div>
                  <h2 id="ocr-empty-title" className="text-base font-semibold text-[var(--text)]">
                    Henüz analiz yok
                  </h2>
                  <p className="mt-1 max-w-2xl text-xs leading-relaxed text-[var(--text-muted)]">
                    Raporu yükleyip <strong className="text-[var(--text-soft)]">Analiz Et</strong> ile
                    başlayın. Sonuç; özet, alan tablosu, uyuşmazlıklar, uyarılar ve insan onayı
                    adımlarıyla burada açılır.
                  </p>
                  <ol className="mt-3 grid gap-2 text-[11px] text-[var(--text-muted)] sm:grid-cols-3">
                    <li className="rounded-lg border border-[var(--border)] bg-[var(--surface-3)] px-3 py-2">
                      <span className="numeric text-[var(--primary)]">01</span> · Dosyayı yükleyin
                    </li>
                    <li className="rounded-lg border border-[var(--border)] bg-[var(--surface-3)] px-3 py-2">
                      <span className="numeric text-[var(--primary)]">02</span> · Alanları inceleyin
                    </li>
                    <li className="rounded-lg border border-[var(--border)] bg-[var(--surface-3)] px-3 py-2">
                      <span className="numeric text-[var(--primary)]">03</span> · Onaya hazırlayın
                    </li>
                  </ol>
                </div>
              </div>
            </section>
          ) : null}

          {result ? (
            <div className="space-y-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-[10px] font-medium uppercase tracking-[0.2em] text-[var(--text-faint)]">
                    Sonuç
                  </p>
                  <h2
                    ref={resultHeadingRef}
                    tabIndex={-1}
                    className="mt-1 text-lg font-semibold text-[var(--text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)]"
                  >
                    Analiz sonucu{" "}
                    <span className="numeric text-xs font-normal text-[var(--text-faint)]">
                      #{shortId(result.id)}
                    </span>
                  </h2>
                  <p className="mt-1 text-[11px] text-[var(--text-muted)]">
                    {result.source ? SOURCE_LABELS[result.source] : "Kaynak bilinmiyor"} ·{" "}
                    {formatNumber(result.page_count ?? 0, 0)} sayfa ·{" "}
                    {formatDateTime(result.finished_at ?? result.created_at)}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {resultDemo ? (
                    <span className="self-center rounded-full border border-[var(--warning-border)] bg-[var(--warning-bg)] px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--warning)]">
                      demo · resmi değil
                    </span>
                  ) : null}
                  <button
                    type="button"
                    onClick={downloadJson}
                    className="inline-flex min-h-10 items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface-3)] px-3.5 py-2 text-xs font-medium text-[var(--text)] hover:border-[var(--info-border)] hover:text-[var(--primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)]"
                  >
                    <Download size={14} aria-hidden="true" />
                    JSON İndir
                  </button>
                  <button
                    type="button"
                    onClick={resetAll}
                    className="inline-flex min-h-10 items-center gap-1.5 rounded-lg border border-[var(--border)] px-3.5 py-2 text-xs font-medium text-[var(--text-soft)] hover:border-[var(--border-strong)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)]"
                  >
                    <Trash2 size={14} aria-hidden="true" />
                    Yeni Analiz
                  </button>
                </div>
              </div>

              <div
                role="status"
                className="rounded-xl border border-[var(--danger-border)] bg-[var(--danger-bg)] px-4 py-3"
              >
                <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-[0.14em] text-[var(--danger)]">
                  <ShieldAlert size={16} aria-hidden="true" />
                  İnsan onayı gerekli
                </p>
                <p className="mt-1 text-[11px] leading-relaxed text-[var(--danger)]">
                  {(result.discrepancies ?? []).some(isBlockingDiscrepancy)
                    ? "Engelleyici uyuşmazlık var; kabul akışı durduruldu. İki kişi onayı önerilir."
                    : "Otomatik çıktı kabul kararı değildir. Tüm alanlar yetkili personel tarafından doğrulanmalıdır."}
                </p>
              </div>

              <SummaryCard result={result} demo={resultDemo} />

              <section className="panel" aria-labelledby="ocr-result-table-title">
                <div className="flex flex-wrap items-center justify-between gap-2 px-5 pt-4">
                  <h2
                    id="ocr-result-table-title"
                    className="text-sm font-semibold text-[var(--text)]"
                  >
                    Sonuç ayrıntıları
                  </h2>
                  <p className="text-[10px] text-[var(--text-faint)]">
                    {ANALYSIS_STATUS_LABELS[result.status]} ·{" "}
                    {comparisonRequested ? "karşılaştırma yapıldı" : "karşılaştırma yapılmadı"}
                  </p>
                </div>
                <div
                  role="tablist"
                  aria-label="Analiz sonucu sekmeleri"
                  className="mt-3 flex flex-wrap gap-1 border-b hairline px-3"
                  onKeyDown={handleTabKeyDown}
                >
                  {tabs.map((item) => {
                    const selected = tab === item.key;
                    return (
                      <button
                        key={item.key}
                        type="button"
                        role="tab"
                        id={`ocr-tab-${item.key}`}
                        aria-selected={selected}
                        aria-controls={`ocr-panel-${item.key}`}
                        tabIndex={selected ? 0 : -1}
                        onClick={() => setTab(item.key)}
                        className={clsx(
                          "inline-flex min-h-10 items-center gap-1.5 rounded-t-lg border-b-2 px-3 py-2 text-xs font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)]",
                          selected
                            ? "border-[var(--primary)] text-[var(--primary)]"
                            : "border-transparent text-[var(--text-muted)] hover:text-[var(--text-soft)]",
                        )}
                      >
                        {item.label}
                        <span
                          className={clsx(
                            "numeric rounded-full px-1.5 py-0.5 text-[10px]",
                            selected ? "bg-[var(--primary-soft)] text-[var(--primary)]" : "bg-[var(--surface-3)] text-[var(--text-muted)]",
                          )}
                        >
                          {item.count}
                        </span>
                      </button>
                    );
                  })}
                </div>

                <div
                  role="tabpanel"
                  id={`ocr-panel-${tab}`}
                  aria-labelledby={`ocr-tab-${tab}`}
                  className="pb-1"
                >
                  {tab === "fields" ? (
                    <FieldsTable
                      fields={fields}
                      selected={selectedFields}
                      edits={edits}
                      onToggle={toggleField}
                      onEdit={editField}
                    />
                  ) : null}
                  {tab === "discrepancies" ? (
                    <DiscrepanciesTable
                      items={result.discrepancies ?? []}
                      hasCalculated={comparisonRequested}
                    />
                  ) : null}
                  {tab === "warnings" ? (
                    <WarningsPanel
                      warnings={result.warnings ?? []}
                      issues={result.issues ?? []}
                      reportWarnings={result.report?.warnings ?? []}
                    />
                  ) : null}
                </div>
              </section>

              <section className="panel p-5" aria-labelledby="ocr-approval-title">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h2 id="ocr-approval-title" className="text-base font-semibold text-[var(--text)]">
                    Alan onayı
                  </h2>
                  <span className="numeric rounded-full border border-[var(--border)] bg-[var(--surface-3)] px-2.5 py-1 text-[10px] text-[var(--text-soft)]">
                    {selectedFields.size}/{fields.length} seçili
                  </span>
                </div>
                <p className="mt-1 max-w-3xl text-[11px] leading-relaxed text-[var(--text-muted)]">
                  Onay, raporun ham değerini değiştirmez; onaylı değer ayrı saklanır. Düşük güvenli
                  alanlar (&lt; {formatNumber(lowThreshold, 2)}) açıkça işaretlenmeden toplu onay
                  verilemez. Kritik güven eşiği &lt; {formatNumber(criticalThreshold, 2)}.
                </p>

                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setSelectedFields(new Set(fields.map((item) => item.descriptor.key)))}
                    disabled={allSelected || fields.length === 0}
                    className="rounded-md border border-[var(--border)] px-2.5 py-1.5 text-[11px] font-medium text-[var(--text-soft)] hover:border-[var(--border-strong)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)] disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    Tümünü seç
                  </button>
                  <button
                    type="button"
                    onClick={() => setSelectedFields(new Set())}
                    disabled={selectedFields.size === 0}
                    className="rounded-md border border-[var(--border)] px-2.5 py-1.5 text-[11px] font-medium text-[var(--text-soft)] hover:border-[var(--border-strong)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)] disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    Seçimi temizle
                  </button>
                  {pendingLowConfidence.length > 0 ? (
                    <span className="rounded-full border border-[var(--warning-border)] bg-[var(--warning-bg)] px-2.5 py-1 text-[10px] text-[var(--warning)]">
                      {pendingLowConfidence.length} düşük güvenli alan onay bekliyor:{" "}
                      {pendingLowConfidence
                        .slice(0, 3)
                        .map((item) => item.descriptor.label)
                        .join(", ")}
                      {pendingLowConfidence.length > 3 ? "…" : ""}
                    </span>
                  ) : (
                    <span className="rounded-full border border-[var(--success-border)] bg-[var(--success-bg)] px-2.5 py-1 text-[10px] text-[var(--success)]">
                      düşük güvenli alan seçimi tamam
                    </span>
                  )}
                  {editedCount > 0 ? (
                    <span className="rounded-full border border-[var(--border)] bg-[var(--surface-3)] px-2.5 py-1 text-[10px] text-[var(--text-soft)]">
                      {editedCount} elle düzeltme
                    </span>
                  ) : null}
                </div>

                <div className="mt-4 flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled
                    title={approveBlockedReason}
                    aria-describedby="ocr-approve-reason"
                    className="inline-flex min-h-10 items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface-3)] px-4 py-2 text-xs font-semibold text-[var(--text-muted)] opacity-60"
                  >
                    <CheckCircle2 size={14} aria-hidden="true" />
                    Seçilenleri onayla ({selectedFields.size})
                  </button>
                  <button
                    type="button"
                    disabled
                    title="Oturuma uygulama, onay tamamlandıktan ve oturum seçildikten sonra etkinleşecek."
                    className="inline-flex min-h-10 items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface-3)] px-4 py-2 text-xs font-semibold text-[var(--text-muted)] opacity-60"
                  >
                    <ArrowRight size={14} aria-hidden="true" />
                    Oturuma uygula
                  </button>
                </div>
                <p
                  id="ocr-approve-reason"
                  className="mt-2 rounded-lg border border-[var(--border)] bg-[var(--surface-3)] px-3 py-2 text-[10px] leading-relaxed text-[var(--text-muted)]"
                >
                  Neden pasif: {approveBlockedReason}
                </p>
                <p className="mt-2 text-[10px] leading-relaxed text-[var(--text-faint)]">
                  Denetim izi: onaylayan kullanıcı, zaman damgası, alan bazlı değer ve ham OCR metni
                  kaydedilir. Uygulama ayrı bir adımdır; onayla birlikte oturuma yazılmaz.
                </p>
              </section>
            </div>
          ) : null}
        </div>

        <aside className="space-y-5" aria-label="OCR bağlamı">
          <StatusPanel
            status={status}
            loading={statusLoading}
            error={statusError}
            demoActive={resultDemo}
            onRetry={() => {
              void loadStatus();
            }}
            onDemo={showDemo}
          />
          <HistoryPanel
            items={history}
            loading={historyLoading}
            error={historyError}
            demo={historyDemo}
            openingId={openingHistoryId}
            selectedId={result?.id ?? null}
            onOpen={(item) => {
              void openHistoryItem(item);
            }}
            onRefresh={() => {
              void loadHistory();
            }}
          />
        </aside>
      </div>

      <div>
        <MappingPanel
          profiles={profiles}
          selectedProfileId={selectedProfileId}
          onSelectProfile={setSelectedProfileId}
          profile={profileDetail}
          loading={profilesLoading || profileDetailLoading}
          error={profileDetailError ?? profilesError}
          onRetry={() => {
            void loadProfiles();
          }}
          demo={profilesDemo}
        />
      </div>
    </div>
  );
}
