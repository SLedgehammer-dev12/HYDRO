"""Pydantic request schemas.

Validation is intentionally structural only: physical/physics rules are left
to the domain so the API returns ``400 domain_validation_error`` (not 422)
for the same inputs the desktop application rejects.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

B_SOURCE = Literal["institutional", "gail", "auto"]
STEEL_MODEL = Literal["volumetric", "linear", "volumetric_temperature"]
SESSION_STATUS = Literal["draft", "active", "completed", "archived"]
TEST_TYPE = Literal[
    "air",
    "pressure",
    "coefficient_a",
    "coefficient_b",
    "profile",
    "pig",
    "pressurization",
    "thermal_balance",
    "pressurization_ramp",
    "pressure_hold",
    "depressurization",
    "discharge",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class PipeSectionIn(StrictModel):
    outside_diameter_mm: float
    wall_thickness_mm: float
    length_m: float
    nps_label: str | None = None
    schedule_label: str | None = None
    start_station_m: float | None = None


class GeometryIn(StrictModel):
    sections: list[PipeSectionIn] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Coefficients
# ---------------------------------------------------------------------------


class CoefficientARequest(StrictModel):
    temperature_c: float
    pressure_bar: float
    backend: str | None = None


class CoefficientBRequest(StrictModel):
    source: B_SOURCE = "institutional"
    temperature_c: float
    pressure_bar: float
    steel_alpha_micro_per_c: float = 12.0
    steel_model: STEEL_MODEL = "volumetric"


class CoefficientCompareRequest(StrictModel):
    temperature_c: float
    pressure_bar: float
    steel_alpha_micro_per_c: float = 12.0
    steel_model: STEEL_MODEL = "volumetric"


class CoefficientTableRequest(StrictModel):
    table: Literal["institutional", "gail"] = "institutional"
    temperature_c: float
    pressure_bar: float
    repair_anomalies: bool = True


class ReferenceCompareRequest(StrictModel):
    temperature_c: float
    pressure_bar: float
    repair_anomalies: bool = True


class BackendComparisonRequest(StrictModel):
    temperature_c: float
    pressure_bar: float
    include_dev_backends: bool = False


# ---------------------------------------------------------------------------
# Calculations
# ---------------------------------------------------------------------------


class AirContentRequest(StrictModel):
    geometry: GeometryIn
    a_micro_per_bar: float
    pressure_rise_bar: float = 1.0
    k_factor: float = 1.02
    actual_added_water_m3: float


class PressureVariationRequest(StrictModel):
    geometry: GeometryIn
    a_micro_per_bar: float
    b_micro_per_c: float
    delta_t_c: float
    actual_pressure_change_bar: float


class PressureProfileRequest(StrictModel):
    geometry: GeometryIn
    design_pressure_bar: float
    smys_mpa: float
    location_class: str
    highest_elevation_m: float
    lowest_elevation_m: float
    start_elevation_m: float
    end_elevation_m: float
    pump_location: str
    monitored_pressure_bar: float | None = None


class PigSpeedRequest(StrictModel):
    mode: str
    distance_m: float
    travel_time_min: float


class PressurizationRequest(StrictModel):
    initial_volume_m3: float
    added_volume_m3: float
    theoretical_volume_m3: float
    pressure_bar: float
    expected_pressure_bar: float


class PressurizationReadingIn(StrictModel):
    elapsed_min: float
    pressure_bar: float
    cumulative_added_volume_m3: float


class PressurizationRampRequest(StrictModel):
    readings: list[PressurizationReadingIn] = Field(default_factory=list)
    test_pressure_100_smys_bar: float
    total_filled_volume_m3: float


class PressureHoldReadingIn(StrictModel):
    elapsed_min: float
    pressure_bar: float
    temperature_c: float


class PressureHoldRequest(StrictModel):
    readings: list[PressureHoldReadingIn] = Field(default_factory=list)
    target_pressure_bar: float


class DepressurizationRequest(StrictModel):
    test_passed: bool | None = None
    release_valve_diameter_in: float | None = None
    pipe_equipment_checked: bool | None = None
    environmental_impact_checked: bool | None = None


class DischargeRequest(StrictModel):
    destination: str | None = None
    used_discharge_pig: bool | None = None
    hydraulic_load_measures_taken: bool | None = None
    approvals_obtained: bool | None = None
    treatment_requested: bool = False
    treatment_done: bool | None = None
    sample_analysis_requested: bool = False
    sample_analysis_done: bool | None = None
    erosion_prevented: bool | None = None
    report_date: str = ""
    report_time: str = ""
    pig_name: str = ""
    discharge_location: str = ""
    duration_min: float | None = None


class ThermalBalanceRecordIn(StrictModel):
    timestamp: datetime | None = None
    pressure_bar: float
    temperature_c: float
    volume_m3: float | None = None
    notes: str = ""


class ThermalBalanceRequest(StrictModel):
    records: list[ThermalBalanceRecordIn] = Field(default_factory=list)


class WaterDensityRequest(StrictModel):
    temperature_c: float = 15.0
    pressure_bar: float = 1.0


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


class SessionCreate(StrictModel):
    name: str | None = Field(default=None, max_length=200)
    project_id: str | None = None
    inputs: dict[str, Any] | None = None
    wizard_state: dict[str, Any] | None = None


class SessionUpdate(StrictModel):
    name: str | None = Field(default=None, max_length=200)
    project_id: str | None = None
    status: SESSION_STATUS | None = None
    inputs: dict[str, Any] | None = None
    wizard_state: dict[str, Any] | None = None
    notes: str | None = None


PROJECT_STATUS = Literal["active", "completed", "archived"]


class ProjectCreate(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    code: str | None = Field(default=None, max_length=64)
    client: str | None = Field(default=None, max_length=200)
    contractor: str | None = Field(default=None, max_length=200)
    supervisor: str | None = Field(default=None, max_length=200)
    pipeline_length_m: float | None = Field(default=None, ge=0, le=5_000_000)
    status: PROJECT_STATUS = "active"
    defaults: dict[str, Any] = Field(default_factory=dict)
    description: str | None = None


class ProjectUpdate(StrictModel):
    name: str | None = Field(default=None, max_length=200)
    code: str | None = Field(default=None, max_length=64)
    client: str | None = Field(default=None, max_length=200)
    contractor: str | None = Field(default=None, max_length=200)
    supervisor: str | None = Field(default=None, max_length=200)
    pipeline_length_m: float | None = Field(default=None, ge=0, le=5_000_000)
    status: PROJECT_STATUS | None = None
    defaults: dict[str, Any] | None = None
    description: str | None = None


class ProjectSummary(StrictModel):
    id: str
    code: str = ""
    name: str
    client: str | None = None
    contractor: str | None = None
    supervisor: str | None = None
    pipeline_length_m: float | None = None
    status: PROJECT_STATUS = "active"
    defaults: dict[str, Any] = Field(default_factory=dict)
    description: str | None = None
    section_count: int = 0
    created_at: str | None = None
    updated_at: str | None = None


class ProjectExportRequest(StrictModel):
    format: Literal["xlsx", "pdf", "csv", "json"] = "xlsx"


class ProjectGenerateSectionsRequest(StrictModel):
    total_length_m: float = Field(gt=0, le=500_000)
    start_kp_m: float = Field(default=0.0, ge=0, le=2_000_000)
    max_section_length_m: float = Field(default=12_000.0, ge=100, le=20_000)
    respect_volume_limit: bool = True
    section_prefix: str = Field(default="K-", min_length=1, max_length=16)
    outside_diameter_mm: float | None = Field(default=None, gt=0, le=5000)
    wall_thickness_mm: float | None = Field(default=None, gt=0, le=200)
    material_grade: str | None = Field(default=None, max_length=160)
    smys_mpa: float | None = Field(default=None, gt=0, le=2000)
    design_pressure_bar: float | None = Field(default=None, gt=0, le=1000)
    location_class: str | None = Field(default=None, max_length=120)
    base_elevation_m: float = Field(default=200.0, ge=-500, le=8000)
    elevation_amplitude_m: float = Field(default=85.0, ge=0, le=2000)
    test_date: str | None = Field(default=None, max_length=40)
    initialize_forms: bool = True


class ProjectSyncFormsRequest(StrictModel):
    overwrite_existing: bool = False
    form_codes: list[str] | None = Field(default=None, max_length=20)


class SampleProjectGenerateRequest(StrictModel):
    scenario: Literal["passing", "mixed", "failing"] = "mixed"
    section_count: int = Field(default=3, ge=1, le=6)
    name: str | None = Field(default=None, max_length=200)
    code: str | None = Field(default=None, max_length=64)
    include_time_series: bool = True
    include_forms: bool = True


class ProjectCloneRequest(StrictModel):
    name: str | None = Field(default=None, max_length=200)
    code: str | None = Field(default=None, max_length=64)
    mode: Literal["template", "full"] = "template"


class WorkspaceClaimRequest(StrictModel):
    source_workspace_hash: str = Field(min_length=8, max_length=64)
    source_workspace_key: str | None = Field(default=None, min_length=1, max_length=256)


class TrashRestoreRequest(StrictModel):
    entity_type: Literal["project", "session"]
    entity_id: str = Field(min_length=1, max_length=64)


class DbBackupRequest(StrictModel):
    reason: str = Field(default="manual", max_length=32)


class DbRestoreRequest(StrictModel):
    backup_filename: str = Field(min_length=1, max_length=180)


class DbMaintenanceRequest(StrictModel):
    checkpoint_wal: bool = True
    vacuum: bool = False
    clean_exports: bool = True
    clean_orphan_uploads: bool = False


class SectionProfilePointIn(StrictModel):
    station_m: float = Field(ge=0, le=1_000_000)
    elevation_m: float = Field(ge=-500, le=10_000)


class SectionLandmarkIn(StrictModel):
    station_m: float = Field(ge=0, le=1_000_000)
    kp: str = Field(default="", max_length=40)
    kind: str = Field(default="crossing", max_length=32)
    label: str = Field(min_length=1, max_length=120)
    elevation_m: float | None = None


class DraftSectionIn(StrictModel):
    section_no: str = Field(min_length=1, max_length=40)
    start_kp: str = Field(min_length=1, max_length=40)
    end_kp: str = Field(min_length=1, max_length=40)
    length_m: float | None = Field(default=None, gt=0, le=1_000_000)
    description: str | None = Field(default=None, max_length=240)
    start_elevation_m: float | None = None
    end_elevation_m: float | None = None
    highest_elevation_m: float | None = None
    lowest_elevation_m: float | None = None
    outside_diameter_mm: float | None = Field(default=None, gt=0, le=5000)
    wall_thickness_mm: float | None = Field(default=None, gt=0, le=200)
    design_pressure_bar: float | None = Field(default=None, gt=0, le=1000)
    material_grade: str | None = Field(default=None, max_length=120)
    smys_mpa: float | None = Field(default=None, gt=0, le=2000)
    test_date: str | None = Field(default=None, max_length=40)
    notes: str | None = Field(default=None, max_length=400)
    profile_points: list[SectionProfilePointIn] = Field(default_factory=list, max_length=250)
    landmarks: list[SectionLandmarkIn] = Field(default_factory=list, max_length=40)


class DraftSectionBatchCreate(StrictModel):
    sections: list[DraftSectionIn] = Field(min_length=1, max_length=100)


class PlanProfileCommitRequest(StrictModel):
    project_id: str | None = None
    project_name: str | None = Field(default=None, max_length=200)
    project_code: str | None = Field(default=None, max_length=64)
    sections: list[DraftSectionIn] = Field(min_length=1, max_length=100)


class SessionDuplicate(StrictModel):
    name: str | None = Field(default=None, max_length=200)


class ResultCreate(StrictModel):
    test_type: TEST_TYPE
    payload: dict[str, Any] = Field(default_factory=dict)


class TimeSeriesCreate(StrictModel):
    timestamp: datetime | None = None
    pressure_bar: float
    temperature_c: float
    volume_m3: float | None = None
    notes: str = ""
    source: str = "manual"


class SnapshotApply(StrictModel):
    snapshot: dict[str, Any]
    mode: Literal["merge", "replace"] = "merge"


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


class ReportExportRequest(StrictModel):
    format: Literal["pdf", "xlsx", "txt"]
    title: str = "Hidrostatik Test Degerlendirme Raporu"
    metadata: dict[str, str] = Field(default_factory=dict)
    geometry_data: dict[str, str] = Field(default_factory=dict)
    test_results: dict[str, str] = Field(default_factory=dict)
    checklist: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------


class OcrApproveField(StrictModel):
    value: float | str | None = None
    unit: str = ""
    approved: bool = True


class OcrApproveRequest(StrictModel):
    fields: dict[str, OcrApproveField] = Field(default_factory=dict)
    approve_all: bool = False
    reviewer_note: str = Field(default="", max_length=2000)


class OcrApplyRequest(StrictModel):
    session_id: str | None = None
    fields: list[str] | None = None
    overwrite: bool = False


class OcrDossierCommitRequest(StrictModel):
    target_project_id: str | None = None
    create_new_project: bool = False
    new_project_name: str | None = Field(default=None, max_length=200)
    new_project_code: str | None = Field(default=None, max_length=64)
    overwrite_filled: bool = False
    selected_sections: list[str] | None = None


class SectionFormUpdateRequest(StrictModel):
    form_date: str | None = Field(default=None, max_length=40)
    extracted_data: dict[str, Any] = Field(default_factory=dict)
    overwrite_session_inputs: bool = True


class MappingProfileCreate(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    format_key: str = Field(min_length=1, max_length=120)
    schema_version: int = 1
    mode: Literal["pre_extract", "post_map"] = "pre_extract"
    is_default: bool = False
    mapping: dict[str, Any] = Field(default_factory=dict)


class MappingProfileUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    format_key: str | None = Field(default=None, min_length=1, max_length=120)
    schema_version: int | None = None
    mode: Literal["pre_extract", "post_map"] | None = None
    is_default: bool | None = None
    mapping: dict[str, Any] | None = None


__all__ = [
    "AirContentRequest",
    "BackendComparisonRequest",
    "CoefficientARequest",
    "CoefficientBRequest",
    "CoefficientCompareRequest",
    "CoefficientTableRequest",
    "DbBackupRequest",
    "DbMaintenanceRequest",
    "DbRestoreRequest",
    "DraftSectionBatchCreate",
    "DraftSectionIn",
    "GeometryIn",
    "MappingProfileCreate",
    "MappingProfileUpdate",
    "OcrApplyRequest",
    "OcrApproveField",
    "OcrApproveRequest",
    "OcrDossierCommitRequest",
    "PigSpeedRequest",
    "PipeSectionIn",
    "PlanProfileCommitRequest",
    "PressureProfileRequest",
    "PressureVariationRequest",
    "PressurizationRampRequest",
    "PressurizationReadingIn",
    "PressurizationRequest",
    "PressureHoldReadingIn",
    "PressureHoldRequest",
    "DepressurizationRequest",
    "DischargeRequest",
    "ProjectCloneRequest",
    "ProjectCreate",
    "ProjectExportRequest",
    "ProjectGenerateSectionsRequest",
    "ProjectSummary",
    "ProjectSyncFormsRequest",
    "ProjectUpdate",
    "ReferenceCompareRequest",
    "ReportExportRequest",
    "ResultCreate",
    "SampleProjectGenerateRequest",
    "SectionFormUpdateRequest",
    "SectionLandmarkIn",
    "SectionProfilePointIn",
    "SessionCreate",
    "SessionDuplicate",
    "SessionUpdate",
    "SnapshotApply",
    "ThermalBalanceRecordIn",
    "ThermalBalanceRequest",
    "TimeSeriesCreate",
    "TrashRestoreRequest",
    "WaterDensityRequest",
    "WorkspaceClaimRequest",
]
