import clsx from "clsx";
import type { ReactNode } from "react";
import { Cpu, Loader2, RefreshCw } from "lucide-react";
import { formatBytes, formatNumber } from "../format";
import type { OcrStatus } from "../types";
import { TONE_BADGE_CLASSES } from "./tone";

export interface StatusErrorDetail {
  code: string;
  status: number;
  message: string;
  requestId?: string | null;
}

export interface StatusPanelProps {
  status: OcrStatus | null;
  loading: boolean;
  error: boolean;
  errorDetail?: StatusErrorDetail | null;
  onRetry: () => void;
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 border-t hairline py-2 first:border-t-0 first:pt-0">
      <dt className="text-[11px] text-[var(--text-faint)]">{label}</dt>
      <dd className="text-right text-[11px] text-[var(--text-soft)]">{children}</dd>
    </div>
  );
}

function errorHeadline(detail: StatusErrorDetail | null | undefined): string {
  if (!detail) return "Sunucuya ulaşılamadı. Bağlantıyı kontrol edip yeniden deneyin.";
  if (detail.code === "aborted") {
    return "OCR motoru durum sorgusu zaman aşımına uğradı.";
  }
  if (detail.status >= 400) {
    return detail.message || `Sunucu OCR durumunu döndüremedi (HTTP ${detail.status}).`;
  }
  return "Yerel HYDRO Web sunucusuna ulaşılamadı.";
}

function errorGuidance(detail: StatusErrorDetail | null | undefined): string {
  if (!detail) {
    return "Servis kapalıysa tarama başlatılamaz; yüklediğiniz dosya cihazdan çıkmaz.";
  }
  if (detail.code === "aborted") {
    return "Kurum antivirüs/EDR ilk taraması arka planda başlatmayı yavaşlatmış olabilir. Tekrar deneyin; metin katmanlı PDF ve Excel (.xlsx/.xls) dosyalarını yine doğrudan analiz edebilirsiniz.";
  }
  if (detail.status >= 400) {
    const reqNote = detail.requestId ? ` · id: ${detail.requestId}` : "";
    if (detail.status === 502 || detail.status === 503 || detail.status === 403) {
      return `Kurum vekil sunucusu (proxy) veya yerel servis yanıtı kesti (${detail.code}${reqNote}). Adresin 127.0.0.1 üzerinden açıldığından emin olun.`;
    }
    return `Teknik kod: ${detail.code}${reqNote}. Yerel sunucu çalışıyorsa metin katmanlı PDF ve Excel analizini yine deneyebilirsiniz.`;
  }
  return '"HYDRO Web Sunucusu" masaüstü penceresini kapatmadığınızdan (simge durumunda açık bırakın), antivirüs/EDR engeli olmadığından ve adresin 127.0.0.1 üzerinden açıldığından emin olun. Dosyanız cihazdan çıkmaz.';
}

export default function StatusPanel({
  status,
  loading,
  error,
  errorDetail,
  onRetry,
}: StatusPanelProps) {
  const available = status?.available === true && !error;
  const isTimeout = errorDetail?.code === "aborted";
  const isHttpError = Boolean(errorDetail && errorDetail.status >= 400);
  const badgeText = error
    ? isTimeout
      ? "Zaman aşımı"
      : isHttpError
        ? `Hata (${errorDetail?.status})`
        : "Çevrimdışı"
    : available
      ? "Hazır"
      : "Kullanılamıyor";

  const engineLabel =
    status?.engine?.name === "windows_ocr"
      ? "Windows Yerleşik OCR"
      : status?.engine?.name === "vision"
        ? "macOS Vision"
        : status?.engine?.name === "tesseract"
          ? "Tesseract OCR"
          : "Görüntü OCR";

  return (
    <section className="panel p-5" aria-labelledby="ocr-status-title" aria-busy={loading}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Cpu size={18} className="text-[var(--primary)]" aria-hidden="true" />
          <h2 id="ocr-status-title" className="text-base font-semibold text-[var(--text)]">
            OCR motoru
          </h2>
        </div>
        {loading ? (
          <span className="inline-flex items-center gap-1 text-[10px] text-[var(--text-muted)]">
            <Loader2 size={12} className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
            Kontrol ediliyor
          </span>
        ) : (
          <span
            className={clsx(
              "rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.1em]",
              error
                ? TONE_BADGE_CLASSES.danger
                : available
                  ? TONE_BADGE_CLASSES.success
                  : TONE_BADGE_CLASSES.warning,
            )}
          >
            {badgeText}
          </span>
        )}
      </div>

      {loading && !status ? (
        <p className="mt-4 text-xs text-[var(--text-muted)]">
          OCR motoru ve PDF görüntüleyici durumu sorgulanıyor…
        </p>
      ) : null}

      {error ? (
        <div
          role="alert"
          className="mt-4 rounded-lg border border-[var(--danger-border)] bg-[var(--danger-bg)] px-3 py-3 text-xs leading-relaxed text-[var(--danger)]"
        >
          <p className="font-medium">{errorHeadline(errorDetail)}</p>
          <p className="mt-1 text-[11px] text-[var(--danger)]">{errorGuidance(errorDetail)}</p>
          <div className="mt-2.5 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={onRetry}
              className="inline-flex min-h-9 items-center gap-1.5 rounded-md border border-[var(--danger-border)] px-2.5 py-1 text-[11px] font-medium text-[var(--danger)] hover:bg-[var(--danger-bg)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)]"
            >
              <RefreshCw size={12} aria-hidden="true" />
              Bağlantıyı dene
            </button>
          </div>
        </div>
      ) : null}

      {status && !error ? (
        <>
          <p className="mt-3 text-[11px] leading-relaxed text-[var(--text-muted)]">{status.status_text}</p>
          <dl className="mt-3">
            <Row label={engineLabel}>
              {status.engine?.name ? (
                <>
                  <span className="numeric">{status.engine.version || "Yerleşik"}</span>
                  <span className="block text-[10px] text-[var(--text-faint)]">
                    {(status.engine.languages ?? []).join(", ") || "dil bilgisi yok"} ·{" "}
                    {status.engine.default_language}
                  </span>
                </>
              ) : (
                <span className="text-[var(--warning)]">Kurulu değil</span>
              )}
            </Row>
            <Row label="PDF rasterizer">
              {status.pdf_rasterizer?.available ? (
                <span>{status.pdf_rasterizer.engine ?? "Açık"}</span>
              ) : (
                <span className="text-[var(--warning)]">Kapalı</span>
              )}
            </Row>
            <Row label="Metin PDF / Excel">
              <span>
                {status.text_layer?.available === false
                  ? "Devre dışı"
                  : "Her zaman aktif (pypdf · openpyxl)"}
              </span>
            </Row>
            <Row label="Kuyruk">
              {status.queue ? (
                <span className="numeric">
                  {formatNumber(status.queue.queued, 0)} bekleyen ·{" "}
                  {formatNumber(status.queue.running, 0)} çalışan
                </span>
              ) : (
                "—"
              )}
            </Row>
            <Row label="Limitler">
              {status.limits ? (
                <span className="numeric">
                  {formatBytes(status.limits.max_file_size_bytes)} · PDF{" "}
                  {formatNumber(status.limits.max_pdf_pages, 0)} sayfa · OCR{" "}
                  {formatNumber(status.limits.max_ocr_pages, 0)} sayfa
                </span>
              ) : (
                "—"
              )}
            </Row>
            {status.thresholds ? (
              <Row label="Güven eşikleri">
                <span className="numeric">
                  otomatik ≥ {status.thresholds.auto_fill} · düşük &lt;{" "}
                  {status.thresholds.low_confidence} · kritik &lt;{" "}
                  {status.thresholds.critical_confidence}
                </span>
              </Row>
            ) : null}
          </dl>

          {status.pdf_rasterizer && !status.pdf_rasterizer.available ? (
            <p className="mt-2 rounded-lg border border-[var(--warning-border)] bg-[var(--warning-bg)] px-2.5 py-2 text-[10px] leading-relaxed text-[var(--warning)]">
              {status.pdf_rasterizer.note ||
                "Taranmış PDF desteği kapalı; metin katmanlı PDF, Excel ve görsel OCR çalışmaya devam eder."}
            </p>
          ) : null}

          {!status.available ? (
            <p className="mt-2 rounded-lg border border-[var(--danger-border)] bg-[var(--danger-bg)] px-2.5 py-2 text-[10px] leading-relaxed text-[var(--danger)]">
              Taranmış belge/görsel için OCR motoru etkin değil; ancak metin katmanlı PDF, CAD
              (.dwg/.dxf) ve Excel (.xlsx/.xls) raporları doğrudan analiz edilebilir. Kurumsal
              Windows 10/11'de yerleşik Türkçe OCR (WinRT) veya yönetici onaylı Tesseract kullanılabilir.
            </p>
          ) : null}
        </>
      ) : null}

      <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t hairline pt-3">
        <p className="text-[10px] text-[var(--text-faint)]">OCR çıktısı resmi kabul değildir.</p>
      </div>
    </section>
  );
}
