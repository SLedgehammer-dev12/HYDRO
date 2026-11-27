import { useCallback, useEffect, useRef, useState } from "react";
import type { DragEvent } from "react";
import clsx from "clsx";
import { FileText, Plus, Trash2, Upload, X } from "lucide-react";
import { formatBytes } from "../format";

export const MAX_FILE_BYTES = 500 * 1024 * 1024;
export const MAX_FILE_LABEL = "500 MB";
export const ACCEPT_ATTRIBUTE = ".pdf,.xlsx,.xls,.jpg,.jpeg,.png,.tif,.tiff,.bmp,.webp";
const SUPPORTED_EXTENSIONS = [".pdf", ".xlsx", ".xls", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"];
const SUPPORTED_HINT = "PDF, XLSX, XLS, JPG, PNG, TIFF, BMP, WEBP";
const PASTE_MIME_EXT: Record<string, string> = {
  "image/png": "png",
  "image/jpeg": "jpg",
  "image/webp": "webp",
  "image/bmp": "bmp",
  "image/tiff": "tiff",
};

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
  file?: File | null;
  files?: File[];
  multiple?: boolean;
  error: string | null;
  maxBytes?: number;
  disabled?: boolean;
  onSelect?: (file: File) => void;
  onSelectFiles?: (files: File[]) => void;
  onRemove?: () => void;
  onRemoveFile?: (index: number) => void;
  onClearAll?: () => void;
  onError: (message: string | null) => void;
}

function fileIdentity(file: File): string {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

export default function Dropzone({
  file = null,
  files,
  multiple = false,
  error,
  maxBytes = MAX_FILE_BYTES,
  disabled = false,
  onSelect,
  onSelectFiles,
  onRemove,
  onRemoveFile,
  onClearAll,
  onError,
}: DropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const effectiveMaxBytes = maxBytes > 0 ? maxBytes : MAX_FILE_BYTES;
  const maxLabel =
    effectiveMaxBytes === MAX_FILE_BYTES ? MAX_FILE_LABEL : formatBytes(effectiveMaxBytes);
  const activeFiles = multiple ? (files ?? (file ? [file] : [])) : file ? [file] : [];

  const acceptFiles = useCallback(
    (candidates: File[]) => {
      if (candidates.length === 0) return;
      if (!multiple) {
        const candidate = candidates[0];
        const validation = validateOcrFile(candidate, effectiveMaxBytes);
        if (validation) {
          onError(validation);
          return;
        }
        onError(null);
        onSelect?.(candidate);
        return;
      }

      const current = files ?? (file ? [file] : []);
      const seen = new Set(current.map(fileIdentity));
      const validAdditions: File[] = [];
      const errors: string[] = [];

      for (const candidate of candidates) {
        const validation = validateOcrFile(candidate, effectiveMaxBytes);
        if (validation) {
          errors.push(`${candidate.name}: ${validation}`);
          continue;
        }
        const key = fileIdentity(candidate);
        if (!seen.has(key)) {
          seen.add(key);
          validAdditions.push(candidate);
        }
      }

      if (validAdditions.length > 0) {
        const nextFiles = [...current, ...validAdditions];
        if (onSelectFiles) {
          onSelectFiles(nextFiles);
        } else {
          onSelect?.(nextFiles[0]);
        }
      }

      if (errors.length > 0) {
        onError(errors.length === 1 ? errors[0] : `${errors.length} dosya reddedildi (${errors[0]})`);
      } else {
        onError(null);
      }
    },
    [effectiveMaxBytes, file, files, multiple, onError, onSelect, onSelectFiles],
  );

  const previewTarget = !multiple || activeFiles.length === 1 ? (activeFiles[0] ?? null) : null;

  useEffect(() => {
    if (!previewTarget || !previewTarget.type.startsWith("image/") || typeof URL.createObjectURL !== "function") {
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(previewTarget);
    setPreviewUrl(url);
    return () => {
      URL.revokeObjectURL(url);
    };
  }, [previewTarget]);

  useEffect(() => {
    if (disabled) return;
    const onPaste = (event: ClipboardEvent) => {
      const target = event.target;
      if (
        target instanceof HTMLElement &&
        (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)
      ) {
        return;
      }
      const items = Array.from(event.clipboardData?.items ?? []);
      const imgItem = items.find((it) => it.kind === "file" && it.type.startsWith("image/"));
      const blob = imgItem?.getAsFile();
      if (!blob) return;
      event.preventDefault();
      const ext = PASTE_MIME_EXT[blob.type.toLowerCase()] ?? "png";
      const named =
        blob.name && blob.name !== "image.png"
          ? blob
          : new File([blob], `pano-goruntusu.${ext}`, { type: blob.type || "image/png" });
      acceptFiles([named]);
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [disabled, acceptFiles]);

  const openPicker = () => {
    if (disabled) return;
    inputRef.current?.click();
  };

  const handleDrop = (event: DragEvent<HTMLElement>) => {
    event.preventDefault();
    event.stopPropagation();
    setDragging(false);
    if (disabled) return;
    const dropped = Array.from(event.dataTransfer.files);
    if (dropped.length === 0) {
      onError("Bırakılan öğe bir dosya değil. PDF, Excel veya görsel seçin.");
      return;
    }
    if (!multiple && dropped.length > 1) {
      acceptFiles([dropped[0]]);
      onError("Tek dosya yükleyin; ilk dosya seçildi.");
      return;
    }
    acceptFiles(dropped);
  };

  const totalBytes = activeFiles.reduce((sum, item) => sum + item.size, 0);

  return (
    <div>
      <input
        ref={inputRef}
        id="ocr-file-input"
        type="file"
        multiple={multiple}
        accept={ACCEPT_ATTRIBUTE}
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
        onChange={(event) => {
          const selected = Array.from(event.target.files ?? []);
          acceptFiles(selected);
          event.target.value = "";
        }}
      />

      {multiple && activeFiles.length > 0 ? (
        <div
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
          className={clsx(
            "panel-soft space-y-3 p-4 transition",
            dragging && "border-[var(--primary)] bg-[var(--info-bg)]",
          )}
        >
          <div className="flex flex-wrap items-center justify-between gap-2 border-b hairline pb-3">
            <div>
              <p className="text-xs font-semibold text-[var(--text)]">
                {activeFiles.length} dosya seçildi
              </p>
              <p className="numeric text-[11px] text-[var(--text-muted)]">
                Toplam boyut: {formatBytes(totalBytes)} · Sürükleyip bırakarak yeni dosya ekleyebilirsiniz
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={openPicker}
                disabled={disabled}
                className="inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-[var(--info-border)] bg-[var(--info-bg)] px-3 py-1.5 text-xs font-medium text-[var(--primary)] transition hover:brightness-105 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)] disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Plus size={14} aria-hidden="true" />
                Dosya Ekle
              </button>
              <button
                type="button"
                onClick={() => {
                  if (onClearAll) onClearAll();
                  else onRemove?.();
                  onError(null);
                }}
                disabled={disabled}
                className="inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-[var(--border)] px-3 py-1.5 text-xs font-medium text-[var(--text-soft)] transition hover:border-[var(--danger-border)] hover:text-[var(--danger)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)] disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Trash2 size={14} aria-hidden="true" />
                Tümünü Temizle
              </button>
            </div>
          </div>

          <ul className="max-h-52 space-y-2 overflow-y-auto pr-1" aria-label="Seçilen OCR dosyaları">
            {activeFiles.map((item, idx) => (
              <li
                key={fileIdentity(item)}
                className="flex items-center gap-3 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2"
              >
                {activeFiles.length === 1 && previewUrl ? (
                  <img
                    src={previewUrl}
                    alt={`${item.name} küçük önizleme`}
                    className="h-9 w-9 shrink-0 rounded-md border border-[var(--border)] bg-white object-cover"
                  />
                ) : (
                  <span className="grid h-8 w-8 shrink-0 place-items-center rounded-md border border-[var(--info-border)] bg-[var(--info-bg)] text-[var(--primary)]">
                    <FileText size={16} aria-hidden="true" />
                  </span>
                )}
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium text-[var(--text)]" title={item.name}>
                    {item.name}
                  </p>
                  <p className="numeric text-[10px] text-[var(--text-muted)]">
                    {formatBytes(item.size)} · {item.type || "tür bilgisi yok"}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    if (onRemoveFile) {
                      onRemoveFile(idx);
                    } else if (activeFiles.length === 1) {
                      onRemove?.();
                    } else {
                      onSelectFiles?.(activeFiles.filter((_, i) => i !== idx));
                    }
                    onError(null);
                  }}
                  disabled={disabled}
                  className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-[var(--border)] text-[var(--text-soft)] transition hover:border-[var(--danger-border)] hover:text-[var(--danger)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)] disabled:cursor-not-allowed disabled:opacity-50"
                  aria-label={`${item.name} dosyasını kaldır`}
                >
                  <X size={14} aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : file ? (
        <div className="panel-soft flex flex-wrap items-center gap-3 p-4">
          {previewUrl ? (
            <img
              src={previewUrl}
              alt={`${file.name} küçük önizleme`}
              className="h-12 w-12 shrink-0 rounded-lg border border-[var(--border)] bg-white object-cover"
            />
          ) : (
            <span className="grid h-11 w-11 shrink-0 place-items-center rounded-lg border border-[var(--info-border)] bg-[var(--info-bg)] text-[var(--primary)]">
              <FileText size={20} aria-hidden="true" />
            </span>
          )}
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
              onRemove?.();
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
            {multiple ? "Rapor dosyalarını sürükleyip bırakın" : "Rapor dosyasını sürükleyip bırakın"}
          </span>
          <span className="text-xs text-[var(--text-muted)]">
            veya <span className="font-semibold text-[var(--primary)]">dosya seçin</span>
          </span>
          <span id="ocr-dropzone-hint" className="text-[11px] leading-relaxed text-[var(--text-faint)]">
            {SUPPORTED_HINT} · en fazla {maxLabel} · {multiple ? "tek veya çoklu dosya" : "tek dosya"} · Ctrl/⌘+V ile görüntü yapıştır
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
