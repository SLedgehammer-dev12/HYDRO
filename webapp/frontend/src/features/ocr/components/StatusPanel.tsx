import clsx from "clsx";
import type { ReactNode } from "react";
import { Cpu, Loader2, RefreshCw } from "lucide-react";
import { formatBytes, formatNumber } from "../format";
import type { OcrStatus } from "../types";
import { TONE_BADGE_CLASSES } from "./tone";

export interface StatusPanelProps {
  status: OcrStatus | null;
  loading: boolean;
  error: boolean;
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

export default function StatusPanel({
  status,
  loading,
  error,
  onRetry,
}: StatusPanelProps) {
  const available = status?.available === true && !error;

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
            {error ? "Çevrimdışı" : available ? "Hazır" : "Kullanılamıyor"}
          </span>
        )}
      </div>

      {loading && !status ? (
        <p className="mt-4 text-xs text-[var(--text-muted)]" role="status">
          Tesseract ve PDF rasterizer durumu sorgulanıyor…
        </p>
      ) : null}

      {error ? (
        <div className="mt-4 rounded-lg border border-[var(--danger-border)] bg-[var(--danger-bg)] px-3 py-3 text-xs leading-relaxed text-[var(--danger)]">
          <p className="font-medium">
            Sunucuya ulaşılamadı. Bağlantıyı kontrol edip yeniden deneyin.
          </p>
          <p className="mt-1 text-[11px] text-[var(--danger)]">
            Servis kapalıysa analiz başlatılamaz; yüklediğiniz dosya cihazdan çıkmaz.
          </p>
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
            <Row label="Tesseract">
              {status.engine ? (
                <>
                  <span className="numeric">{status.engine.version}</span>
                  <span className="block text-[10px] text-[var(--text-faint)]">
                    {(status.engine.languages ?? []).join(", ") || "dil yok"} ·{" "}
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
                "Taranmış PDF desteği kapalı; metin katmanlı PDF ve görsel OCR çalışmaya devam eder."}
            </p>
          ) : null}

          {!status.available ? (
            <p className="mt-2 rounded-lg border border-[var(--danger-border)] bg-[var(--danger-bg)] px-2.5 py-2 text-[10px] leading-relaxed text-[var(--danger)]">
              Taranmış belge için OCR kurulu değil. Yönetici kurulumu:{" "}
              <span className="numeric">brew install tesseract tesseract-lang</span>
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
