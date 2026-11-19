/**
 * OCR API istemcisi (webapp/docs/api_contract.md §10).
 *
 * Ortak fetch istemcisi `src/lib/api.ts` kullanılır: X-Session-ID, hata zarfı,
 * zaman aşımı ve iptal davranışı tek yerden gelir. Backend yoksa çağrılar
 * `OcrApiError` fırlatır ve sayfa demo sonucuna düşer.
 */
import { ApiError, apiFetch, getWorkspaceId } from "../../lib/api";
import type {
  AnalyzeRequestInput,
  ApplyRequestInput,
  ApplyResponse,
  ApproveRequestInput,
  ApproveResponse,
  DossierCommitRequest,
  DossierCommitResponse,
  ListEnvelope,
  MappingProfile,
  OcrAnalysisResult,
  OcrAnalysisStatus,
  OcrAnalysisSummary,
  OcrAnalyzeJob,
  OcrStatus,
} from "./types";

export interface ApiErrorEnvelope {
  code: string;
  message: string;
  details: Record<string, unknown>;
  request_id: string | null;
}

interface OcrApiErrorInit {
  code: string;
  message: string;
  details?: Record<string, unknown>;
  requestId?: string | null;
  status?: number;
}

export class OcrApiError extends Error {
  readonly code: string;
  readonly details: Record<string, unknown>;
  readonly requestId: string | null;
  readonly status: number;

  constructor(init: OcrApiErrorInit) {
    super(init.message);
    this.name = "OcrApiError";
    this.code = init.code;
    this.details = init.details ?? {};
    this.requestId = init.requestId ?? null;
    this.status = init.status ?? 0;
  }

  get hint(): string {
    return errorHint(this.code);
  }

  toEnvelope(): ApiErrorEnvelope {
    return {
      code: this.code,
      message: this.message,
      details: this.details,
      request_id: this.requestId,
    };
  }
}

export function isAbortError(error: unknown): boolean {
  if (error instanceof OcrApiError) return error.code === "aborted";
  return (
    (error instanceof DOMException && error.name === "AbortError") ||
    (error instanceof Error && error.name === "AbortError")
  );
}

export function toOcrApiError(error: unknown): OcrApiError {
  if (error instanceof OcrApiError) return error;
  if (error instanceof ApiError) {
    return new OcrApiError({
      code: error.code === "aborted" ? "aborted" : error.code,
      message: error.message,
      details: error.details,
      requestId: error.requestId || null,
      status: error.status,
    });
  }
  if (error instanceof Error) {
    return new OcrApiError({ code: "client_error", message: error.message });
  }
  return new OcrApiError({ code: "client_error", message: "Bilinmeyen istemci hatası." });
}

/**
 * Anonim çalışma alanı anahtarı. `X-Session-ID` başlığını ortak istemci ekler;
 * aynı değer analiz gövdesindeki `session_id` alanında da gönderilir.
 */
export function currentSessionId(): string {
  return getWorkspaceId();
}

async function request<T>(
  path: string,
  options: Parameters<typeof apiFetch>[1] = {},
): Promise<T> {
  try {
    return await apiFetch<T>(path, options);
  } catch (error) {
    throw toOcrApiError(error);
  }
}

export async function getOcrStatus(signal?: AbortSignal, refresh = false): Promise<OcrStatus> {
  const suffix = refresh ? "?refresh=true" : "";
  return request<OcrStatus>(`/ocr/status${suffix}`, {
    method: "GET",
    signal,
    timeoutMs: 15_000,
  });
}

function buildAnalyzeBody(input: AnalyzeRequestInput): FormData {
  const body = new FormData();
  body.append("file", input.file, input.file.name);
  if (input.calculated !== undefined && input.calculated !== null) {
    body.append("calculated", JSON.stringify(input.calculated));
  }
  if (input.mappingProfileId) {
    body.append("mapping_profile_id", input.mappingProfileId);
  }
  body.append("session_id", input.sessionId ?? currentSessionId());
  if (input.language) {
    body.append("language", input.language);
  }
  if (input.force) {
    body.append("force", "true");
  }
  body.append("async_mode", "true");
  return body;
}

export async function analyzeOcr(
  input: AnalyzeRequestInput,
  signal?: AbortSignal,
): Promise<OcrAnalyzeJob> {
  return request<OcrAnalyzeJob>("/ocr/analyze", {
    method: "POST",
    body: buildAnalyzeBody(input),
    signal,
    timeoutMs: 120_000,
    headers: {
      "Idempotency-Key": currentSessionId() + "-" + Date.now().toString(36),
      Prefer: "respond-async",
    },
  });
}

export async function listAnalyses(
  params: { status?: OcrAnalysisStatus; limit?: number; offset?: number } = {},
  signal?: AbortSignal,
): Promise<ListEnvelope<OcrAnalysisSummary>> {
  const query = new URLSearchParams();
  if (params.status) query.set("status", params.status);
  query.set("limit", String(params.limit ?? 20));
  query.set("offset", String(params.offset ?? 0));
  return request<ListEnvelope<OcrAnalysisSummary>>(`/ocr/analyses?${query.toString()}`, {
    method: "GET",
    signal,
    timeoutMs: 10_000,
  });
}

export async function getAnalysis(
  analysisId: string,
  signal?: AbortSignal,
): Promise<OcrAnalysisResult> {
  return request<OcrAnalysisResult>(`/ocr/analyses/${encodeURIComponent(analysisId)}`, {
    method: "GET",
    signal,
    timeoutMs: 15_000,
  });
}

export async function cancelOcrAnalysis(
  analysisId: string,
  signal?: AbortSignal,
): Promise<{ id: string; status: OcrAnalysisStatus }> {
  return request<{ id: string; status: OcrAnalysisStatus }>(
    `/ocr/analyses/${encodeURIComponent(analysisId)}/cancel`,
    { method: "POST", signal, timeoutMs: 10_000 },
  );
}

/** Onay uç noktası hazır; arayüzde yetki katmanı bağlanınca etkinleştirilecek. */
export async function approveOcrAnalysis(
  analysisId: string,
  input: ApproveRequestInput,
): Promise<ApproveResponse> {
  return request<ApproveResponse>(`/ocr/analyses/${encodeURIComponent(analysisId)}/approve`, {
    method: "POST",
    body: input,
    timeoutMs: 15_000,
  });
}

/** Uygula uç noktası hazır; oturum seçimi bağlanınca etkinleştirilecek. */
export async function applyOcrAnalysis(
  analysisId: string,
  input: ApplyRequestInput,
): Promise<ApplyResponse> {
  return request<ApplyResponse>(`/ocr/analyses/${encodeURIComponent(analysisId)}/apply`, {
    method: "POST",
    body: input,
    timeoutMs: 15_000,
  });
}

export async function commitOcrDossier(
  analysisId: string,
  input: DossierCommitRequest,
  signal?: AbortSignal,
): Promise<DossierCommitResponse> {
  return request<DossierCommitResponse>(
    `/ocr/analyses/${encodeURIComponent(analysisId)}/commit-dossier`,
    {
      method: "POST",
      body: input,
      signal,
      timeoutMs: 30_000,
    },
  );
}

export async function listMappingProfiles(
  signal?: AbortSignal,
): Promise<ListEnvelope<MappingProfile>> {
  return request<ListEnvelope<MappingProfile>>("/ocr/mapping-profiles", {
    method: "GET",
    signal,
    timeoutMs: 10_000,
  });
}

export async function getMappingProfile(
  profileId: string,
  signal?: AbortSignal,
): Promise<MappingProfile> {
  return request<MappingProfile>(`/ocr/mapping-profiles/${encodeURIComponent(profileId)}`, {
    method: "GET",
    signal,
    timeoutMs: 10_000,
  });
}

/**
 * Sözleşmedeki kısa adlar. Sayfa `getOcrStatus` adını kullanır; dışarıdan
 * tüketen modüller için `ocrStatus` takma adı da sunulur.
 */
export const ocrStatus = getOcrStatus;
export const approveAnalysis = approveOcrAnalysis;
export const applyAnalysis = applyOcrAnalysis;

export interface AnalysisProgressInfo {
  status: OcrAnalysisStatus;
  stage: string;
  elapsed_s: number;
}

const TERMINAL_STATUSES: ReadonlySet<OcrAnalysisStatus> = new Set([
  "succeeded",
  "failed",
  "cancelled",
]);

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("İstek iptal edildi.", "AbortError"));
      return;
    }
    const timer = window.setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      window.clearTimeout(timer);
      reject(new DOMException("İstek iptal edildi.", "AbortError"));
    };
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

/**
 * Analiz işini tamamlanana kadar yoklar. Sunucu zaman aşımı 600 sn;
 * istemci 630 sn sonra `ocr_timeout` üretir. İptal `AbortSignal` ile yapılır.
 */
export async function waitForAnalysis(
  analysisId: string,
  options: {
    signal?: AbortSignal;
    onProgress?: (info: AnalysisProgressInfo) => void;
    pollIntervalMs?: number;
    timeoutMs?: number;
  } = {},
): Promise<OcrAnalysisResult> {
  const { signal, onProgress, pollIntervalMs = 750, timeoutMs = 630_000 } = options;
  const startedAt = Date.now();

  for (;;) {
    if (signal?.aborted) {
      throw new OcrApiError({ code: "aborted", message: "Analiz iptal edildi." });
    }
    const result = await getAnalysis(analysisId, signal);
    const elapsed = result.progress?.elapsed_s ?? (Date.now() - startedAt) / 1000;
    onProgress?.({
      status: result.status,
      stage: result.progress?.stage ?? result.status,
      elapsed_s: elapsed,
    });
    if (TERMINAL_STATUSES.has(result.status)) {
      return result;
    }
    if (Date.now() - startedAt > timeoutMs) {
      throw new OcrApiError({
        code: "ocr_timeout",
        message:
          "Analiz 600 saniye sınırını aştı. Daha az sayfalı veya daha küçük bir dosyayla yeniden deneyin.",
        details: { analysis_id: analysisId },
      });
    }
    await sleep(pollIntervalMs, signal);
  }
}

/** Hata koduna göre operatöre ne yapacağını söyleyen kısa yönlendirme. */
export function errorHint(code: string): string {
  switch (code) {
    case "network_error":
    case "client_error":
      return "Sunucuya ulaşılamıyor. Sunucunun çalıştığını kontrol edip yeniden deneyin.";
    case "aborted":
      return "İstek iptal edildi. Dosya korunuyor; yeniden deneyebilirsiniz.";
    case "file_too_large":
      return "Dosya boyutu 500 MB sınırını aşıyor; taranmış PDF'lerde sayfaları bölün veya 200–300 DPI ile yeniden tarayın.";
    case "unsupported_format":
      return "Yalnızca PDF, XLSX, XLS, JPG, PNG, TIFF, BMP ve WEBP yükleyin. DOCX desteklenmez.";
    case "empty_file":
      return "Dosya boş görünüyor. Farklı bir kopya seçin veya yeniden tarayın.";
    case "encrypted_pdf":
      return "PDF parola korumalı. Parolayı kaldırıp dosyayı yeniden yükleyin.";
    case "corrupt_document":
    case "corrupt_image":
      return "Dosya bozuk veya yarım. Kaynağından yeniden dışa aktarıp deneyin.";
    case "empty_text":
      return "Belgede okunabilir metin bulunamadı. Düz, iyi aydınlatılmış 200–300 DPI tarama kullanın.";
    case "ocr_unavailable":
      return "Taranmış belge için Tesseract kurulu değil. Yöneticiden kurulum isteyin (brew install tesseract tesseract-lang).";
    case "dependency_missing":
      return "Sunucuda eksik bağımlılık var. Yöneticiye bildirin; metin katmanlı PDF'ler yine okunabilir.";
    case "invalid_calculated":
      return "Hesaplanan değer JSON'u geçersiz. 'Örnek doldur' ile şemayı karşılaştırıp yeniden deneyin.";
    case "ocr_timeout":
      return "Süre sınırı aşıldı. Daha az sayfalı veya daha küçük dosyayla yeniden deneyin.";
    case "ocr_cancelled":
      return "Analiz kullanıcı tarafından iptal edildi.";
    case "worker_interrupted":
      return "Sunucu yeniden başlatıldığı için yarıda kalan analiz sonlandırıldı; lütfen tekrar deneyin.";
    case "ocr_already_running":
      return "Aynı dosya için analiz sürüyor. Geçmiş analizler listesinden mevcut kaydı açın.";
    case "rate_limited":
      return "Kısa bir süre bekleyip yeniden deneyin; aynı anda birden fazla analiz göndermeyin.";
    case "low_confidence_unreviewed":
      return "Düşük güvenli alanlar açıkça işaretlenmeden toplu onay verilemez.";
    case "field_not_approved":
      return "Yalnızca onaylanmış alanlar oturuma uygulanabilir; önce alan onayını tamamlayın.";
    case "analysis_not_succeeded":
      return "Analiz tamamlanmadan onay/uygulama yapılamaz. Önce sonucun bitmesini bekleyin.";
    case "not_cancellable":
      return "Analiz zaten bitmiş; iptal yerine yeni analiz başlatın.";
    case "not_found":
      return "Analiz kaydı bulunamadı. Geçmiş listesini yenileyip yeniden açın.";
    case "duplicate_filled_forms":
      return "Seçili test bölümünde daha önce doldurulmuş formlar mevcut. Üzerine yazmayı onaylayın veya yalnızca yeni formları seçin.";
    case "project_required":
      return "Kayıt için mevcut bir proje seçin ya da yeni proje adı girin.";
    default:
      return "Yeniden deneyin. Sorun sürerse request_id ile yöneticiye bildirin.";
  }
}
