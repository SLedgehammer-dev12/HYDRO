"""Project CRUD routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session as OrmSession

from .. import schemas
from ..core.timeutil import json_safe
from ..db import get_db
from ..services import projects as project_service
from .deps import Workspace, get_workspace

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("")
def list_projects(
    response: Response,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None, max_length=200),
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    payload = project_service.list_projects(
        db, workspace.hash, limit=limit, offset=offset, q=q
    )
    response.headers["X-Total-Count"] = str(payload["total"])
    return json_safe(payload)


@router.post("", status_code=201)
def create_project(
    payload: schemas.ProjectCreate,
    response: Response,
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    project = project_service.create_project(db, workspace.hash, payload)
    response.headers["Location"] = f"/api/projects/{project.id}"
    return json_safe(project_service.serialize_project(project))


@router.get("/{project_id}")
def get_project(
    project_id: str,
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    project = project_service.get_project(db, project_id, workspace.hash)
    count = project_service.section_count(db, project.id)
    return json_safe(project_service.serialize_project(project, count))


@router.put("/{project_id}")
def update_project(
    project_id: str,
    payload: schemas.ProjectUpdate,
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    project = project_service.get_project(db, project_id, workspace.hash)
    project = project_service.update_project(
        db, project, changes=payload.model_dump(exclude_unset=True)
    )
    count = project_service.section_count(db, project.id)
    return json_safe(project_service.serialize_project(project, count))


@router.delete("/{project_id}", status_code=204)
def delete_project(
    project_id: str,
    hard: bool = Query(default=False),
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> Response:
    project = project_service.get_project(db, project_id, workspace.hash)
    project_service.delete_project(db, project, hard=hard)
    return Response(status_code=204)


__all__ = ["router"]
