"""Session, result and time-series persistence."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session as OrmSession

from hidrostatik_test import APP_VERSION
from hidrostatik_test.data import BOTAS_REFERENCE_OPTION_LABEL
from hidrostatik_test.domain import DEFAULT_STEEL_MODEL

from ..core.errors import AppError, not_found
from ..core.timeutil import (
    as_float,
    deep_merge,
    ensure_utc,
    iso_z,
    json_safe,
    utcnow,
)
from ..desktop_labels import FIELD_CHECK_KEYS
from ..models import (
    Attachment,
    HydroSession,
    OcrAnalysis,
    Project,
    TestResult,
    TimeSeriesRecord,
    new_uuid,
)
from . import audit
from .storage import resolve_stored_path

ENGINE_VERSION = f"{APP_VERSION}/schema1"


# ---------------------------------------------------------------------------
# Defaults and serialisation
# ---------------------------------------------------------------------------


def default_inputs() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "active_tab": "air",
        "water_backend": "table_v1",
        "section_meta": {
            "section_no": "",
            "description": "",
            "location": "",
            "start_kp": "",
            "end_kp": "",
            "test_date": "",
            "test_type": "Hidrostatik test",
            "notes": "",
        },
        "geometry": {
            "outside_diameter_mm": None,
            "wall_thickness_mm": None,
            "length_m": None,
        },
        "geometry_catalog": {"size_option": "", "schedule_option": ""},
        "section_profile": {
            "highest_elevation_m": None,
            "lowest_elevation_m": None,
            "start_elevation_m": None,
            "end_elevation_m": None,
            "design_pressure_bar": None,
            "smys_mpa": None,
        },
        "material_grade": "",
        "location_class": "Class 1 - min 1.25 x dizayn basinci",
        "pump_location": "",
        "segments": [],
        "profile_points": [],
        "landmarks": [],
        "equipment": [],
        "air": {
            "temperature_c": None,
            "pressure_bar": None,
            "a_micro_per_bar": None,
            "pressure_rise_bar": 1.0,
            "k_factor": 1.02,
            "actual_added_water_m3": None,
        },
        "pressure": {
            "temperature_c": None,
            "pressure_bar": None,
            "a_micro_per_bar": None,
            "b_micro_per_c": None,
            "delta_t_c": None,
            "actual_pressure_change_bar": None,
            "t_initial_c": None,
            "t_final_c": None,
            "derive_delta_t": False,
        },
        "field": {
            "ambient_temperature_c": None,
            "pig_distance_m": None,
            "pig_travel_time_min": None,
            "pig_speed_m_per_s": None,
            "pig_speed_km_per_h": None,
        },
        "helper": {"steel_alpha_micro_per_c": 12.0, "water_beta_micro_per_c": None},
        "modes": {
            "air_a_mode": "auto",
            "air_a_reference": "",
            "pressure_a_mode": "auto",
            "pressure_a_reference": "",
            "pressure_b_mode": "table",
            "pressure_b_reference": BOTAS_REFERENCE_OPTION_LABEL,
            "pressure_b_source": "institutional",
            "steel_model": DEFAULT_STEEL_MODEL,
            "k_preset": "Kaynakli boru - 1.02",
            "steel_preset": "Karbon celik - 12.0",
            "pig_mode": "Temizlik pigi",
        },
        "checks": {key: False for key in FIELD_CHECK_KEYS},
        "check_details": {},
        "forms_summary": None,
        "coefficients": {
            "air_a": {"state": "empty", "source": "empty"},
            "pressure_a": {"state": "empty", "source": "empty"},
            "pressure_b": {"state": "empty", "source": "empty"},
        },
        "report": {
            "report_no": "",
            "operator": "",
            "date": "",
            "section_id": "",
        },
        "report_entries": [],
    }


def normalize_inputs(raw: dict[str, Any] | None) -> dict[str, Any]:
    base = default_inputs()
    if raw:
        merged = deep_merge(base, raw)
    else:
        merged = base
    merged["schema_version"] = 1
    if not isinstance(merged.get("segments"), list):
        merged["segments"] = []
    if not isinstance(merged.get("profile_points"), list):
        merged["profile_points"] = []
    if not isinstance(merged.get("landmarks"), list):
        merged["landmarks"] = []
    if not isinstance(merged.get("equipment"), list):
        merged["equipment"] = []
    if not isinstance(merged.get("checks"), dict):
        merged["checks"] = {}
    for key in FIELD_CHECK_KEYS:
        merged["checks"].setdefault(key, False)
    if not isinstance(merged.get("check_details"), dict):
        merged["check_details"] = {}
    if not isinstance(merged.get("report"), dict):
        merged["report"] = {}
    raw_report_meta = merged.get("report_meta")
    for key in ("report_no", "operator", "date", "section_id"):
        val = merged["report"].get(key)
        text = "" if val is None else str(val)
        if not text and isinstance(raw_report_meta, dict):
            fallback_val = raw_report_meta.get(key)
            if fallback_val is not None and str(fallback_val).strip():
                text = str(fallback_val).strip()
        merged["report"][key] = text
    if not isinstance(merged.get("report_entries"), list):
        merged["report_entries"] = []
    # Keep air.ambient_temperature_c and field.ambient_temperature_c canonical & identical.
    air_block = merged.get("air")
    field_block = merged.get("field")
    if isinstance(air_block, dict) and isinstance(field_block, dict):
        air_ambient = as_float(air_block.get("ambient_temperature_c"))
        field_ambient = as_float(field_block.get("ambient_temperature_c"))
        raw_air_amb = (raw.get("air") if isinstance(raw, dict) else None) or {}
        raw_fld_amb = (raw.get("field") if isinstance(raw, dict) else None) or {}
        has_raw_air = isinstance(raw_air_amb, dict) and "ambient_temperature_c" in raw_air_amb
        has_raw_fld = isinstance(raw_fld_amb, dict) and "ambient_temperature_c" in raw_fld_amb
        if has_raw_fld and not has_raw_air:
            canonical_ambient = field_ambient
        elif has_raw_air and not has_raw_fld:
            canonical_ambient = air_ambient
        elif air_ambient is not None:
            canonical_ambient = air_ambient
        else:
            canonical_ambient = field_ambient
        air_block["ambient_temperature_c"] = canonical_ambient
        field_block["ambient_temperature_c"] = canonical_ambient
    return merged


def serialize_session(session: HydroSession) -> dict[str, Any]:
    return {
        "id": session.id,
        "project_id": session.project_id,
        "name": session.name,
        "status": session.status,
        "revision": session.revision,
        "inputs": session.inputs or {},
        "wizard_state": session.wizard_state,
        "result_summary": session.result_summary or {},
        "notes": session.notes or "",
        "legacy_id": session.legacy_id,
        "created_at": iso_z(session.created_at),
        "updated_at": iso_z(session.updated_at),
        "deleted_at": iso_z(session.deleted_at),
    }


def session_brief(session: HydroSession) -> dict[str, Any]:
    summary = session.result_summary or {}
    raw_inputs: dict[str, Any] = session.inputs if isinstance(session.inputs, dict) else {}
    raw_meta_val = raw_inputs.get("section_meta")
    raw_meta: dict[str, Any] = raw_meta_val if isinstance(raw_meta_val, dict) else {}
    section_meta = {
        "section_no": str(raw_meta.get("section_no") or ""),
        "description": str(raw_meta.get("description") or ""),
        "location": str(raw_meta.get("location") or ""),
        "start_kp": str(raw_meta.get("start_kp") or ""),
        "end_kp": str(raw_meta.get("end_kp") or ""),
        "test_date": str(raw_meta.get("test_date") or ""),
        "test_type": str(raw_meta.get("test_type") or ""),
        "notes": str(raw_meta.get("notes") or ""),
    }
    return {
        "id": session.id,
        "project_id": session.project_id,
        "name": session.name,
        "status": session.status,
        "revision": session.revision,
        "updated_at": iso_z(session.updated_at),
        "created_at": iso_z(session.created_at),
        "result_summary": summary,
        "section_meta": section_meta,
        "forms_summary": raw_inputs.get("forms_summary"),
    }


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def get_session(
    db: OrmSession,
    session_id: str,
    workspace_hash: str,
    *,
    include_deleted: bool = False,
) -> HydroSession:
    session = db.get(HydroSession, session_id)
    if (
        session is None
        or session.workspace_id_hash != workspace_hash
        or (session.deleted_at is not None and not include_deleted)
    ):
        raise not_found("session", session_id)
    return session


def _validate_project(db: OrmSession, project_id: str | None, workspace_hash: str) -> None:
    if project_id is None:
        return
    project = db.get(Project, project_id)
    if (
        project is None
        or project.workspace_id_hash != workspace_hash
        or project.deleted_at is not None
    ):
        raise not_found("project", project_id)


def _next_name(db: OrmSession, workspace_hash: str) -> str:
    count = db.scalar(
        select(func.count(HydroSession.id)).where(
            HydroSession.workspace_id_hash == workspace_hash,
            HydroSession.deleted_at.is_(None),
        )
    )
    return f"Oturum {(count or 0) + 1}"


def _apply_project_defaults(
    normalized: dict[str, Any],
    project: Project | None,
    *,
    raw_inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if project is None or not isinstance(getattr(project, "defaults", None), dict):
        return normalized
    defaults = project.defaults
    if not defaults:
        return normalized

    raw = raw_inputs if isinstance(raw_inputs, dict) else {}
    geom = normalized.setdefault("geometry", {})
    for key in ("outside_diameter_mm", "wall_thickness_mm"):
        if geom.get(key) is None and as_float(defaults.get(key)) is not None:
            geom[key] = float(defaults[key])

    catalog = normalized.setdefault("geometry_catalog", {})
    for key in ("size_option", "schedule_option"):
        if not str(catalog.get(key) or "").strip() and defaults.get(key):
            catalog[key] = str(defaults[key]).strip()

    profile = normalized.setdefault("section_profile", {})
    for key in ("smys_mpa", "design_pressure_bar"):
        if profile.get(key) is None and as_float(defaults.get(key)) is not None:
            profile[key] = float(defaults[key])

    if not str(normalized.get("material_grade") or "").strip() and defaults.get("material_grade"):
        normalized["material_grade"] = str(defaults["material_grade"]).strip()

    if not str(normalized.get("pump_location") or "").strip() and defaults.get("pump_location"):
        normalized["pump_location"] = str(defaults["pump_location"]).strip()

    raw_loc = str(raw.get("location_class") or "").strip()
    if not raw_loc and defaults.get("location_class"):
        normalized["location_class"] = str(defaults["location_class"]).strip()

    raw_air_val = raw.get("air")
    raw_air: dict[str, Any] = raw_air_val if isinstance(raw_air_val, dict) else {}
    if raw_air.get("k_factor") is None and as_float(defaults.get("k_factor")) is not None:
        normalized.setdefault("air", {})["k_factor"] = float(defaults["k_factor"])

    raw_helper_val = raw.get("helper")
    raw_helper: dict[str, Any] = raw_helper_val if isinstance(raw_helper_val, dict) else {}
    if (
        raw_helper.get("steel_alpha_micro_per_c") is None
        and as_float(defaults.get("steel_alpha_micro_per_c")) is not None
    ):
        normalized.setdefault("helper", {})["steel_alpha_micro_per_c"] = float(
            defaults["steel_alpha_micro_per_c"]
        )
    return normalized


def create_session(
    db: OrmSession,
    *,
    workspace_hash: str,
    name: str | None = None,
    project_id: str | None = None,
    inputs: dict[str, Any] | None = None,
    wizard_state: dict[str, Any] | None = None,
    commit: bool = True,
) -> HydroSession:
    _validate_project(db, project_id, workspace_hash)
    project = db.get(Project, project_id) if project_id is not None else None
    merged_inputs = _apply_project_defaults(
        normalize_inputs(inputs),
        project,
        raw_inputs=inputs,
    )
    session = HydroSession(
        id=new_uuid(),
        workspace_id_hash=workspace_hash,
        project_id=project_id,
        name=(name or "").strip() or _next_name(db, workspace_hash),
        status="draft",
        inputs=merged_inputs,
        wizard_state=wizard_state,
        result_summary={},
        revision=1,
        notes="",
    )
    db.add(session)
    db.flush()
    if project_id is not None:
        from . import dossier as dossier_service

        dossier_service.ensure_section_form_slots(db, session, commit=False)
    audit.record(
        db,
        action="session.create",
        entity_type="session",
        entity_id=session.id,
        session_id=session.id,
        workspace_hash=workspace_hash,
        after={"name": session.name},
    )
    if commit:
        db.commit()
        db.refresh(session)
    return session


def list_sessions(
    db: OrmSession,
    *,
    workspace_hash: str,
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    q: str | None = None,
    project_id: str | None = None,
    include_deleted: bool = False,
) -> dict[str, Any]:
    conditions = [HydroSession.workspace_id_hash == workspace_hash]
    if not include_deleted:
        conditions.append(HydroSession.deleted_at.is_(None))
    if status:
        conditions.append(HydroSession.status == status)
    if project_id:
        conditions.append(HydroSession.project_id == project_id)
    if q:
        conditions.append(HydroSession.name.ilike(f"%{q.strip()}%"))

    total = db.scalar(select(func.count(HydroSession.id)).where(*conditions)) or 0
    rows = (
        db.execute(
            select(HydroSession)
            .where(*conditions)
            .order_by(HydroSession.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return {
        "items": [session_brief(row) for row in rows],
        "total": int(total),
        "limit": limit,
        "offset": offset,
    }


_CONFLICT_SCALAR_KEYS = (
    "water_backend",
    "material_grade",
    "location_class",
    "pump_location",
    "active_tab",
)

_CONFLICT_DICT_SECTIONS = (
    "section_meta",
    "geometry",
    "geometry_catalog",
    "section_profile",
    "air",
    "pressure",
    "field",
    "helper",
    "modes",
    "checks",
    "report",
)

_CONFLICT_LIST_SECTIONS = (
    "segments",
    "profile_points",
    "landmarks",
    "equipment",
)


def _prepare_updated_inputs(
    current_inputs: dict[str, Any],
    raw_patch: dict[str, Any],
    *,
    replace_inputs: bool = False,
) -> dict[str, Any]:
    if replace_inputs:
        return normalize_inputs(raw_patch)
    patch = dict(raw_patch)
    patch_air = patch.get("air")
    patch_field = patch.get("field")
    if isinstance(patch_air, dict) and "ambient_temperature_c" in patch_air:
        if not (isinstance(patch_field, dict) and "ambient_temperature_c" in patch_field):
            patch["field"] = {
                **(dict(patch_field) if isinstance(patch_field, dict) else {}),
                "ambient_temperature_c": patch_air["ambient_temperature_c"],
            }
    elif isinstance(patch_field, dict) and "ambient_temperature_c" in patch_field:
        patch["air"] = {
            **(dict(patch_air) if isinstance(patch_air, dict) else {}),
            "ambient_temperature_c": patch_field["ambient_temperature_c"],
        }
    return normalize_inputs(deep_merge(current_inputs or {}, patch))


def _strip_segment_ids(items: list[Any]) -> list[Any]:
    cleaned: list[Any] = []
    for item in items:
        if isinstance(item, dict):
            cleaned.append(
                {
                    "outside_diameter_mm": item.get("outside_diameter_mm"),
                    "wall_thickness_mm": item.get("wall_thickness_mm"),
                    "length_m": item.get("length_m"),
                    "nps_label": item.get("nps_label") or "",
                    "schedule_label": item.get("schedule_label") or "",
                    "start_station_m": item.get("start_station_m"),
                }
            )
        else:
            cleaned.append(item)
    return cleaned


def _values_equal(a: Any, b: Any) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(a) == float(b)
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False
        return all(_values_equal(x, y) for x, y in zip(a, b, strict=True))
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a.keys()) != set(b.keys()):
            return False
        return all(_values_equal(a[k], b[k]) for k in a)
    return bool(a == b)


def _build_conflict_diff(
    session: HydroSession,
    changes: dict[str, Any],
    *,
    replace_inputs: bool = False,
) -> list[dict[str, Any]]:
    diff: list[dict[str, Any]] = []
    if "name" in changes and changes["name"] is not None:
        incoming_name = str(changes["name"]).strip() or session.name
        if incoming_name != session.name:
            diff.append({"path": "name", "incoming": incoming_name, "server": session.name})
    if "status" in changes and changes["status"] is not None:
        incoming_status = str(changes["status"])
        if incoming_status != session.status:
            diff.append({"path": "status", "incoming": incoming_status, "server": session.status})
    if "project_id" in changes and changes["project_id"] != session.project_id:
        diff.append(
            {
                "path": "project_id",
                "incoming": changes["project_id"],
                "server": session.project_id,
            }
        )
    if "notes" in changes and changes["notes"] is not None:
        incoming_notes = str(changes["notes"])
        server_notes = session.notes or ""
        if incoming_notes != server_notes:
            diff.append({"path": "notes", "incoming": incoming_notes, "server": server_notes})

    raw_patch = changes.get("inputs")
    if isinstance(raw_patch, dict):
        server_inputs = normalize_inputs(session.inputs or {})
        incoming_inputs = _prepare_updated_inputs(
            session.inputs or {},
            raw_patch,
            replace_inputs=replace_inputs,
        )
        for key in _CONFLICT_SCALAR_KEYS:
            inc_val = incoming_inputs.get(key)
            srv_val = server_inputs.get(key)
            if not _values_equal(inc_val, srv_val):
                diff.append({"path": key, "incoming": inc_val, "server": srv_val})
        for section in _CONFLICT_DICT_SECTIONS:
            raw_inc_sec = incoming_inputs.get(section)
            raw_srv_sec = server_inputs.get(section)
            inc_sec: dict[str, Any] = raw_inc_sec if isinstance(raw_inc_sec, dict) else {}
            srv_sec: dict[str, Any] = raw_srv_sec if isinstance(raw_srv_sec, dict) else {}
            all_keys = list(dict.fromkeys([*srv_sec.keys(), *inc_sec.keys()]))
            for field_key in all_keys:
                if section == "air" and field_key == "ambient_temperature_c":
                    continue
                inc_val = inc_sec.get(field_key)
                srv_val = srv_sec.get(field_key)
                if not _values_equal(inc_val, srv_val):
                    diff.append(
                        {"path": f"{section}.{field_key}", "incoming": inc_val, "server": srv_val}
                    )
        for section in _CONFLICT_LIST_SECTIONS:
            raw_inc_list = incoming_inputs.get(section)
            raw_srv_list = server_inputs.get(section)
            inc_list: list[Any] = raw_inc_list if isinstance(raw_inc_list, list) else []
            srv_list: list[Any] = raw_srv_list if isinstance(raw_srv_list, list) else []
            cmp_inc = _strip_segment_ids(inc_list) if section == "segments" else inc_list
            cmp_srv = _strip_segment_ids(srv_list) if section == "segments" else srv_list
            if not _values_equal(cmp_inc, cmp_srv):
                diff.append({"path": section, "incoming": inc_list, "server": srv_list})
    return diff


def update_session(
    db: OrmSession,
    session: HydroSession,
    *,
    changes: dict[str, Any],
    expected_revision: int | None = None,
    replace_inputs: bool = False,
    commit: bool = True,
) -> HydroSession:
    if expected_revision is not None and expected_revision != session.revision:
        raise AppError(
            "revision_conflict",
            "Oturum baska bir istemci tarafindan guncellendi.",
            status_code=409,
            details={
                "expected_revision": expected_revision,
                "current_revision": session.revision,
                "current": json_safe(serialize_session(session)),
                "diff": json_safe(
                    _build_conflict_diff(session, changes, replace_inputs=replace_inputs)
                ),
            },
        )

    before = {
        "name": session.name,
        "status": session.status,
        "revision": session.revision,
    }

    if "name" in changes and changes["name"] is not None:
        session.name = str(changes["name"]).strip() or session.name
    if "status" in changes and changes["status"] is not None:
        session.status = str(changes["status"])
    if "project_id" in changes:
        _validate_project(db, changes["project_id"], session.workspace_id_hash)
        session.project_id = changes["project_id"]
    if "notes" in changes and changes["notes"] is not None:
        session.notes = str(changes["notes"])
    if "inputs" in changes and changes["inputs"] is not None:
        raw_patch = changes["inputs"]
        if not isinstance(raw_patch, dict):
            raise AppError("validation_error", "inputs bir nesne olmalidir.", status_code=422)
        session.inputs = _prepare_updated_inputs(
            session.inputs or {},
            raw_patch,
            replace_inputs=replace_inputs,
        )
    if "wizard_state" in changes:
        session.wizard_state = changes["wizard_state"]

    session.revision = int(session.revision or 1) + 1
    session.updated_at = utcnow()
    audit.record(
        db,
        action="session.update",
        entity_type="session",
        entity_id=session.id,
        session_id=session.id,
        workspace_hash=session.workspace_id_hash,
        before=before,
        after={"name": session.name, "status": session.status, "revision": session.revision},
    )
    if commit:
        db.commit()
        db.refresh(session)
    else:
        db.flush()
    return session


def _unlink_stored_attachments(
    db: OrmSession,
    stored_paths: list[str],
    uploads_dir: Path | None,
) -> None:
    if uploads_dir is None or not stored_paths:
        return
    for rel_path in stored_paths:
        if not rel_path:
            continue
        still_referenced = db.scalar(
            select(func.count(Attachment.id)).where(Attachment.stored_path == rel_path)
        )
        if still_referenced:
            continue
        try:
            target = resolve_stored_path(uploads_dir, rel_path)
            target.unlink(missing_ok=True)
        except AppError:
            pass


def delete_session(
    db: OrmSession,
    session: HydroSession,
    *,
    hard: bool = False,
    uploads_dir: Path | None = None,
) -> None:
    stored_paths: list[str] = []
    if hard:
        attachments = (
            db.execute(select(Attachment).where(Attachment.session_id == session.id))
            .scalars()
            .all()
        )
        attachment_ids = [att.id for att in attachments]
        stored_paths = [att.stored_path for att in attachments if att.stored_path]
        if attachment_ids:
            analyses = (
                db.execute(select(OcrAnalysis).where(OcrAnalysis.attachment_id.in_(attachment_ids)))
                .scalars()
                .all()
            )
            for item in analyses:
                db.delete(item)
            for att in attachments:
                db.delete(att)
        db.delete(session)
    else:
        session.deleted_at = utcnow()
        session.updated_at = utcnow()
        session.revision = int(session.revision or 1) + 1
    audit.record(
        db,
        action="session.delete",
        entity_type="session",
        entity_id=session.id,
        session_id=session.id,
        workspace_hash=session.workspace_id_hash,
        after={"hard": hard},
    )
    db.commit()
    if hard:
        _unlink_stored_attachments(db, stored_paths, uploads_dir)


def duplicate_session(
    db: OrmSession,
    session: HydroSession,
    *,
    name: str | None = None,
) -> HydroSession:
    clone = HydroSession(
        id=new_uuid(),
        workspace_id_hash=session.workspace_id_hash,
        project_id=session.project_id,
        name=(name or "").strip() or f"{session.name} (kopya)",
        status="draft",
        inputs=copy.deepcopy(session.inputs or {}),
        wizard_state=copy.deepcopy(session.wizard_state),
        result_summary={},
        revision=1,
        notes=session.notes,
    )
    db.add(clone)
    db.flush()
    audit.record(
        db,
        action="session.duplicate",
        entity_type="session",
        entity_id=clone.id,
        session_id=clone.id,
        workspace_hash=session.workspace_id_hash,
        after={"source_session_id": session.id, "name": clone.name},
    )
    db.commit()
    db.refresh(clone)
    return clone


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


def _result_payload(row: TestResult) -> dict[str, Any]:
    decision = row.decision or {
        "status": row.decision_status,
        "title": row.decision_title,
        "summary": row.decision_summary,
        "rule": row.decision_rule,
        "margin": None,
    }
    return {
        "id": row.id,
        "test_type": row.test_type,
        "inputs": row.inputs or {},
        "result": row.result or {},
        "decision": decision,
        "computed_at": iso_z(row.computed_at),
        "created_at": iso_z(row.created_at),
        "engine_version": row.engine_version,
    }


def list_results(
    db: OrmSession,
    session: HydroSession,
    *,
    test_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    conditions = [TestResult.session_id == session.id]
    if test_type:
        conditions.append(TestResult.test_type == test_type)
    total = db.scalar(select(func.count(TestResult.id)).where(*conditions)) or 0
    rows = (
        db.execute(
            select(TestResult)
            .where(*conditions)
            .order_by(TestResult.computed_at.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return {
        "items": [_result_payload(row) for row in rows],
        "total": int(total),
        "limit": limit,
        "offset": offset,
    }


def create_result(
    db: OrmSession,
    session: HydroSession,
    *,
    test_type: str,
    payload: dict[str, Any],
    expected_revision: int | None = None,
    commit: bool = True,
) -> dict[str, Any]:
    if expected_revision is not None and expected_revision != session.revision:
        raise AppError(
            "revision_conflict",
            "Oturum baska bir istemci tarafindan guncellendi.",
            status_code=409,
            details={
                "expected_revision": expected_revision,
                "current_revision": session.revision,
                "current": json_safe(serialize_session(session)),
                "diff": [],
            },
        )
    from .calculations import evaluate_test

    result, decision = evaluate_test(test_type, payload)
    now = utcnow()
    row = TestResult(
        id=new_uuid(),
        session_id=session.id,
        test_type=test_type,
        inputs={"payload": payload, "session_snapshot": copy.deepcopy(session.inputs or {})},
        result=json_safe(result),
        decision_status=str(decision.get("status", "BEKLIYOR")),
        decision_title=str(decision.get("title", "")),
        decision_summary=str(decision.get("summary", "")),
        decision_rule=str(decision.get("rule", "")),
        decision=json_safe(decision),
        engine_version=ENGINE_VERSION,
        computed_at=now,
    )
    db.add(row)
    db.flush()

    summary = dict(session.result_summary or {})
    summary[test_type] = {
        "status": decision.get("status", "BEKLIYOR"),
        "computed_at": iso_z(now),
    }
    summary["last_computed_at"] = iso_z(now)
    session.result_summary = summary
    if session.status == "draft":
        session.status = "active"
    # ``revision`` belongs to explicit session writes (PUT); result creation
    # updates the summary/status but must not invalidate the client's ETag.
    session.updated_at = now

    if commit and test_type in {"depressurization", "discharge"}:
        from . import dossier as dossier_service

        dossier_service.sync_operation_result_to_dewatering_form(
            db, session, test_type=test_type, payload=payload
        )

    audit.record(
        db,
        action="result.create",
        entity_type="test_result",
        entity_id=row.id,
        session_id=session.id,
        workspace_hash=session.workspace_id_hash,
        after={"test_type": test_type, "decision_status": row.decision_status},
    )
    if commit:
        db.commit()
        db.refresh(row)
    return {
        "id": row.id,
        "test_type": row.test_type,
        "result": row.result,
        "decision": row.decision,
        "computed_at": iso_z(row.computed_at),
        "session_revision": session.revision,
    }


# ---------------------------------------------------------------------------
# Time series
# ---------------------------------------------------------------------------


def _record_payload(row: TimeSeriesRecord) -> dict[str, Any]:
    return {
        "id": row.id,
        "timestamp": iso_z(row.timestamp),
        "pressure_bar": row.pressure_bar,
        "temperature_c": row.temperature_c,
        "volume_m3": row.volume_m3,
        "notes": row.notes,
        "source": row.source,
    }


def _ordered_records(
    db: OrmSession,
    session: HydroSession,
    *,
    limit: int | None = None,
    offset: int = 0,
    from_ts: Any = None,
    to_ts: Any = None,
) -> tuple[list[TimeSeriesRecord], int]:
    conditions = [TimeSeriesRecord.session_id == session.id]
    if from_ts is not None:
        conditions.append(TimeSeriesRecord.timestamp >= from_ts)
    if to_ts is not None:
        conditions.append(TimeSeriesRecord.timestamp <= to_ts)
    total = db.scalar(select(func.count(TimeSeriesRecord.id)).where(*conditions)) or 0
    query = (
        select(TimeSeriesRecord)
        .where(*conditions)
        .order_by(TimeSeriesRecord.timestamp.asc())
        .offset(offset)
    )
    if limit is not None:
        query = query.limit(limit)
    rows = db.execute(query).scalars().all()
    return list(rows), int(total)


def get_ordered_time_series(db: OrmSession, session: HydroSession) -> list[TimeSeriesRecord]:
    rows, _ = _ordered_records(db, session)
    return rows


def time_series_summary(rows: Iterable[TimeSeriesRecord]) -> dict[str, Any]:
    from hidrostatik_test.domain.time_series import TimeSeriesRecord as DomainTimeSeriesRecord
    from hidrostatik_test.domain.time_series import evaluate_time_series

    from .calculations import format_time_series_evaluation

    ordered = sorted(rows, key=lambda r: ensure_utc(r.timestamp) or utcnow())
    domain_records = [
        DomainTimeSeriesRecord(
            timestamp=ensure_utc(row.timestamp) or utcnow(),
            pressure_bar=float(row.pressure_bar),
            temperature_c=float(row.temperature_c),
            volume_m3=row.volume_m3,
            notes=row.notes or "",
        )
        for row in ordered
    ]
    evaluation = evaluate_time_series(domain_records)
    return format_time_series_evaluation(evaluation)


def list_time_series(
    db: OrmSession,
    session: HydroSession,
    *,
    limit: int = 1000,
    offset: int = 0,
    from_ts: Any = None,
    to_ts: Any = None,
) -> dict[str, Any]:
    rows, total = _ordered_records(
        db,
        session,
        limit=limit,
        offset=offset,
        from_ts=ensure_utc(from_ts),
        to_ts=ensure_utc(to_ts),
    )
    return {
        "items": [_record_payload(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def add_time_series(
    db: OrmSession,
    session: HydroSession,
    *,
    timestamp: Any,
    pressure_bar: float,
    temperature_c: float,
    volume_m3: float | None,
    notes: str = "",
    source: str = "manual",
) -> dict[str, Any]:
    row = TimeSeriesRecord(
        id=new_uuid(),
        session_id=session.id,
        timestamp=ensure_utc(timestamp) or utcnow(),
        pressure_bar=pressure_bar,
        temperature_c=temperature_c,
        volume_m3=volume_m3,
        notes=notes or "",
        source=(source or "manual")[:16],
    )
    db.add(row)
    session.updated_at = utcnow()
    audit.record(
        db,
        action="time_series.create",
        entity_type="time_series",
        entity_id=row.id,
        session_id=session.id,
        workspace_hash=session.workspace_id_hash,
    )
    db.commit()
    db.refresh(row)
    rows, _ = _ordered_records(db, session)
    return {"record": _record_payload(row), "summary": time_series_summary(rows)}


def batch_add_time_series(
    db: OrmSession,
    session: HydroSession,
    *,
    records: Iterable[Any],
    mode: str = "append",
    default_source: str | None = None,
    commit: bool = True,
) -> dict[str, Any]:
    if mode == "replace":
        db.execute(delete(TimeSeriesRecord).where(TimeSeriesRecord.session_id == session.id))
        db.flush()

    now = utcnow()
    new_rows: list[TimeSeriesRecord] = []
    for item in records:
        if isinstance(item, dict):
            ts_raw = item.get("timestamp")
            p_val = float(item["pressure_bar"])
            t_val = float(item["temperature_c"])
            v_val = item.get("volume_m3")
            notes_val = str(item.get("notes") or "")
            src_raw = default_source or str(item.get("source") or "manual")
        else:
            ts_raw = getattr(item, "timestamp", None)
            p_val = float(item.pressure_bar)
            t_val = float(item.temperature_c)
            v_val = item.volume_m3
            notes_val = str(getattr(item, "notes", "") or "")
            src_raw = default_source or str(getattr(item, "source", "manual") or "manual")

        row = TimeSeriesRecord(
            id=new_uuid(),
            session_id=session.id,
            timestamp=ensure_utc(ts_raw) or now,
            pressure_bar=p_val,
            temperature_c=t_val,
            volume_m3=v_val,
            notes=notes_val,
            source=(src_raw or "manual")[:16],
        )
        db.add(row)
        new_rows.append(row)

    session.updated_at = now
    audit.record(
        db,
        action="time_series.batch",
        entity_type="session",
        entity_id=session.id,
        session_id=session.id,
        workspace_hash=session.workspace_id_hash,
        after={"mode": mode, "inserted": len(new_rows)},
    )
    if commit:
        db.commit()
    else:
        db.flush()

    rows, _ = _ordered_records(db, session)
    return {
        "inserted": len(new_rows),
        "total": len(rows),
        "items": [_record_payload(row) for row in rows],
        "summary": time_series_summary(rows),
    }


def clear_time_series(db: OrmSession, session: HydroSession) -> dict[str, Any]:
    existing_count = (
        db.scalar(
            select(func.count(TimeSeriesRecord.id)).where(TimeSeriesRecord.session_id == session.id)
        )
        or 0
    )
    if existing_count:
        db.execute(delete(TimeSeriesRecord).where(TimeSeriesRecord.session_id == session.id))
    session.updated_at = utcnow()
    audit.record(
        db,
        action="time_series.clear",
        entity_type="session",
        entity_id=session.id,
        session_id=session.id,
        workspace_hash=session.workspace_id_hash,
        after={"deleted": int(existing_count)},
    )
    db.commit()
    return {"deleted": int(existing_count), "summary": time_series_summary([])}


def delete_time_series(db: OrmSession, session: HydroSession, record_id: str) -> None:
    row = db.get(TimeSeriesRecord, record_id)
    if row is None or row.session_id != session.id:
        raise not_found("time_series", record_id)
    db.delete(row)
    session.updated_at = utcnow()
    audit.record(
        db,
        action="time_series.delete",
        entity_type="time_series",
        entity_id=record_id,
        session_id=session.id,
        workspace_hash=session.workspace_id_hash,
    )
    db.commit()


# ---------------------------------------------------------------------------
# Summary / audit / stats
# ---------------------------------------------------------------------------


def _sections_from_inputs(inputs: dict[str, Any]) -> list[Any]:
    """Build request sections from session inputs (segments win)."""

    from .. import schemas

    segments = inputs.get("segments") or []
    if isinstance(segments, list) and segments:
        rows = []
        for item in segments:
            if not isinstance(item, dict):
                continue
            od = as_float(item.get("outside_diameter_mm"))
            wt = as_float(item.get("wall_thickness_mm"))
            length = as_float(item.get("length_m"))
            if od is None or wt is None or length is None:
                continue
            rows.append(
                schemas.PipeSectionIn(
                    outside_diameter_mm=od,
                    wall_thickness_mm=wt,
                    length_m=length,
                    nps_label=item.get("nps_label"),
                    schedule_label=item.get("schedule_label"),
                    start_station_m=as_float(item.get("start_station_m")),
                )
            )
        if rows:
            return rows
    geometry = inputs.get("geometry") or {}
    od = as_float(geometry.get("outside_diameter_mm"))
    wt = as_float(geometry.get("wall_thickness_mm"))
    length = as_float(geometry.get("length_m"))
    if od is None or wt is None or length is None:
        return []
    return [schemas.PipeSectionIn(outside_diameter_mm=od, wall_thickness_mm=wt, length_m=length)]


def profile_summary(inputs: dict[str, Any]) -> dict[str, Any] | None:
    from .. import schemas
    from .calculations import calculate_pressure_profile

    try:
        sections = _sections_from_inputs(inputs)
        profile = inputs.get("section_profile") or {}
        if not sections:
            return None
        design = as_float(profile.get("design_pressure_bar"))
        smys = as_float(profile.get("smys_mpa"))
        highest = as_float(profile.get("highest_elevation_m"))
        lowest = as_float(profile.get("lowest_elevation_m"))
        start = as_float(profile.get("start_elevation_m"))
        end = as_float(profile.get("end_elevation_m"))
        location_class = (inputs.get("location_class") or "").strip()
        pump_location = (inputs.get("pump_location") or "").strip()
        if (
            design is None
            or smys is None
            or highest is None
            or lowest is None
            or start is None
            or end is None
        ):
            return None
        if not location_class or not pump_location:
            return None
        air = inputs.get("air") or {}
        pressure = inputs.get("pressure") or {}
        field = inputs.get("field") or {}
        monitored = as_float(field.get("monitored_pressure_bar"))
        if monitored is None:
            monitored = as_float(pressure.get("pressure_bar"))
        if monitored is None:
            monitored = as_float(air.get("pressure_bar"))
        request = schemas.PressureProfileRequest(
            geometry=schemas.GeometryIn(sections=sections),
            design_pressure_bar=design,
            smys_mpa=smys,
            location_class=location_class,
            highest_elevation_m=highest,
            lowest_elevation_m=lowest,
            start_elevation_m=start,
            end_elevation_m=end,
            pump_location=pump_location,
            monitored_pressure_bar=monitored,
        )
        result = calculate_pressure_profile(request)
        window = result["selected_window"]
        return {
            "feasible": result["feasible"],
            "window": {
                "min_bar": window["minimum_required_pressure_bar"],
                "max_bar": window["maximum_allowable_pressure_bar"],
            },
            "decision": result["decision"],
        }
    except Exception:
        return None


def session_summary(db: OrmSession, session: HydroSession) -> dict[str, Any]:
    from ..desktop_labels import FIELD_CHECKS

    inputs = session.inputs or {}
    rows = (
        db.execute(
            select(TestResult)
            .where(TestResult.session_id == session.id)
            .order_by(TestResult.computed_at.asc())
        )
        .scalars()
        .all()
    )
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        bucket = grouped.setdefault(
            row.test_type, {"status": row.decision_status, "count": 0, "computed_at": None}
        )
        bucket["count"] += 1
        bucket["status"] = row.decision_status
        bucket["computed_at"] = iso_z(row.computed_at)

    tests: dict[str, Any] = {
        name: {
            "status": grouped.get(name, {}).get("status", "BEKLIYOR"),
            "count": grouped.get(name, {}).get("count", 0),
        }
        for name in (
            "air",
            "pressure",
            "profile",
            "pig",
            "pressurization",
            "thermal_balance",
            "pressurization_ramp",
            "pressure_hold",
            "depressurization",
            "discharge",
            "coefficient_a",
            "coefficient_b",
        )
    }

    checks = inputs.get("checks") or {}
    total_checks = len(FIELD_CHECKS)
    checked = sum(1 for item in FIELD_CHECKS if bool(checks.get(item[0])))
    coefficients = inputs.get("coefficients") or {}

    profile = profile_summary(inputs)
    ts_rows = get_ordered_time_series(db, session)
    ts_summary = time_series_summary(ts_rows)

    scene_info = None
    try:
        from .scene import build_scene

        scene = build_scene(inputs)
        scene_info = {
            "segment_count": len(scene["segments"]),
            "total_length_m": scene["extent"]["station_end_m"],
            "volume_m3": scene.get("totals", {}).get("internal_volume_m3", 0.0),
            "approximate_profile": any(
                "yaklasik" in warning.lower() for warning in scene.get("warnings", [])
            ),
        }
    except Exception:
        scene_info = None

    last = max((row.computed_at for row in rows), default=None) if rows else None

    return {
        "session_id": session.id,
        "status": session.status,
        "tests": tests,
        "checklist": {
            "checked": checked,
            "total": total_checks,
            "progress": (checked / total_checks) if total_checks else 0.0,
        },
        "coefficients": {
            "air_a": (coefficients.get("air_a") or {}).get("state", "empty"),
            "pressure_a": (coefficients.get("pressure_a") or {}).get("state", "empty"),
            "pressure_b": (coefficients.get("pressure_b") or {}).get("state", "empty"),
        },
        "profile": profile,
        "scene": scene_info,
        "time_series": ts_summary,
        "last_computed_at": iso_z(last),
    }


def list_audit(
    db: OrmSession,
    session: HydroSession,
    *,
    limit: int = 50,
    offset: int = 0,
    action: str | None = None,
) -> dict[str, Any]:
    from ..models import AuditEvent

    conditions = [AuditEvent.session_id == session.id]
    if action:
        conditions.append(AuditEvent.action == action)
    total = db.scalar(select(func.count(AuditEvent.id)).where(*conditions)) or 0
    rows = (
        db.execute(
            select(AuditEvent)
            .where(*conditions)
            .order_by(AuditEvent.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return {
        "items": [audit.user_payload(row) for row in rows],
        "total": int(total),
        "limit": limit,
        "offset": offset,
    }


def stats(db: OrmSession, workspace_hash: str) -> dict[str, Any]:
    from ..models import OcrAnalysis

    session_ids = select(HydroSession.id).where(
        HydroSession.workspace_id_hash == workspace_hash,
        HydroSession.deleted_at.is_(None),
    )
    total_sessions = (
        db.scalar(
            select(func.count(HydroSession.id)).where(
                HydroSession.workspace_id_hash == workspace_hash,
                HydroSession.deleted_at.is_(None),
            )
        )
        or 0
    )
    total_tests = (
        db.scalar(select(func.count(TestResult.id)).where(TestResult.session_id.in_(session_ids)))
        or 0
    )
    ts_count = (
        db.scalar(
            select(func.count(TimeSeriesRecord.id)).where(
                TimeSeriesRecord.session_id.in_(session_ids)
            )
        )
        or 0
    )

    by_status: dict[str, int] = {}
    for status, count in db.execute(
        select(TestResult.decision_status, func.count(TestResult.id))
        .where(TestResult.session_id.in_(session_ids))
        .group_by(TestResult.decision_status)
    ).all():
        by_status[str(status)] = int(count)

    by_type: dict[str, int] = {}
    for test_type, count in db.execute(
        select(TestResult.test_type, func.count(TestResult.id))
        .where(TestResult.session_id.in_(session_ids))
        .group_by(TestResult.test_type)
    ).all():
        by_type[str(test_type)] = int(count)

    ocr_counts = {"queued": 0, "running": 0, "succeeded": 0, "failed": 0}
    for status, count in db.execute(
        select(OcrAnalysis.status, func.count(OcrAnalysis.id))
        .where(OcrAnalysis.workspace_id_hash == workspace_hash)
        .group_by(OcrAnalysis.status)
    ).all():
        if status in ocr_counts:
            ocr_counts[str(status)] = int(count)

    return {
        "total_sessions": int(total_sessions),
        "total_tests": int(total_tests),
        "time_series_records": int(ts_count),
        "by_status": by_status,
        "by_type": by_type,
        "ocr": ocr_counts,
    }


__all__ = [
    "ENGINE_VERSION",
    "add_time_series",
    "batch_add_time_series",
    "clear_time_series",
    "create_result",
    "create_session",
    "default_inputs",
    "delete_session",
    "delete_time_series",
    "duplicate_session",
    "get_ordered_time_series",
    "get_session",
    "list_audit",
    "list_results",
    "list_sessions",
    "list_time_series",
    "normalize_inputs",
    "profile_summary",
    "serialize_session",
    "session_brief",
    "session_summary",
    "stats",
    "time_series_summary",
    "update_session",
]
