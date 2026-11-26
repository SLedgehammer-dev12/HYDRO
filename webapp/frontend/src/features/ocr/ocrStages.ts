export type StageKey = "upload" | "extract" | "parse" | "compare";

export const STAGES: Array<{ key: StageKey; label: string; detail: string }> = [
  { key: "upload", label: "Yükleniyor", detail: "Dosya sunucuya aktarılıyor" },
  { key: "extract", label: "Metin / OCR çıkarılıyor", detail: "Metin katmanı veya Tesseract" },
  { key: "parse", label: "Alanlar ayrıştırılıyor", detail: "Etiket + regex eşleme" },
  { key: "compare", label: "Karşılaştırılıyor", detail: "Toleranslı hesap kontrolü" },
];

export function mapServerStage(raw: string | null | undefined): StageKey {
  const value = (raw ?? "").toLowerCase();
  if (value.includes("queue") || value.includes("upload")) return "upload";
  if (value.includes("compare")) return "compare";
  if (value.includes("pars") || value.includes("field")) return "parse";
  if (value.includes("extract") || value.includes("ocr") || value.includes("text")) return "extract";
  return "extract";
}

export function serverStageLabel(raw: string | null | undefined): string {
  const stage = mapServerStage(raw);
  return STAGES.find((item) => item.key === stage)?.label ?? "İşleniyor";
}

export function parseExtractProgress(
  stage: string | null | undefined,
  pagesDone?: number,
  pagesTotal?: number,
): { done: number; total: number } | null {
  const match = /^extract:(\d+)\/(\d+)/i.exec(stage ?? "");
  const done = pagesDone ?? (match ? Number(match[1]) : undefined);
  const total = pagesTotal ?? (match ? Number(match[2]) : undefined);
  if (total && total > 0 && done !== undefined) {
    return { done, total };
  }
  return null;
}

export function wait(ms: number, signal: AbortSignal): Promise<void> {
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
