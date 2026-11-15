import clsx from "clsx";
import { History, Loader2, RefreshCw } from "lucide-react";
import { formatConfidence, formatDateTime, formatNumber } from "../format";
import {
  ANALYSIS_STATUS_LABELS,
  SOURCE_LABELS,
  type OcrAnalysisSummary,
} from "../types";
import { TONE_BADGE_CLASSES, analysisStatusTone } from "./tone";

export interface HistoryPanelProps {
  items: OcrAnalysisSummary[];
  loading: boolean;
  error: boolean;
  demo: boolean;
  openingId: string | null;
  selectedId?: string | null;
  onOpen: (item: OcrAnalysisSummary) => void;
  onRefresh: () => void;
}

export default function HistoryPanel({
  items,
  loading,
  error,
  demo,
  openingId,
  selectedId = null,
  onOpen,
  onRefresh,
}: HistoryPanelProps) {
  return (
    <section className="panel p-5" aria-labelledby="ocr-history-title" aria-busy={loading}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <History size={18} className="text-[var(--primary)]" aria-hidden="true" />
          <h2 id="ocr-history-title" className="text-base font-semibold text-[var(--text)]">
            Geçmiş analizler
          </h2>
          {demo ? (
            <span className="rounded-full border border-[var(--warning-border)] bg-[var(--warning-bg)] px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.1em] text-[var(--warning)]">
              demo
            </span>
          ) : null}
        </div>
        <button
          type="button"
          onClick={onRefresh}
          disabled={loading}
          className="grid h-9 w-9 place-items-center rounded-lg border border-[var(--border)] text-[var(--text-soft)] transition hover:border-[var(--border-strong)] hover:text-[var(--primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)] disabled:cursor-not-allowed disabled:opacity-40"
          aria-label="Geçmiş analizleri yenile"
          title="Yenile"
        >
          {loading ? (
            <Loader2 size={14} className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
          ) : (
            <RefreshCw size={14} aria-hidden="true" />
          )}
        </button>
      </div>

      {loading && items.length === 0 ? (
        <div className="mt-4 space-y-2" role="status" aria-label="Geçmiş yükleniyor">
          {[0, 1, 2].map((index) => (
            <div
              key={index}
              className="h-16 animate-pulse rounded-lg bg-[var(--surface-3)] motion-reduce:animate-none"
            />
          ))}
        </div>
      ) : null}

      {error ? (
        <p className="mt-4 rounded-lg border border-[var(--warning-border)] bg-[var(--warning-bg)] px-3 py-2 text-[11px] leading-relaxed text-[var(--warning)]">
          Geçmiş listesi yüklenemedi; demo kayıtları gösteriliyor. Sunucu bağlantısı kurulunca
          gerçek analizler listelenir.
        </p>
      ) : null}

      {!loading && items.length === 0 ? (
        <p className="mt-4 rounded-lg border border-dashed border-[var(--border)] px-3 py-6 text-center text-xs leading-relaxed text-[var(--text-faint)]">
          Henüz analiz yok.
          <br />
          İlk raporu yükleyerek başlayın.
        </p>
      ) : null}

      {items.length > 0 ? (
        <ul className="mt-4 space-y-2" role="list">
          {items.map((item) => {
            const tone = analysisStatusTone(item.status);
            const opening = openingId === item.id;
            const selected = selectedId === item.id;
            const blocking = item.blocking_count ?? 0;
            return (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => onOpen(item)}
                  disabled={opening}
                  aria-current={selected ? "true" : undefined}
                  aria-label={`Analizi aç: ${ANALYSIS_STATUS_LABELS[item.status]} · ${formatDateTime(item.created_at)}`}
                  className={clsx(
                    "w-full rounded-lg border px-3 py-2.5 text-left transition hover:border-[var(--border-strong)] hover:bg-[var(--surface-raised)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)] disabled:cursor-wait disabled:opacity-70",
                    selected
                      ? "border-[var(--info-border)] bg-[var(--primary-soft)]"
                      : "border-[var(--border)] bg-[var(--surface-3)]",
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span
                      className={clsx(
                        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.08em]",
                        TONE_BADGE_CLASSES[tone],
                      )}
                    >
                      {opening ? (
                        <Loader2 size={10} className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
                      ) : null}
                      {ANALYSIS_STATUS_LABELS[item.status]}
                    </span>
                    <span className="text-[10px] text-[var(--text-faint)]">{formatDateTime(item.created_at)}</span>
                  </div>
                  <div className="mt-1.5 flex items-center justify-between gap-2">
                    <span className="text-[11px] text-[var(--text-soft)]">
                      {item.source ? SOURCE_LABELS[item.source] : "Kaynak bilinmiyor"}
                    </span>
                    <span className="numeric text-[10px] text-[var(--text-muted)]">
                      {formatConfidence(item.confidence ?? undefined)} ·{" "}
                      {formatNumber(item.page_count ?? 0, 0)} sayfa
                    </span>
                  </div>
                  <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[10px]">
                    {blocking > 0 ? (
                      <span className="rounded border border-[var(--danger-border)] bg-[var(--danger-bg)] px-1.5 py-0.5 text-[var(--danger)]">
                        {blocking} engelleyici
                      </span>
                    ) : (
                      <span className="rounded border border-[var(--success-border)] bg-[var(--success-bg)] px-1.5 py-0.5 text-[var(--success)]">
                        engelleyici yok
                      </span>
                    )}
                    {(item.warnings_count ?? 0) > 0 ? (
                      <span className="text-[var(--warning)]">{item.warnings_count} uyarı</span>
                    ) : null}
                    <span className="numeric text-[var(--text-faint)]">{item.id.slice(0, 10)}…</span>
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}

      <p className="mt-4 border-t hairline pt-3 text-[10px] leading-relaxed text-[var(--text-faint)]">
        Analizler oturumdan bağımsız listelenir; seçili kayıt ham değerleri ve kullanılan eşleme
        profilini saklar.
      </p>
    </section>
  );
}
