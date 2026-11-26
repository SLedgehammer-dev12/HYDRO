"""OCR orchestration (upload -> analyze -> approve -> apply)."""

from __future__ import annotations

import copy
import inspect
import json
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, BinaryIO, Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from hidrostatik_test.services.report_ocr import (
    ERROR_CANCELLED,
    MAX_OCR_PAGES,
    MAX_PDF_PAGES,
    SUPPORTED_EXTENSIONS,
    OcrAnalysisResult,
    ReportOcrError,
    analyze_report,
    effective_max_file_size_bytes,
    ocr_engine_details,
    ocr_status,
    pdf_rasterizer_status,
    suggest_field_fixes_from_report_dict,
)

from .. import db as db_module
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
from . import dossier as dossier_service
from . import sessions as session_service
from .ocr_queue import OCR_QUEUE
from .storage import StoredUpload, kind_for_extension, store_upload

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
    "ocr_cancelled": 409,
    "worker_interrupted": 503,
}

#: Canonical OCR field -> session input paths.
FIELD_TARGETS: dict[str, tuple[str, ...]] = {
    "pipe_od_mm": ("geometry.outside_diameter_mm",),
    "pipe_id_mm": ("geometry.inside_diameter_mm",),
    "wall_mm": ("geometry.wall_thickness_mm",),
    "length_m": ("geometry.length_m",),
    "section_volume_m3": ("geometry.section_volume_m3",),
    "max_operating_pressure_bar": ("section_profile.design_pressure_bar",),
    "smys_mpa": ("section_profile.smys_mpa",),
    "test_pressure_bar": ("air.pressure_bar", "pressure.pressure_bar"),
    "air_test.vpa": ("air.actual_added_water_m3",),
    "air_test.k": ("air.k_factor",),
    "air_test.a": ("air.a_micro_per_bar",),
    "pressure_test.a": ("pressure.a_micro_per_bar",),
    "pressure_test.b": ("pressure.b_micro_per_c",),
    "pressure_test.delta_t": ("pressure.delta_t_c",),
    "pressure_test.p_delta": ("pressure.p_delta_bar",),
    "pressure_test.pa": ("pressure.actual_pressure_change_bar",),
    "pressure_test.pl": ("pressure.allowed_pressure_change_bar",),
    "pressure_test.t_initial": ("pressure.t_initial_c",),
    "pressure_test.t_final": ("pressure.t_final_c",),
    "report_no": ("report_meta.report_no",),
    "date": ("report_meta.date",),
    "operator": ("report_meta.operator",),
    "section_id": ("report_meta.section_id",),
    "start_kp": ("section_meta.start_kp",),
    "end_kp": ("section_meta.end_kp",),
    "notes": ("report_meta.notes",),
}

_PASSTHROUGH_FIELDS = {"result"}
TEXT_TARGETS = {
    "report_meta.report_no",
    "report_meta.date",
    "report_meta.operator",
    "report_meta.section_id",
    "report_meta.notes",
    "section_meta.start_kp",
    "section_meta.end_kp",
}


def _profile_aliases(profile: OcrMappingProfile | None) -> dict[str, list[str]]:
    """Return ``pre_extract`` alias overrides from a mapping profile."""

    if profile is None or profile.mode != "pre_extract":
        return {}
    fields = (profile.mapping or {}).get("fields") or {}
    aliases: dict[str, list[str]] = {}
    for key, value in fields.items():
        if not isinstance(value, dict):
            continue
        items = value.get("aliases")
        if isinstance(items, list):
            cleaned = [str(item).strip() for item in items if str(item).strip()]
            if cleaned:
                aliases[key] = cleaned
    return aliases


def _profile_targets(profile: OcrMappingProfile | None) -> dict[str, tuple[str, ...]]:
    """Return ``post_map`` target overrides from a mapping profile."""

    if profile is None or profile.mode != "post_map":
        return {}
    fields = (profile.mapping or {}).get("fields") or {}
    targets: dict[str, tuple[str, ...]] = {}
    for key, value in fields.items():
        if not isinstance(value, dict):
            continue
        raw = value.get("targets") or value.get("target")
        if isinstance(raw, str):
            raw = [raw]
        if isinstance(raw, list):
            cleaned = tuple(str(item).strip() for item in raw if str(item).strip())
            if cleaned:
                targets[key] = cleaned
    return targets


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


def _engine_payload(details: dict[str, Any] | None = None) -> dict[str, Any]:
    info = details if details is not None else ocr_engine_details()
    return {
        "name": info.get("engine_name"),
        "version": info.get("version"),
        "languages": list(info.get("languages") or []),
        "default_language": info.get("default_language"),
    }


def _rasterizer_payload() -> dict[str, Any]:
    available, engine = pdf_rasterizer_status()
    if available:
        return {"available": True, "engine": engine, "note": ""}
    return {
        "available": False,
        "engine": None,
        "note": "Taranmis PDF icin pypdfium2, PyMuPDF, Windows PDF (WinRT) veya pdf2image + Poppler gerekir.",
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


def status_payload(db: OrmSession, workspace_hash: str, *, refresh: bool = False) -> dict[str, Any]:
    details = ocr_engine_details(force_refresh=refresh)
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
        "available": bool(details["available"]),
        "status_text": str(details["status_text"]),
        "engine": _engine_payload(details),
        "pdf_rasterizer": _rasterizer_payload(),
        "text_layer": {"available": True, "engines": ["pypdf", "openpyxl", "xlrd"]},
        "limits": {
            "max_file_size_bytes": effective_max_file_size_bytes(),
            "max_pdf_pages": MAX_PDF_PAGES,
            "max_ocr_pages": MAX_OCR_PAGES,
            "supported_extensions": sorted(SUPPORTED_EXTENSIONS),
        },
        "queue": {
            **_queue_counts(db, workspace_hash),
            "max_concurrency": OCR_QUEUE.max_concurrency,
        },
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


def _is_stale_analysis(existing: OcrAnalysis, file_path: Path, extension: str) -> bool:
    """Return True if a cached successful OCR row lacks `dossier` or was truncated (e.g. old 30-page limit)."""
    if existing.status != "succeeded":
        return False
    if (
        not isinstance(existing.dossier, dict)
        or int(existing.dossier.get("schema_version") or 0) < dossier_service.DOSSIER_SCHEMA_VERSION
    ):
        return True
    if extension.lower() == ".pdf":
        try:
            from pypdf import PdfReader

            total_pages = len(PdfReader(str(file_path)).pages)
            expected = min(total_pages, MAX_OCR_PAGES)
            if existing.page_count is not None and expected > int(existing.page_count):
                return True
        except Exception:
            pass
    return False


def _elapsed_seconds(started_at: datetime | None) -> int:
    if started_at is None:
        return 0
    start = (
        started_at.replace(tzinfo=timezone.utc)
        if started_at.tzinfo is None
        else started_at.astimezone(timezone.utc)
    )
    return max(0, int((utcnow() - start).total_seconds()))


def _prepare_upload(
    db: OrmSession,
    settings: Settings,
    workspace_hash: str,
    *,
    file_name: str | None,
    stream: BinaryIO,
    calculated_raw: str | None,
    session_id: str | None,
    mapping_profile_id: str | None,
    force: bool,
) -> tuple[
    OcrAnalysis,
    bool,
    StoredUpload | None,
    dict[str, Any] | None,
    OcrMappingProfile | None,
]:
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

    existing = (
        None
        if force
        else _existing_analysis(
            db,
            workspace_hash=workspace_hash,
            session_id=session_id,
            sha256=stored.sha256,
        )
    )
    if existing is not None and not _is_stale_analysis(existing, stored.path, stored.extension):
        stored.path.unlink(missing_ok=True)
        return existing, True, None, calculated, profile

    attachment = Attachment(
        id=new_uuid(),
        workspace_id_hash=workspace_hash,
        session_id=session_id,
        filename=stored.filename,
        stored_path=stored.relative_path,
        mime=stored.mime,
        size_bytes=stored.size_bytes,
        sha256=stored.sha256,
        kind=kind_for_extension(stored.extension),
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
    return analysis, False, stored, calculated, profile


def _apply_success_result(
    db: OrmSession,
    analysis: OcrAnalysis,
    *,
    result: OcrAnalysisResult,
    stored_filename: str,
    workspace_hash: str,
) -> dict[str, Any]:
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
    analysis.dossier = json_safe(
        dossier_service.analyze_dossier_pages(
            result.pages,
            source_filename=stored_filename,
            fallback_report=payload.get("report"),
        )
    )
    analysis.needs_human_review = True
    analysis.finished_at = utcnow()
    analysis.error_code = None
    analysis.error_message = None

    audit.record(
        db,
        action="ocr.analyze",
        entity_type="ocr_analysis",
        entity_id=analysis.id,
        session_id=analysis.session_id,
        workspace_hash=workspace_hash,
        after={"status": analysis.status, "source": analysis.source},
    )
    db.commit()
    db.refresh(analysis)
    setattr(
        analysis, "_extracted_pages", list(result.pages)
    )  # transient in-process reuse avoids double OCR
    return payload


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
    force: bool = False,
) -> tuple[OcrAnalysis, bool]:
    analysis, reused, stored, calculated, profile = _prepare_upload(
        db,
        settings,
        workspace_hash,
        file_name=file_name,
        stream=stream,
        calculated_raw=calculated_raw,
        session_id=session_id,
        mapping_profile_id=mapping_profile_id,
        force=force,
    )
    if reused or stored is None:
        return analysis, True

    cancel_event = OCR_QUEUE.register_sync(analysis.id)
    started = time.monotonic()
    try:
        analysis.status = "running"
        analysis.started_at = utcnow()
        db.commit()

        try:
            result: OcrAnalysisResult = analyze_report(
                stored.path,
                calculated,
                extra_aliases=_profile_aliases(profile),
                language=language,
                cancel_event=cancel_event,
                timeout_seconds=float(settings.ocr_timeout_s),
            )
        except ReportOcrError as exc:
            if exc.code == ERROR_CANCELLED or cancel_event.is_set():
                analysis.status = "cancelled"
                analysis.error_code = None
                analysis.error_message = None
            else:
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

        OCR_QUEUE.record_duration(time.monotonic() - started)
        _apply_success_result(
            db,
            analysis,
            result=result,
            stored_filename=stored.filename,
            workspace_hash=workspace_hash,
        )
        return analysis, False
    finally:
        OCR_QUEUE.unregister(analysis.id)


def update_job_progress(
    session_factory: sessionmaker[OrmSession],
    analysis_id: str,
    done: int,
    total: int,
) -> None:
    """Persist page-level OCR progress on job_payload without requiring a schema migration."""
    if total <= 0:
        return
    with session_factory() as pdb:
        row = pdb.get(OcrAnalysis, analysis_id)
        if row is None or row.status != "running":
            return
        payload = dict(row.job_payload or {})
        payload["progress_done"] = max(0, min(int(done), int(total)))
        payload["progress_total"] = int(total)
        row.job_payload = payload
        pdb.commit()


def call_analyze_with_progress(
    analyze_fn: Any,
    *args: Any,
    progress_callback: Any = None,
    **kwargs: Any,
) -> OcrAnalysisResult:
    """Call analyze_report while passing progress_callback only if accepted by callee/mock."""
    if progress_callback is not None:
        try:
            params = inspect.signature(analyze_fn).parameters
            if "progress_callback" in params or any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
            ):
                kwargs["progress_callback"] = progress_callback
        except (TypeError, ValueError):
            pass
    return analyze_fn(*args, **kwargs)


def _submit_inline_ocr_job(
    *,
    analysis_id: str,
    workspace_hash: str,
    stored_path: Path,
    stored_filename: str,
    calculated: dict[str, Any] | None,
    aliases: dict[str, list[str]] | None,
    language: str | None,
    timeout_s: float,
) -> None:
    session_factory = db_module.get_sessionmaker()

    def _mark_cancelled_if_needed(wdb: OrmSession, row: OcrAnalysis) -> None:
        row.status = "cancelled"
        row.error_code = None
        row.error_message = None
        row.finished_at = row.finished_at or utcnow()
        wdb.commit()

    def _worker(cancel_event: threading.Event) -> None:
        if cancel_event.is_set():
            with session_factory() as wdb:
                row = wdb.get(OcrAnalysis, analysis_id)
                if row is not None and row.status != "cancelled":
                    _mark_cancelled_if_needed(wdb, row)
            return

        with session_factory() as wdb:
            row = wdb.get(OcrAnalysis, analysis_id)
            if row is None or row.status == "cancelled" or cancel_event.is_set():
                if row is not None and row.status != "cancelled":
                    _mark_cancelled_if_needed(wdb, row)
                if row is None:
                    stored_path.unlink(missing_ok=True)
                return
            row.status = "running"
            row.started_at = utcnow()
            wdb.commit()

        started = time.monotonic()
        result: OcrAnalysisResult | None = None
        caught_ocr_err: ReportOcrError | None = None
        caught_unexpected = False
        def _on_progress(done: int, total: int) -> None:
            update_job_progress(session_factory, analysis_id, done, total)

        try:
            result = call_analyze_with_progress(
                analyze_report,
                stored_path,
                calculated,
                extra_aliases=aliases,
                language=language,
                cancel_event=cancel_event,
                timeout_seconds=timeout_s,
                progress_callback=_on_progress,
            )
        except ReportOcrError as exc:
            caught_ocr_err = exc
        except Exception:  # unexpected domain failure
            caught_unexpected = True

        with session_factory() as wdb:
            row = wdb.get(OcrAnalysis, analysis_id)
            if row is None:
                stored_path.unlink(missing_ok=True)
                return
            if (
                cancel_event.is_set()
                or row.status == "cancelled"
                or (caught_ocr_err is not None and caught_ocr_err.code == ERROR_CANCELLED)
            ):
                _mark_cancelled_if_needed(wdb, row)
                return
            if caught_ocr_err is not None:
                row.status = "failed"
                row.error_code = caught_ocr_err.code
                row.error_message = caught_ocr_err.message
                row.finished_at = utcnow()
                wdb.commit()
                return
            if caught_unexpected or result is None:
                row.status = "failed"
                row.error_code = "internal_error"
                row.error_message = "OCR analizi tamamlanamadi."
                row.finished_at = utcnow()
                wdb.commit()
                return

            OCR_QUEUE.record_duration(time.monotonic() - started)
            _apply_success_result(
                wdb,
                row,
                result=result,
                stored_filename=stored_filename,
                workspace_hash=workspace_hash,
            )

    OCR_QUEUE.submit(analysis_id, _worker)


def enqueue_upload(
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
    force: bool = False,
) -> tuple[OcrAnalysis, bool, int | None]:
    """Persist an upload in ``queued`` state and schedule background OCR execution."""
    analysis, reused, stored, calculated, profile = _prepare_upload(
        db,
        settings,
        workspace_hash,
        file_name=file_name,
        stream=stream,
        calculated_raw=calculated_raw,
        session_id=session_id,
        mapping_profile_id=mapping_profile_id,
        force=force,
    )
    if reused or stored is None:
        est: int | None = None
        if analysis.status in {"queued", "running"}:
            counts = _queue_counts(db, workspace_hash)
            att = db.get(Attachment, analysis.attachment_id)
            est = OCR_QUEUE.estimate_wait_seconds(
                queued=counts["queued"],
                running=counts["running"],
                size_bytes=att.size_bytes if att is not None else 0,
            )
        return analysis, True, est

    analysis.job_payload = json_safe({"calculated": calculated, "language": language})
    analysis.cancel_requested = False
    db.commit()
    db.refresh(analysis)

    counts = _queue_counts(db, workspace_hash)
    est_wait = OCR_QUEUE.estimate_wait_seconds(
        queued=max(0, counts["queued"] - 1),
        running=counts["running"],
        size_bytes=stored.size_bytes,
    )
    if getattr(settings, "ocr_worker_mode", "inline") == "external":
        return analysis, False, est_wait

    _submit_inline_ocr_job(
        analysis_id=analysis.id,
        workspace_hash=workspace_hash,
        stored_path=stored.path,
        stored_filename=stored.filename,
        calculated=calculated,
        aliases=_profile_aliases(profile),
        language=language,
        timeout_s=float(settings.ocr_timeout_s),
    )
    return analysis, False, est_wait


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
        "suggested_fixes": [],
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
        base["suggested_fixes"] = suggest_field_fixes_from_report_dict(analysis.report)
        base["filename"] = attachment.filename if attachment is not None else None
        base["used_ocr"] = analysis.source in {"ocr", "mixed"}
        base["dossier"] = dossier_service.build_dossier_view(db, analysis)
    elif analysis.status in {"queued", "running"}:
        counts = _queue_counts(db, analysis.workspace_id_hash)
        jp = dict(analysis.job_payload or {})
        pages_done = jp.get("progress_done")
        pages_total = jp.get("progress_total")
        has_pages = (
            analysis.status == "running"
            and isinstance(pages_total, int)
            and pages_total > 0
            and isinstance(pages_done, int)
        )
        progress_payload: dict[str, Any] = {
            "stage": (
                f"extract:{pages_done}/{pages_total}"
                if has_pages
                else ("analyzing" if analysis.status == "running" else "queued")
            ),
            "elapsed_s": _elapsed_seconds(analysis.started_at),
        }
        if has_pages:
            progress_payload["pages_done"] = pages_done
            progress_payload["pages_total"] = pages_total
        base["progress"] = progress_payload
        base["estimated_wait_s"] = OCR_QUEUE.estimate_wait_seconds(
            queued=counts["queued"],
            running=counts["running"],
            size_bytes=attachment.size_bytes if attachment is not None else 0,
        )
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
    OCR_QUEUE.cancel(analysis.id)
    analysis.cancel_requested = True
    analysis.status = "cancelled"
    analysis.lease_until = None
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


def queue_overview(
    db: OrmSession,
    workspace_hash: str,
    settings: Settings,
) -> dict[str, Any]:
    """Return OCR queue status counts, oldest queued job age, and recent dead-letter jobs."""

    counts: dict[str, int] = {
        "queued": 0,
        "running": 0,
        "succeeded": 0,
        "failed": 0,
        "cancelled": 0,
    }
    rows = db.execute(
        select(OcrAnalysis.status, func.count(OcrAnalysis.id))
        .where(OcrAnalysis.workspace_id_hash == workspace_hash)
        .group_by(OcrAnalysis.status)
    ).all()
    for st, count in rows:
        if st in counts:
            counts[st] = int(count)

    oldest_queued = db.execute(
        select(func.min(OcrAnalysis.created_at)).where(
            OcrAnalysis.workspace_id_hash == workspace_hash,
            OcrAnalysis.status == "queued",
        )
    ).scalar_one_or_none()
    oldest_age_s: float | None = None
    if oldest_queued is not None:
        ref = (
            oldest_queued.replace(tzinfo=timezone.utc)
            if oldest_queued.tzinfo is None
            else oldest_queued
        )
        oldest_age_s = max(0.0, round((utcnow() - ref).total_seconds(), 2))

    dead_rows = (
        db.execute(
            select(OcrAnalysis)
            .where(
                OcrAnalysis.workspace_id_hash == workspace_hash,
                OcrAnalysis.status == "failed",
            )
            .order_by(OcrAnalysis.finished_at.desc(), OcrAnalysis.created_at.desc())
            .limit(20)
        )
        .scalars()
        .all()
    )
    dead_letter = [
        {
            "id": row.id,
            "status": row.status,
            "attempts": int(row.attempts or 0),
            "max_attempts": int(row.max_attempts or 3),
            "error_code": row.error_code,
            "error_message": row.error_message,
            "created_at": iso_z(row.created_at),
            "finished_at": iso_z(row.finished_at),
        }
        for row in dead_rows
    ]
    return {
        "worker_mode": getattr(settings, "ocr_worker_mode", "inline"),
        "counts": counts,
        "oldest_queued_age_s": oldest_age_s,
        "dead_letter_count": counts["failed"],
        "dead_letter": dead_letter,
    }


def retry_analysis(
    db: OrmSession,
    settings: Settings,
    analysis: OcrAnalysis,
) -> dict[str, Any]:
    """Reset a failed/cancelled OCR analysis back to queued and dispatch to worker."""

    if analysis.status not in {"failed", "cancelled"}:
        raise AppError(
            "not_retryable",
            "Yalnizca basarisiz veya iptal edilmis analizler yeniden kuyruga alinabilir.",
            status_code=409,
            details={"status": analysis.status},
        )
    att = db.get(Attachment, analysis.attachment_id)
    if att is None:
        raise AppError(
            "attachment_missing",
            "Yuklenen dosya eki bulunamadi; dosyayi yeniden yukleyin.",
            status_code=404,
        )
    stored_path = (settings.uploads_dir / att.stored_path).resolve()
    if not stored_path.is_file():
        raise AppError(
            "attachment_missing",
            "Yuklenen dosya eki diskte bulunamadi; dosyayi yeniden yukleyin.",
            status_code=404,
        )

    analysis.status = "queued"
    analysis.attempts = 0
    analysis.cancel_requested = False
    analysis.lease_until = None
    analysis.worker_id = None
    analysis.error_code = None
    analysis.error_message = None
    analysis.started_at = None
    analysis.finished_at = None
    audit.record(
        db,
        action="ocr.retry",
        entity_type="ocr_analysis",
        entity_id=analysis.id,
        session_id=analysis.session_id,
        workspace_hash=analysis.workspace_id_hash,
    )
    db.commit()
    db.refresh(analysis)

    if getattr(settings, "ocr_worker_mode", "inline") != "external":
        job_payload = dict(analysis.job_payload or {})
        calculated = job_payload.get("calculated")
        language = job_payload.get("language") or settings.ocr_lang
        profile = (
            db.get(OcrMappingProfile, analysis.mapping_profile_id)
            if analysis.mapping_profile_id
            else None
        )
        _submit_inline_ocr_job(
            analysis_id=analysis.id,
            workspace_hash=analysis.workspace_id_hash,
            stored_path=stored_path,
            stored_filename=att.filename,
            calculated=calculated if isinstance(calculated, dict) else None,
            aliases=_profile_aliases(profile),
            language=str(language) if language else None,
            timeout_s=float(settings.ocr_timeout_s),
        )

    return detail_payload(db, analysis)


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

    profile = (
        db.get(OcrMappingProfile, analysis.mapping_profile_id)
        if analysis.mapping_profile_id
        else None
    )
    target_overrides = _profile_targets(profile)

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
        targets = target_overrides.get(name) or FIELD_TARGETS.get(name)
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
    recomp = dossier_service.recompute_session_from_inputs_and_forms(db, session)
    audit.record(
        db,
        action="ocr.apply",
        entity_type="session",
        entity_id=session.id,
        session_id=session.id,
        workspace_hash=analysis.workspace_id_hash,
        after={
            "analysis_id": analysis.id,
            "applied": [item["field"] for item in applied],
            "persisted_result_types": recomp.get("persisted_result_types", []),
        },
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
        "persisted_result_types": recomp.get("persisted_result_types", []),
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


def cleanup_stale_failed_uploads(
    db: OrmSession,
    settings: Settings,
    *,
    max_age_days: int = 7,
) -> int:
    """Remove uploaded files for old failed/cancelled OCR jobs past the retry window."""

    cutoff = utcnow() - timedelta(days=max(1, int(max_age_days)))
    rows = (
        db.execute(select(OcrAnalysis).where(OcrAnalysis.status.in_(("failed", "cancelled"))))
        .scalars()
        .all()
    )
    removed = 0
    for row in rows:
        stamp = row.finished_at or row.created_at
        if stamp is None:
            continue
        aware = (
            stamp.replace(tzinfo=timezone.utc)
            if stamp.tzinfo is None
            else stamp.astimezone(timezone.utc)
        )
        if aware >= cutoff:
            continue
        att = db.get(Attachment, row.attachment_id)
        if att is None:
            continue
        other_active = (
            db.execute(
                select(OcrAnalysis.id)
                .where(
                    OcrAnalysis.attachment_id == att.id,
                    OcrAnalysis.id != row.id,
                    OcrAnalysis.status.in_(("queued", "running", "succeeded")),
                )
                .limit(1)
            )
            .scalars()
            .first()
        )
        if other_active is not None:
            continue
        stored = (settings.uploads_dir / att.stored_path).resolve()
        if stored.is_file():
            stored.unlink(missing_ok=True)
            removed += 1
    return removed


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
    "cleanup_stale_failed_uploads",
    "create_profile",
    "delete_profile",
    "detail_payload",
    "enqueue_upload",
    "get_analysis",
    "get_profile",
    "list_analyses",
    "list_profiles",
    "profile_brief",
    "profile_payload",
    "status_payload",
    "update_profile",
]
