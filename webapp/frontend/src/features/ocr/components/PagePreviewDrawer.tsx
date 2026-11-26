import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, Eye, Loader2, RotateCw, X, ZoomIn, ZoomOut } from "lucide-react";
import { fetchAnalysisPagePreview, isAbortError, toOcrApiError } from "../ocrApi";

export interface PagePreviewDrawerProps {
  analysisId: string;
  pageNo: number;
  pageCount: number;
  demo?: boolean;
  onPageChange: (page: number) => void;
  onClose: () => void;
}

export default function PagePreviewDrawer({
  analysisId,
  pageNo,
  pageCount,
  demo = false,
  onPageChange,
  onClose,
}: PagePreviewDrawerProps) {
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [zoom, setZoom] = useState(100);
  const [rotation, setRotation] = useState(0);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  useEffect(() => {
    if (demo) {
      setImageUrl(null);
      setLoading(false);
      setError("Çevrimdışı demo kayıtlarında sayfa önizlemesi sunulmaz.");
      return;
    }

    const controller = new AbortController();
    let activeUrl: string | null = null;
    setLoading(true);
    setError(null);

    fetchAnalysisPagePreview(analysisId, pageNo, controller.signal)
      .then((blob) => {
        activeUrl = URL.createObjectURL(blob);
        setImageUrl(activeUrl);
        setLoading(false);
      })
      .catch((caught) => {
        if (isAbortError(caught)) return;
        setImageUrl(null);
        setError(toOcrApiError(caught).message || "Sayfa görseli yüklenemedi.");
        setLoading(false);
      });

    return () => {
      controller.abort();
      if (activeUrl) URL.revokeObjectURL(activeUrl);
    };
  }, [analysisId, pageNo, demo]);

  const maxPage = Math.max(1, pageCount || 1);

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end"
      role="dialog"
      aria-modal="true"
      aria-label={`Belge sayfa ${pageNo} önizlemesi`}
    >
      <button
        type="button"
        aria-label="Önizleme arka planını kapat"
        onClick={onClose}
        className="flex-1 cursor-default border-0 bg-black/50 backdrop-blur-[2px]"
      />
      <aside
        className="flex h-full w-full max-w-2xl flex-col border-l border-[var(--border)] bg-[var(--surface-1)] shadow-2xl"
      >
        <header className="flex flex-wrap items-center justify-between gap-2 border-b hairline px-4 py-3">
          <div className="flex items-center gap-2">
            <Eye size={16} className="text-[var(--primary)]" aria-hidden="true" />
            <h3 className="text-sm font-semibold text-[var(--text)]">
              Kaynak Sayfa Önizleme ·{" "}
              <span className="numeric text-[var(--primary)]">
                {pageNo} / {maxPage}
              </span>
            </h3>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <button
              type="button"
              disabled={pageNo <= 1}
              onClick={() => onPageChange(Math.max(1, pageNo - 1))}
              aria-label="Önceki sayfa"
              className="rounded-md border border-[var(--border)] p-1.5 text-[var(--text-soft)] hover:border-[var(--border-strong)] disabled:opacity-40"
            >
              <ChevronLeft size={14} aria-hidden="true" />
            </button>
            <button
              type="button"
              disabled={pageNo >= maxPage}
              onClick={() => onPageChange(Math.min(maxPage, pageNo + 1))}
              aria-label="Sonraki sayfa"
              className="rounded-md border border-[var(--border)] p-1.5 text-[var(--text-soft)] hover:border-[var(--border-strong)] disabled:opacity-40"
            >
              <ChevronRight size={14} aria-hidden="true" />
            </button>
            <button
              type="button"
              disabled={zoom <= 75}
              onClick={() => setZoom((z) => Math.max(75, z - 25))}
              aria-label="Uzaklaştır"
              className="rounded-md border border-[var(--border)] p-1.5 text-[var(--text-soft)] hover:border-[var(--border-strong)] disabled:opacity-40"
            >
              <ZoomOut size={14} aria-hidden="true" />
            </button>
            <span className="numeric min-w-[42px] text-center text-[11px] font-medium text-[var(--text-soft)]">
              %{zoom}
            </span>
            <button
              type="button"
              disabled={zoom >= 225}
              onClick={() => setZoom((z) => Math.min(225, z + 25))}
              aria-label="Yakınlaştır"
              className="rounded-md border border-[var(--border)] p-1.5 text-[var(--text-soft)] hover:border-[var(--border-strong)] disabled:opacity-40"
            >
              <ZoomIn size={14} aria-hidden="true" />
            </button>
            <button
              type="button"
              onClick={() => setRotation((r) => (r + 90) % 360)}
              aria-label="90 derece döndür"
              title="90° Döndür"
              className="rounded-md border border-[var(--border)] p-1.5 text-[var(--text-soft)] hover:border-[var(--border-strong)]"
            >
              <RotateCw size={14} aria-hidden="true" />
            </button>
            <button
              type="button"
              onClick={onClose}
              aria-label="Önizlemeyi kapat"
              className="ml-1 rounded-md border border-[var(--border)] p-1.5 text-[var(--text-soft)] hover:border-[var(--danger-border)] hover:text-[var(--danger)]"
            >
              <X size={14} aria-hidden="true" />
            </button>
          </div>
        </header>

        <div className="flex-1 overflow-auto bg-[var(--surface-2)] p-4">
          {loading ? (
            <div className="flex h-full min-h-[280px] items-center justify-center gap-2 text-xs text-[var(--text-muted)]">
              <Loader2 size={16} className="animate-spin text-[var(--primary)]" aria-hidden="true" />
              Sayfa görüntüsü hazırlanıyor...
            </div>
          ) : error ? (
            <div className="rounded-xl border border-[var(--warning-border)] bg-[var(--warning-bg)] p-4 text-xs text-[var(--warning)]">
              {error}
            </div>
          ) : imageUrl ? (
            <div className="flex min-h-full items-start justify-center">
              <img
                src={imageUrl}
                alt={`Rapor sayfa ${pageNo}`}
                style={{
                  width: `${zoom}%`,
                  maxWidth: "none",
                  transform: rotation ? `rotate(${rotation}deg)` : undefined,
                  transformOrigin: "center center",
                }}
                className="rounded-lg border border-[var(--border)] bg-white shadow-md transition-transform"
              />
            </div>
          ) : null}
        </div>
      </aside>
    </div>
  );
}
