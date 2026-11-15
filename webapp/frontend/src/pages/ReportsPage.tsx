import { useMemo, useRef, useState } from "react";
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
import { useMeta, useSessions } from "../hooks/queries";
import { useAppStore } from "../store/useAppStore";
import { api, apiErrorMessage } from "../lib/api";
import { buildReportText, buildSnapshot, downloadJson, downloadText, reportFileName } from "../lib/report";
import { dateOnly, fmt, num, relativeTime } from "../lib/format";
import { CHECK_DEFINITIONS } from "../lib/constants";

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
  const pushToast = useAppStore((state) => state.pushToast);

  const sessionId = useAppStore((state) => state.sessionId);
  const backend = useAppStore((state) => state.backend);
  const revision = useAppStore((state) => state.revision);
  const currentName = useAppStore((state) => state.sessionName);

  const { data: meta } = useMeta();
  const { data: sessions } = useSessions();

  const [generatedAt, setGeneratedAt] = useState(() => new Date());
  const [busy, setBusy] = useState<Format | null>(null);
  const [snapshotBusy, setSnapshotBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const reportText = useMemo(
    () => buildReportText(inputs, results, meta, generatedAt),
    [inputs, results, meta, generatedAt],
  );

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
    setBusy(format);
    try {
      if (format === "txt" && (backend !== "online" || !sessionId)) {
        localTxt();
        return;
      }
      if (backend !== "online" || !sessionId) {
        localTxt(
          `${FORMAT_META[format].label} çıktısı backend gerektirir; rapor TXT olarak indirildi ve dışa aktarma geçmişine eklendi.`,
        );
        return;
      }
      const { blob, filename } = await api.exportSession(sessionId, format);
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
    try {
      const text = await file.text();
      const snapshot = JSON.parse(text) as Record<string, unknown>;
      if (backend === "online" && sessionId) {
        const response = await api.snapshotUpload(sessionId, snapshot, revision);
        applySessionInputs(response.inputs);
        setSessionMeta({ revision: response.revision });
        pushToast(
          "success",
          "Snapshot uygulandı",
          `${response.mapping?.converted ?? 0} alan dönüştürüldü, ${response.mapping?.skipped.length ?? 0} alan atlandı.`,
        );
      } else {
        applySessionInputs(snapshot);
        pushToast("success", "Snapshot yerel olarak yüklendi", "Backend yok; girdiler tarayıcı oturumuna uygulandı.");
      }
    } catch (error) {
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

  async function openSession(id: string) {
    if (backend !== "online") {
      pushToast("info", "Demo oturumu", "Oturum açma yalnızca backend bağlıyken çalışır.");
      return;
    }
    try {
      const session = await api.session(id);
      applySessionInputs(session.inputs);
      setSessionMeta({ id: session.id, name: session.name, revision: session.revision, status: session.status });
      pushToast("success", "Oturum açıldı", session.name);
    } catch (error) {
      pushToast("error", "Oturum açılamadı", apiErrorMessage(error));
    }
  }

  return (
    <div className="space-y-5">
      <PageHeader
        kicker="Raporlar"
        title="Rapor önizleme ve dışa aktarma"
        description="Önizleme salt okunurdur; düzeltmeler ilgili sekmelerde yapılır. Rapor kimliği oturum bazlıdır."
        meta={
          <>
            <Badge tone="info">{inputs.report.report_no || "Rapor no yok"}</Badge>
            <span className="text-[10.5px] text-[var(--text-faint)]">
              {inputs.report.operator || "Operatör belirtilmedi"} · {inputs.report.date || "Tarih yok"}
            </span>
            {backend === "demo" ? <Badge tone="warning">demo çıktı</Badge> : null}
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
              loading={busy === "pdf"}
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
            <div className="grid grid-cols-3 gap-2">
              {(Object.keys(FORMAT_META) as Format[]).map((format) => {
                const Icon = FORMAT_META[format].icon;
                return (
                  <button
                    key={format}
                    type="button"
                    className="flex flex-col items-center gap-2 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] px-2 py-3 transition-colors hover:border-[var(--border-strong)] hover:bg-[var(--surface-3)] disabled:opacity-50"
                    disabled={busy !== null}
                    onClick={() => void exportReport(format)}
                  >
                    <span className="grid size-8 place-items-center rounded-lg border border-[var(--border)] bg-[var(--surface)]">
                      <Icon size={15} aria-hidden />
                    </span>
                    <span className="text-[11.5px] font-semibold">{FORMAT_META[format].label}</span>
                    <span className="text-[9.5px] text-[var(--text-faint)]">
                      {busy === format ? "Hazırlanıyor…" : "İndir"}
                    </span>
                  </button>
                );
              })}
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2">
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
                onClick={() => fileRef.current?.click()}
              >
                Snapshot yükle
              </Button>
              <input
                ref={fileRef}
                type="file"
                accept="application/json,.json"
                className="hidden"
                aria-label="Snapshot JSON dosyası"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) void uploadSnapshot(file);
                }}
              />
            </div>
            <InlineNotice tone="info" title="Masaüstü uyumu">
              Snapshot `schema_version: 1` biçimindedir; sayısal alanlar string taşır ve masaüstü
              uygulamasına içe aktarılabilir.
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
            description="Bu tarayıcı oturumundaki indirmeler."
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
                    {entry.demo ? <Badge tone="warning">demo</Badge> : <Badge tone="pass">sunucu</Badge>}
                  </li>
                ))}
              </ul>
            )}
          </SectionCard>

          <SectionCard
            title="Oturum geçmişi"
            description="Son oturumlar ve test durumları."
            icon={History}
            action={
              <Button size="sm" variant="ghost" icon={<ArrowRight size={12} />} onClick={() => setTab("settings")}>
                Oturum yönetimi
              </Button>
            }
          >
            <div className="table-wrap scroll-thin">
              <table className="data">
                <caption>Bu çalışma alanındaki oturumlar</caption>
                <thead>
                  <tr>
                    <th scope="col">Oturum</th>
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
                          onClick={() => void openSession(session.id)}
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
