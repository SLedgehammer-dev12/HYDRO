/**
 * API sözleşmesi tipleri (`webapp/docs/api_contract.md` §13) ve
 * web arayüzünün yerel girdi modelleri.
 *
 * Alan adları API ile birebir aynıdır; snake_case korunur.
 */

export type {
  SceneData,
  SceneEquipment,
  SceneEquipmentType,
  SceneLandmark,
  ScenePoint,
  SceneSegment,
  SceneStatus,
} from "./scene";
import type { SceneData, SceneEquipmentType, SceneStatus } from "./scene";

/* ------------------------------------------------------------------ */
/* Ortak enum'lar                                                      */
/* ------------------------------------------------------------------ */

export type DecisionStatus =
  | "BEKLIYOR"
  | "KATSAYI GUNCELLENMELI"
  | "DOGRULANAMADI"
  | "BASARILI"
  | "BASARISIZ";

export type BSource = "institutional" | "gail" | "auto";
export type SteelModel = "volumetric" | "linear" | "volumetric_temperature";
export type AMode = "auto" | "table" | "manual";
export type CoefficientState = "empty" | "computed" | "reference" | "manual" | "stale";

export type SessionStatus = "draft" | "active" | "completed" | "archived";

export type TestType =
  | "air"
  | "pressure"
  | "coefficient_a"
  | "coefficient_b"
  | "profile"
  | "pig"
  | "pressurization"
  | "thermal_balance"
  | "pressurization_ramp"
  | "pressure_hold"
  | "depressurization"
  | "discharge";

export type PigStatus = "UYGUN" | "LIMIT ASILDI" | "BILGI";
export type LocationClassNumber = 1 | 2 | 3 | 4;

/* ------------------------------------------------------------------ */
/* Ortak zarflar                                                       */
/* ------------------------------------------------------------------ */

export interface ApiErrorBody {
  code: string;
  message: string;
  details: Record<string, unknown>;
  request_id: string;
}

export interface ListResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface Decision {
  status: DecisionStatus;
  title: string;
  summary: string;
  rule: string;
  margin?: number | null;
}

export interface BackendInfo {
  key: string;
  label: string;
  distribution_ready: boolean;
  note?: string;
}

/* ------------------------------------------------------------------ */
/* Geometri                                                            */
/* ------------------------------------------------------------------ */

export interface PipeSectionIn {
  outside_diameter_mm: number;
  wall_thickness_mm: number;
  length_m: number;
  nps_label?: string | null;
  schedule_label?: string | null;
  start_station_m?: number | null;
}

export interface GeometryIn {
  sections: PipeSectionIn[];
}

export interface GeometrySectionResult {
  index: number;
  outside_diameter_mm: number;
  wall_thickness_mm: number;
  length_m: number;
  internal_radius_mm: number;
  internal_volume_m3: number;
  elasticity_term: number;
}

export interface GeometrySummary {
  total_length_m: number;
  internal_volume_m3: number;
  internal_radius_mm: number;
  elasticity_term: number;
}

export interface GeometryResponse extends GeometrySummary {
  section_count: number;
  sections: GeometrySectionResult[];
}

/* ------------------------------------------------------------------ */
/* Meta / şartname                                                     */
/* ------------------------------------------------------------------ */

export interface WaterBackendOption extends BackendInfo {
  note?: string;
}

export interface BSourceOption {
  key: BSource;
  label: string;
  default?: boolean;
}

export interface LocationClassRule {
  class_number: number;
  label: string;
  minimum_test_factor: number;
  spec_reference: string;
}

export interface PigModeOption {
  label: string;
  spec_reference: string;
  max_speed_m_per_s: number | null;
}

export interface SpecLimits {
  max_file_size_bytes: number;
  max_pdf_pages: number;
  max_ocr_pages: number;
  max_test_section_length_m: number;
  max_test_section_volume_m3: number;
  air_acceptance_factor: number;
  pressure_variation_acceptance_bar: number;
  pressurization_volume_limit_percent: number;
  thermal_balance_min_hours: number;
  thermal_balance_threshold_c: number;
  ambient_temp_limit_c: number;
  air_pressure_rise_bar: number;
}

export interface MetaResponse {
  app: { name: string; version: string };
  spec: { code: string; title: string };
  engine: { domain_schema: number; decision_statuses: DecisionStatus[] };
  water_backends: WaterBackendOption[];
  b_sources: BSourceOption[];
  steel_models: SteelModel[];
  location_classes: LocationClassRule[];
  pump_locations: string[];
  pig_modes: PigModeOption[];
  limits: SpecLimits;
  features: { ocr: boolean; scene: boolean; dev_backends: boolean; auth: string };
  units: Record<string, string>;
}

export interface SpecCheck {
  key: string;
  label: string;
  reference: string;
}

export interface SpecResponse {
  code: string;
  title: string;
  acceptance_rules: {
    air: { text: string; factor: number };
    pressure: { text: string; tolerance_bar: number };
  };
  sign_convention: { delta_t: string; pa: string };
  checks: SpecCheck[];
  notes: string[];
}

export interface HealthResponse {
  status: "ok" | "degraded" | "fail";
  version: string;
  engine: string;
  db: { ok: boolean; dialect: string; migration: string };
  data_dir: { ok: boolean; writable: boolean };
  ocr: {
    available: boolean;
    status: string;
    queue: { queued: number; running: number };
  };
  uptime_s: number;
}

/* ------------------------------------------------------------------ */
/* Katalog                                                             */
/* ------------------------------------------------------------------ */

export interface ScheduleOption {
  label: string;
  wall_thickness_mm: number;
}

export interface PipeOption {
  nps: string;
  dn: string;
  outside_diameter_mm: number;
  option_label: string;
  schedules: ScheduleOption[];
}

export interface GradeOption {
  grade: string;
  iso_label: string;
  smys_mpa: number;
  option_label: string;
}

export interface TableAxis {
  min: number;
  max: number;
  step: number;
  count: number;
}

export interface ARepairInfo {
  enabled: boolean;
  band_c: number;
  pressure_range_bar: [number, number];
}

export interface ReferenceTableMeta {
  key: "institutional" | "gail";
  label: string;
  option_label: string;
  temperature: TableAxis;
  pressure: TableAxis;
  a_unit: string;
  b_unit: string;
  source_note: string;
  a_repair?: ARepairInfo;
}

/* ------------------------------------------------------------------ */
/* Katsayılar                                                          */
/* ------------------------------------------------------------------ */

export interface CoefficientAResponse {
  a_micro_per_bar: number;
  temperature_c: number;
  pressure_bar: number;
  backend: BackendInfo;
  state: CoefficientState;
}

export interface BSourceResult {
  b_micro_per_c: number;
  source: BSource;
  label: string;
  note: string;
  repaired_table: boolean;
  water_beta_micro_per_c: number | null;
  steel_alpha_micro_per_c: number | null;
  steel_model: string;
}

export interface BComparisonResponse {
  temperature_c: number;
  pressure_bar: number;
  institutional: BSourceResult;
  gail: BSourceResult;
  auto: BSourceResult;
  deltas: {
    institutional_vs_gail: number;
    auto_vs_institutional: number;
    auto_vs_gail: number;
  };
}

export interface TablePointResponse {
  table: "institutional" | "gail";
  table_label: string;
  requested: { temperature_c: number; pressure_bar: number };
  a_micro_per_bar: number;
  b_micro_per_c: number;
  source_note: string;
  repaired: boolean;
  repair_note: string;
}

export interface ReferenceCompareResponse {
  temperature_c: number;
  pressure_bar: number;
  control_point: { a_micro_per_bar: number; b_micro_per_c: number; source_note: string; repaired: boolean };
  gail_point: { a_micro_per_bar: number; b_micro_per_c: number; source_note: string; repaired: boolean };
  a_delta: number;
  b_delta: number;
}

export interface BackendComparisonItem {
  backend: BackendInfo;
  a_micro_per_bar: number | null;
  beta_micro_per_c: number | null;
  density_kg_per_m3: number | null;
  error: string | null;
}

export interface BackendComparisonResponse {
  temperature_c: number;
  pressure_bar: number;
  items: BackendComparisonItem[];
}

/* ------------------------------------------------------------------ */
/* Hesaplamalar                                                        */
/* ------------------------------------------------------------------ */

export interface AirContentResponse {
  theoretical_added_water_m3: number;
  acceptance_limit_m3: number;
  actual_added_water_m3: number;
  ratio: number;
  passed: boolean;
  geometry: GeometrySummary;
  decision: Decision;
}

export interface PressureVariationResponse {
  theoretical_pressure_change_bar: number;
  allowable_upper_pressure_change_bar: number;
  actual_pressure_change_bar: number;
  margin_bar: number;
  passed: boolean;
  negative_b: boolean;
  geometry: GeometrySummary;
  decision: Decision;
}

export interface PressureWindow {
  location_label: string;
  location_elevation_m: number;
  hydraulic_head_to_high_point_bar: number;
  hydraulic_head_to_low_point_bar: number;
  minimum_required_pressure_bar: number;
  maximum_allowable_pressure_bar: number;
}

export interface PressureProfileResponse {
  location_class: {
    label: string;
    class_number: number;
    minimum_test_factor: number;
    spec_reference: string;
  };
  required_minimum_pressure_at_high_point_bar: number;
  maximum_allowable_pressure_at_low_point_bar: number;
  hydraulic_span_bar: number;
  required_pressure_with_span_bar: number;
  start_window: PressureWindow;
  end_window: PressureWindow;
  selected_window: PressureWindow;
  limiting_pressure_at_100_smys_bar: number;
  limiting_pipe_description: string;
  total_length_m: number;
  total_internal_volume_m3: number;
  within_length_limit: boolean;
  within_volume_limit: boolean;
  within_100_smys_span_limit: boolean;
  feasible: boolean;
  monitored_pressure_bar: number | null;
  monitored_meets_minimum: boolean | null;
  monitored_under_maximum: boolean | null;
  decision: Decision;
}

export interface PigSpeedResponse {
  distance_m: number;
  travel_time_min: number;
  speed_m_per_s: number;
  speed_km_per_h: number;
  limit: {
    label: string;
    spec_reference: string;
    max_speed_m_per_s: number | null;
    max_speed_km_per_h: number | null;
  };
  passed: boolean | null;
  status: PigStatus;
  summary: string;
  decision: Decision;
}

export interface PressurizationResponse {
  volume_deviation_percent: number;
  pressure_deviation_bar: number;
  within_volume_limit: boolean;
  within_pressure_limit: boolean;
  passed: boolean;
  volume_limit_percent: number;
  pressure_tolerance_bar: number;
  underfilled: boolean;
  volume_shortfall_percent: number;
  decision: Decision;
}

export interface PressurizationRampResponse {
  max_ramp_rate_bar_per_min: number;
  ramp_rate_violations: Array<{
    start_elapsed_min: number;
    end_elapsed_min: number;
    rate_bar_per_min: number;
  }>;
  reached_95_smys: boolean;
  reached_100_smys: boolean;
  pumped_since_95_smys_m3: number;
  excess_volume_limit_m3: number;
  excess_volume_percent: number;
  volume_limit_exceeded: boolean;
  stop_required: boolean;
  monitoring_gaps: number[];
  passed: boolean | null;
  decision: Decision;
}

export interface PressureHoldResponse {
  duration_min: number;
  duration_ok: boolean;
  max_reading_gap_min: number;
  interval_ok: boolean;
  pressure_drop_bar: number;
  pressure_tolerance_bar: number;
  repressurize_required: boolean;
  passed: boolean;
  decision: Decision;
}

export interface OperationCheckResponse {
  violations: string[];
  missing: string[];
  passed: boolean;
  decision: Decision;
}

export interface DepressurizationRequest {
  test_passed: boolean | null;
  release_valve_diameter_in: number | null;
  pipe_equipment_checked: boolean | null;
  environmental_impact_checked: boolean | null;
}

export interface DischargeRequest {
  destination: string | null;
  used_discharge_pig: boolean | null;
  hydraulic_load_measures_taken: boolean | null;
  approvals_obtained: boolean | null;
  treatment_requested: boolean;
  treatment_done: boolean | null;
  sample_analysis_requested: boolean;
  sample_analysis_done: boolean | null;
  erosion_prevented: boolean | null;
  report_date: string;
  report_time: string;
  pig_name: string;
  discharge_location: string;
  duration_min: number | null;
}

/* ------------------------------------------------------------------ */
/* Hesap istekleri                                                     */
/* ------------------------------------------------------------------ */

export interface CoefficientARequest {
  temperature_c: number;
  pressure_bar: number;
  backend?: string | null;
}

export interface CoefficientBRequest {
  source: BSource;
  temperature_c: number;
  pressure_bar: number;
  steel_alpha_micro_per_c: number;
  steel_model: SteelModel;
  backend?: string | null;
}

export interface CoefficientCompareRequest {
  temperature_c: number;
  pressure_bar: number;
  steel_alpha_micro_per_c: number;
  steel_model: SteelModel;
  backend?: string | null;
}

export interface AirContentRequest {
  geometry: GeometryIn;
  a_micro_per_bar: number;
  pressure_rise_bar: number;
  k_factor: number;
  actual_added_water_m3: number;
}

export interface PressureVariationRequest {
  geometry: GeometryIn;
  a_micro_per_bar: number;
  b_micro_per_c: number;
  delta_t_c: number;
  actual_pressure_change_bar: number;
}

export interface PressureProfileRequest {
  geometry: GeometryIn;
  design_pressure_bar: number;
  smys_mpa: number;
  location_class: string;
  highest_elevation_m: number;
  lowest_elevation_m: number;
  start_elevation_m: number;
  end_elevation_m: number;
  pump_location: string;
  monitored_pressure_bar?: number | null;
}

export interface PigSpeedRequest {
  mode: string;
  distance_m: number;
  travel_time_min: number;
}

/* ------------------------------------------------------------------ */
/* Oturum                                                              */
/* ------------------------------------------------------------------ */

export interface ResultSummaryEntry {
  status: DecisionStatus;
  count?: number;
  computed_at?: string | null;
}

/* ------------------------------------------------------------------ */
/* Projeler ve kesitler                                                */
/* ------------------------------------------------------------------ */

export type ProjectStatus = "active" | "completed" | "archived";

export interface ProjectDefaults {
  outside_diameter_mm?: number | null;
  wall_thickness_mm?: number | null;
  material_grade?: string;
  smys_mpa?: number | null;
  design_pressure_bar?: number | null;
  location_class?: string;
  pump_location?: string;
  k_factor?: number | null;
  steel_alpha_micro_per_c?: number | null;
}

export interface Project {
  id: string;
  code: string;
  name: string;
  client: string | null;
  contractor?: string | null;
  supervisor?: string | null;
  pipeline_length_m?: number | null;
  status?: ProjectStatus;
  defaults?: ProjectDefaults;
  description: string | null;
  section_count: number;
  created_at: string;
  updated_at: string;
}

export interface ProjectInput {
  name: string;
  code?: string;
  client?: string;
  contractor?: string;
  supervisor?: string;
  pipeline_length_m?: number | null;
  status?: ProjectStatus;
  defaults?: ProjectDefaults;
  description?: string;
}

export interface SectionMeta {
  section_no: string;
  description: string;
  location: string;
  start_kp: string;
  end_kp: string;
  test_date: string;
  test_type: string;
  notes: string;
}

export interface ProfilePointItem {
  station_m: number;
  elevation_m: number;
}

export interface SectionLandmarkItem {
  station_m: number;
  kp?: string;
  kind: string;
  label: string;
  elevation_m?: number | null;
}

export interface EquipmentInputItem {
  id: string;
  type: SceneEquipmentType;
  label: string;
  station_m: number;
  elevation_m: number | null;
  status?: SceneStatus;
}

export interface DraftSectionItem {
  section_no: string;
  start_kp: string;
  end_kp: string;
  start_m: number;
  end_m: number;
  length_m: number;
  description: string;
  start_elevation_m: number | null;
  end_elevation_m: number | null;
  highest_elevation_m: number | null;
  lowest_elevation_m: number | null;
  outside_diameter_mm: number | null;
  wall_thickness_mm: number | null;
  design_pressure_bar: number | null;
  material_grade: string;
  smys_mpa: number | null;
  prev_end_kp: string | null;
  continuity_ok: boolean;
  continuity_note: string;
  source_file?: string;
  profile_points?: ProfilePointItem[];
  landmarks?: SectionLandmarkItem[];
}

export interface ProjectSceneSectionItem {
  session_id: string;
  section_no: string;
  name: string;
  start_kp: string;
  end_kp: string;
  start_m: number;
  end_m: number;
  length_m: number;
  status: SceneStatus;
}

export interface ProjectSceneResponse extends SceneData {
  project_id: string;
  project_name: string;
  section_count: number;
  total_length_m: number;
  continuity_ok: boolean;
  sections: ProjectSceneSectionItem[];
}

export interface SimilarProjectCandidate {
  id: string;
  name: string;
  code: string;
  similarity: number;
  similarity_pct: number;
  section_count: number;
  exact_match?: boolean;
}

export interface CheckAutoDetail {
  status: "passed" | "failed" | "warning" | "pending";
  checked: boolean | null;
  auto_evaluated: boolean;
  source_forms: string[];
  message: string;
  metrics?: Record<string, unknown>;
}

export type BotasFormCode =
  | "test_data"
  | "cleaning"
  | "filling"
  | "leak_stabilization"
  | "strength"
  | "air_acceptance"
  | "pressure_test"
  | "pressure_acceptance"
  | "dewatering"
  | "pre_drying"
  | "final_drying"
  | "pressurization"
  | "spool_test"
  | "calculation_sheet"
  | "chart_recorder"
  | "caliper_pig";

export interface FormFinding {
  code: string;
  title: string;
  status: "passed" | "warning" | "failed" | "info";
  message: string;
  ref: string;
  expected?: string;
  actual?: string;
}

export interface SectionFormsSummary {
  required_total: number;
  filled_required: number;
  missing_required: number;
  missing_titles: string[];
  supplementary_filled: number;
  failed_forms: string[];
  warning_forms?: string[];
  passed_forms_count?: number;
  warning_forms_count?: number;
  findings_counts?: { passed: number; warning: number; failed: number };
  first_issue_form_code?: string | null;
  key_metrics?: {
    air_excess_pct?: number | null;
    air_passed?: boolean | null;
    pa_minus_pt_bar?: number | null;
    pressure_passed?: boolean | null;
    thermal_delta_c?: number | null;
    filled_volume_m3?: number | null;
    dew_point_c?: number | null;
  };
  complete: boolean;
}

export interface SectionFormRecord {
  id: string;
  form_code: BotasFormCode;
  botas_code: string;
  form_title: string;
  required: boolean;
  order?: number;
  status: "empty" | "filled" | "passed" | "failed" | "warning";
  analysis_id: string | null;
  source_filename: string;
  pages: number[];
  form_date: string;
  extracted_data?: Record<string, unknown>;
  findings?: FormFinding[];
  warnings: string[];
  revision: number;
  filled_at: string | null;
  updated_at: string | null;
}

export interface SessionFormCheckpoint {
  key: CheckKey;
  label: string;
  ref: string;
  checked: boolean;
  status: "passed" | "failed" | "warning" | "pending";
  message: string;
  source_forms: string[];
}

export interface SessionFormsResponse {
  session_id: string;
  project_id: string | null;
  section_no: string;
  session_name: string;
  summary: SectionFormsSummary;
  merged_header?: Record<string, unknown>;
  calculations?: Record<string, Record<string, unknown>>;
  forms: SectionFormRecord[];
  missing_required_forms: Array<{
    form_code: string;
    botas_code: string;
    form_title: string;
  }>;
  checkpoints: SessionFormCheckpoint[];
}

export interface SectionFormUpdatePayload {
  form_date?: string | null;
  extracted_data: Record<string, unknown>;
  overwrite_session_inputs?: boolean;
}

export interface SectionFormUpdateResponse {
  form: SectionFormRecord;
  forms_payload: SessionFormsResponse;
  session: Session;
}

export interface SectionFormScanResponse extends SectionFormUpdateResponse {
  analysis_id: string;
  updated_form_codes: string[];
}

export interface UpdateWebAsset {
  name: string;
  download_url: string;
  size: number;
  kind: string;
}

export interface UpdateJobState {
  state:
    | "idle"
    | "checking"
    | "available"
    | "up_to_date"
    | "downloading"
    | "verifying"
    | "ready_to_install"
    | "installing"
    | "restarting"
    | "failed";
  target_version: string;
  asset_name: string;
  download_url: string;
  downloaded_bytes: number;
  total_bytes: number;
  progress_pct: number;
  sha256_verified: boolean;
  signature_verified: boolean;
  verified_path: string;
  verified_sha256: string;
  error: string;
  message: string;
  updated_at: string;
}

export interface UpdateManagerStatus {
  current_version: string;
  runtime: {
    frozen: boolean;
    platform: string;
    arch: string;
    install_mode: string;
    can_self_install: boolean;
    executable_path?: string;
    install_dir?: string;
    prefer_kind?: string;
  };
  checked: boolean;
  checked_at: string | null;
  latest_version: string | null;
  tag_name: string | null;
  html_url: string;
  release_notes: string;
  published_at: string;
  source_repository: string;
  update_available: boolean;
  check_error: string;
  selected_asset: UpdateWebAsset | null;
  all_assets: UpdateWebAsset[];
  job: UpdateJobState;
}

export interface PlanProfileCommitRequest {
  project_id?: string | null;
  project_name?: string | null;
  project_code?: string | null;
  sections: Array<Partial<DraftSectionItem>>;
}

export interface PlanProfileCommitResponse {
  project_id: string;
  created_count: number;
  updated_count?: number;
  items: SessionListItem[];
  project: Project;
}

export interface PlanProfileScanResponse {
  file_name: string;
  page_count: number;
  extraction_method: string;
  strategy: "cad_profile" | "explicit" | "auto_split";
  station_count: number;
  elevation_point_count: number;
  min_kp: string;
  max_kp: string;
  total_length_m: number;
  pipe_meta: {
    outside_diameter_mm: number | null;
    wall_thickness_mm: number | null;
    design_pressure_bar: number | null;
    material_grade: string;
    smys_mpa: number | null;
  };
  profile_points: Array<{ kp: string; station_m: number; elevation_m: number }>;
  draft_sections: DraftSectionItem[];
  continuity_ok: boolean;
  continuity_issues: string[];
  warnings: string[];
  detected_project_name?: string | null;
  similar_projects?: SimilarProjectCandidate[];
}

export interface SessionResultSummary {
  air?: ResultSummaryEntry;
  pressure?: ResultSummaryEntry;
  checklist?: { checked: number; total: number };
  last_computed_at?: string | null;
}

export interface Session {
  id: string;
  project_id: string | null;
  name: string;
  status: SessionStatus;
  revision: number;
  inputs: Record<string, unknown>;
  wizard_state: Record<string, unknown> | null;
  result_summary: SessionResultSummary;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

export interface SessionListItem {
  id: string;
  project_id: string | null;
  name: string;
  status: SessionStatus;
  revision: number;
  updated_at: string;
  created_at?: string;
  result_summary?: SessionResultSummary;
  section_meta?: SectionMeta;
  forms_summary?: SectionFormsSummary | null;
}

export interface SessionSummaryResponse {
  session_id: string;
  status: SessionStatus;
  tests: Record<string, { status: DecisionStatus; count: number }>;
  checklist: { checked: number; total: number; progress: number };
  coefficients: { air_a: CoefficientState; pressure_a: CoefficientState; pressure_b: CoefficientState };
  profile: { feasible: boolean; window: { min_bar: number; max_bar: number } };
  scene: { segment_count: number; total_length_m: number; volume_m3: number; approximate_profile: boolean };
  last_computed_at: string | null;
}

export interface TestResultRecord {
  id: string;
  test_type: TestType;
  inputs?: Record<string, unknown>;
  result: Record<string, unknown>;
  decision: Decision;
  computed_at: string;
}

export interface SessionUpdateResponse extends Session {
  mapping?: SnapshotMapping;
}

export interface SnapshotMapping {
  converted: number;
  skipped: string[];
  invalid_fields: string[];
  warnings: string[];
}

export interface ExportResult {
  blob: Blob;
  filename: string;
}

/* ------------------------------------------------------------------ */
/* OCR                                                                 */
/* ------------------------------------------------------------------ */

export interface OcrStatusResponse {
  available: boolean;
  status_text: string;
  engine: {
    name: string;
    version: string;
    languages: string[];
    default_language: string;
  } | null;
  pdf_rasterizer: { available: boolean; engine: string | null; note: string };
  limits: {
    max_file_size_bytes: number;
    max_pdf_pages: number;
    max_ocr_pages: number;
    supported_extensions: string[];
  };
  queue: { queued: number; running: number; max_concurrency: number };
  thresholds: {
    auto_fill: number;
    low_confidence: number;
    critical_confidence: number;
    human_review_required: boolean;
  };
  mapping_profiles: { default_id: string | null; count: number };
}

/* ------------------------------------------------------------------ */
/* Yerel girdi modeli (UI)                                             */
/* ------------------------------------------------------------------ */

export interface GeometryInputs {
  outside_diameter_mm: number | null;
  wall_thickness_mm: number | null;
  length_m: number | null;
}

export interface SegmentRow extends GeometryInputs {
  id: string;
  nps_label: string;
  schedule_label: string;
  start_station_m: number | null;
}

export interface GeometryCatalogInputs {
  size_option: string;
  schedule_option: string;
}

export interface SectionProfileInputs {
  highest_elevation_m: number | null;
  lowest_elevation_m: number | null;
  start_elevation_m: number | null;
  end_elevation_m: number | null;
  design_pressure_bar: number | null;
  smys_mpa: number | null;
}

export interface AirInputs {
  temperature_c: number | null;
  pressure_bar: number | null;
  a_micro_per_bar: number | null;
  pressure_rise_bar: number;
  k_factor: number;
  actual_added_water_m3: number | null;
  ambient_temperature_c: number | null;
}

export interface PressureInputs {
  temperature_c: number | null;
  pressure_bar: number | null;
  a_micro_per_bar: number | null;
  b_micro_per_c: number | null;
  delta_t_c: number | null;
  actual_pressure_change_bar: number | null;
  t_initial_c: number | null;
  t_final_c: number | null;
  derive_delta_t: boolean;
}

export interface FieldInputs {
  ambient_temperature_c: number | null;
  pig_distance_m: number | null;
  pig_travel_time_min: number | null;
  pig_speed_m_per_s: number | null;
  pig_speed_km_per_h: number | null;
  monitored_pressure_bar: number | null;
}

export interface HelperInputs {
  steel_alpha_micro_per_c: number;
  water_beta_micro_per_c: number | null;
}

export interface ModeInputs {
  air_a_mode: AMode;
  air_a_reference: string;
  pressure_a_mode: AMode;
  pressure_a_reference: string;
  pressure_b_mode: "auto" | "table" | "manual";
  pressure_b_source: BSource;
  pressure_b_reference: string;
  steel_model: SteelModel;
  k_preset: string;
  steel_preset: string;
  pig_mode: string;
}

export type CheckKey =
  | "ambient_temp"
  | "temp_probes"
  | "fill_air_entry"
  | "fill_records"
  | "thermal_balance"
  | "air_content_limit"
  | "pressurization_volume"
  | "two_hour_hold"
  | "pressure_records"
  | "depressurize_discharge"
  | "forms";

export interface ReportMeta {
  report_no: string;
  operator: string;
  date: string;
  section_id: string;
}

export interface AppInputs {
  water_backend: string;
  section_meta: SectionMeta;
  geometry: GeometryInputs;
  geometry_catalog: GeometryCatalogInputs;
  segments: SegmentRow[];
  profile_points: ProfilePointItem[];
  landmarks: SectionLandmarkItem[];
  equipment: EquipmentInputItem[];
  section_profile: SectionProfileInputs;
  material_grade: string;
  location_class: string;
  pump_location: string;
  air: AirInputs;
  pressure: PressureInputs;
  field: FieldInputs;
  helper: HelperInputs;
  modes: ModeInputs;
  checks: Record<CheckKey, boolean>;
  check_details?: Partial<Record<CheckKey, CheckAutoDetail>>;
  forms_summary?: SectionFormsSummary | null;
  report: ReportMeta;
}

export type InputPatch = {
  [K in keyof AppInputs]?: AppInputs[K] extends Array<infer _T>
    ? AppInputs[K]
    : Partial<AppInputs[K]>;
};

export interface CoefficientBundle {
  airA?: CoefficientAResponse;
  pressureA?: CoefficientAResponse;
  pressureB?: BSourceResult;
}

export interface ResultBundle {
  geometry?: GeometryResponse;
  air?: AirContentResponse;
  pressure?: PressureVariationResponse;
  profile?: PressureProfileResponse;
  pig?: PigSpeedResponse;
  coefficients?: CoefficientBundle;
  bCompare?: BComparisonResponse;
  backendCompare?: BackendComparisonResponse;
  tablePoint?: TablePointResponse;
  lastComputedAt?: string;
  source: "demo" | "live";
}

export interface HistoryEntry {
  id: string;
  testType: TestType;
  title: string;
  status: DecisionStatus;
  summary: string;
  at: string;
}

export interface ExportEntry {
  id: string;
  format: "pdf" | "xlsx" | "txt";
  filename: string;
  at: string;
  size: number;
  demo: boolean;
}

export type BackendMode = "checking" | "online" | "demo";

export type ToastTone = "success" | "error" | "warning" | "info";

export interface ToastItem {
  id: string;
  tone: ToastTone;
  title: string;
  description?: string;
}

export type TabKey =
  | "dashboard"
  | "projects"
  | "geometry"
  | "coefficients"
  | "coefficient_detail"
  | "air"
  | "pressure"
  | "forms"
  | "field"
  | "reports"
  | "ocr"
  | "settings";

/* ------------------------------------------------------------------ */
/* Veritabanı Yönetimi, Proje Veri Merkezi ve Arşiv Tipleri           */
/* ------------------------------------------------------------------ */

export type ProjectExportFormat = "xlsx" | "pdf" | "csv" | "json";

export interface ProjectDatasetFormCell {
  status: string;
  revision: number;
  page_count: number;
  short_code: string;
}

export interface ProjectDatasetSection {
  session_id: string;
  section_no: string;
  name: string;
  status: SessionStatus;
  revision: number;
  start_kp: string;
  end_kp: string;
  length_m: number | null;
  outside_diameter_mm: number | null;
  wall_thickness_mm: number | null;
  material_grade: string;
  smys_mpa: number | null;
  internal_volume_m3: number | null;
  design_pressure_bar: number | null;
  window_min_bar: number | null;
  window_max_bar: number | null;
  air_ratio: number | null;
  air_status: DecisionStatus;
  pressure_pt_bar: number | null;
  pressure_pa_bar: number | null;
  pressure_margin_bar: number | null;
  delta_t_c: number | null;
  pressure_status: DecisionStatus;
  dew_point_c: number | null;
  forms_filled: number;
  forms_required: number;
  failed_forms: string[];
  warning_forms: string[];
  overall_status: DecisionStatus | "KISMI";
  test_date: string;
  updated_at: string;
}

export interface ProjectDatasetSummary {
  section_count: number;
  total_length_m: number;
  total_volume_m3: number;
  continuity_ok: boolean;
  continuity_gaps: Array<{
    from_section: string;
    to_section: string;
    prev_end_kp: string;
    next_start_kp: string;
    delta_m: number;
  }>;
  evaluated_count: number;
  passed_count: number;
  failed_count: number;
  pending_count: number;
  forms_filled_total: number;
  forms_required_total: number;
  forms_completion_pct: number;
}

export interface ProjectDatasetResponse {
  project: Project;
  summary: ProjectDatasetSummary;
  sections: ProjectDatasetSection[];
  form_catalog: Array<{ code: string; botas_code: string; title: string; required: boolean }>;
  forms_matrix: Array<{
    session_id: string;
    section_no: string;
    start_kp: string;
    end_kp: string;
    forms: Record<string, ProjectDatasetFormCell>;
  }>;
  generated_at: string;
}

export interface ProjectGenerateSectionsPayload {
  start_kp_m?: number;
  total_length_m: number;
  max_section_length_m?: number;
  respect_volume_limit?: boolean;
  section_prefix?: string;
  start_index?: number;
  outside_diameter_mm?: number | null;
  wall_thickness_mm?: number | null;
  material_grade?: string | null;
  smys_mpa?: number | null;
  design_pressure_bar?: number | null;
  location_class?: string | null;
  test_date?: string | null;
  create_form_slots?: boolean;
}

export interface ProjectGenerateSectionsResponse {
  project_id: string;
  created_count: number;
  target_section_length_m: number;
  volume_limited_length_m: number | null;
  items: SessionListItem[];
}

export interface ProjectSyncFormsResponse {
  project_id: string;
  sessions_processed: number;
  updated_forms: number;
}

export interface SampleProjectPayload {
  scenario: "passing" | "mixed" | "failing";
  section_count?: number;
  name?: string | null;
  code?: string | null;
  include_time_series?: boolean;
  include_forms?: boolean;
}

export interface ProjectClonePayload {
  name?: string | null;
  code?: string | null;
  mode: "template" | "full";
}

export interface ArchiveImportResponse {
  project: Project;
  imported_sections: number;
  imported_forms: number;
  imported_results: number;
  imported_time_series: number;
  imported_attachments: number;
}

export interface DesktopDbImportResponse {
  project: Project;
  imported_sessions: number;
  imported_results: number;
  imported_time_series: number;
}

export interface WorkspaceInfo {
  workspace_hash: string;
  hash_short: string;
  is_current: boolean;
  project_count: number;
  section_count: number;
  last_updated_at: string | null;
  sample_projects: string[];
}

export interface WorkspacesResponse {
  current_workspace_hash: string;
  items: WorkspaceInfo[];
}

export interface DbStatsResponse {
  dialect: string;
  is_sqlite: boolean;
  db_path: string | null;
  schema_migration: string;
  db_size_bytes: number;
  wal_size_bytes: number;
  shm_size_bytes: number;
  journal_mode: string;
  integrity_status: string;
  table_counts: Record<string, number>;
  storage: {
    uploads_bytes: number;
    uploads_files: number;
    exports_bytes: number;
    exports_files: number;
    backups_bytes: number;
    backups_count: number;
  };
  workspace_count: number;
  current_workspace_hash: string;
}

export interface DbBackupItem {
  filename: string;
  size_bytes: number;
  created_at: string | null;
  reason?: string;
}

export interface DbBackupsResponse {
  items: DbBackupItem[];
  total: number;
  backups_dir: string;
}

export interface DbRestoreResponse {
  restored: boolean;
  source: string;
  pre_restore_backup: DbBackupItem | null;
  stats: DbStatsResponse;
}

export interface TrashItem {
  entity_type: "project" | "session";
  id: string;
  name: string;
  code: string;
  project_id: string | null;
  section_count: number | null;
  deleted_at: string | null;
}

export interface TrashResponse {
  items: TrashItem[];
  total: number;
}

export interface DbMaintenancePayload {
  checkpoint_wal: boolean;
  vacuum: boolean;
  clean_exports: boolean;
  clean_orphan_uploads: boolean;
}

export interface DbMaintenanceResponse {
  integrity_status: string;
  wal_checkpointed: boolean;
  vacuumed: boolean;
  removed_export_files: number;
  reclaimed_export_bytes: number;
  removed_orphan_files: number;
  reclaimed_upload_bytes: number;
}

/* ------------------------------------------------------------------ */
/* Zaman Serisi (Şartname Bölüm 12 & 15)                               */
/* ------------------------------------------------------------------ */

export interface TimeSeriesRecordInput {
  timestamp?: string | null;
  pressure_bar: number;
  temperature_c: number;
  volume_m3?: number | null;
  notes?: string;
  source?: string;
}

export interface TimeSeriesRecordItem {
  id: string;
  timestamp: string;
  pressure_bar: number;
  temperature_c: number;
  volume_m3: number | null;
  notes: string;
  source: string;
}

export interface TimeSeriesSummary {
  record_count: number;
  duration_hours: number;
  balanced: boolean;
  thermal_duration_ok: boolean;
  temp_diff_c: number | null;
  reason?: string | null;
  average_temperature_last_4h_c: number | null;
  previous_4h_avg_c: number | null;
  average_temperature_c: number | null;
  first_timestamp: string | null;
  last_timestamp: string | null;
  max_gap_hours: number | null;
  recording_duration_ok: boolean;
  recording_interval_ok: boolean;
  recording_passed: boolean;
  initial_pressure_bar: number | null;
  final_pressure_bar: number | null;
  pressure_change_pa_bar: number | null;
  min_pressure_bar: number | null;
  max_pressure_bar: number | null;
  initial_temperature_c: number | null;
  final_temperature_c: number | null;
  temperature_change_dt_c: number | null;
  min_temperature_c: number | null;
  max_temperature_c: number | null;
  initial_volume_m3: number | null;
  final_volume_m3: number | null;
  volume_delta_m3: number | null;
  decision: Decision;
  recording_decision: Decision;
}

export type ThermalBalanceResponse = TimeSeriesSummary;

export interface TimeSeriesAddResponse {
  record: TimeSeriesRecordItem;
  summary: TimeSeriesSummary;
}

export interface TimeSeriesBatchResponse {
  inserted: number;
  total: number;
  items: TimeSeriesRecordItem[];
  summary: TimeSeriesSummary;
}

export interface TimeSeriesClearResponse {
  deleted: number;
  summary: TimeSeriesSummary;
}

export interface TimeSeriesSyncFormResponse {
  direction: "from_form" | "to_form";
  form_code: "leak_stabilization" | "pressure_test";
  synced_count: number;
  skipped_rows: number;
  items?: TimeSeriesRecordItem[];
  summary: TimeSeriesSummary;
}
