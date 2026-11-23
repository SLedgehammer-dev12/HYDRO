"""Project persistence: CRUD, listing and section (session) counts."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as OrmSession

from ..core.errors import not_found, validation_error
from ..core.timeutil import as_float, iso_z, utcnow
from ..models import Attachment, HydroSession, OcrAnalysis, Project, SectionForm, new_uuid
from . import audit
from .sessions import _unlink_stored_attachments

_DEFAULT_STR_KEYS = (
    "material_grade",
    "location_class",
    "pump_location",
    "spec_code",
    "size_option",
    "schedule_option",
)
_DEFAULT_NUM_KEYS = (
    "outside_diameter_mm",
    "wall_thickness_mm",
    "smys_mpa",
    "design_pressure_bar",
    "k_factor",
    "steel_alpha_micro_per_c",
)
_VALID_PROJECT_STATUSES = {"active", "completed", "archived"}

# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


def normalize_project_defaults(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    cleaned: dict[str, Any] = {}
    for key in _DEFAULT_STR_KEYS:
        val = raw.get(key)
        if val is not None:
            text = str(val).strip()
            if text:
                cleaned[key] = text[:160]
    for key in _DEFAULT_NUM_KEYS:
        num = as_float(raw.get(key))
        if num is not None and math.isfinite(num) and num > 0:
            cleaned[key] = round(num, 4)
    return cleaned


def _clean_length(value: Any) -> float | None:
    num = as_float(value)
    if num is None or not math.isfinite(num) or num <= 0:
        return None
    return round(num, 2)


def serialize_project(project: Project, section_count: int = 0) -> dict[str, Any]:
    raw_status = (getattr(project, "status", None) or "active").strip().lower()
    status = raw_status if raw_status in _VALID_PROJECT_STATUSES else "active"
    return {
        "id": project.id,
        "code": project.code or "",
        "name": project.name,
        "client": project.client,
        "contractor": getattr(project, "contractor", None),
        "supervisor": getattr(project, "supervisor", None),
        "pipeline_length_m": getattr(project, "pipeline_length_m", None),
        "status": status,
        "defaults": normalize_project_defaults(getattr(project, "defaults", None)),
        "description": project.description,
        "section_count": int(section_count or 0),
        "created_at": iso_z(project.created_at),
        "updated_at": iso_z(project.updated_at),
    }


def _payload_get(payload: Any, key: str, default: Any = None) -> Any:
    if isinstance(payload, dict):
        return payload.get(key, default)
    return getattr(payload, key, default)


def _clean_optional(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def section_count(db: OrmSession, project_id: str) -> int:
    count = db.scalar(
        select(func.count(HydroSession.id)).where(
            HydroSession.project_id == project_id,
            HydroSession.deleted_at.is_(None),
        )
    )
    return int(count or 0)


def get_project(db: OrmSession, project_id: str, workspace_hash: str) -> Project:
    project = db.get(Project, project_id)
    if (
        project is None
        or project.workspace_id_hash != workspace_hash
        or project.deleted_at is not None
    ):
        raise not_found("project", project_id)
    return project


def list_projects(
    db: OrmSession,
    workspace_hash: str,
    *,
    limit: int = 50,
    offset: int = 0,
    q: str | None = None,
) -> dict[str, Any]:
    conditions = [
        Project.workspace_id_hash == workspace_hash,
        Project.deleted_at.is_(None),
    ]
    if q:
        like = f"%{q.strip()}%"
        conditions.append(
            or_(
                Project.name.ilike(like),
                Project.code.ilike(like),
                Project.client.ilike(like),
            )
        )

    counts = (
        select(
            HydroSession.project_id.label("project_id"),
            func.count(HydroSession.id).label("section_count"),
        )
        .where(
            HydroSession.project_id.is_not(None),
            HydroSession.deleted_at.is_(None),
        )
        .group_by(HydroSession.project_id)
        .subquery()
    )

    total = db.scalar(select(func.count(Project.id)).where(*conditions)) or 0
    rows = db.execute(
        select(Project, func.coalesce(counts.c.section_count, 0))
        .outerjoin(counts, counts.c.project_id == Project.id)
        .where(*conditions)
        .order_by(Project.updated_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    return {
        "items": [serialize_project(project, count) for project, count in rows],
        "total": int(total),
        "limit": limit,
        "offset": offset,
    }


def create_project(
    db: OrmSession,
    workspace_hash: str,
    payload: Any,
    *,
    commit: bool = True,
) -> Project:
    name = str(_payload_get(payload, "name") or "").strip()
    if not name:
        raise validation_error("Proje adi bos olamaz.", field="name")
    code = str(_payload_get(payload, "code") or "").strip()
    client = _clean_optional(_payload_get(payload, "client"))
    contractor = _clean_optional(_payload_get(payload, "contractor"))
    supervisor = _clean_optional(_payload_get(payload, "supervisor"))
    pipeline_length_m = _clean_length(_payload_get(payload, "pipeline_length_m"))
    raw_status = str(_payload_get(payload, "status") or "active").strip().lower()
    status = raw_status if raw_status in _VALID_PROJECT_STATUSES else "active"
    defaults = normalize_project_defaults(_payload_get(payload, "defaults"))
    description = _payload_get(payload, "description")

    project = Project(
        id=new_uuid(),
        workspace_id_hash=workspace_hash,
        code=code,
        name=name,
        client=client,
        contractor=contractor,
        supervisor=supervisor,
        pipeline_length_m=pipeline_length_m,
        status=status,
        defaults=defaults,
        description=None if description is None else str(description),
    )
    db.add(project)
    db.flush()
    audit.record(
        db,
        action="project.create",
        entity_type="project",
        entity_id=project.id,
        workspace_hash=workspace_hash,
        after={
            "name": project.name,
            "code": project.code,
            "client": project.client,
            "contractor": project.contractor,
        },
    )
    if commit:
        db.commit()
        db.refresh(project)
    return project


def update_project(
    db: OrmSession,
    project: Project,
    *,
    changes: dict[str, Any],
) -> Project:
    before = {
        "name": project.name,
        "code": project.code,
        "client": project.client,
        "contractor": project.contractor,
        "supervisor": project.supervisor,
        "pipeline_length_m": project.pipeline_length_m,
        "status": project.status,
        "defaults": project.defaults or {},
        "description": project.description,
    }

    if "name" in changes:
        name = str(changes.get("name") or "").strip()
        if not name:
            raise validation_error("Proje adi bos olamaz.", field="name")
        project.name = name
    if "code" in changes:
        project.code = str(changes.get("code") or "").strip()
    if "client" in changes:
        project.client = _clean_optional(changes.get("client"))
    if "contractor" in changes:
        project.contractor = _clean_optional(changes.get("contractor"))
    if "supervisor" in changes:
        project.supervisor = _clean_optional(changes.get("supervisor"))
    if "pipeline_length_m" in changes:
        project.pipeline_length_m = _clean_length(changes.get("pipeline_length_m"))
    if "status" in changes and changes.get("status") is not None:
        raw_status = str(changes.get("status")).strip().lower()
        if raw_status in _VALID_PROJECT_STATUSES:
            project.status = raw_status
    if "defaults" in changes and changes.get("defaults") is not None:
        project.defaults = normalize_project_defaults(changes.get("defaults"))
    if "description" in changes:
        value = changes.get("description")
        project.description = None if value is None else str(value)

    project.updated_at = utcnow()
    audit.record(
        db,
        action="project.update",
        entity_type="project",
        entity_id=project.id,
        workspace_hash=project.workspace_id_hash,
        before=before,
        after={
            "name": project.name,
            "code": project.code,
            "client": project.client,
            "contractor": project.contractor,
            "supervisor": project.supervisor,
            "pipeline_length_m": project.pipeline_length_m,
            "status": project.status,
            "description": project.description,
        },
    )
    db.commit()
    db.refresh(project)
    return project


def delete_project(
    db: OrmSession,
    project: Project,
    *,
    hard: bool = False,
    uploads_dir: Path | None = None,
) -> None:
    now = utcnow()
    sessions = (
        db.execute(select(HydroSession).where(HydroSession.project_id == project.id))
        .scalars()
        .all()
    )
    stored_paths: list[str] = []
    if hard:
        session_ids = [session.id for session in sessions]
        if session_ids:
            attachments = (
                db.execute(select(Attachment).where(Attachment.session_id.in_(session_ids)))
                .scalars()
                .all()
            )
            attachment_ids = [att.id for att in attachments]
            stored_paths = [att.stored_path for att in attachments if att.stored_path]
            if attachment_ids:
                analyses = (
                    db.execute(
                        select(OcrAnalysis).where(OcrAnalysis.attachment_id.in_(attachment_ids))
                    )
                    .scalars()
                    .all()
                )
                for item in analyses:
                    db.delete(item)
                for att in attachments:
                    db.delete(att)
        forms = (
            db.execute(select(SectionForm).where(SectionForm.project_id == project.id))
            .scalars()
            .all()
        )
        for form in forms:
            db.delete(form)
        db.flush()
        for session in sessions:
            db.delete(session)
        db.flush()
        db.delete(project)
    else:
        for session in sessions:
            if session.deleted_at is None:
                session.deleted_at = now
                session.updated_at = now
                session.revision = int(session.revision or 1) + 1
        project.deleted_at = now
        project.updated_at = now

    audit.record(
        db,
        action="project.delete",
        entity_type="project",
        entity_id=project.id,
        workspace_hash=project.workspace_id_hash,
        after={"hard": hard, "deleted_sessions": len(sessions)},
    )
    db.commit()
    if hard:
        _unlink_stored_attachments(db, stored_paths, uploads_dir)


__all__ = [
    "create_project",
    "delete_project",
    "get_project",
    "list_projects",
    "normalize_project_defaults",
    "section_count",
    "serialize_project",
    "update_project",
]
