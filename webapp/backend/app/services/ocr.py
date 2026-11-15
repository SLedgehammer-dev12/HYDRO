"""OCR orchestration (upload -> analyze -> approve -> apply)."""

from __future__ import annotations

import copy
import importlib
import importlib.util
import json
import os
from typing import Any, BinaryIO, Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from hidrostatik_test.services.report_ocr import (
    MAX_FILE_SIZE_BYTES,
    MAX_OCR_PAGES,
    MAX_PDF_PAGES,
    SUPPORTED_EXTENSIONS,
    OcrAnalysisResult,
    ReportOcrError,
    analyze_report,
    ocr_available,
    ocr_status,
)

from ..core.config import Settings
from ..core.errors import AppError, not_found
from ..core.timeutil import as_float, iso_z, json_safe, utcnow
from ..models import (
    Attachment,
    OcrAnalysis,
    OcrMappingProfile,
    new_uuid,
)
from . import audit
from . import sessions as session_service
from .storage import StoredUpload, store_upload

LOW_CONFIDENCE = 0.6
CRITICAL_CONFIDENCE = 0.4
AUTO_FILL = 0.85

_ERROR_STATUS = {
    "file_not_found": 404,
    "invalid_path": 400,
    "file_too_large": 413,
    "unsupported_format": 415,
    "empty_file": 422,
    "empty_text": 422,
    "encrypted_pdf": 422,
    "corrupt_document": 422,
    "corrupt_image": 422,
    "invalid_calculated": 400,
    "ocr_unavailable": 503,
    "dependency_missing": 503,
    "ocr_timeout": 504,
}

#: Canonical OCR field -> session input paths.
FIELD_TARGETS: dict[str, tuple[str, ...]] = {
    "pipe_od_mm": ("geometry.outside_diameter_mm",),
    "wall_mm": ("geometry.wall_thickness_mm",),
    "length_m": ("geometry.length_m",),
    "test_pressure_bar": ("air.pressure_bar", "pressure.pressure_bar"),
    "air_test.vpa": ("air.actual_added_water_m3",),
    "air_test.a": ("air.a_micro_per_bar",),
    "pressure_test.a": ("pressure.a_micro_per_bar",),
    "pressure_test.b": ("pressure.b_micro_per_c",),
    "pressure_test.delta_t": ("pressure.delta_t_c",),
    "pressure_test.pa": ("pressure.actual_pressure_change_bar",),
    "pressure_test.t_initial": ("pressure.t_initial_c",),
    "pressure_test.t_final": ("pressure.t_final_c",),
    "report_no": ("report_meta.report_no",),
    "date": ("report_meta.date",),
    "operator": ("report_meta.operator",),
    "section_id": ("report_meta.section_id",),
    "notes": ("report_meta.notes",),
}

_PASSTHROUGH_FIELDS = {"result"}
TEXT_TARGETS = {
    "report_meta.report_no",
    "report_meta.date",
    "report_meta.operator",
    "report_meta.section_id",
    "report_meta.notes",
}


def _http_error(exc: ReportOcrError, **details: Any) -> AppError:
    status = _ERROR_STATUS.get(exc.code, 422)
    payload: dict[str, Any] = {"ocr_code": exc.code}
    if exc.detail:
        payload["detail"] = exc.detail
    payload.update(details)
    return AppError(exc.code, exc.message, status_code=status, details=payload)


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def _engine_payload() -> dict[str, Any]:
    version = None
    languages: list[str] = []
    try:
        import pytesseract  # type: ignore

        version = str(pytesseract.get_tesseract_version())
        languages = sorted(pytesseract.get_languages(config=""))
    except Exception:
        version = None
    return {
        "name": "tesseract",
        "version": version,
        "languages": languages,
        "default_language": os.environ.get("HYDRO_OCR_LANG", "tur+eng"),
    }


def _rasterizer_payload() -> dict[str, Any]:
    for module, engine in (("fitz", "PyMuPDF"), ("pdf2image", "pdf2image")):
        if importlib.util.find_spec(module) is not None:
            return {"available": True, "engine": engine, "note": ""}
    return {
        "available": False,
        "engine": None,
        "note": "Taranmis PDF icin PyMuPDF veya pdf2image + Poppler gerekir.",
    }


def _queue_counts(db: OrmSession, workspace_hash: str) -> dict[str, int]:
    counts = {"queued": 0, "running": 0}
    rows = db.execute(
        select(OcrAnalysis.status, func.count(OcrAnalysis.id))
        .where(OcrAnalysis.workspace_id_hash == workspace_hash)
        .group_by(OcrAnalysis.status)
    ).all()
    for status, count in rows:
        if status in counts:
            counts[status] = int(count)
    return counts


def status_payload(db: OrmSession, workspace_hash: str) -> dict[str, Any]:
    profiles = (
        db.execute(
            select(OcrMappingProfile)
            .where(OcrMappingProfile.workspace_id_hash == workspace_hash)
            .order_by(OcrMappingProfile.created_at.desc())
        )
        .scalars()
        .all()
    )
    default_id = next((item.id for item in profiles if item.is_default), None)
    return {
        "available": ocr_available(),
        "status_text": ocr_status(),
        "engine": _engine_payload(),
        "pdf_rasterizer": _rasterizer_payload(),
        "limits": {
            "max_file_size_bytes": MAX_FILE_SIZE_BYTES,
            "max_pdf_pages": MAX_PDF_PAGES,
            "max_ocr_pages": MAX_OCR_PAGES,
            "supported_extensions": sorted(SUPPORTED_EXTENSIONS),
        },
        "queue": {**_queue_counts(db, workspace_hash), "max_concurrency": 1},
        "thresholds": {
            "auto_fill": AUTO_FILL,
            "low_confidence": LOW_CONFIDENCE,
            "critical_confidence": CRITICAL_CONFIDENCE,
            "human_review_required": True,
        },
        "mapping_profiles": {"default_id": default_id, "count": len(profiles)},
    }


# ---------------------------------------------------------------------------
# Analyze
# ---------------------------------------------------------------------------


def _get_profile(
    db: OrmSession, workspace_hash: str, profile_id: str | None
) -> OcrMappingProfile | None:
    if profile_id:
        profile = db.get(OcrMappingProfile, profile_id)
        if profile is None or profile.workspace_id_hash != workspace_hash:
            raise not_found("ocr_mapping_profile", profile_id)
        return profile
    return (
        db.execute(
            select(OcrMappingProfile).where(
                OcrMappingProfile.workspace_id_hash == workspace_hash,
                OcrMappingProfile.is_default.is_(True),
            )
        )
        .scalars()
        .first()
    )


def _parse_calculated(raw: str | None) -> dict[str, Any] | None:
    if raw is None or not str(raw).strip():
        return None
    try:
        value = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise AppError(
            "invalid_calculated",
            "Karsilastirma payload'i gecersiz JSON.",
            status_code=400,
            details={"reason": str(exc)},
        ) from exc
    if not isinstance(value, dict):
        raise AppError(
            "invalid_calculated",
            "Karsilastirma payload'i bir JSON nesnesi olmalidir.",
            status_code=400,
        )
    return value


def _existing_analysis(
    db: OrmSession,
    *,
    workspace_hash: str,
    session_id: str | None,
    sha256: str,
) -> OcrAnalysis | None:
    query = (
        select(OcrAnalysis)
        .join(Attachment, OcrAnalysis.attachment_id == Attachment.id)
        .where(
            Attachment.workspace_id_hash == workspace_hash,
            Attachment.sha256 == sha256,
            OcrAnalysis.status.in_(("queued", "running", "succeeded")),
        )
        .order_by(OcrAnalysis.created_at.desc())
    )
    if session_id is None:
        query = query.where(Attachment.session_id.is_(None))
    else:
        query = query.where(Attachment.session_id == session_id)
    return db.execute(query).scalars().first()


def analyze_upload(
    db: OrmSession,
    settings: Settings,
    workspace_hash: str,
    *,
    file_name: str | None,
    stream: BinaryIO,
    calculated_raw: str | None,
    session_id: str | None,
    mapping_profile_id: str | None,
    language: str | None,
) -> tuple[OcrAnalysis, bool]:
    if session_id:
        try:
            session_service.get_session(db, session_id, workspace_hash)
        except AppError:
            # The SPA sends its workspace key as ``session_id`` when no domain
            # session is selected. Treat unknown ids as "unassigned" instead of
            # rejecting the upload.
            session_id = None
    calculated = _parse_calculated(calculated_raw)
    profile = _get_profile(db, workspace_hash, mapping_profile_id)

    stored: StoredUpload = store_upload(
        uploads_root=settings.uploads_dir,
        workspace_hash=workspace_hash,
        session_id=session_id,
        original_name=file_name,
        stream=stream,
        max_bytes=settings.max_upload_bytes,
    )

    existing = _existing_analysis(
        db,
        workspace_hash=workspace_hash,
        session_id=session_id,
        sha256=stored.sha256,
    )
    if existing is not None:
        stored.path.unlink(missing_ok=True)
        return existing, True

    attachment = Attachment(
        id=new_uuid(),
        workspace_id_hash=workspace_hash,
        session_id=session_id,
        filename=stored.filename,
        stored_path=stored.relative_path,
        mime=stored.mime,
        size_bytes=stored.size_bytes,
        sha256=stored.sha256,
        kind="report_pdf" if stored.extension == ".pdf" else "report_image",
    )
    db.add(attachment)
    db.flush()

    analysis = OcrAnalysis(
        id=new_uuid(),
        workspace_id_hash=workspace_hash,
        session_id=session_id,
        attachment_id=attachment.id,
        mapping_profile_id=profile.id if profile else None,
        status="queued",
        needs_human_review=True,
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    analysis.status = "running"
    analysis.started_at = utcnow()
    db.commit()

    previous_lang = os.environ.get("HYDRO_OCR_LANG")
    if language:
        os.environ["HYDRO_OCR_LANG"] = language
    try:
        result: OcrAnalysisResult = analyze_report(stored.path, calculated)
    except ReportOcrError as exc:
        analysis.status = "failed"
        analysis.error_code = exc.code
        analysis.error_message = exc.message
        analysis.finished_at = utcnow()
        db.commit()
        raise _http_error(exc, analysis_id=analysis.id) from exc
    except Exception as exc:  # unexpected domain failure
        analysis.status = "failed"
        analysis.error_code = "internal_error"
        analysis.error_message = "OCR analizi tamamlanamadi."
        analysis.finished_at = utcnow()
        db.commit()
        raise AppError(
            "internal_error",
            "OCR analizi tamamlanamadi.",
            status_code=500,
            details={"analysis_id": analysis.id},
        ) from exc
    finally:
        if language:
            if previous_lang is None:
                os.environ.pop("HYDRO_OCR_LANG", None)
            else:
                os.environ["HYDRO_OCR_LANG"] = previous_lang

    payload = json_safe(result.to_dict())
    analysis.status = "succeeded"
    analysis.source = result.source
    analysis.page_count = result.page_count
    analysis.character_count = result.character_count
    analysis.confidence = float(result.confidence)
    analysis.report = payload.get("report")
    analysis.discrepancies = payload.get("discrepancies") or []
    analysis.issues = payload.get("issues") or []
    analysis.warnings = payload.get("warnings") or []
    analysis.needs_human_review = True
    analysis.finished_at = utcnow()
    analysis.error_code = None
    analysis.error_message = None

    audit.record(
        db,
        action="ocr.analyze",
        entity_type="ocr_analysis",
        entity_id=analysis.id,
        session_id=session_id,
        workspace_hash=workspace_hash,
        after={"status": analysis.status, "source": analysis.source},
    )
    db.commit()
    db.refresh(analysis)
    return analysis, False


def _lookup_field(report: Any, path: str) -> dict[str, Any] | None:
    current: Any = report
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    if isinstance(current, dict) and "value" in current:
        return current
    return None


def _iter_fields(report: Any, prefix: str = "") -> Iterable[tuple[str, dict[str, Any]]]:
    if not isinstance(report, dict):
        return
    for key, value in report.items():
        if not isinstance(value, dict):
            continue
        path = f"{prefix}.{key}" if prefix else key
        if "value" in value and "confidence" in value:
            yield path, value
        else:
            yield from _iter_fields(value, path)


def _parse_stored(raw: Any) -> Any:
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except ValueError:
            return None
    return raw


def _metrics(report: dict[str, Any] | None) -> dict[str, int]:
    low = 0
    critical = 0
    for _path, entry in _iter_fields(report or {}):
        confidence = as_float(entry.get("confidence"))
        if confidence is None:
            continue
        if confidence < CRITICAL_CONFIDENCE:
            critical += 1
        elif confidence < LOW_CONFIDENCE:
            low += 1
    return {"low_confidence_fields": low, "critical_confidence_fields": critical}


def _error_payload(analysis: OcrAnalysis) -> dict[str, Any] | None:
    if not analysis.error_code:
        return None
    return {
        "code": analysis.error_code,
        "message": analysis.error_message or "",
        "detail": "",
    }


def detail_payload(db: OrmSession, analysis: OcrAnalysis) -> dict[str, Any]:
    attachment = db.get(Attachment, analysis.attachment_id)
    base: dict[str, Any] = {
        "id": analysis.id,
        "analysis_id": analysis.id,
        "session_id": analysis.session_id,
        "mapping_profile_id": analysis.mapping_profile_id,
        "status": analysis.status,
        "source": analysis.source,
        "page_count": analysis.page_count,
        "character_count": analysis.character_count,
        "confidence": analysis.confidence,
        "needs_human_review": analysis.needs_human_review,
        "diagnostics": {"report_ocr": ocr_status()},
        "metrics": _metrics(analysis.report),
        "warnings": analysis.warnings or [],
        "issues": analysis.issues or [],
        "discrepancies": analysis.discrepancies or [],
        "approved_fields": analysis.approved_fields,
        "error": _error_payload(analysis),
        "created_at": iso_z(analysis.created_at),
        "started_at": iso_z(analysis.started_at),
        "finished_at": iso_z(analysis.finished_at),
        "attachment": (
            {
                "id": attachment.id,
                "filename": attachment.filename,
                "mime": attachment.mime,
                "size_bytes": attachment.size_bytes,
                "sha256": attachment.sha256,
            }
            if attachment is not None
            else None
        ),
        "poll_url": f"/api/ocr/analyses/{analysis.id}",
    }
    if analysis.status == "succeeded":
        base["report"] = analysis.report
        base["filename"] = attachment.filename if attachment is not None else None
        base["used_ocr"] = analysis.source in {"ocr", "mixed"}
    elif analysis.status in {"queued", "running"}:
        base["progress"] = {
            "stage": "analyzing" if analysis.status == "running" else "queued",
            "elapsed_s": 0,
        }
    return base


def list_analyses(
    db: OrmSession,
    workspace_hash: str,
    *,
    session_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    conditions = [OcrAnalysis.workspace_id_hash == workspace_hash]
    if session_id:
        conditions.append(OcrAnalysis.session_id == session_id)
    if status:
        conditions.append(OcrAnalysis.status == status)
    total = db.scalar(select(func.count(OcrAnalysis.id)).where(*conditions)) or 0
    rows = (
        db.execute(
            select(OcrAnalysis)
            .where(*conditions)
            .order_by(OcrAnalysis.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    items = []
    for row in rows:
        discrepancies = row.discrepancies or []
        blocking = sum(
            1
            for item in discrepancies
            if isinstance(item, dict) and item.get("status") in {"mismatch", "missing_in_report"}
        )
        attachment = db.get(Attachment, row.attachment_id)
        items.append(
            {
                "id": row.id,
                "session_id": row.session_id,
                "status": row.status,
                "source": row.source,
                "confidence": row.confidence,
                "page_count": row.page_count,
                "created_at": iso_z(row.created_at),
                "finished_at": iso_z(row.finished_at),
                "warnings_count": len(row.warnings or []),
                "discrepancies_count": len(discrepancies),
                "blocking_count": blocking,
                "filename": attachment.filename if attachment is not None else None,
                "error_code": row.error_code,
            }
        )
    return {"items": items, "total": int(total), "limit": limit, "offset": offset}


def get_analysis(db: OrmSession, workspace_hash: str, analysis_id: str) -> OcrAnalysis:
    analysis = db.get(OcrAnalysis, analysis_id)
    if analysis is None or analysis.workspace_id_hash != workspace_hash:
        raise not_found("ocr_analysis", analysis_id)
    return analysis


def cancel_analysis(db: OrmSession, analysis: OcrAnalysis) -> dict[str, Any]:
    if analysis.status not in {"queued", "running"}:
        raise AppError(
            "not_cancellable",
            "Analiz tamamlanmis; iptal edilemez.",
            status_code=409,
            details={"status": analysis.status},
        )
    analysis.status = "cancelled"
    analysis.finished_at = utcnow()
    audit.record(
        db,
        action="ocr.cancel",
        entity_type="ocr_analysis",
        entity_id=analysis.id,
        session_id=analysis.session_id,
        workspace_hash=analysis.workspace_id_hash,
    )
    db.commit()
    return {"id": analysis.id, "status": analysis.status}


# ---------------------------------------------------------------------------
# Approve / apply
# ---------------------------------------------------------------------------


def approve(
    db: OrmSession,
    analysis: OcrAnalysis,
    *,
    fields: dict[str, Any],
    approve_all: bool,
    reviewer_note: str,
) -> dict[str, Any]:
    if analysis.status != "succeeded":
        raise AppError(
            "analysis_not_succeeded",
            "Yalnizca tamamlanmis analiz onaylanabilir.",
            status_code=409,
            details={"status": analysis.status},
        )

    report = _parse_stored(analysis.report) or {}
    known = dict(_iter_fields(report))
    unknown = [path for path in fields if path not in known]
    if unknown:
        raise AppError(
            "unknown_field",
            "Bilinmeyen OCR alani.",
            status_code=422,
            details={"fields": unknown},
        )

    approved = dict(analysis.approved_fields or {})
    now = iso_z(utcnow())

    if approve_all:
        reviewed = {path for path, payload in fields.items() if payload.approved}
        low_confidence = {
            path
            for path, entry in known.items()
            if (as_float(entry.get("confidence")) or 0.0) < LOW_CONFIDENCE
        }
        missing_review = sorted(low_confidence - reviewed)
        if missing_review:
            raise AppError(
                "low_confidence_unreviewed",
                "Dusuk guvenli alanlar acikca onaylanmalidir.",
                status_code=422,
                details={"fields": missing_review},
            )
        targets = known.keys()
    else:
        targets = fields.keys()

    for path in targets:
        entry = known[path]
        explicit = fields.get(path)
        if explicit is not None:
            if not explicit.approved:
                continue
            value = explicit.value if explicit.value is not None else entry.get("value")
            unit = explicit.unit or entry.get("unit", "")
        else:
            value = entry.get("value")
            unit = entry.get("unit", "")
        approved[path] = {
            "value": value,
            "unit": unit,
            "approved": True,
            "approved_at": now,
            "reviewer_note": reviewer_note,
        }

    analysis.approved_fields = approved
    event = audit.record(
        db,
        action="ocr.approve",
        entity_type="ocr_analysis",
        entity_id=analysis.id,
        session_id=analysis.session_id,
        workspace_hash=analysis.workspace_id_hash,
        after={"approved_fields": sorted(approved)},
    )
    db.commit()

    pending = sorted(
        path
        for path, entry in known.items()
        if (as_float(entry.get("confidence")) or 0.0) < LOW_CONFIDENCE and path not in approved
    )
    return {
        "id": analysis.id,
        "approved_count": len(approved),
        "pending_low_confidence": pending,
        "audit_event_id": event.id,
        "approved_at": now,
    }


def _get_path(data: dict[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _set_path(data: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    current = data
    for part in parts[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    current[parts[-1]] = value


def apply_to_session(
    db: OrmSession,
    analysis: OcrAnalysis,
    *,
    session_id: str | None,
    field_names: list[str] | None,
    overwrite: bool,
) -> dict[str, Any]:
    if analysis.status != "succeeded":
        raise AppError(
            "analysis_not_succeeded",
            "Yalnizca tamamlanmis analiz uygulanabilir.",
            status_code=409,
            details={"status": analysis.status},
        )
    approved = dict(analysis.approved_fields or {})
    if not approved:
        raise AppError(
            "field_not_approved",
            "Uygulanacak onayli alan yok.",
            status_code=422,
            details={"fields": []},
        )
    target_session_id = session_id or analysis.session_id
    if not target_session_id:
        raise not_found("session", None)
    session = session_service.get_session(db, target_session_id, analysis.workspace_id_hash)

    selected = list(field_names) if field_names is not None else sorted(approved)
    not_approved = [name for name in selected if name not in approved]
    if not_approved:
        raise AppError(
            "field_not_approved",
            "Secili alanlar onaylanmamis.",
            status_code=422,
            details={"fields": not_approved},
        )

    inputs = copy.deepcopy(session.inputs or {})
    applied: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []

    for name in selected:
        targets = FIELD_TARGETS.get(name)
        if not targets:
            skipped.append(
                {
                    "field": name,
                    "reason": "no_mapping" if name not in _PASSTHROUGH_FIELDS else "not_applicable",
                }
            )
            continue
        value = approved[name].get("value")
        if value is None:
            skipped.append({"field": name, "reason": "missing_value"})
            continue
        for target in targets:
            current = _get_path(inputs, target)
            if not overwrite and current not in (None, ""):
                skipped.append({"field": name, "reason": "already_set", "target": target})
                continue
            if target in TEXT_TARGETS:
                resolved: Any = str(value).strip()
                if not resolved:
                    skipped.append({"field": name, "reason": "invalid_value", "target": target})
                    continue
            else:
                resolved = as_float(value)
                if resolved is None:
                    skipped.append({"field": name, "reason": "invalid_value", "target": target})
                    continue
            if overwrite and current not in (None, "") and current != resolved:
                conflicts.append(
                    {"field": name, "target": target, "previous": current, "new": resolved}
                )
            _set_path(inputs, target, resolved)
            applied.append({"field": name, "target": target, "from": current, "to": resolved})

    session.inputs = session_service.normalize_inputs(inputs)
    session.revision = int(session.revision or 1) + 1
    session.updated_at = utcnow()
    audit.record(
        db,
        action="ocr.apply",
        entity_type="session",
        entity_id=session.id,
        session_id=session.id,
        workspace_hash=analysis.workspace_id_hash,
        after={"analysis_id": analysis.id, "applied": [item["field"] for item in applied]},
    )
    db.commit()
    db.refresh(session)

    return {
        "session_id": session.id,
        "analysis_id": analysis.id,
        "applied": applied,
        "skipped": skipped,
        "conflicts": conflicts,
        "session_revision": session.revision,
    }


# ---------------------------------------------------------------------------
# Mapping profiles
# ---------------------------------------------------------------------------


def _validate_mapping(mapping: dict[str, Any]) -> None:
    errors: list[str] = []
    if not isinstance(mapping, dict):
        errors.append("mapping must be an object")
    else:
        fields = mapping.get("fields", {})
        if fields is not None and not isinstance(fields, dict):
            errors.append("mapping.fields must be an object")
        elif isinstance(fields, dict):
            for key, value in fields.items():
                if not isinstance(value, dict):
                    errors.append(f"mapping.fields.{key} must be an object")
                    continue
                aliases = value.get("aliases")
                if aliases is not None and (not isinstance(aliases, list) or not aliases):
                    errors.append(f"mapping.fields.{key}.aliases must be a non-empty list")
        sections = mapping.get("sections")
        if sections is not None and not isinstance(sections, list):
            errors.append("mapping.sections must be a list")
    if errors:
        raise AppError(
            "invalid_mapping",
            "Alan esleme semasi gecersiz.",
            status_code=422,
            details={"errors": errors},
        )


def profile_payload(profile: OcrMappingProfile) -> dict[str, Any]:
    return {
        "id": profile.id,
        "name": profile.name,
        "format_key": profile.format_key,
        "schema_version": profile.schema_version,
        "mode": profile.mode,
        "is_default": profile.is_default,
        "mapping": profile.mapping or {},
        "created_at": iso_z(profile.created_at),
        "updated_at": iso_z(profile.updated_at),
    }


def profile_brief(profile: OcrMappingProfile) -> dict[str, Any]:
    payload = profile_payload(profile)
    payload.pop("mapping", None)
    return payload


def list_profiles(
    db: OrmSession, workspace_hash: str, *, limit: int = 50, offset: int = 0
) -> dict[str, Any]:
    conditions = [OcrMappingProfile.workspace_id_hash == workspace_hash]
    total = db.scalar(select(func.count(OcrMappingProfile.id)).where(*conditions)) or 0
    rows = (
        db.execute(
            select(OcrMappingProfile)
            .where(*conditions)
            .order_by(OcrMappingProfile.is_default.desc(), OcrMappingProfile.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return {
        "items": [profile_brief(row) for row in rows],
        "total": int(total),
        "limit": limit,
        "offset": offset,
    }


def get_profile(db: OrmSession, workspace_hash: str, profile_id: str) -> OcrMappingProfile:
    profile = db.get(OcrMappingProfile, profile_id)
    if profile is None or profile.workspace_id_hash != workspace_hash:
        raise not_found("ocr_mapping_profile", profile_id)
    return profile


def create_profile(
    db: OrmSession, workspace_hash: str, payload: dict[str, Any]
) -> OcrMappingProfile:
    _validate_mapping(payload.get("mapping") or {})
    duplicate = (
        db.execute(
            select(OcrMappingProfile).where(
                OcrMappingProfile.workspace_id_hash == workspace_hash,
                OcrMappingProfile.format_key == payload["format_key"],
            )
        )
        .scalars()
        .first()
    )
    if duplicate is not None:
        raise AppError(
            "format_key_exists",
            "Bu format anahtari zaten kayitli.",
            status_code=409,
            details={"format_key": payload["format_key"]},
        )
    if payload.get("is_default"):
        _clear_default(db, workspace_hash)
    profile = OcrMappingProfile(
        id=new_uuid(),
        workspace_id_hash=workspace_hash,
        name=payload["name"],
        format_key=payload["format_key"],
        schema_version=int(payload.get("schema_version", 1)),
        mode=payload.get("mode", "pre_extract"),
        mapping=payload.get("mapping") or {},
        is_default=bool(payload.get("is_default", False)),
    )
    db.add(profile)
    audit.record(
        db,
        action="ocr.mapping.create",
        entity_type="ocr_mapping_profile",
        entity_id=profile.id,
        workspace_hash=workspace_hash,
        after={"format_key": profile.format_key},
    )
    db.commit()
    db.refresh(profile)
    return profile


def _clear_default(db: OrmSession, workspace_hash: str) -> None:
    rows = (
        db.execute(
            select(OcrMappingProfile).where(
                OcrMappingProfile.workspace_id_hash == workspace_hash,
                OcrMappingProfile.is_default.is_(True),
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        row.is_default = False


def update_profile(
    db: OrmSession,
    profile: OcrMappingProfile,
    *,
    changes: dict[str, Any],
) -> OcrMappingProfile:
    if "mapping" in changes and changes["mapping"] is not None:
        _validate_mapping(changes["mapping"])
        profile.mapping = changes["mapping"]
    if "format_key" in changes and changes["format_key"] is not None:
        duplicate = (
            db.execute(
                select(OcrMappingProfile).where(
                    OcrMappingProfile.workspace_id_hash == profile.workspace_id_hash,
                    OcrMappingProfile.format_key == changes["format_key"],
                    OcrMappingProfile.id != profile.id,
                )
            )
            .scalars()
            .first()
        )
        if duplicate is not None:
            raise AppError(
                "format_key_exists",
                "Bu format anahtari zaten kayitli.",
                status_code=409,
                details={"format_key": changes["format_key"]},
            )
        profile.format_key = changes["format_key"]
    if "name" in changes and changes["name"] is not None:
        profile.name = changes["name"]
    if "schema_version" in changes and changes["schema_version"] is not None:
        profile.schema_version = int(changes["schema_version"])
    if "mode" in changes and changes["mode"] is not None:
        profile.mode = changes["mode"]
    if "is_default" in changes and changes["is_default"] is not None:
        if changes["is_default"]:
            _clear_default(db, profile.workspace_id_hash)
        profile.is_default = bool(changes["is_default"])
    profile.updated_at = utcnow()
    audit.record(
        db,
        action="ocr.mapping.update",
        entity_type="ocr_mapping_profile",
        entity_id=profile.id,
        workspace_hash=profile.workspace_id_hash,
        after={"format_key": profile.format_key},
    )
    db.commit()
    db.refresh(profile)
    return profile


def delete_profile(db: OrmSession, profile: OcrMappingProfile) -> None:
    if profile.is_default:
        raise AppError(
            "default_profile",
            "Varsayilan profil silinemez.",
            status_code=409,
            details={"id": profile.id},
        )
    audit.record(
        db,
        action="ocr.mapping.delete",
        entity_type="ocr_mapping_profile",
        entity_id=profile.id,
        workspace_hash=profile.workspace_id_hash,
    )
    db.delete(profile)
    db.commit()


__all__ = [
    "FIELD_TARGETS",
    "analyze_upload",
    "apply_to_session",
    "approve",
    "cancel_analysis",
    "create_profile",
    "delete_profile",
    "detail_payload",
    "get_analysis",
    "get_profile",
    "list_analyses",
    "list_profiles",
    "profile_brief",
    "profile_payload",
    "status_payload",
    "update_profile",
]
