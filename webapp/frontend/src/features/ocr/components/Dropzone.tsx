import { useRef, useState } from "react";
import type { DragEvent } from "react";
import clsx from "clsx";
import { FileText, Upload, X } from "lucide-react";
import { formatBytes } from "../format";

export const MAX_FILE_BYTES = 500 * 1024 * 1024;
export const MAX_FILE_LABEL = "500 MB";
export const ACCEPT_ATTRIBUTE = ".pdf,.xlsx,.xls,.jpg,.jpeg,.png,.tif,.tiff,.bmp,.webp";
const SUPPORTED_EXTENSIONS = [".pdf", ".xlsx", ".xls", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"];
const SUPPORTED_HINT = "PDF, XLSX, XLS, JPG, PNG, TIFF, BMP, WEBP";

export function validateOcrFile(file: File, maxBytes = MAX_FILE_BYTES): string | null {
  const name = file.name.toLowerCase();
  const dot = name.lastIndexOf(".");
  const extension = dot >= 0 ? name.slice(dot) : "";
  if (!SUPPORTED_EXTENSIONS.includes(extension)) {
    return `Desteklenmeyen dosya türü (${extension || "uzantısız"}). ${SUPPORTED_HINT} yükleyin.`;
  }
  if (file.size === 0) {
    return "Dosya boş. Başka bir kopya seçin veya belgeyi yeniden tarayın.";
  }
  if (file.size > maxBytes) {
    const limitLabel = maxBytes === MAX_FILE_BYTES ? MAX_FILE_LABEL : formatBytes(maxBytes);
    return `Dosya ${formatBytes(file.size)}; ${limitLabel} sınırını aşıyor. Sayfaları bölerek yükleyin.`;
  }
  return null;
}

export interface DropzoneProps {
  file: File | null;
  error: string | null;
  maxBytes?: number;
  disabled?: boolean;
  onSelect: (file: File) => void;
  onRemove: () => void;
  onError: (message: string | null) => void;
}

export default function Dropzone({
  file,
  error,
  maxBytes = MAX_FILE_BYTES,
  disabled = false,
  onSelect,
  onRemove,
  onError,
}: DropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const effectiveMaxBytes = maxBytes > 0 ? maxBytes : MAX_FILE_BYTES;
  const maxLabel =
    effectiveMaxBytes === MAX_FILE_BYTES ? MAX_FILE_LABEL : formatBytes(effectiveMaxBytes);

  const acceptFile = (candidate: File | undefined) => {
    if (!candidate) return;
    const validation = validateOcrFile(candidate, effectiveMaxBytes);
    if (validation) {
      onError(validation);
      return;
    }
    onError(null);
    onSelect(candidate);
  };

  const openPicker = () => {
    if (disabled) return;
    inputRef.current?.click();
  };

  const handleDrop = (event: DragEvent<HTMLButtonElement>) => {
    event.preventDefault();
    event.stopPropagation();
    setDragging(false);
    if (disabled) return;
    const files = Array.from(event.dataTransfer.files);
    if (files.length === 0) {
      onError("Bırakılan öğe bir dosya değil. PDF, Excel veya görsel seçin.");
      return;
    }
    acceptFile(files[0]);
    if (files.length > 1) {
      onError("Tek dosya yükleyin; ilk dosya seçildi.");
    }
  };

  return (
    <div>
      <input
        ref={inputRef}
        id="ocr-file-input"
        type="file"
        accept={ACCEPT_ATTRIBUTE}
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
        onChange={(event) => {
          const selected = event.target.files?.[0];
          acceptFile(selected);
          event.target.value = "";
        }}
      />

      {file ? (
        <div className="panel-soft flex flex-wrap items-center gap-3 p-4">
          <span className="grid h-11 w-11 shrink-0 place-items-center rounded-lg border border-[var(--info-border)] bg-[var(--info-bg)] text-[var(--primary)]">
            <FileText size={20} aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-[var(--text)]" title={file.name}>
              {file.name}
            </p>
            <p className="numeric mt-1 text-xs text-[var(--text-muted)]">
              {formatBytes(file.size)} · {file.type || "tür bilgisi yok"} · tek dosya
            </p>
          </div>
          <button
            type="button"
            onClick={() => {
              onRemove();
              onError(null);
            }}
            disabled={disabled}
            className="inline-flex min-h-10 items-center gap-1.5 rounded-lg border border-[var(--border)] px-3 py-2 text-xs font-medium text-[var(--text-soft)] transition hover:border-[var(--danger-border)] hover:text-[var(--danger)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--canvas)] disabled:cursor-not-allowed disabled:opacity-50"
            aria-label={`Seçili dosyayı kaldır: ${file.name}`}
          >
            <X size={14} aria-hidden="true" />
            Kaldır
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={openPicker}
          onDragEnter={(event) => {
            event.preventDefault();
            if (!disabled) setDragging(true);
          }}
          onDragOver={(event) => {
            event.preventDefault();
            if (!disabled) setDragging(true);
          }}
          onDragLeave={(event) => {
            event.preventDefault();
            setDragging(false);
          }}
          onDrop={handleDrop}
          disabled={disabled}
          aria-describedby="ocr-dropzone-hint"
          className={clsx(
            "flex min-h-48 w-full flex-col items-center justify-center gap-3 rounded-2xl border border-dashed px-6 py-8 text-center transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--canvas)]",
            dragging
              ? "border-[var(--primary)] bg-[var(--info-bg)]"
              : "border-[var(--border)] bg-[var(--surface-3)] hover:border-[var(--border-strong)] hover:bg-[var(--surface-raised)]",
            disabled && "cursor-not-allowed opacity-60",
          )}
        >
          <span
            className="grid h-12 w-12 place-items-center rounded-full border border-[var(--info-border)] bg-[var(--info-bg)] text-[var(--primary)]"
            aria-hidden="true"
          >
            <Upload size={22} />
          </span>
          <span className="text-sm font-medium text-[var(--text)]">
            Rapor dosyasını sürükleyip bırakın
          </span>
          <span className="text-xs text-[var(--text-muted)]">
            veya <span className="font-semibold text-[var(--primary)]">dosya seçin</span>
          </span>
          <span id="ocr-dropzone-hint" className="text-[11px] leading-relaxed text-[var(--text-faint)]">
            {SUPPORTED_HINT} · en fazla {maxLabel} · tek dosya
          </span>
        </button>
      )}

      {error ? (
        <p
          id="ocr-file-error"
          role="alert"
          className="mt-2 rounded-lg border border-[var(--danger-border)] bg-[var(--danger-bg)] px-3 py-2 text-xs text-[var(--danger)]"
        >
          {error}
        </p>
      ) : null}
    </div>
  );
}
