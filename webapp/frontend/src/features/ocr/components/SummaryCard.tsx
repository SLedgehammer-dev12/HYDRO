import clsx from "clsx";
import { CheckCircle2, Gauge, ShieldAlert } from "lucide-react";
import {
  analysisStatusTone,
  confidenceTone,
  TONE_TEXT_CLASSES as TONE_TEXT,
  type Tone,
} from "./tone";
import { formatConfidence, formatNumber } from "../format";
import {
  ANALYSIS_STATUS_LABELS,
  SOURCE_LABELS,
  isBlockingDiscrepancy,
  type OcrAnalysisResult,
} from "../types";

const SOURCE_HINTS: Record<string, string> = {
  "pdf-text-layer": "Gömülü metin katmanı kullanıldı; OCR çalıştırılmadı.",
  spreadsheet: "Excel hücreleri doğrudan okundu; görüntü OCR çalıştırılmadı.",
  ocr: "Sayfalar rasterleştirilip Tesseract ile okundu.",
  mixed: "Bazı sayfalar metin katmanından, bazıları OCR ile okundu.",
};

function Stat({
  label,
  value,
  hint,
  tone = "neutral",
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: Tone;
}) {
  return (
    <div className="panel-soft p-3">
      <dt className="text-[10px] font-medium uppercase tracking-[0.18em] text-[var(--text-faint)]">
        {label}
      </dt>
      <dd className={clsx("numeric mt-1.5 text-sm font-semibold", TONE_TEXT[tone])}>{value}</dd>
      {hint ? <p className="mt-1 text-[10px] leading-snug text-[var(--text-faint)]">{hint}</p> : null}
    </div>
  );
}

export interface SummaryCardProps {
  result: OcrAnalysisResult;
  demo: boolean;
}

export default function SummaryCard({ result, demo }: SummaryCardProps) {
  const discrepancies = result.discrepancies ?? [];
  const blocking = discrepancies.filter(isBlockingDiscrepancy).length;
  const warningCount = result.warnings?.length ?? 0;
  const issueCount = result.issues?.length ?? 0;
  const confidence = result.confidence;
  const sourceLabel = result.source ? SOURCE_LABELS[result.source] : "Bilinmiyor";
  const sourceHint = result.source ? SOURCE_HINTS[result.source] : undefined;
  const statusTone = analysisStatusTone(result.status);

  return (
    <section className="panel p-5" aria-labelledby="ocr-summary-title">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Gauge size={18} className="text-[var(--primary)]" aria-hidden="true" />
          <h2 id="ocr-summary-title" className="text-base font-semibold text-[var(--text)]">
            Analiz özeti
          </h2>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {demo ? (
            <span className="rounded-full border border-[var(--warning-border)] bg-[var(--warning-bg)] px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--warning)]">
              Çevrimdışı kayıt
            </span>
          ) : null}
          <span
            className={clsx(
              "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em]",
              statusTone === "success" && "border-[var(--success-border)] bg-[var(--success-bg)] text-[var(--success)]",
              statusTone === "warning" && "border-[var(--warning-border)] bg-[var(--warning-bg)] text-[var(--warning)]",
              statusTone === "danger" && "border-[var(--danger-border)] bg-[var(--danger-bg)] text-[var(--danger)]",
              statusTone === "neutral" && "border-[var(--border)] bg-[var(--surface-3)] text-[var(--text-soft)]",
            )}
          >
            <CheckCircle2 size={12} aria-hidden="true" />
            {ANALYSIS_STATUS_LABELS[result.status]}
          </span>
        </div>
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-2.5 sm:grid-cols-3 xl:grid-cols-4">
        <Stat label="Kaynak" value={sourceLabel} hint={sourceHint} tone="info" />
        <Stat
          label="Sayfa"
          value={result.page_count !== undefined ? formatNumber(result.page_count, 0) : "—"}
        />
        <Stat
          label="Karakter"
          value={
            result.character_count !== undefined ? formatNumber(result.character_count, 0) : "—"
          }
        />
        <Stat
          label="Ortalama güven"
          value={formatConfidence(confidence)}
          hint="Tüm alanların ortalaması"
          tone={confidenceTone(confidence ?? 0)}
        />
        <Stat
          label="İnsan onayı"
          value={result.needs_human_review === false ? "Gerekmiyor" : "Gerekli"}
          hint="Resmi kabul için zorunlu"
          tone="danger"
        />
        <Stat
          label="Engelleyici"
          value={formatNumber(blocking, 0)}
          hint={blocking > 0 ? "Kabul akışı durduruldu" : "Engelleyici uyuşmazlık yok"}
          tone={blocking > 0 ? "danger" : "success"}
        />
        <Stat
          label="Uyarı"
          value={formatNumber(warningCount, 0)}
          hint="Backend uyarı listesi"
          tone={warningCount > 0 ? "warning" : "neutral"}
        />
        <Stat
          label="Doğrulama sorunu"
          value={formatNumber(issueCount, 0)}
          hint="Şema / fizik kontrolleri"
          tone={issueCount > 0 ? "warning" : "success"}
        />
      </dl>

      {result.ocr_telemetry ? (
        <div
          data-testid="ocr-telemetry-strip"
          className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 rounded-lg border hairline bg-[var(--surface-2)] px-3 py-2 text-[11px] text-[var(--text-muted)]"
        >
          {result.ocr_telemetry.engine ? (
            <span>
              Motor: <strong className="text-[var(--text-soft)]">{result.ocr_telemetry.engine}</strong>
            </span>
          ) : null}
          {result.ocr_telemetry.duration_ms !== undefined ? (
            <span className="numeric">
              OCR süresi:{" "}
              <strong className="text-[var(--text-soft)]">
                {formatNumber(result.ocr_telemetry.duration_ms / 1000, 1)} sn
              </strong>
            </span>
          ) : null}
          {(result.ocr_telemetry.escalated_pages ?? 0) > 0 ? (
            <span className="numeric text-[var(--primary)]">
              {formatNumber(result.ocr_telemetry.escalated_pages ?? 0, 0)} sayfa 300 DPI iyileştirme
            </span>
          ) : null}
        </div>
      ) : null}

      <p className="mt-3 flex items-start gap-2 text-[11px] leading-relaxed text-[var(--text-faint)]">
        <ShieldAlert size={13} className="mt-0.5 shrink-0 text-[var(--warning)]" aria-hidden="true" />
        <span>
          OCR çıktısı resmi kabul değildir. Güven skoru yalnızca otomatik doldurma ve inceleme
          seviyesini belirler; her alan yetkili personel tarafından doğrulanmalıdır.
        </span>
      </p>
    </section>
  );
}
