"""Session CRUD, results, time-series, scene, snapshot and export routes."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Header, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session as OrmSession

from .. import schemas
from ..core.config import Settings
from ..core.errors import AppError, validation_error
from ..core.rate_limit import enforce_rate_limit
from ..core.timeutil import json_safe
from ..db import get_db
from ..services import audit
from ..services import dossier as dossier_service
from ..services import reports as report_service
from ..services import scene as scene_service
from ..services import sessions as session_service
from ..services import snapshot as snapshot_service
from .deps import Workspace, get_settings, get_workspace

router = APIRouter(prefix="/sessions", tags=["sessions"])


def parse_if_match(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    text = value.strip()
    if text.startswith("W/"):
        text = text[2:]
    text = text.strip().strip('"')
    try:
        return int(text)
    except ValueError as exc:
        raise validation_error(
            "If-Match gecersiz; revision numarasi bekleniyor.", field="If-Match"
        ) from exc


def _etag(response: Response, revision: int) -> None:
    response.headers["ETag"] = f'"{revision}"'


@router.get("")
def list_sessions(
    response: Response,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    project_id: str | None = Query(default=None),
    include_deleted: bool = Query(default=False),
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    payload = session_service.list_sessions(
        db,
        workspace_hash=workspace.hash,
        limit=limit,
        offset=offset,
        status=status,
        q=q,
        project_id=project_id,
        include_deleted=include_deleted,
    )
    response.headers["X-Total-Count"] = str(payload["total"])
    return payload


@router.post("", status_code=201)
def create_session(
    payload: schemas.SessionCreate,
    response: Response,
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    session = session_service.create_session(
        db,
        workspace_hash=workspace.hash,
        name=payload.name,
        project_id=payload.project_id,
        inputs=payload.inputs,
        wizard_state=payload.wizard_state,
    )
    response.headers["Location"] = f"/api/sessions/{session.id}"
    body = json_safe(session_service.serialize_session(session))
    _etag(response, session.revision)
    return body


@router.get("/{session_id}")
def get_session(
    session_id: str,
    response: Response,
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    session = session_service.get_session(db, session_id, workspace.hash)
    _etag(response, session.revision)
    return json_safe(session_service.serialize_session(session))


@router.get("/{session_id}/forms")
def get_session_forms(
    session_id: str,
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    session = session_service.get_session(db, session_id, workspace.hash)
    return json_safe(dossier_service.get_session_forms_payload(db, session))


@router.get("/{session_id}/forms/{form_code}")
def get_single_session_form(
    session_id: str,
    form_code: str,
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    session = session_service.get_session(db, session_id, workspace.hash)
    return json_safe(dossier_service.get_single_session_form_payload(db, session, form_code))


@router.put("/{session_id}/forms/{form_code}")
def update_session_form(
    session_id: str,
    form_code: str,
    payload: schemas.SectionFormUpdateRequest,
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    session = session_service.get_session(db, session_id, workspace.hash)
    return json_safe(
        dossier_service.update_session_form(
            db,
            session,
            workspace_hash=workspace.hash,
            form_code=form_code,
            form_date=payload.form_date,
            extracted_data=payload.extracted_data,
            overwrite_session_inputs=payload.overwrite_session_inputs,
        )
    )


@router.post("/{session_id}/forms/{form_code}/scan")
def scan_single_form(
    request: Request,
    session_id: str,
    form_code: str,
    file: UploadFile | None = File(default=None),
    files: list[UploadFile] | None = File(default=None),
    language: str | None = Form(default=None),
    overwrite: bool = Form(default=True),
    mode: str = Form(default="replace"),
    db: OrmSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    enforce_rate_limit(request, settings, bucket="form_ocr_scan", limit=30)
    raw_uploads = list(files) if files else ([file] if file is not None else [])
    if not raw_uploads:
        raise AppError(
            "missing_file",
            "Taranacak en az bir dokuman secilmelidir.",
            status_code=400,
        )
    if len(raw_uploads) > 20:
        raise AppError(
            "too_many_files",
            "Tek seferde en fazla 20 sayfa/dosya yuklenebilir.",
            status_code=422,
        )
    norm_mode = (mode or "replace").strip().lower()
    if norm_mode not in {"replace", "append"}:
        raise AppError(
            "invalid_scan_mode",
            "Gecersiz tarama modu; 'replace' veya 'append' olmalidir.",
            status_code=422,
        )

    session = session_service.get_session(db, session_id, workspace.hash)
    return json_safe(
        dossier_service.scan_single_form_upload(
            db,
            settings,
            workspace_hash=workspace.hash,
            session=session,
            form_code=form_code,
            uploads=[(u.filename, u.file) for u in raw_uploads],
            language=language or None,
            overwrite=bool(overwrite),
            mode=norm_mode,
        )
    )


@router.put("/{session_id}")
def update_session(
    session_id: str,
    payload: schemas.SessionUpdate,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    session = session_service.get_session(db, session_id, workspace.hash)
    expected = parse_if_match(if_match)
    changes = payload.model_dump(exclude_unset=True)
    session = session_service.update_session(
        db, session, changes=changes, expected_revision=expected
    )
    _etag(response, session.revision)
    return json_safe(session_service.serialize_session(session))


@router.delete("/{session_id}", status_code=204)
def delete_session(
    session_id: str,
    hard: bool = Query(default=False),
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
    settings: Settings = Depends(get_settings),
) -> Response:
    session = session_service.get_session(db, session_id, workspace.hash, include_deleted=hard)
    session_service.delete_session(db, session, hard=hard, uploads_dir=settings.uploads_dir)
    return Response(status_code=204)


@router.post("/{session_id}/duplicate", status_code=201)
def duplicate_session(
    session_id: str,
    payload: schemas.SessionDuplicate,
    response: Response,
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    session = session_service.get_session(db, session_id, workspace.hash)
    clone = session_service.duplicate_session(db, session, name=payload.name)
    response.headers["Location"] = f"/api/sessions/{clone.id}"
    _etag(response, clone.revision)
    return json_safe(session_service.serialize_session(clone))


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


@router.get("/{session_id}/results")
def list_results(
    session_id: str,
    test_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    session = session_service.get_session(db, session_id, workspace.hash)
    return json_safe(
        session_service.list_results(db, session, test_type=test_type, limit=limit, offset=offset)
    )


@router.post("/{session_id}/results", status_code=201)
def create_result(
    session_id: str,
    payload: schemas.ResultCreate,
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    session = session_service.get_session(db, session_id, workspace.hash)
    return json_safe(
        session_service.create_result(
            db, session, test_type=payload.test_type, payload=payload.payload
        )
    )


# ---------------------------------------------------------------------------
# Time series
# ---------------------------------------------------------------------------


@router.get("/{session_id}/time-series")
def list_time_series(
    session_id: str,
    limit: int = Query(default=1000, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    from_ts: datetime | None = Query(default=None, alias="from"),
    to_ts: datetime | None = Query(default=None, alias="to"),
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    session = session_service.get_session(db, session_id, workspace.hash)
    return json_safe(
        session_service.list_time_series(
            db,
            session,
            limit=limit,
            offset=offset,
            from_ts=from_ts,
            to_ts=to_ts,
        )
    )


@router.post("/{session_id}/time-series", status_code=201)
def add_time_series(
    session_id: str,
    payload: schemas.TimeSeriesCreate,
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    session = session_service.get_session(db, session_id, workspace.hash)
    return json_safe(
        session_service.add_time_series(
            db,
            session,
            timestamp=payload.timestamp,
            pressure_bar=payload.pressure_bar,
            temperature_c=payload.temperature_c,
            volume_m3=payload.volume_m3,
            notes=payload.notes,
            source=payload.source,
        )
    )


@router.get("/{session_id}/time-series/summary")
def time_series_summary(
    session_id: str,
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    session = session_service.get_session(db, session_id, workspace.hash)
    rows, _ = session_service._ordered_records(db, session)
    return json_safe(session_service.time_series_summary(rows))


@router.delete("/{session_id}/time-series/{record_id}", status_code=204)
def delete_time_series(
    session_id: str,
    record_id: str,
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> Response:
    session = session_service.get_session(db, session_id, workspace.hash)
    session_service.delete_time_series(db, session, record_id)
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Scene / summary / audit
# ---------------------------------------------------------------------------


@router.get("/{session_id}/scene")
def scene(
    session_id: str,
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    session = session_service.get_session(db, session_id, workspace.hash)
    return json_safe(scene_service.build_scene(session.inputs or {}))


@router.get("/{session_id}/summary")
def summary(
    session_id: str,
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    session = session_service.get_session(db, session_id, workspace.hash)
    return json_safe(session_service.session_summary(db, session))


@router.get("/{session_id}/audit")
def audit_events(
    session_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    action: str | None = Query(default=None),
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    session = session_service.get_session(db, session_id, workspace.hash)
    return json_safe(
        session_service.list_audit(db, session, limit=limit, offset=offset, action=action)
    )


# ---------------------------------------------------------------------------
# Export / snapshot
# ---------------------------------------------------------------------------


@router.get("/{session_id}/export")
def export_session(
    session_id: str,
    fmt: str = Query(alias="format"),
    preview: bool = Query(default=False),
    include_raw_ocr: bool = Query(default=False),
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
    settings: Settings = Depends(get_settings),
):
    _ = include_raw_ocr
    if fmt not in report_service.FORMAT_ALIASES:
        raise validation_error(f"Desteklenmeyen rapor formati: {fmt}", field="format")
    session = session_service.get_session(db, session_id, workspace.hash)
    from sqlalchemy import select

    from ..models import TestResult

    result_rows = (
        db.execute(
            select(TestResult)
            .where(TestResult.session_id == session.id)
            .order_by(TestResult.computed_at.asc())
        )
        .scalars()
        .all()
    )
    if fmt == "txt" and preview:
        context = report_service.build_context(session, result_rows)
        content = report_service.build_report_text(context, session)
        audit.record(
            db,
            action="report.export",
            entity_type="session",
            entity_id=session.id,
            session_id=session.id,
            workspace_hash=workspace.hash,
            after={"format": "txt", "preview": True},
        )
        db.commit()
        return {"format": "txt", "content": content}
    target, _context = report_service.export_session(settings, session, result_rows, fmt=fmt)
    audit.record(
        db,
        action="report.export",
        entity_type="session",
        entity_id=session.id,
        session_id=session.id,
        workspace_hash=workspace.hash,
        after={"format": fmt, "path": target.name},
    )
    db.commit()
    return FileResponse(
        path=target,
        media_type=report_service.CONTENT_TYPES[fmt],
        filename=report_service.export_filename(fmt),
    )


@router.get("/{session_id}/snapshot")
def get_snapshot(
    session_id: str,
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> JSONResponse:
    session = session_service.get_session(db, session_id, workspace.hash)
    payload = snapshot_service.build_snapshot(session.inputs or {})
    filename = f"hidrostatik_test_girdileri_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    return JSONResponse(
        content=json_safe(payload),
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "ETag": f'"{session.revision}"',
        },
    )


@router.post("/{session_id}/snapshot")
def apply_snapshot(
    session_id: str,
    payload: schemas.SnapshotApply,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    session = session_service.get_session(db, session_id, workspace.hash)
    expected = parse_if_match(if_match)
    new_inputs, mapping = snapshot_service.apply_snapshot(
        session.inputs or {}, payload.snapshot, mode=payload.mode
    )
    session = session_service.update_session(
        db,
        session,
        changes={"inputs": new_inputs},
        expected_revision=expected,
        replace_inputs=payload.mode == "replace",
    )
    audit.record(
        db,
        action="snapshot.apply",
        entity_type="session",
        entity_id=session.id,
        session_id=session.id,
        workspace_hash=workspace.hash,
        after={"mode": payload.mode, "mapping": mapping},
    )
    db.commit()
    _etag(response, session.revision)
    session_payload = json_safe(session_service.serialize_session(session))
    return {
        **session_payload,
        "session": session_payload,
        "mapping": mapping,
    }


__all__ = ["parse_if_match", "router"]
