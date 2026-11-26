/**
 * OCR API sözleşmesi (webapp/docs/api_contract.md §10).
 * Alan adları backend ile birebir aynıdır; frontend'de kopya anahtar üretilmez.
 */

export type OcrSource = "pdf-text-layer" | "spreadsheet" | "ocr" | "mixed";

export type OcrAnalysisStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";

export type Severity = "info" | "warning" | "critical";

export type FieldValue = string | number | null;

export type DiscrepancyStatus =
  | "match"
  | "within_tolerance"
  | "mismatch"
  | "missing_in_report"
  | "missing_in_calculation"
  | "not_comparable";

/** Rapordan okunan tek alan (kaynak, güven ve ham metin korunur). */
export interface ExtractedField {
  value: FieldValue;
  unit: string;
  confidence: number;
  raw_text: string;
  page: number | null;
  bbox?: [number, number, number, number] | null;
}

export interface AirTestFields {
  vp?: ExtractedField | null;
  vpa?: ExtractedField | null;
  a?: ExtractedField | null;
}

export interface PressureTestFields {
  t_initial?: ExtractedField | null;
  t_final?: ExtractedField | null;
  delta_t?: ExtractedField | null;
  pa?: ExtractedField | null;
  a?: ExtractedField | null;
  b?: ExtractedField | null;
}

export interface OcrReport {
  schema_version?: number;
  report_no?: ExtractedField | null;
  date?: ExtractedField | null;
  operator?: ExtractedField | null;
  section_id?: ExtractedField | null;
  pipe_od_mm?: ExtractedField | null;
  wall_mm?: ExtractedField | null;
  length_m?: ExtractedField | null;
  test_pressure_bar?: ExtractedField | null;
  air_test?: AirTestFields | null;
  pressure_test?: PressureTestFields | null;
  result?: ExtractedField | null;
  notes?: ExtractedField | null;
  warnings?: string[];
}

/** Rapor değeri ile hesaplanan değer arasındaki tek karşılaştırma. */
export interface Discrepancy {
  field: string;
  label: string;
  reported: FieldValue;
  calculated: FieldValue;
  unit: string;
  delta: number | null;
  tolerance: string;
  status: DiscrepancyStatus;
  severity: Severity;
  message: string;
}

export interface ValidationIssue {
  field: string;
  code: string;
  message: string;
  severity: Severity;
}

export interface ApprovedField {
  value: FieldValue;
  unit: string;
  approved: boolean;
}

export interface OcrErrorDetail {
  code: string;
  message: string;
  detail?: string;
}

import type {
  CheckAutoDetail,
  CheckKey,
  Project,
  SectionFormsSummary,
  SimilarProjectCandidate,
} from "../../lib/types";

export interface DossierFormEntry {
  form_code: string;
  botas_code: string;
  form_title: string;
  required: boolean;
  order: number;
  status: "empty" | "filled" | "passed" | "failed" | "warning";
  source_filename: string;
  pages: number[];
  form_date: string;
  extracted_data: Record<string, unknown>;
  warnings: string[];
}

export interface DossierMissingForm {
  form_code: string;
  botas_code: string;
  form_title: string;
}

export interface DossierCalcResult {
  status: "passed" | "failed" | "warning" | "pending";
  passed: boolean | null;
  summary: string;
  [key: string]: unknown;
}

export interface DossierSection {
  section_no: string;
  header: Record<string, unknown>;
  present_forms: DossierFormEntry[];
  missing_required_forms: DossierMissingForm[];
  filled_required_count: number;
  required_total: number;
  supplementary_count: number;
  calculations: {
    air?: DossierCalcResult;
    pressure?: DossierCalcResult;
    profile?: DossierCalcResult;
    pig?: DossierCalcResult;
  };
  checks: Record<string, boolean>;
  check_details: Partial<Record<CheckKey, CheckAutoDetail>>;
  pages: number[];
}

export interface DossierConflictItem {
  section_no: string;
  session_id: string;
  session_name: string;
  form_code: string;
  botas_code: string;
  form_title: string;
  existing_status: string;
  existing_filename: string;
  existing_date: string;
  existing_revision: number;
  new_date: string;
  new_pages: number[];
}

export interface OcrDossierView {
  schema_version?: number;
  detected_project_name?: string | null;
  source_filename: string;
  page_count: number;
  sections_count: number;
  sections: DossierSection[];
  unassigned_pages: Array<{
    page: number;
    form_code?: string;
    section_no?: string;
    reason: string;
  }>;
  blank_template_pages: number[];
  required_form_catalog: DossierMissingForm[];
  warnings: string[];
  similar_projects?: SimilarProjectCandidate[];
  project_conflicts?: Record<string, DossierConflictItem[]>;
}

export interface DossierCommitRequest {
  target_project_id?: string | null;
  create_new_project: boolean;
  new_project_name?: string | null;
  new_project_code?: string | null;
  overwrite_filled: boolean;
  selected_sections?: string[] | null;
}

export interface DossierCommitResponse {
  project: Project;
  created_sections: Array<{ session_id: string; section_no: string; name: string }>;
  updated_sections: Array<{ session_id: string; section_no: string; name: string }>;
  created_sections_count?: number;
  updated_sections_count?: number;
  saved_forms_count: number;
  overwritten_forms_count: number;
  sections_summary: Array<{
    session_id: string;
    section_no: string;
    forms_summary: SectionFormsSummary;
    calculations?: Record<string, DossierCalcResult>;
  }>;
}

export interface OcrAnalysisMetrics {
  low_confidence_fields: number;
  critical_confidence_fields: number;
}

export interface SuggestedFix {
  field: string;
  label: string;
  current_value: number;
  suggested_value: number;
  reason: string;
}

export interface OcrTelemetry {
  duration_ms?: number;
  escalated_pages?: number;
  engine?: string | null;
}

/** `GET /api/ocr/analyses/{id}` yanıtı (durum alanları opsiyoneldir). */
export interface OcrAnalysisResult {
  id: string;
  status: OcrAnalysisStatus;
  source?: OcrSource | null;
  page_count?: number;
  character_count?: number;
  confidence?: number;
  needs_human_review?: boolean;
  metrics?: OcrAnalysisMetrics;
  report?: OcrReport;
  discrepancies?: Discrepancy[];
  issues?: ValidationIssue[];
  warnings?: string[];
  suggested_fixes?: SuggestedFix[];
  approved_fields?: Record<string, ApprovedField> | null;
  dossier?: OcrDossierView | null;
  ocr_telemetry?: OcrTelemetry | null;
  progress?: {
    stage: string;
    elapsed_s: number;
    pages_done?: number;
    pages_total?: number;
  } | null;
  error?: OcrErrorDetail | null;
  created_at?: string;
  started_at?: string | null;
  finished_at?: string | null;
  reused?: boolean;
  /** Yalnızca yerel demo sonuçlarında bulunur; sunucudan gelmez. */
  demo?: boolean;
}

/** `GET /api/ocr/analyses` liste elemanı. */
export interface OcrAnalysisSummary {
  id: string;
  status: OcrAnalysisStatus;
  source?: OcrSource | null;
  confidence?: number | null;
  page_count?: number | null;
  created_at?: string;
  finished_at?: string | null;
  warnings_count?: number;
  discrepancies_count?: number;
  blocking_count?: number;
}

/** `POST /api/ocr/analyze` yanıtı. */
export interface OcrAnalyzeJob {
  analysis_id: string;
  status: OcrAnalysisStatus;
  poll_url?: string;
  estimated_wait_s?: number;
  reused?: boolean;
}

/** Ortak liste zarfı. */
export interface ListEnvelope<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface OcrEngineInfo {
  name: string | null;
  version: string | null;
  languages: string[];
  default_language: string;
}

export interface OcrPdfRasterizerInfo {
  available: boolean;
  engine: string | null;
  note: string;
}

export interface OcrTextLayerInfo {
  available: boolean;
  engines?: string[];
}

export interface OcrLimits {
  max_file_size_bytes: number;
  max_pdf_pages: number;
  max_ocr_pages: number;
  supported_extensions: string[];
}

export interface OcrThresholds {
  auto_fill: number;
  low_confidence: number;
  critical_confidence: number;
  human_review_required: boolean;
}

/** `GET /api/ocr/status` yanıtı. */
export interface OcrStatus {
  available: boolean;
  status_text: string;
  engine?: OcrEngineInfo | null;
  pdf_rasterizer?: OcrPdfRasterizerInfo | null;
  text_layer?: OcrTextLayerInfo | null;
  limits?: OcrLimits;
  queue?: { queued: number; running: number; max_concurrency: number };
  thresholds?: OcrThresholds;
  mapping_profiles?: { default_id: string | null; count: number };
}

export interface MappingFieldRule {
  aliases: string[];
  unit?: string;
  required?: boolean;
  canonical_field?: string;
}

export interface MappingSection {
  name: string;
  heading_aliases: string[];
  before?: string;
}

export interface MappingTableHints {
  column_count?: number;
  label_value_layout?: string;
}

export interface MappingDefinition {
  schema_version?: number;
  sections?: MappingSection[];
  fields?: Record<string, MappingFieldRule>;
  table_hints?: MappingTableHints;
}

/** `GET /api/ocr/mapping-profiles` elemanı (+ detayda `mapping`). */
export interface MappingProfile {
  id: string;
  name: string;
  format_key: string;
  schema_version?: number;
  is_default?: boolean;
  mode?: string;
  created_at?: string;
  updated_at?: string;
  mapping?: MappingDefinition;
}

export interface AnalyzeRequestInput {
  file: File;
  calculated?: Record<string, unknown> | null;
  mappingProfileId?: string | null;
  sessionId?: string | null;
  language?: string;
  force?: boolean;
}

export interface ApproveRequestInput {
  fields: Record<string, ApprovedField>;
  approve_all?: boolean;
  reviewer_note?: string;
}

export interface ApproveResponse {
  id: string;
  approved_count: number;
  pending_low_confidence: string[];
  audit_event_id: string;
  approved_at: string;
}

export interface ApplyRequestInput {
  session_id: string;
  fields: string[];
  overwrite?: boolean;
}

export interface ApplyResponse {
  session_id: string;
  applied: Array<{ field: string; from: FieldValue; to: FieldValue }>;
  skipped: Array<{ field: string; reason: string }>;
  conflicts: Array<{ field: string; reason?: string }>;
  session_revision: number;
}

export const SOURCE_LABELS: Record<OcrSource, string> = {
  "pdf-text-layer": "PDF metin katmanı",
  spreadsheet: "Excel çalışma kitabı",
  ocr: "OCR",
  mixed: "Karma (metin + OCR)",
};

export const ANALYSIS_STATUS_LABELS: Record<OcrAnalysisStatus, string> = {
  queued: "Kuyrukta",
  running: "Çalışıyor",
  succeeded: "Tamamlandı",
  failed: "Başarısız",
  cancelled: "İptal edildi",
};

export const DISCREPANCY_STATUS_LABELS: Record<DiscrepancyStatus, string> = {
  match: "Eşleşti",
  within_tolerance: "Tolerans içinde",
  mismatch: "Uyuşmazlık",
  missing_in_report: "Raporda yok",
  missing_in_calculation: "Hesapta yok",
  not_comparable: "Karşılaştırılamaz",
};

export const SEVERITY_LABELS: Record<Severity, string> = {
  info: "Bilgi",
  warning: "Uyarı",
  critical: "Kritik",
};

/**
 * Engelleme kuralı backend ile aynıdır (`Discrepancy.is_blocking`):
 * tolerans dışı veya raporda okunamayan alan kabul akışını durdurur.
 */
export function isBlockingDiscrepancy(item: Discrepancy): boolean {
  return item.status === "mismatch" || item.status === "missing_in_report";
}
