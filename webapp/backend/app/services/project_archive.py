"""Portable `.hydroproj.zip` project archive export/import and desktop `hydro.db` importer."""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
import posixpath
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from ..core import security
from ..core.config import Settings
from ..core.errors import AppError, validation_error
from ..core.timeutil import iso_z, json_safe, utcnow
from ..models import (
    Attachment,
    HydroSession,
    SectionForm,
    TestResult,
    TimeSeriesRecord,
    new_uuid,
)
from . import audit, storage
from . import dossier as dossier_service
from . import projects as project_service
from . import sessions as session_service

ARCHIVE_FORMAT = "hydroproj/v1"
ARCHIVE_SCHEMA_VERSION = "0002"
MAX_ARCHIVE_BYTES = 200 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 500
MAX_UNCOMPRESSED_BYTES = 500 * 1024 * 1024
MAX_ENTRY_BYTES = 100 * 1024 * 1024
SQLITE_MAGIC = b"SQLite format 3\x00"


def _parse_iso_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _safe_json_loads(raw: Any, default: Any) -> Any:
    if raw is None or raw == "":
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(str(raw))
    except Exception:
        return default


def _encode_json(payload: Any) -> bytes:
    return json.dumps(json_safe(payload), ensure_ascii=False, indent=2).encode("utf-8")


def _validate_zip_entry_name(info: zipfile.ZipInfo) -> str:
    raw_name = info.filename
    if not raw_name or "\x00" in raw_name or "\\" in raw_name:
        raise validation_error("Arsiv icinde gecersiz dosya yolu tespit edildi.", field="file")
    if raw_name.startswith("/") or (len(raw_name) >= 2 and raw_name[1] == ":"):
        raise validation_error("Arsiv mutlak dosya yolu iceremez.", field="file")
    # Reject symlinks inside ZIP (Unix mode S_IFLNK = 0o120000)
    unix_mode = (info.external_attr >> 16) & 0o170000
    if unix_mode == 0o120000:
        raise validation_error("Arsiv sembolik baglanti (symlink) iceremez.", field="file")
    norm = posixpath.normpath(raw_name)
    parts = [p for p in norm.split("/") if p]
    if not parts or norm.startswith("..") or ".." in parts:
        raise validation_error("Arsiv path traversal (..) iceremez.", field="file")
    return norm


def _read_zip_entry_bounded(
    zf: zipfile.ZipFile, info: zipfile.ZipInfo, *, remaining_budget: int
) -> bytes:
    limit = min(MAX_ENTRY_BYTES, remaining_budget)
    chunks: list[bytes] = []
    total = 0
    with zf.open(info, "r") as stream:
        while True:
            chunk = stream.read(256 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                raise AppError(
                    "archive_too_large",
                    "Arsiv acilmis boyut siniri asildi.",
                    status_code=413,
                )
            chunks.append(chunk)
    return b"".join(chunks)


def export_project_archive(
    db: OrmSession,
    settings: Settings,
    workspace_hash: str,
    project_id: str,
    *,
    include_attachments: bool = True,
) -> tuple[bytes, str]:
    """Bundle a full project (metadata, sections, results, time series, BOTAŞ forms, attachments) into `.hydroproj.zip`."""

    project = project_service.get_project(db, project_id, workspace_hash)
    sessions = (
        db.execute(
            select(HydroSession)
            .where(
                HydroSession.project_id == project.id,
                HydroSession.workspace_id_hash == workspace_hash,
                HydroSession.deleted_at.is_(None),
            )
            .order_by(HydroSession.created_at.asc())
        )
        .scalars()
        .all()
    )
    session_ids = [s.id for s in sessions]

    results_by_sec: dict[str, list[TestResult]] = {sid: [] for sid in session_ids}
    ts_by_sec: dict[str, list[TimeSeriesRecord]] = {sid: [] for sid in session_ids}
    forms_by_sec: dict[str, list[SectionForm]] = {sid: [] for sid in session_ids}
    attachments_meta: list[dict[str, Any]] = []
    attachment_blobs: dict[str, bytes] = {}

    if session_ids:
        for res in (
            db.execute(
                select(TestResult)
                .where(TestResult.session_id.in_(session_ids))
                .order_by(TestResult.computed_at.asc())
            )
            .scalars()
            .all()
        ):
            results_by_sec.setdefault(res.session_id, []).append(res)

        for row in (
            db.execute(
                select(TimeSeriesRecord)
                .where(TimeSeriesRecord.session_id.in_(session_ids))
                .order_by(TimeSeriesRecord.timestamp.asc())
            )
            .scalars()
            .all()
        ):
            ts_by_sec.setdefault(row.session_id, []).append(row)

        for form in (
            db.execute(select(SectionForm).where(SectionForm.session_id.in_(session_ids)))
            .scalars()
            .all()
        ):
            forms_by_sec.setdefault(form.session_id, []).append(form)

        if include_attachments:
            attachments = (
                db.execute(
                    select(Attachment)
                    .where(
                        Attachment.session_id.in_(session_ids),
                        Attachment.workspace_id_hash == workspace_hash,
                    )
                    .order_by(Attachment.created_at.asc())
                )
                .scalars()
                .all()
            )
            for att in attachments:
                if not att.stored_path:
                    continue
                try:
                    resolved = storage.resolve_stored_path(settings.uploads_dir, att.stored_path)
                    if not resolved.exists() or not resolved.is_file():
                        continue
                    blob = resolved.read_bytes()
                except Exception:
                    continue
                safe_name = security.safe_filename(att.filename)
                arc_path = f"attachments/{att.id}_{safe_name}"
                attachment_blobs[arc_path] = blob
                attachments_meta.append(
                    {
                        "id": att.id,
                        "session_id": att.session_id,
                        "filename": att.filename,
                        "mime": att.mime,
                        "size_bytes": len(blob),
                        "sha256": hashlib.sha256(blob).hexdigest(),
                        "kind": att.kind,
                        "archive_path": arc_path,
                    }
                )

    payload_files: dict[str, bytes] = {}
    payload_files["project.json"] = _encode_json(
        {
            "id": project.id,
            "code": project.code or "",
            "name": project.name,
            "client": project.client,
            "contractor": project.contractor,
            "supervisor": project.supervisor,
            "pipeline_length_m": project.pipeline_length_m,
            "status": project.status or "active",
            "defaults": project.defaults or {},
            "description": project.description,
            "created_at": iso_z(project.created_at),
            "updated_at": iso_z(project.updated_at),
        }
    )

    for idx, sess in enumerate(sessions):
        prefix = f"sections/{idx:04d}"
        payload_files[f"{prefix}/session.json"] = _encode_json(
            {
                "id": sess.id,
                "name": sess.name,
                "status": sess.status,
                "inputs": sess.inputs or {},
                "wizard_state": sess.wizard_state,
                "result_summary": sess.result_summary or {},
                "notes": sess.notes or "",
                "created_at": iso_z(sess.created_at),
                "updated_at": iso_z(sess.updated_at),
            }
        )
        payload_files[f"{prefix}/results.json"] = _encode_json(
            [
                {
                    "test_type": r.test_type,
                    "inputs": r.inputs or {},
                    "result": r.result or {},
                    "decision_status": r.decision_status,
                    "decision_title": r.decision_title,
                    "decision_summary": r.decision_summary,
                    "decision_rule": r.decision_rule,
                    "decision": r.decision or {},
                    "engine_version": r.engine_version,
                    "computed_at": iso_z(r.computed_at),
                }
                for r in results_by_sec.get(sess.id, [])
            ]
        )
        payload_files[f"{prefix}/time_series.json"] = _encode_json(
            [
                {
                    "timestamp": iso_z(t.timestamp),
                    "pressure_bar": t.pressure_bar,
                    "temperature_c": t.temperature_c,
                    "volume_m3": t.volume_m3,
                    "notes": t.notes or "",
                    "source": t.source or "archive",
                }
                for t in ts_by_sec.get(sess.id, [])
            ]
        )
        payload_files[f"{prefix}/forms.json"] = _encode_json(
            [
                {
                    "form_code": f.form_code,
                    "botas_code": f.botas_code,
                    "form_title": f.form_title,
                    "required": bool(f.required),
                    "status": f.status,
                    "attachment_id": f.attachment_id,
                    "source_filename": f.source_filename or "",
                    "pages": f.pages or [],
                    "form_date": f.form_date or "",
                    "extracted_data": f.extracted_data or {},
                    "warnings": f.warnings or [],
                    "revision": int(f.revision or 0),
                    "filled_at": iso_z(f.filled_at),
                }
                for f in forms_by_sec.get(sess.id, [])
            ]
        )

    payload_files["attachments.json"] = _encode_json(attachments_meta)
    for arc_path, blob in attachment_blobs.items():
        payload_files[arc_path] = blob

    manifest_files: dict[str, dict[str, Any]] = {}
    for rel_path, blob in sorted(payload_files.items()):
        manifest_files[rel_path] = {
            "sha256": hashlib.sha256(blob).hexdigest(),
            "size_bytes": len(blob),
        }

    manifest_bytes = _encode_json(
        {
            "format": ARCHIVE_FORMAT,
            "schema_version": ARCHIVE_SCHEMA_VERSION,
            "exported_at": iso_z(utcnow()),
            "project_code": project.code or "",
            "project_name": project.name,
            "section_count": len(sessions),
            "files": manifest_files,
        }
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", manifest_bytes)
        for rel_path, blob in sorted(payload_files.items()):
            zf.writestr(rel_path, blob)

    slug = security.safe_filename((project.code or project.name or "proje").replace(" ", "_"))
    return buf.getvalue(), f"{slug}.hydroproj.zip"


def import_project_archive(
    db: OrmSession,
    settings: Settings,
    workspace_hash: str,
    archive_bytes: bytes,
    *,
    target_project_name: str | None = None,
    target_project_code: str | None = None,
    include_attachments: bool = True,
) -> dict[str, Any]:
    """Verify integrity and atomically import a `.hydroproj.zip` archive into a new Project."""

    if not archive_bytes:
        raise validation_error("Bos arsiv dosyasi yuklendi.", field="file")
    if len(archive_bytes) > MAX_ARCHIVE_BYTES:
        raise AppError(
            "archive_too_large",
            f"Arsiv boyutu ust siniri asti ({MAX_ARCHIVE_BYTES // (1024 * 1024)} MB).",
            status_code=413,
        )

    try:
        zf = zipfile.ZipFile(io.BytesIO(archive_bytes), mode="r")
    except zipfile.BadZipFile as exc:
        raise validation_error("Gecersiz .hydroproj.zip arsiv dosyasi.", field="file") from exc

    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_ARCHIVE_ENTRIES:
            raise AppError(
                "archive_too_many_entries",
                f"Arsivdeki dosya sayisi limiti asti ({MAX_ARCHIVE_ENTRIES}).",
                status_code=413,
            )

        entries_by_name: dict[str, zipfile.ZipInfo] = {}
        declared_total = 0
        for info in infos:
            if info.is_dir():
                _validate_zip_entry_name(info)
                continue
            clean_name = _validate_zip_entry_name(info)
            if clean_name in entries_by_name:
                raise validation_error(f"Arsivde yinelenen dosya: {clean_name}", field="file")
            declared_total += max(0, int(info.file_size))
            if declared_total > MAX_UNCOMPRESSED_BYTES:
                raise AppError(
                    "archive_too_large",
                    "Arsiv acilmis toplam boyut sinirini asti.",
                    status_code=413,
                )
            entries_by_name[clean_name] = info

        if "manifest.json" not in entries_by_name or "project.json" not in entries_by_name:
            raise validation_error(
                "Arsivde manifest.json veya project.json bulunamadi.", field="file"
            )

        remaining = MAX_UNCOMPRESSED_BYTES
        blobs: dict[str, bytes] = {}
        for rel_path, info in entries_by_name.items():
            data = _read_zip_entry_bounded(zf, info, remaining_budget=remaining)
            remaining -= len(data)
            blobs[rel_path] = data

    try:
        manifest = json.loads(blobs["manifest.json"].decode("utf-8"))
    except Exception as exc:
        raise validation_error("manifest.json okunamadi.", field="file") from exc

    if not isinstance(manifest, dict) or manifest.get("format") != ARCHIVE_FORMAT:
        raise validation_error(
            "Desteklenmeyen arsiv bicimi (hydroproj/v1 bekleniyor).", field="file"
        )

    manifest_files = manifest.get("files")
    if not isinstance(manifest_files, dict):
        raise validation_error("manifest.json files haritasi gecersiz.", field="file")

    expected_paths = set(manifest_files.keys())
    actual_paths = {k for k in blobs if k != "manifest.json"}
    if expected_paths != actual_paths:
        raise validation_error(
            "Arsiv dosya listesi manifest ile eslesmiyor.",
            field="file",
            details={
                "missing": sorted(expected_paths - actual_paths)[:10],
                "unexpected": sorted(actual_paths - expected_paths)[:10],
            },
        )

    for rel_path, meta in manifest_files.items():
        if not isinstance(meta, dict):
            raise validation_error(f"Manifest girisi gecersiz: {rel_path}", field="file")
        blob = blobs[rel_path]
        expected_sha = str(meta.get("sha256") or "").lower()
        actual_sha = hashlib.sha256(blob).hexdigest()
        if not expected_sha or expected_sha != actual_sha:
            raise validation_error(
                f"Arsiv SHA-256 butunluk dogrulamasi basarisiz: {rel_path}",
                field="file",
            )

    try:
        proj_meta = json.loads(blobs["project.json"].decode("utf-8"))
    except Exception as exc:
        raise validation_error("project.json okunamadi.", field="file") from exc
    if not isinstance(proj_meta, dict):
        raise validation_error("project.json gecersiz.", field="file")

    proj_name = (target_project_name or "").strip() or str(proj_meta.get("name") or "").strip()
    if not proj_name:
        proj_name = "İçe Aktarılan Proje"
    proj_code = (
        target_project_code.strip()
        if isinstance(target_project_code, str) and target_project_code.strip()
        else str(proj_meta.get("code") or "").strip()
    )

    attachments_meta_raw = _safe_json_loads(
        blobs.get("attachments.json", b"[]").decode("utf-8"), []
    )
    if not isinstance(attachments_meta_raw, list):
        attachments_meta_raw = []

    section_prefixes = sorted(
        {
            posixpath.dirname(p)
            for p in blobs
            if p.startswith("sections/") and p.endswith("/session.json")
        }
    )

    project = project_service.create_project(
        db,
        workspace_hash,
        {
            "name": proj_name,
            "code": proj_code,
            "client": proj_meta.get("client"),
            "contractor": proj_meta.get("contractor"),
            "supervisor": proj_meta.get("supervisor"),
            "pipeline_length_m": proj_meta.get("pipeline_length_m"),
            "status": proj_meta.get("status") or "active",
            "defaults": proj_meta.get("defaults") or {},
            "description": proj_meta.get("description"),
        },
        commit=False,
    )

    session_id_map: dict[str, str] = {}
    created_sessions: list[HydroSession] = []
    imported_results = 0
    imported_ts = 0
    imported_forms = 0
    imported_attachments = 0
    created_upload_paths: list[Path] = []
    attachment_id_map: dict[str, str] = {}

    try:
        for prefix in section_prefixes:
            sec_data = json.loads(blobs[f"{prefix}/session.json"].decode("utf-8"))
            old_sid = str(sec_data.get("id") or "")
            inputs = session_service.normalize_inputs(sec_data.get("inputs") or {})
            sess = HydroSession(
                id=new_uuid(),
                project_id=project.id,
                workspace_id_hash=workspace_hash,
                name=str(sec_data.get("name") or "Kesit")[:200],
                status=str(sec_data.get("status") or "draft")[:16],
                inputs=inputs,
                wizard_state=sec_data.get("wizard_state"),
                result_summary=sec_data.get("result_summary") or {},
                revision=1,
                notes=str(sec_data.get("notes") or ""),
                created_at=_parse_iso_dt(sec_data.get("created_at")) or utcnow(),
                updated_at=utcnow(),
            )
            db.add(sess)
            db.flush()
            if old_sid:
                session_id_map[old_sid] = sess.id
            created_sessions.append(sess)

            # Results
            res_blob = blobs.get(f"{prefix}/results.json")
            if res_blob:
                for item in _safe_json_loads(res_blob.decode("utf-8"), []):
                    if not isinstance(item, dict):
                        continue
                    db.add(
                        TestResult(
                            id=new_uuid(),
                            session_id=sess.id,
                            test_type=str(item.get("test_type") or "")[:32],
                            inputs=item.get("inputs") or {},
                            result=item.get("result") or {},
                            decision_status=str(item.get("decision_status") or "BEKLIYOR")[:32],
                            decision_title=str(item.get("decision_title") or "")[:200],
                            decision_summary=str(item.get("decision_summary") or ""),
                            decision_rule=str(item.get("decision_rule") or ""),
                            decision=item.get("decision") or {},
                            engine_version=str(item.get("engine_version") or "")[:64],
                            computed_at=_parse_iso_dt(item.get("computed_at")) or utcnow(),
                        )
                    )
                    imported_results += 1

            # Time series
            ts_blob = blobs.get(f"{prefix}/time_series.json")
            if ts_blob:
                for item in _safe_json_loads(ts_blob.decode("utf-8"), []):
                    if not isinstance(item, dict):
                        continue
                    ts_dt = _parse_iso_dt(item.get("timestamp"))
                    if ts_dt is None:
                        continue
                    p_bar = item.get("pressure_bar")
                    t_c = item.get("temperature_c")
                    v_m3 = item.get("volume_m3")
                    if (
                        p_bar is None
                        or t_c is None
                        or isinstance(p_bar, bool)
                        or isinstance(t_c, bool)
                        or isinstance(v_m3, bool)
                    ):
                        continue
                    try:
                        p_val = float(p_bar)
                        t_val = float(t_c)
                        v_val = float(v_m3) if v_m3 is not None else None
                    except (TypeError, ValueError):
                        continue
                    if (
                        not math.isfinite(p_val)
                        or not math.isfinite(t_val)
                        or (v_val is not None and not math.isfinite(v_val))
                    ):
                        continue
                    db.add(
                        TimeSeriesRecord(
                            id=new_uuid(),
                            session_id=sess.id,
                            timestamp=ts_dt,
                            pressure_bar=p_val,
                            temperature_c=t_val,
                            volume_m3=v_val,
                            notes=str(item.get("notes") or ""),
                            source=str(item.get("source") or "archive")[:16],
                        )
                    )
                    imported_ts += 1

        # Attachments (before forms so forms.attachment_id can remap cleanly)
        if include_attachments:
            for meta in attachments_meta_raw:
                if not isinstance(meta, dict):
                    continue
                arc_path = str(meta.get("archive_path") or "")
                raw_file = blobs.get(arc_path)
                if raw_file is None:
                    continue
                display_name = security.safe_filename(str(meta.get("filename") or "attachment"))
                ext = Path(display_name).suffix.lower()
                if not ext or ext not in {
                    ".pdf",
                    ".png",
                    ".jpg",
                    ".jpeg",
                    ".tif",
                    ".tiff",
                    ".bmp",
                    ".webp",
                    ".xlsx",
                    ".xls",
                }:
                    continue
                sniffed = security.sniff_mime(raw_file[:64])
                if sniffed is None:
                    raise validation_error(
                        f"Arsiv eki desteklenmeyen dosya bicimi iceriyor: {display_name}",
                        field="file",
                    )
                stored_name = security.new_stored_name(ext)
                rel_dir = f"{workspace_hash[:12]}/{utcnow().strftime('%Y%m')}"
                target = security.ensure_within(
                    settings.uploads_dir, settings.uploads_dir / rel_dir / stored_name
                )
                security.write_private_file(target, [raw_file])
                created_upload_paths.append(target)

                old_att_id = str(meta.get("id") or "")
                new_att_id = new_uuid()
                mapped_sid = session_id_map.get(str(meta.get("session_id") or ""))
                db.add(
                    Attachment(
                        id=new_att_id,
                        workspace_id_hash=workspace_hash,
                        session_id=mapped_sid,
                        filename=display_name,
                        stored_path=f"{rel_dir}/{stored_name}",
                        mime=sniffed,
                        size_bytes=len(raw_file),
                        sha256=hashlib.sha256(raw_file).hexdigest(),
                        kind=storage.kind_for_extension(ext),
                    )
                )
                if old_att_id:
                    attachment_id_map[old_att_id] = new_att_id
                imported_attachments += 1

        db.flush()

        # Forms
        for idx, prefix in enumerate(section_prefixes):
            sess = created_sessions[idx]
            forms_blob = blobs.get(f"{prefix}/forms.json")
            seen_codes: set[str] = set()
            if forms_blob:
                for item in _safe_json_loads(forms_blob.decode("utf-8"), []):
                    if not isinstance(item, dict):
                        continue
                    f_code = str(item.get("form_code") or "")[:40]
                    if not f_code or f_code in seen_codes:
                        continue
                    seen_codes.add(f_code)
                    spec = dossier_service.FORM_SPEC_BY_CODE.get(f_code)
                    db.add(
                        SectionForm(
                            id=new_uuid(),
                            workspace_id_hash=workspace_hash,
                            project_id=project.id,
                            session_id=sess.id,
                            form_code=f_code,
                            botas_code=str(
                                item.get("botas_code") or (spec.botas_code if spec else "")
                            )[:48],
                            form_title=str(
                                item.get("form_title") or (spec.title if spec else f_code)
                            )[:160],
                            required=bool(item.get("required", spec.required if spec else True)),
                            status=str(item.get("status") or "empty")[:20],
                            analysis_id=None,
                            attachment_id=attachment_id_map.get(
                                str(item.get("attachment_id") or "")
                            ),
                            source_filename=str(item.get("source_filename") or "")[:255],
                            pages=list(item.get("pages") or []),
                            form_date=str(item.get("form_date") or "")[:40],
                            extracted_data=item.get("extracted_data") or {},
                            warnings=list(item.get("warnings") or []),
                            revision=int(item.get("revision") or 0),
                            filled_at=_parse_iso_dt(item.get("filled_at")),
                        )
                    )
                    imported_forms += 1
            db.flush()
            dossier_service.ensure_section_form_slots(db, sess, commit=False)
            sess.result_summary = session_service.session_summary(db, sess)

        audit.record(
            db,
            action="project.import_archive",
            entity_type="project",
            entity_id=project.id,
            workspace_hash=workspace_hash,
            after={
                "sections": len(created_sessions),
                "forms": imported_forms,
                "results": imported_results,
                "time_series": imported_ts,
                "attachments": imported_attachments,
            },
        )
        db.commit()
        db.refresh(project)
    except Exception:
        db.rollback()
        for p in created_upload_paths:
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass
        raise

    return {
        "project": project_service.serialize_project(project, len(created_sessions)),
        "imported_sections": len(created_sessions),
        "imported_forms": imported_forms,
        "imported_results": imported_results,
        "imported_time_series": imported_ts,
        "imported_attachments": imported_attachments,
    }


def _desktop_status_to_web(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"active", "draft", "completed", "archived"}:
        return raw
    return "active" if raw in {"1", "true"} else "draft"


def import_desktop_db(
    db: OrmSession,
    settings: Settings,
    workspace_hash: str,
    db_bytes: bytes,
    *,
    project_name: str | None = None,
    project_code: str | None = None,
) -> dict[str, Any]:
    """Import sessions, geometry, results and time series from a desktop `hydro.db` SQLite file."""

    if len(db_bytes) < 100 or not db_bytes.startswith(SQLITE_MAGIC):
        raise validation_error(
            "Gecersiz SQLite veritabani dosyasi (SQLite format 3 imzasi bulunamadi).", field="file"
        )
    if len(db_bytes) > settings.max_upload_bytes:
        raise AppError("file_too_large", "Veritabani dosya boyut siniri asildi.", status_code=413)

    tmp_fd, tmp_name = tempfile.mkstemp(prefix="hydro_desktop_", suffix=".db")
    tmp_path = Path(tmp_name)
    try:
        try:
            os.fchmod(tmp_fd, 0o600)
        except OSError:
            pass
        with os.fdopen(tmp_fd, "wb") as handle:
            handle.write(db_bytes)

        conn: sqlite3.Connection | None = None
        try:
            conn = sqlite3.connect(f"file:{tmp_path.as_posix()}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            qcheck = conn.execute("PRAGMA quick_check").fetchone()
            if not qcheck or str(qcheck[0]).lower() != "ok":
                raise validation_error(
                    "SQLite veritabani butunluk kontrolunu gecemedi.", field="file"
                )
            tables = {
                str(r[0])
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            if "sessions" not in tables:
                raise validation_error(
                    "Masaustu veritabaninda 'sessions' tablosu bulunamadi.", field="file"
                )
            sess_rows = conn.execute("SELECT * FROM sessions ORDER BY updated_at ASC").fetchall()
            geom_rows = (
                conn.execute("SELECT * FROM geometry_records").fetchall()
                if "geometry_records" in tables
                else []
            )
            entry_rows = (
                conn.execute("SELECT * FROM test_entries ORDER BY id ASC").fetchall()
                if "test_entries" in tables
                else []
            )
            ts_rows = (
                conn.execute("SELECT * FROM time_series_records ORDER BY id ASC").fetchall()
                if "time_series_records" in tables
                else []
            )
        except sqlite3.DatabaseError as exc:
            raise validation_error(f"SQLite veritabani okunamadi: {exc}", field="file") from exc
        finally:
            if conn is not None:
                conn.close()
    finally:
        tmp_path.unlink(missing_ok=True)

    geom_by_sid: dict[str, sqlite3.Row] = {str(r["session_id"]): r for r in geom_rows}
    entries_by_sid: dict[str, list[sqlite3.Row]] = {}
    for row in entry_rows:
        entries_by_sid.setdefault(str(row["session_id"]), []).append(row)
    ts_by_sid: dict[str, list[sqlite3.Row]] = {}
    for row in ts_rows:
        ts_by_sid.setdefault(str(row["session_id"]), []).append(row)

    target_name = (
        project_name or ""
    ).strip() or f"Masaüstü Hydro DB ({utcnow().strftime('%Y-%m-%d %H:%M')})"
    target_code = (project_code or "").strip()

    project = project_service.create_project(
        db,
        workspace_hash,
        {
            "name": target_name,
            "code": target_code,
            "client": "BOTAŞ",
            "description": "Masaüstü SQLite (hydro.db) veritabanından aktarılan kesitler.",
        },
        commit=False,
    )

    imported_sessions = 0
    imported_results = 0
    imported_ts = 0

    for idx, srow in enumerate(sess_rows, start=1):
        old_sid = str(srow["id"])
        raw_inputs = _safe_json_loads(srow["inputs_json"], {})
        if not isinstance(raw_inputs, dict):
            raw_inputs = {}
        wizard_state = _safe_json_loads(srow["wizard_state_json"], None)

        g_row = geom_by_sid.get(old_sid)
        if g_row is not None and not raw_inputs.get("geometry"):
            raw_inputs["geometry"] = {
                "outside_diameter_mm": g_row["outside_diameter_mm"],
                "wall_thickness_mm": g_row["wall_thickness_mm"],
                "length_m": g_row["length_m"],
            }
            raw_inputs.setdefault(
                "section_profile",
                {
                    "highest_elevation_m": g_row["highest_elevation_m"],
                    "lowest_elevation_m": g_row["lowest_elevation_m"],
                    "design_pressure_bar": g_row["design_pressure_bar"],
                },
            )
            segs = _safe_json_loads(g_row["segments_json"], None)
            if isinstance(segs, list) and segs:
                raw_inputs["segments"] = segs

        inputs = session_service.normalize_inputs(raw_inputs)
        meta = inputs.setdefault("section_meta", {})
        if isinstance(meta, dict) and not str(meta.get("section_no") or "").strip():
            meta["section_no"] = f"K-{idx:02d}"

        sess = HydroSession(
            id=new_uuid(),
            project_id=project.id,
            workspace_id_hash=workspace_hash,
            name=str(srow["name"] or f"Masaüstü Kesit {idx}")[:200],
            status=_desktop_status_to_web("active" if srow["is_active"] else "draft"),
            inputs=inputs,
            wizard_state=wizard_state if isinstance(wizard_state, dict) else None,
            notes=str(srow["notes"] or ""),
            created_at=_parse_iso_dt(srow["created_at"]) or utcnow(),
            updated_at=_parse_iso_dt(srow["updated_at"]) or utcnow(),
        )
        db.add(sess)
        db.flush()
        imported_sessions += 1

        for erow in entries_by_sid.get(old_sid, []):
            dec_status = str(erow["decision_status"] or "BEKLIYOR")[:32]
            dec_title = str(erow["decision_title"] or "")[:200]
            dec_sum = str(erow["decision_summary"] or "")
            db.add(
                TestResult(
                    id=new_uuid(),
                    session_id=sess.id,
                    test_type=str(erow["test_type"] or "air")[:32],
                    inputs=_safe_json_loads(erow["inputs_json"], {}),
                    result=_safe_json_loads(erow["result_json"], {}),
                    decision_status=dec_status,
                    decision_title=dec_title,
                    decision_summary=dec_sum,
                    decision={
                        "status": dec_status,
                        "title": dec_title,
                        "summary": dec_sum,
                    },
                    engine_version="desktop-import",
                    computed_at=_parse_iso_dt(erow["evaluated_at"]) or utcnow(),
                )
            )
            imported_results += 1

        for trow in ts_by_sid.get(old_sid, []):
            ts_dt = _parse_iso_dt(trow["timestamp"]) or utcnow()
            raw_p, raw_t, raw_v = trow["pressure_bar"], trow["temperature_c"], trow["volume_m3"]
            if isinstance(raw_p, bool) or isinstance(raw_t, bool) or isinstance(raw_v, bool):
                continue
            try:
                p_val = float(raw_p if raw_p is not None else 0.0)
                t_val = float(raw_t if raw_t is not None else 0.0)
                v_val = float(raw_v) if raw_v is not None else None
            except (TypeError, ValueError):
                continue
            if (
                not math.isfinite(p_val)
                or not math.isfinite(t_val)
                or (v_val is not None and not math.isfinite(v_val))
            ):
                continue
            db.add(
                TimeSeriesRecord(
                    id=new_uuid(),
                    session_id=sess.id,
                    timestamp=ts_dt,
                    pressure_bar=p_val,
                    temperature_c=t_val,
                    volume_m3=v_val,
                    notes=str(trow["notes"] or ""),
                    source="desktop_db",
                )
            )
            imported_ts += 1

        dossier_service.ensure_section_form_slots(db, sess, commit=False)
        sess.result_summary = session_service.session_summary(db, sess)

    audit.record(
        db,
        action="import.desktop_db",
        entity_type="project",
        entity_id=project.id,
        workspace_hash=workspace_hash,
        after={
            "sessions": imported_sessions,
            "results": imported_results,
            "time_series": imported_ts,
        },
    )
    db.commit()
    db.refresh(project)

    return {
        "project": project_service.serialize_project(project, imported_sessions),
        "imported_sessions": imported_sessions,
        "imported_results": imported_results,
        "imported_time_series": imported_ts,
    }


__all__ = [
    "ARCHIVE_FORMAT",
    "ARCHIVE_SCHEMA_VERSION",
    "export_project_archive",
    "import_desktop_db",
    "import_project_archive",
]
