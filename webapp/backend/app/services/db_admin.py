"""Local SQLite / database management, workspace recovery, backups, trash and maintenance."""

from __future__ import annotations

import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session as OrmSession

from .. import db as db_mod
from ..core import security
from ..core.config import Settings
from ..core.errors import AppError, not_found, validation_error
from ..core.timeutil import iso_z, utcnow
from ..models import (
    Attachment,
    AuditEvent,
    HydroSession,
    OcrAnalysis,
    OcrMappingProfile,
    Project,
    SchemaMigration,
    SectionForm,
    TestResult,
    TimeSeriesRecord,
)
from . import audit
from . import projects as project_service
from . import sessions as session_service

SQLITE_MAGIC = b"SQLite format 3\x00"


def list_workspaces(db: OrmSession, current_workspace_hash: str) -> dict[str, Any]:
    """Summarize all workspaces present in ``projects`` / ``sessions`` so lost keys can recover."""

    proj_rows = db.execute(
        select(
            Project.workspace_id_hash,
            func.count(Project.id),
            func.max(Project.updated_at),
        )
        .where(Project.deleted_at.is_(None))
        .group_by(Project.workspace_id_hash)
    ).all()

    sess_rows = db.execute(
        select(
            HydroSession.workspace_id_hash,
            func.count(HydroSession.id),
            func.max(HydroSession.updated_at),
        )
        .where(HydroSession.deleted_at.is_(None))
        .group_by(HydroSession.workspace_id_hash)
    ).all()

    buckets: dict[str, dict[str, Any]] = {}
    for ws_hash, cnt, last_ts in proj_rows:
        item = buckets.setdefault(
            ws_hash,
            {
                "workspace_hash": ws_hash,
                "hash_short": ws_hash[:10],
                "is_current": ws_hash == current_workspace_hash,
                "project_count": 0,
                "section_count": 0,
                "last_updated_at": None,
                "sample_projects": [],
            },
        )
        item["project_count"] = int(cnt or 0)
        item["_last_dt"] = last_ts

    for ws_hash, cnt, last_ts in sess_rows:
        item = buckets.setdefault(
            ws_hash,
            {
                "workspace_hash": ws_hash,
                "hash_short": ws_hash[:10],
                "is_current": ws_hash == current_workspace_hash,
                "project_count": 0,
                "section_count": 0,
                "last_updated_at": None,
                "sample_projects": [],
            },
        )
        item["section_count"] = int(cnt or 0)
        prev = item.get("_last_dt")
        if prev is None or (last_ts is not None and last_ts > prev):
            item["_last_dt"] = last_ts

    if current_workspace_hash not in buckets:
        buckets[current_workspace_hash] = {
            "workspace_hash": current_workspace_hash,
            "hash_short": current_workspace_hash[:10],
            "is_current": True,
            "project_count": 0,
            "section_count": 0,
            "last_updated_at": None,
            "sample_projects": [],
            "_last_dt": None,
        }

    for ws_hash, item in buckets.items():
        names = (
            db.execute(
                select(Project.name)
                .where(Project.workspace_id_hash == ws_hash, Project.deleted_at.is_(None))
                .order_by(Project.updated_at.desc())
                .limit(4)
            )
            .scalars()
            .all()
        )
        item["sample_projects"] = [str(name) for name in names]
        item["last_updated_at"] = iso_z(item.pop("_last_dt", None))

    items = sorted(
        buckets.values(),
        key=lambda row: (
            not row["is_current"],
            -(row["project_count"] + row["section_count"]),
            row["workspace_hash"],
        ),
    )
    return {"current_workspace_hash": current_workspace_hash, "items": items}


def claim_workspace(
    db: OrmSession,
    *,
    source_workspace_hash: str,
    target_workspace_hash: str,
) -> dict[str, Any]:
    """Reassign all records from ``source_workspace_hash`` into ``target_workspace_hash``."""

    source = source_workspace_hash.strip()
    target = target_workspace_hash.strip()
    if not source or len(source) < 8:
        raise validation_error("Gecersiz kaynak workspace ozeti.", field="source_workspace_hash")
    if source == target:
        raise validation_error(
            "Kaynak ve hedef çalışma alanı aynı olamaz.", field="source_workspace_hash"
        )

    projects = (
        db.execute(select(Project).where(Project.workspace_id_hash == source)).scalars().all()
    )
    sessions = (
        db.execute(select(HydroSession).where(HydroSession.workspace_id_hash == source))
        .scalars()
        .all()
    )
    forms = (
        db.execute(select(SectionForm).where(SectionForm.workspace_id_hash == source))
        .scalars()
        .all()
    )
    attachments = (
        db.execute(select(Attachment).where(Attachment.workspace_id_hash == source)).scalars().all()
    )
    analyses = (
        db.execute(select(OcrAnalysis).where(OcrAnalysis.workspace_id_hash == source))
        .scalars()
        .all()
    )
    profiles = (
        db.execute(select(OcrMappingProfile).where(OcrMappingProfile.workspace_id_hash == source))
        .scalars()
        .all()
    )

    if not any((projects, sessions, forms, attachments, analyses, profiles)):
        raise not_found("workspace", source)

    existing_formats = set(
        db.execute(
            select(OcrMappingProfile.format_key).where(
                OcrMappingProfile.workspace_id_hash == target
            )
        )
        .scalars()
        .all()
    )
    moved_profiles = 0
    for prof in profiles:
        if prof.format_key in existing_formats:
            # Keep target profile, avoid unique constraint collision while still updating referencing analyses
            replacement = db.scalar(
                select(OcrMappingProfile.id).where(
                    OcrMappingProfile.workspace_id_hash == target,
                    OcrMappingProfile.format_key == prof.format_key,
                )
            )
            for item in analyses:
                if item.mapping_profile_id == prof.id:
                    item.mapping_profile_id = replacement
            db.delete(prof)
        else:
            prof.workspace_id_hash = target
            existing_formats.add(prof.format_key)
            moved_profiles += 1

    for project_row in projects:
        project_row.workspace_id_hash = target
    for session_row in sessions:
        session_row.workspace_id_hash = target
    for form_row in forms:
        form_row.workspace_id_hash = target
    for attachment_row in attachments:
        attachment_row.workspace_id_hash = target
    for analysis_row in analyses:
        analysis_row.workspace_id_hash = target

    moved = {
        "projects": len(projects),
        "sessions": len(sessions),
        "section_forms": len(forms),
        "attachments": len(attachments),
        "ocr_analyses": len(analyses),
        "mapping_profiles": moved_profiles,
    }
    audit.record(
        db,
        action="workspace.claim",
        entity_type="workspace",
        entity_id=target,
        workspace_hash=target,
        before={"source_workspace_hash": source},
        after=moved,
    )
    db.commit()
    return {"source_workspace_hash": source, "target_workspace_hash": target, "moved": moved}


def _sqlite_db_path(settings: Settings) -> Path | None:
    try:
        parsed = make_url(settings.database_url)
    except Exception:
        return None
    if not parsed.drivername.startswith("sqlite"):
        return None
    db_file = parsed.database
    if not db_file or db_file == ":memory:":
        return None
    return Path(db_file).expanduser().resolve()


def _backups_dir(settings: Settings) -> Path:
    path = settings.data_dir / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _dir_usage(root: Path) -> tuple[int, int]:
    if not root.exists():
        return 0, 0
    total_bytes = 0
    count = 0
    for item in root.rglob("*"):
        if item.is_file():
            try:
                total_bytes += item.stat().st_size
                count += 1
            except OSError:
                continue
    return total_bytes, count


def get_db_stats(db: OrmSession, settings: Settings, current_workspace_hash: str) -> dict[str, Any]:
    """Collect SQLite/DB engine health, schema version, table counts and local storage usage."""

    db_path = _sqlite_db_path(settings)
    is_sqlite = db_mod._is_sqlite(settings.database_url)
    engine = db_mod.get_engine()
    schema_version = (
        db.scalar(select(func.max(SchemaMigration.version))) or db_mod.CURRENT_MIGRATION
    )

    db_size = 0
    wal_size = 0
    shm_size = 0
    if db_path is not None and db_path.exists():
        try:
            db_size = db_path.stat().st_size
        except OSError:
            db_size = 0
        wal_path = Path(f"{db_path}-wal")
        shm_path = Path(f"{db_path}-shm")
        if wal_path.exists():
            try:
                wal_size = wal_path.stat().st_size
            except OSError:
                wal_size = 0
        if shm_path.exists():
            try:
                shm_size = shm_path.stat().st_size
            except OSError:
                shm_size = 0

    journal_mode = "n/a"
    integrity_status = "unknown"
    if is_sqlite:
        try:
            jm = db.execute(text("PRAGMA journal_mode")).scalar()
            journal_mode = str(jm or "unknown")
        except Exception:
            journal_mode = "unknown"
        try:
            qc = db.execute(text("PRAGMA quick_check")).scalar()
            integrity_status = str(qc or "unknown")
        except Exception:
            integrity_status = "error"
    else:
        integrity_status = "ok"

    uploads_bytes, uploads_files = _dir_usage(settings.uploads_dir)
    exports_bytes, exports_files = _dir_usage(settings.exports_dir)
    backups_dir = _backups_dir(settings)
    backups_bytes, backups_count = _dir_usage(backups_dir)

    table_counts = {
        "projects": int(
            db.scalar(select(func.count(Project.id)).where(Project.deleted_at.is_(None))) or 0
        ),
        "projects_deleted": int(
            db.scalar(select(func.count(Project.id)).where(Project.deleted_at.is_not(None))) or 0
        ),
        "sessions": int(
            db.scalar(select(func.count(HydroSession.id)).where(HydroSession.deleted_at.is_(None)))
            or 0
        ),
        "sessions_deleted": int(
            db.scalar(
                select(func.count(HydroSession.id)).where(HydroSession.deleted_at.is_not(None))
            )
            or 0
        ),
        "test_results": int(db.scalar(select(func.count(TestResult.id))) or 0),
        "time_series": int(db.scalar(select(func.count(TimeSeriesRecord.id))) or 0),
        "section_forms": int(db.scalar(select(func.count(SectionForm.id))) or 0),
        "attachments": int(db.scalar(select(func.count(Attachment.id))) or 0),
        "ocr_analyses": int(db.scalar(select(func.count(OcrAnalysis.id))) or 0),
        "audit_events": int(db.scalar(select(func.count(AuditEvent.id))) or 0),
    }

    workspaces = list_workspaces(db, current_workspace_hash)
    return {
        "dialect": engine.dialect.name,
        "is_sqlite": is_sqlite,
        "db_path": str(db_path) if db_path else None,
        "schema_migration": str(schema_version),
        "db_size_bytes": db_size,
        "wal_size_bytes": wal_size,
        "shm_size_bytes": shm_size,
        "journal_mode": journal_mode,
        "integrity_status": integrity_status,
        "table_counts": table_counts,
        "storage": {
            "uploads_bytes": uploads_bytes,
            "uploads_files": uploads_files,
            "exports_bytes": exports_bytes,
            "exports_files": exports_files,
            "backups_bytes": backups_bytes,
            "backups_count": backups_count,
        },
        "workspace_count": len(workspaces["items"]),
        "current_workspace_hash": current_workspace_hash,
    }


def list_db_backups(settings: Settings) -> dict[str, Any]:
    """List verified local SQLite backups under ``data_dir/backups``."""

    bdir = _backups_dir(settings)
    items: list[dict[str, Any]] = []
    for path in bdir.iterdir():
        if not path.is_file() or path.suffix.lower() != ".db":
            continue
        try:
            st = path.stat()
        except OSError:
            continue
        items.append(
            {
                "filename": path.name,
                "size_bytes": st.st_size,
                "created_at": iso_z(datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)),
                "_mtime": st.st_mtime,
            }
        )
    items.sort(key=lambda r: float(r.pop("_mtime", 0.0)), reverse=True)
    return {"items": items, "total": len(items), "backups_dir": str(bdir)}


def resolve_backup_path(settings: Settings, filename: str) -> Path:
    bdir = _backups_dir(settings)
    clean = security.safe_filename(filename)
    if not clean.endswith(".db"):
        raise validation_error("Gecersiz yedek dosya adi (.db bekleniyor).", field="filename")
    target = security.ensure_within(bdir, bdir / clean)
    if not target.exists() or not target.is_file():
        raise not_found("backup", clean)
    return target


def create_db_backup(settings: Settings, *, reason: str = "manual") -> dict[str, Any]:
    """Create a hot online SQLite backup via ``sqlite3.Connection.backup``."""

    db_path = _sqlite_db_path(settings)
    if db_path is None:
        raise validation_error(
            "Anlik yedekleme yalnizca yerel dosya tabanli SQLite veritabani icin kullanilabilir."
        )
    if not db_path.exists():
        raise not_found("database", str(db_path))

    bdir = _backups_dir(settings)
    stamp = utcnow().strftime("%Y%m%d_%H%M%S_%f")[:18]
    safe_reason = security.safe_filename(reason.strip() or "manual")[:24].strip("._") or "manual"
    filename = f"hydro_{stamp}_{safe_reason}.db"
    target = security.ensure_within(bdir, bdir / filename)
    tmp_path = bdir / f".tmp_{filename}"

    try:
        fd = os.open(str(tmp_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        src = sqlite3.connect(str(db_path), timeout=30.0)
        dst = sqlite3.connect(str(tmp_path), timeout=30.0)
        try:
            src.backup(dst)
            dst.commit()
            qcheck = dst.execute("PRAGMA quick_check").fetchone()
            if not qcheck or str(qcheck[0]).lower() != "ok":
                raise AppError(
                    "backup_corrupt", "Yedek dosyasi butunluk testini gecemedi.", status_code=500
                )
        finally:
            dst.close()
            src.close()
        os.replace(tmp_path, target)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)

    st = target.stat()
    return {
        "filename": target.name,
        "size_bytes": st.st_size,
        "reason": safe_reason,
        "created_at": iso_z(utcnow()),
    }


def _validate_sqlite_backup_file(path: Path) -> None:
    head = path.read_bytes()[:16] if path.exists() else b""
    if not head.startswith(SQLITE_MAGIC):
        raise validation_error("Yedek dosyasi gecerli bir SQLite veritabani degil.", field="file")
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        ic = conn.execute("PRAGMA integrity_check").fetchone()
        if not ic or str(ic[0]).lower() != "ok":
            raise validation_error("Yedek veritabani butunluk kontrolunu gecemedi.", field="file")
        tables = {
            str(r[0])
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        required = {"projects", "sessions"}
        if not required.issubset(tables):
            raise validation_error(
                "Yedek dosyasi HYDRO web veritabani semasi icermiyor (projects/sessions eksik).",
                field="file",
            )
    except sqlite3.DatabaseError as exc:
        raise validation_error(f"SQLite yedek dosyasi bozuk: {exc}", field="file") from exc
    finally:
        conn.close()


def restore_db_backup(
    settings: Settings,
    *,
    backup_bytes: bytes | None = None,
    backup_filename: str | None = None,
    workspace_hash: str = "",
) -> dict[str, Any]:
    """Validate a SQLite backup, save a ``pre_restore`` snapshot, replace live DB cleanly and re-migrate."""

    db_path = _sqlite_db_path(settings)
    if db_path is None:
        raise validation_error(
            "Geri yukleme yalnizca yerel dosya tabanli SQLite veritabani icin kullanilabilir."
        )
    if backup_bytes is None and not backup_filename:
        raise validation_error("Geri yukleme icin yedek dosyasi veya dosya adi gereklidir.")

    temp_source: Path | None = None
    try:
        if backup_bytes is not None:
            if len(backup_bytes) < 100 or not backup_bytes.startswith(SQLITE_MAGIC):
                raise validation_error(
                    "Yuklenen dosya gecerli bir SQLite veritabani degil.", field="file"
                )
            if len(backup_bytes) > settings.max_upload_bytes:
                raise AppError(
                    "file_too_large", "Yedek dosyasi boyut sinirini asti.", status_code=413
                )
            fd, tmp_name = tempfile.mkstemp(prefix="hydro_restore_", suffix=".db")
            temp_source = Path(tmp_name)
            try:
                os.fchmod(fd, 0o600)
            except OSError:
                pass
            with os.fdopen(fd, "wb") as handle:
                handle.write(backup_bytes)
            source_path = temp_source
            source_label = "uploaded_file"
        else:
            source_path = resolve_backup_path(settings, str(backup_filename))
            source_label = source_path.name

        _validate_sqlite_backup_file(source_path)

        pre_backup: dict[str, Any] | None = None
        if db_path.exists() and db_path.stat().st_size > 0:
            pre_backup = create_db_backup(settings, reason="pre_restore")

        db_mod.dispose_database()

        for sidecar in (Path(f"{db_path}-wal"), Path(f"{db_path}-shm")):
            if sidecar.exists():
                try:
                    sidecar.unlink()
                except OSError:
                    pass

        src = sqlite3.connect(str(source_path), timeout=30.0)
        dst = sqlite3.connect(str(db_path), timeout=30.0)
        try:
            src.backup(dst)
            dst.commit()
        finally:
            dst.close()
            src.close()

        db_mod.configure_database(settings.database_url)
        db_mod.init_db()

        with db_mod.session_scope() as fresh_db:
            if workspace_hash:
                audit.record(
                    fresh_db,
                    action="db.restore",
                    entity_type="database",
                    entity_id=db_path.name,
                    workspace_hash=workspace_hash,
                    after={"source": source_label, "pre_backup": pre_backup},
                )
            stats = get_db_stats(
                fresh_db,
                settings,
                workspace_hash or security.workspace_hash(security.DEFAULT_WORKSPACE),
            )

        return {
            "restored": True,
            "source": source_label,
            "pre_restore_backup": pre_backup,
            "stats": stats,
        }
    finally:
        if temp_source is not None and temp_source.exists():
            temp_source.unlink(missing_ok=True)


def list_trash(db: OrmSession, workspace_hash: str) -> dict[str, Any]:
    """List soft-deleted projects and sections in the active workspace."""

    deleted_projects = (
        db.execute(
            select(Project)
            .where(Project.workspace_id_hash == workspace_hash, Project.deleted_at.is_not(None))
            .order_by(Project.deleted_at.desc())
        )
        .scalars()
        .all()
    )
    deleted_sessions = (
        db.execute(
            select(HydroSession)
            .where(
                HydroSession.workspace_id_hash == workspace_hash,
                HydroSession.deleted_at.is_not(None),
            )
            .order_by(HydroSession.deleted_at.desc())
        )
        .scalars()
        .all()
    )

    items: list[dict[str, Any]] = []
    for proj in deleted_projects:
        cnt = int(
            db.scalar(select(func.count(HydroSession.id)).where(HydroSession.project_id == proj.id))
            or 0
        )
        items.append(
            {
                "entity_type": "project",
                "id": proj.id,
                "name": proj.name,
                "code": proj.code or "",
                "project_id": proj.id,
                "section_count": cnt,
                "deleted_at": iso_z(proj.deleted_at),
            }
        )
    for sess in deleted_sessions:
        items.append(
            {
                "entity_type": "session",
                "id": sess.id,
                "name": sess.name,
                "code": str(
                    ((sess.inputs or {}).get("section_meta") or {}).get("section_no") or ""
                ),
                "project_id": sess.project_id,
                "section_count": None,
                "deleted_at": iso_z(sess.deleted_at),
            }
        )
    return {"items": items, "total": len(items)}


def restore_trash_item(
    db: OrmSession,
    workspace_hash: str,
    *,
    entity_type: str,
    entity_id: str,
) -> dict[str, Any]:
    """Restore a soft-deleted project or section back into active workspace views."""

    now = utcnow()
    if entity_type == "project":
        proj = db.get(Project, entity_id)
        if proj is None or proj.workspace_id_hash != workspace_hash or proj.deleted_at is None:
            raise not_found("deleted_project", entity_id)
        proj.deleted_at = None
        proj.updated_at = now
        restored_sessions = 0
        child_sessions = (
            db.execute(
                select(HydroSession).where(
                    HydroSession.project_id == proj.id,
                    HydroSession.workspace_id_hash == workspace_hash,
                    HydroSession.deleted_at.is_not(None),
                )
            )
            .scalars()
            .all()
        )
        for sess in child_sessions:
            sess.deleted_at = None
            sess.updated_at = now
            sess.revision = int(sess.revision or 1) + 1
            restored_sessions += 1
        audit.record(
            db,
            action="trash.restore",
            entity_type="project",
            entity_id=proj.id,
            workspace_hash=workspace_hash,
            after={"restored_sessions": restored_sessions},
        )
        db.commit()
        return {
            "entity_type": "project",
            "id": proj.id,
            "restored_sessions": restored_sessions,
        }

    if entity_type == "session":
        restored_sess = db.get(HydroSession, entity_id)
        if (
            restored_sess is None
            or restored_sess.workspace_id_hash != workspace_hash
            or restored_sess.deleted_at is None
        ):
            raise not_found("deleted_session", entity_id)
        restored_sess.deleted_at = None
        restored_sess.updated_at = now
        restored_sess.revision = int(restored_sess.revision or 1) + 1
        if restored_sess.project_id:
            parent = db.get(Project, restored_sess.project_id)
            if (
                parent is not None
                and parent.workspace_id_hash == workspace_hash
                and parent.deleted_at is not None
            ):
                parent.deleted_at = None
                parent.updated_at = now
        audit.record(
            db,
            action="trash.restore",
            entity_type="session",
            entity_id=restored_sess.id,
            session_id=restored_sess.id,
            workspace_hash=workspace_hash,
        )
        db.commit()
        return {"entity_type": "session", "id": restored_sess.id, "restored_sessions": 1}

    raise validation_error("Desteklenmeyen cop ogesi turu.", field="entity_type")


def purge_trash_item(
    db: OrmSession,
    settings: Settings,
    workspace_hash: str,
    *,
    entity_type: str,
    entity_id: str,
) -> dict[str, Any]:
    """Permanently delete a previously soft-deleted project or section."""

    if entity_type == "project":
        proj = db.get(Project, entity_id)
        if proj is None or proj.workspace_id_hash != workspace_hash or proj.deleted_at is None:
            raise not_found("deleted_project", entity_id)
        project_service.delete_project(db, proj, hard=True, uploads_dir=settings.uploads_dir)
        return {"purged": True, "entity_type": "project", "id": entity_id}

    if entity_type == "session":
        sess = db.get(HydroSession, entity_id)
        if sess is None or sess.workspace_id_hash != workspace_hash or sess.deleted_at is None:
            raise not_found("deleted_session", entity_id)
        session_service.delete_session(db, sess, hard=True, uploads_dir=settings.uploads_dir)
        return {"purged": True, "entity_type": "session", "id": entity_id}

    raise validation_error("Desteklenmeyen cop ogesi turu.", field="entity_type")


def run_db_maintenance(
    db: OrmSession,
    settings: Settings,
    workspace_hash: str,
    *,
    checkpoint_wal: bool = True,
    vacuum: bool = False,
    clean_exports: bool = True,
    clean_orphan_uploads: bool = False,
) -> dict[str, Any]:
    """Run SQLite maintenance (integrity_check, WAL checkpoint, optional VACUUM) and clean temporary/orphan files."""

    integrity = "ok"
    wal_checkpointed = False
    vacuumed = False
    is_sqlite = db_mod._is_sqlite(settings.database_url)

    if is_sqlite:
        row = db.execute(text("PRAGMA integrity_check")).scalar()
        integrity = str(row or "unknown")
        if checkpoint_wal:
            db.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))
            db.commit()
            wal_checkpointed = True
        if vacuum:
            db.commit()
            with (
                db_mod.get_engine()
                .connect()
                .execution_options(isolation_level="AUTOCOMMIT") as conn
            ):
                conn.execute(text("VACUUM"))
            vacuumed = True

    removed_export_files = 0
    reclaimed_export_bytes = 0
    if clean_exports and settings.exports_dir.exists():
        for item in settings.exports_dir.iterdir():
            if item.is_file():
                try:
                    sz = item.stat().st_size
                    item.unlink()
                    removed_export_files += 1
                    reclaimed_export_bytes += sz
                except OSError:
                    continue

    removed_orphan_files = 0
    reclaimed_upload_bytes = 0
    if clean_orphan_uploads and settings.uploads_dir.exists():
        # Safety check: query referenced stored paths across ALL workspaces before deleting anything!
        all_paths = set(
            str(p) for p in db.execute(select(Attachment.stored_path)).scalars().all() if p
        )
        uploads_root = settings.uploads_dir.resolve()
        referenced_abs: set[Path] = set()
        for rel in all_paths:
            try:
                referenced_abs.add((uploads_root / rel).resolve())
            except Exception:
                continue
        for item in uploads_root.rglob("*"):
            if not item.is_file():
                continue
            if item.name.startswith(".tmp-"):
                continue
            try:
                resolved_item = item.resolve()
            except OSError:
                continue
            if resolved_item not in referenced_abs:
                try:
                    sz = item.stat().st_size
                    item.unlink()
                    removed_orphan_files += 1
                    reclaimed_upload_bytes += sz
                except OSError:
                    continue

    result = {
        "integrity_status": integrity,
        "wal_checkpointed": wal_checkpointed,
        "vacuumed": vacuumed,
        "removed_export_files": removed_export_files,
        "reclaimed_export_bytes": reclaimed_export_bytes,
        "removed_orphan_files": removed_orphan_files,
        "reclaimed_upload_bytes": reclaimed_upload_bytes,
    }
    audit.record(
        db,
        action="db.maintenance",
        entity_type="database",
        entity_id="hydro.db",
        workspace_hash=workspace_hash,
        after=result,
    )
    db.commit()
    return result


__all__ = [
    "claim_workspace",
    "create_db_backup",
    "get_db_stats",
    "list_db_backups",
    "list_trash",
    "list_workspaces",
    "purge_trash_item",
    "resolve_backup_path",
    "restore_db_backup",
    "restore_trash_item",
    "run_db_maintenance",
]
