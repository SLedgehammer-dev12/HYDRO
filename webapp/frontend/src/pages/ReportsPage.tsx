import { useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  ClipboardCopy,
  Download,
  FileJson,
  FileSpreadsheet,
  FileText,
  History,
  RefreshCw,
  ScanLine,
  Upload,
} from "lucide-react";
import { PageHeader } from "../components/layout/PageHeader";
import { SectionCard } from "../components/ui/Card";
import { Badge } from "../components/ui/Badge";
import { Button, IconButton } from "../components/ui/Button";
import { TextField } from "../components/ui/Field";
import { InlineNotice, EmptyState } from "../components/ui/State";
import {
  hydrateSessionResults,
  useImportDesktopSnapshot,
  useMeta,
  useSafeSwitchSession,
  useSessions,
} from "../hooks/queries";
import { useAppStore } from "../store/useAppStore";
import { api, apiErrorMessage, extractRevisionConflict } from "../lib/api";
import { applyOfflineSnapshot } from "../lib/normalize";
import { buildReportText, buildSnapshot, downloadJson, downloadText, reportFileName } from "../lib/report";
import { dateOnly, fmt, nowIso, num, relativeTime } from "../lib/format";
import { CHECK_DEFINITIONS } from "../lib/constants";
import type { SnapshotMapping } from "../lib/types";

type Format = "pdf" | "xlsx" | "txt";

const FORMAT_META: Record<Format, { label: string; icon: typeof FileText; mime: string }> = {
  pdf: { label: "PDF", icon: FileText, mime: "application/pdf" },
  xlsx: { label: "Excel", icon: FileSpreadsheet, mime: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" },
  txt: { label: "TXT", icon: FileText, mime: "text/plain" },
};

export function ReportsPage() {
  const inputs = useAppStore((state) => state.inputs);
  const results = useAppStore((state) => state.results);
  const exports = useAppStore((state) => state.exports);
  const addExport = useAppStore((state) => state.addExport);
  const patchInputs = useAppStore((state) => state.patchInputs);
  const setTab = useAppStore((state) => state.setTab);
  const applySessionInputs = useAppStore((state) => state.applySessionInputs);
  const setSessionMeta = useAppStore((state) => state.setSessionMeta);
  const markSaved = useAppStore((state) => state.markSaved);
  const markDirty = useAppStore((state) => state.markDirty);
  const setRevisionConflict = useAppStore((state) => state.setRevisionConflict);
  const pushToast = useAppStore((state) => state.pushToast);

  const sessionId = useAppStore((state) => state.sessionId);
  const projectId = useAppStore((state) => state.projectId);
  const backend = useAppStore((state) => state.backend);
  const sessionApiReady = useAppStore((state) => state.sessionApiReady);
  const revision = useAppStore((state) => state.revision);
  const currentName = useAppStore((state) => state.sessionName);
  const sessionStatus = useAppStore((state) => state.sessionStatus);

  const queryClient = useQueryClient();
  const { data: meta } = useMeta();
  const { data: sessions } = useSessions();
  const safeSwitchSession = useSafeSwitchSession();
  const importDesktopSnapshot = useImportDesktopSnapshot();

  const [generatedAt, setGeneratedAt] = useState(() => new Date());
  const [busy, setBusy] = useState<Format | null>(null);
  const [includeRawOcr, setIncludeRawOcr] = useState(false);
  const [snapshotBusy, setSnapshotBusy] = useState(false);
  const [snapshotMode, setSnapshotMode] = useState<"merge" | "replace">("merge");
  const [lastMapping, setLastMapping] = useState<{
    action: "upload" | "import";
    name: string;
    mapping: SnapshotMapping;
  } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const newImportRef = useRef<HTMLInputElement>(null);
  const isOffline = backend !== "online";

  const history = useAppStore((state) => state.history);
  const reportText = useMemo(() => {
    const base = buildReportText(inputs, results, meta, generatedAt, history);
    return isOffline
      ? `[TASLAK / ÇEVRİMDIŞI DEMO — RESMİ KABUL DEĞİLDİR]\nSunucu bağlantısı olmadan tarayıcıda üretilmiştir.\n\n${base}`
      : base;
  }, [inputs, results, meta, generatedAt, history, isOffline]);

  const sectionsStatus = [
    { label: "Geometri", ready: Boolean(results.geometry), detail: results.geometry ? fmt.m(results.geometry.total_length_m, 0) : "hesap yok" },
    { label: "A katsayısı", ready: Boolean(inputs.air.a_micro_per_bar), detail: fmt.a(inputs.air.a_micro_per_bar) },
    { label: "B katsayısı", ready: inputs.pressure.b_micro_per_c !== null, detail: fmt.b(inputs.pressure.b_micro_per_c) },
    { label: "Hava testi", ready: Boolean(results.air), detail: results.air?.decision.status ?? "—" },
    { label: "Basınç testi", ready: Boolean(results.pressure), detail: results.pressure?.decision.status ?? "—" },
    { label: "Profil", ready: Boolean(results.profile), detail: results.profile?.decision.status ?? "—" },
    { label: "Pig", ready: Boolean(results.pig), detail: results.pig?.status ?? "—" },
    {
      label: "Saha kontrolü",
      ready: CHECK_DEFINITIONS.every((check) => inputs.checks[check.key]),
      detail: `${CHECK_DEFINITIONS.filter((check) => inputs.checks[check.key]).length}/${CHECK_DEFINITIONS.length}`,
    },
  ];

  async function copyPreview() {
    try {
      await navigator.clipboard.writeText(reportText);
      pushToast("success", "Rapor metni kopyalandı");
    } catch {
      pushToast("error", "Kopyalanamadı", "Tarayıcı pano iznini kontrol edin.");
    }
  }

  function localTxt(fallbackReason?: string) {
    const filename = reportFileName("txt", inputs.report.report_no);
    downloadText(reportText, filename);
    addExport({ format: "txt", filename, size: new Blob([reportText]).size, demo: true });
    pushToast(
      fallbackReason ? "warning" : "success",
      "TXT raporu indirildi",
      fallbackReason ?? "Rapor önizlemesi yerel olarak üretildi.",
    );
  }

  async function exportReport(format: Format) {
    if ((format === "pdf" || format === "xlsx") && (isOffline || !sessionId)) {
      pushToast(
        "warning",
        `${FORMAT_META[format].label} çıktısı çevrimdışı/demo modda kapalı`,
        "Resmi PDF/Excel çıktısı için sunucuya bağlanın ve aktif oturum seçin.",
      );
      return;
    }
    setBusy(format);
    try {
      if (format === "txt" && (isOffline || !sessionId)) {
        localTxt();
        return;
      }
      if (!sessionId) {
        return;
      }
      const { blob, filename } = await api.exportSession(sessionId, format, { includeRawOcr });
      const link = document.createElement("a");
      const url = URL.createObjectURL(blob);
      link.href = url;
      link.download = filename || reportFileName(format, inputs.report.report_no);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 2_000);
      addExport({
        format,
        filename: filename || reportFileName(format, inputs.report.report_no),
        size: blob.size,
        demo: false,
      });
      pushToast("success", `${FORMAT_META[format].label} raporu indirildi`, "Dosya indirme klasörünüze kaydedildi.");
    } catch (error) {
      pushToast("error", "Rapor indirilemedi", apiErrorMessage(error));
    } finally {
      setBusy(null);
    }
  }

  async function downloadSnapshot() {
    setSnapshotBusy(true);
    try {
      const snapshot = buildSnapshot(inputs, results, meta);
      if (backend === "online" && sessionId) {
        const { blob, filename } = await api.snapshotDownload(sessionId);
        const link = document.createElement("a");
        const url = URL.createObjectURL(blob);
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.setTimeout(() => URL.revokeObjectURL(url), 2_000);
        pushToast("success", "Snapshot indirildi", filename);
      } else {
        const filename = reportFileName("json", inputs.report.report_no).replace("hidrostatik_test", "hidrostatik_test_girdileri");
        downloadJson(snapshot, filename);
        pushToast("success", "Snapshot indirildi", "Masaüstü uyumlu JSON tarayıcıdan üretildi.");
      }
    } catch (error) {
      pushToast("error", "Snapshot indirilemedi", apiErrorMessage(error));
    } finally {
      setSnapshotBusy(false);
    }
  }

  async function uploadSnapshot(file: File) {
    setSnapshotBusy(true);
    let parsedSnapshot: Record<string, unknown> | null = null;
    try {
      const text = await file.text();
      const parsed: unknown = JSON.parse(text);
      if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
        pushToast("error", "Snapshot yüklenemedi", "Dosya kök değeri geçerli bir JSON nesnesi değil.");
        return;
      }
      parsedSnapshot = parsed as Record<string, unknown>;
      if (backend === "online" && sessionApiReady !== false && sessionId) {
        const response = await api.snapshotUpload(sessionId, parsedSnapshot, revision, snapshotMode);
        applySessionInputs(response.inputs);
        setSessionMeta({
          id: response.id,
          name: response.name,
          status: response.status,
          revision: response.revision,
        });
        markSaved(response.revision);
        setRevisionConflict(null);
        queryClient.setQueryData(["session", response.id], response);
        void queryClient.invalidateQueries({ queryKey: ["results", response.id] });
        void queryClient.invalidateQueries({ queryKey: ["sessions"] });
        void queryClient.invalidateQueries({ queryKey: ["project-scene"] });
        void hydrateSessionResults(response.id);
        if (response.mapping) {
          setLastMapping({ action: "upload", name: response.name, mapping: response.mapping });
        }
        pushToast(
          "success",
          "Snapshot mevcut kesite uygulandı",
          `${response.mapping?.converted ?? 0} alan dönüştürüldü, ${response.mapping?.skipped.length ?? 0} alan atlandı.`,
        );
      } else {
        const offlineResult = applyOfflineSnapshot(inputs, parsedSnapshot, snapshotMode);
        applySessionInputs(offlineResult.inputs);
        markDirty();
        setLastMapping({ action: "upload", name: currentName, mapping: offlineResult.mapping });
        pushToast(
          "success",
          "Snapshot yerel olarak yüklendi",
          backend === "online" && sessionApiReady !== false
            ? "Aktif sunucu oturumu seçili değil; girdiler yerel taslağa uygulandı."
            : "Sunucu bağlantısı yok; girdiler tarayıcı oturumuna uygulandı.",
        );
      }
    } catch (error) {
      const conflict = extractRevisionConflict(error);
      if (conflict && sessionId && parsedSnapshot) {
        setRevisionConflict({
          sessionId,
          localRevision: revision,
          localName: currentName,
          localStatus: sessionStatus,
          localProjectId: projectId && !projectId.startsWith("demo-") ? projectId : null,
          localInputs: inputs,
          serverSession: conflict.serverSession,
          serverDiff: conflict.serverDiff,
          sourceAction: "snapshot_upload",
          detectedAt: nowIso(),
          pendingSnapshot: { snapshot: parsedSnapshot, mode: snapshotMode },
        });
        pushToast(
          "warning",
          "Revizyon çakışması (HTTP 409)",
          `Sunucuda revizyon ${conflict.currentRevision} bulundu; fark penceresi açıldı.`,
        );
        return;
      }
      pushToast(
        "error",
        "Snapshot yüklenemedi",
        error instanceof SyntaxError ? "Dosya geçerli JSON değil." : apiErrorMessage(error),
      );
    } finally {
      setSnapshotBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  function importSnapshotAsNewSession(file: File) {
    const cleanName = file.name.replace(/\.json$/i, "").trim() || undefined;
    importDesktopSnapshot.mutate(
      {
        file,
        name: cleanName,
        projectId,
        openAfterImport: true,
      },
      {
        onSuccess: (res) => {
          setLastMapping({ action: "import", name: res.session.name, mapping: res.mapping });
        },
        onSettled: () => {
          if (newImportRef.current) newImportRef.current.value = "";
        },
      },
    );
  }

  return (
    <div className="space-y-5">
      <PageHeader
        kicker="Raporlar"
        title="Rapor önizleme ve dışa aktarma"
        description="Önizleme salt okunurdur; düzeltmeler ilgili sekmelerde yapılır. Rapor kimliği Test Bölümü bazlıdır."
        meta={
          <>
            <Badge tone="info">{inputs.report.report_no || "Rapor no yok"}</Badge>
            <span className="text-[10.5px] text-[var(--text-faint)]">
              {inputs.report.operator || "Operatör belirtilmedi"} · {inputs.report.date || "Tarih yok"}
            </span>
            {backend === "demo" ? <Badge tone="warning">yerel çıktı</Badge> : null}
          </>
        }
        actions={
          <>
            <Button variant="ghost" icon={<ScanLine size={14} />} onClick={() => setTab("ocr")}>
              OCR ile karşılaştır
            </Button>
            <Button
              variant="primary"
              icon={<Download size={14} />}
              disabled={isOffline || !sessionId}
              loading={busy === "pdf"}
              title={isOffline || !sessionId ? "Çevrimdışı/demo modda resmi PDF kapalı" : undefined}
              onClick={() => void exportReport("pdf")}
            >
              PDF indir
            </Button>
          </>
        }
      />

      <div className="grid gap-4 xl:grid-cols-[1fr_1.35fr]">
        <div className="space-y-4">
          <SectionCard
            title="Rapor kimliği"
            description="Boş bırakılabilir; boş alanlar raporda “—” görünür."
            icon={FileText}
          >
            <div className="grid grid-cols-2 gap-3">
              <TextField
                label="Rapor no"
                value={inputs.report.report_no}
                onChange={(value) => patchInputs({ report: { report_no: value } })}
                placeholder="BOT-2026-0142"
                maxLength={60}
              />
              <TextField
                label="Operatör"
                value={inputs.report.operator}
                onChange={(value) => patchInputs({ report: { operator: value } })}
                placeholder="Ad Soyad"
                maxLength={80}
              />
              <TextField
                label="Tarih"
                value={inputs.report.date}
                onChange={(value) => patchInputs({ report: { date: value } })}
                placeholder="YYYY-AA-GG"
                help={inputs.report.date ? `Raporda: ${dateOnly(inputs.report.date)}` : "ISO tarih (YYYY-AA-GG)"}
              />
              <TextField
                label="Bölüm no"
                value={inputs.report.section_id}
                onChange={(value) => patchInputs({ report: { section_id: value } })}
                placeholder="12-13"
                maxLength={40}
              />
            </div>
          </SectionCard>

          <SectionCard
            title="İçerik durumu"
            description="Boş bölümler raporda “Kaydedilecek sonuç yok” olarak görünür."
            icon={History}
          >
            <ul className="grid gap-1.5">
              {sectionsStatus.map((section) => (
                <li
                  key={section.label}
                  className="flex items-center justify-between gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-1.5"
                >
                  <span className="flex items-center gap-1.5 text-[11px]">
                    <span className={section.ready ? "status-dot tone-pass" : "status-dot tone-pending"} aria-hidden />
                    {section.label}
                  </span>
                  <span className="max-w-[55%] truncate text-right font-mono text-[10px] text-[var(--text-faint)]">{section.detail}</span>
                </li>
              ))}
            </ul>
          </SectionCard>

          <SectionCard title="Dışa aktarma" description="PDF, Excel ve TXT biçimleri." icon={Download}>
            <label className="mb-2.5 flex cursor-pointer items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-[11.5px] text-[var(--text-soft)]">
              <input
                type="checkbox"
                className="accent-[var(--primary)]"
                checked={includeRawOcr}
                onChange={(event) => setIncludeRawOcr(event.target.checked)}
              />
              <span>Ham OCR özetini rapora ekle (include_raw_ocr)</span>
            </label>
            <div className="grid grid-cols-3 gap-2">
              {(Object.keys(FORMAT_META) as Format[]).map((format) => {
                const Icon = FORMAT_META[format].icon;
                const officialDisabled = format !== "txt" && (isOffline || !sessionId);
                return (
                  <button
                    key={format}
                    type="button"
                    className="flex flex-col items-center gap-2 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] px-2 py-3 transition-colors hover:border-[var(--border-strong)] hover:bg-[var(--surface-3)] disabled:opacity-50"
                    disabled={busy !== null || officialDisabled}
                    title={officialDisabled ? "Çevrimdışı/demo modda kapalı" : undefined}
                    onClick={() => void exportReport(format)}
                  >
                    <span className="grid size-8 place-items-center rounded-lg border border-[var(--border)] bg-[var(--surface)]">
                      <Icon size={15} aria-hidden />
                    </span>
                    <span className="text-[11.5px] font-semibold">{FORMAT_META[format].label}</span>
                    <span className="text-[9.5px] text-[var(--text-faint)]">
                      {busy === format ? "Hazırlanıyor…" : officialDisabled ? "Çevrimdışı kapalı" : "İndir"}
                    </span>
                  </button>
                );
              })}
            </div>
            <div className="mt-3 space-y-2">
              <div className="seg-control" role="group" aria-label="Snapshot uygulama modu">
                <button
                  type="button"
                  className="seg-btn"
                  aria-pressed={snapshotMode === "merge"}
                  onClick={() => setSnapshotMode("merge")}
                >
                  Birleştir (merge)
                </button>
                <button
                  type="button"
                  className="seg-btn"
                  aria-pressed={snapshotMode === "replace"}
                  onClick={() => setSnapshotMode("replace")}
                >
                  Üzerine yaz (replace)
                </button>
              </div>
              <div className="grid gap-2 sm:grid-cols-3">
                <Button
                  size="sm"
                  icon={<Download size={12} />}
                  loading={snapshotBusy}
                  onClick={() => void downloadSnapshot()}
                >
                  Snapshot indir
                </Button>
                <Button
                  size="sm"
                  icon={<Upload size={12} />}
                  loading={snapshotBusy}
                  onClick={() => fileRef.current?.click()}
                >
                  Mevcut kesite uygula
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  icon={<FileJson size={12} />}
                  loading={importDesktopSnapshot.isPending}
                  onClick={() => newImportRef.current?.click()}
                >
                  JSON&apos;dan yeni kesit aç
                </Button>
              </div>
              <input
                ref={fileRef}
                type="file"
                accept="application/json,.json"
                className="hidden"
                aria-label="Mevcut kesite snapshot JSON dosyası"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) void uploadSnapshot(file);
                }}
              />
              <input
                ref={newImportRef}
                type="file"
                accept="application/json,.json"
                className="hidden"
                aria-label="Yeni kesit için masaüstü JSON snapshot dosyası"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) importSnapshotAsNewSession(file);
                }}
              />
            </div>
            {lastMapping ? (
              <div className="mt-3">
                <InlineNotice
                  tone={
                    lastMapping.mapping.warnings.length > 0 ||
                    lastMapping.mapping.invalid_fields.length > 0
                      ? "warning"
                      : "info"
                  }
                  title={
                    lastMapping.action === "import"
                      ? `Yeni kesit açıldı: ${lastMapping.name}`
                      : `Snapshot uygulandı: ${lastMapping.name}`
                  }
                >
                  <div className="space-y-1 text-[11px]">
                    <p>
                      <strong>{lastMapping.mapping.converted}</strong> alan dönüştürüldü
                      {lastMapping.mapping.skipped.length > 0
                        ? ` · Atlanan: ${lastMapping.mapping.skipped.join(", ")}`
                        : ""}
                    </p>
                    {lastMapping.mapping.invalid_fields.length > 0 ? (
                      <p>Geçersiz alanlar: {lastMapping.mapping.invalid_fields.join(", ")}</p>
                    ) : null}
                    {lastMapping.mapping.warnings.length > 0 ? (
                      <p>{lastMapping.mapping.warnings.join(" · ")}</p>
                    ) : null}
                  </div>
                </InlineNotice>
              </div>
            ) : null}
            <InlineNotice tone="info" title="Masaüstü uyumu">
              Snapshot <code className="font-mono text-[10.5px]">schema_version: 1</code> biçimindedir;
              mevcut kesite birleştirebilir veya{" "}
              <code className="font-mono text-[10.5px]">POST /api/import/desktop-snapshot</code> ile
              doğrudan yeni kesit oluşturabilirsiniz.
            </InlineNotice>
          </SectionCard>
        </div>

        <div className="space-y-4">
          <SectionCard
            title="TXT önizleme"
            description="Sunucu raporuyla aynı bölüm sırası; salt okunur."
            icon={FileText}
            action={
              <>
                <IconButton label="Önizlemeyi yenile" onClick={() => setGeneratedAt(new Date())}>
                  <RefreshCw size={14} />
                </IconButton>
                <IconButton label="Rapor metnini kopyala" onClick={() => void copyPreview()}>
                  <ClipboardCopy size={14} />
                </IconButton>
              </>
            }
          >
            <div className="mb-2 flex flex-wrap items-center gap-2 text-[10px] text-[var(--text-faint)]">
              <span className="chip">{new Blob([reportText]).size} bayt</span>
              <span className="chip">{reportText.split("\n").length} satır</span>
              <span>Oluşturma: {generatedAt.toLocaleTimeString("tr-TR")}</span>
            </div>
            <pre className="scroll-thin max-h-[560px] overflow-auto rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-3.5 font-mono text-[10.5px] leading-relaxed text-[var(--text-soft)] whitespace-pre-wrap">
              {reportText}
            </pre>
          </SectionCard>

          <SectionCard
            title="Dışa aktarma geçmişi"
            description="Bu tarayıcıdaki Test Bölümü indirmeleri."
            icon={History}
            action={<Badge tone="neutral">{exports.length} kayıt</Badge>}
          >
            {exports.length === 0 ? (
              <EmptyState title="Henüz dışa aktarma yok" description="İlk indirmeden sonra format, dosya adı, boyut ve zaman burada listelenir." icon={Download} />
            ) : (
              <ul className="space-y-1.5">
                {exports.map((entry) => (
                  <li key={entry.id} className="flex items-center gap-2.5 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-2">
                    <span className="grid size-7 place-items-center rounded-md border border-[var(--border)] bg-[var(--surface)]">
                      {entry.format === "xlsx" ? <FileSpreadsheet size={13} /> : <FileText size={13} />}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[11px] font-medium">{entry.filename}</p>
                      <p className="text-[9.5px] text-[var(--text-faint)]">
                        {entry.format.toUpperCase()} · {fmt.bytes(entry.size)} · {relativeTime(entry.at)}
                      </p>
                    </div>
                    {entry.demo ? <Badge tone="warning">yerel</Badge> : <Badge tone="pass">sunucu</Badge>}
                  </li>
                ))}
              </ul>
            )}
          </SectionCard>

          <SectionCard
            title="Test Bölümü geçmişi"
            description="Son Test Bölümleri ve test durumları."
            icon={History}
            action={
              <Button size="sm" variant="ghost" icon={<ArrowRight size={12} />} onClick={() => setTab("settings")}>
                Bölüm yönetimi
              </Button>
            }
          >
            <div className="table-wrap scroll-thin">
              <table className="data">
                <caption>Bu çalışma alanındaki Test Bölümleri</caption>
                <thead>
                  <tr>
                    <th scope="col">Test Bölümü</th>
                    <th scope="col">Durum</th>
                    <th scope="col" className="num">Rev.</th>
                    <th scope="col">Güncelleme</th>
                    <th scope="col"><span className="sr-only">Aç</span></th>
                  </tr>
                </thead>
                <tbody>
                  {(sessions ?? []).map((session) => (
                    <tr key={session.id}>
                      <td>
                        <span className="font-medium text-[var(--text)]">{session.name}</span>
                        {session.name === currentName ? <Badge tone="info" className="ml-1.5">aktif</Badge> : null}
                      </td>
                      <td>
                        <Badge tone={session.status === "completed" ? "pass" : session.status === "draft" ? "pending" : "info"}>
                          {session.status}
                        </Badge>
                      </td>
                      <td className="num">{session.revision}</td>
                      <td className="text-[10.5px] text-[var(--text-faint)]">{relativeTime(session.updated_at)}</td>
                      <td className="text-right">
                        <button
                          type="button"
                          className="link-button"
                          disabled={safeSwitchSession.isPending}
                          onClick={() => safeSwitchSession.switchSession(session.id)}
                        >
                          Aç
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              <Button size="sm" variant="ghost" icon={<FileJson size={12} />} onClick={() => setTab("settings")}>
                Snapshot ayarları
              </Button>
              <Button size="sm" variant="ghost" icon={<ScanLine size={12} />} onClick={() => setTab("ocr")}>
                OCR karşılaştırması
              </Button>
            </div>
          </SectionCard>
        </div>
      </div>

      <SectionCard title="Rapor kapsamı" description="Hangi bölümlerin sunucu raporuna dahil olduğu." icon={FileText}>
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
          {[
            ["Başlık", meta.app.version],
            ["Boru kesiti", results.geometry ? `${num(results.geometry.section_count, 0)} kesit` : "—"],
            ["Hava", results.air?.decision.status ?? "—"],
            ["Basınç", results.pressure?.decision.status ?? "—"],
            ["Profil", results.profile?.decision.status ?? "—"],
            ["Pig", results.pig?.status ?? "—"],
            ["Checklist", `${CHECK_DEFINITIONS.filter((c) => inputs.checks[c.key]).length}/11`],
            ["Şartname", meta.spec.code],
          ].map(([label, value]) => (
            <div key={label} className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-2">
              <p className="text-[9.5px] uppercase tracking-wide text-[var(--text-faint)]">{label}</p>
              <p className="mt-0.5 truncate font-mono text-[11px]">{value}</p>
            </div>
          ))}
        </div>
      </SectionCard>
    </div>
  );
}
