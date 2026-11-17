"""Project persistence: CRUD, listing and section (session) counts."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as OrmSession

from ..core.errors import not_found, validation_error
from ..core.timeutil import iso_z, utcnow
from ..models import HydroSession, Project, SectionForm, new_uuid
from . import audit

# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


def serialize_project(project: Project, section_count: int = 0) -> dict[str, Any]:
    return {
        "id": project.id,
        "code": project.code or "",
        "name": project.name,
        "client": project.client,
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
    description = _payload_get(payload, "description")

    project = Project(
        id=new_uuid(),
        workspace_id_hash=workspace_hash,
        code=code,
        name=name,
        client=client,
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
        after={"name": project.name, "code": project.code, "client": project.client},
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
) -> None:
    now = utcnow()
    sessions = (
        db.execute(select(HydroSession).where(HydroSession.project_id == project.id))
        .scalars()
        .all()
    )
    if hard:
        forms = (
            db.execute(select(SectionForm).where(SectionForm.project_id == project.id))
            .scalars()
            .all()
        )
        for form in forms:
            db.delete(form)
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


__all__ = [
    "create_project",
    "delete_project",
    "get_project",
    "list_projects",
    "section_count",
    "serialize_project",
    "update_project",
]
