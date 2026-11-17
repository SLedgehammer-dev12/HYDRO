"""Project CRUD routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from sqlalchemy.orm import Session as OrmSession

from .. import schemas
from ..core.timeutil import json_safe
from ..db import get_db
from ..services import dossier as dossier_service
from ..services import plan_profile as plan_profile_service
from ..services import projects as project_service
from ..services import scene as scene_service
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
    payload = project_service.list_projects(db, workspace.hash, limit=limit, offset=offset, q=q)
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


@router.get("/{project_id}/scene")
def get_project_scene(
    project_id: str,
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    return json_safe(scene_service.build_project_scene(db, project_id, workspace.hash))


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


@router.post("/plan-profile/scan")
def scan_plan_profile(
    file: UploadFile = File(...),
    max_section_length_m: float = Form(default=12_000.0),
    max_elevation_diff_m: float | None = Form(default=None),
    language: str | None = Form(default=None),
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    payload = plan_profile_service.scan_plan_profile_upload(
        file_name=file.filename,
        stream=file.file,
        max_section_length_m=max_section_length_m,
        max_elevation_diff_m=max_elevation_diff_m,
        language=language,
    )
    payload["similar_projects"] = dossier_service.find_similar_projects(
        db,
        workspace.hash,
        payload.get("detected_project_name"),
        threshold=0.70,
    )
    return json_safe(payload)


@router.post("/plan-profile/commit", status_code=201)
def commit_plan_profile(
    payload: schemas.PlanProfileCommitRequest,
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    if payload.project_id:
        project = project_service.get_project(db, payload.project_id, workspace.hash)
    else:
        name = (payload.project_name or "").strip()
        if not name:
            from ..core.errors import validation_error

            raise validation_error(
                "Hedef proje secilmeli veya yeni proje adi girilmelidir.",
                field="project_name",
            )
        project = project_service.create_project(
            db,
            workspace.hash,
            {"name": name, "code": (payload.project_code or "").strip(), "client": "BOTAŞ"},
        )
    result = plan_profile_service.create_sections_from_drafts(
        db,
        workspace_hash=workspace.hash,
        project_id=project.id,
        drafts=[item.model_dump() for item in payload.sections],
    )
    result["project"] = project_service.serialize_project(
        project, project_service.section_count(db, project.id)
    )
    return json_safe(result)


@router.post("/{project_id}/sections/batch", status_code=201)
def create_sections_batch(
    project_id: str,
    payload: schemas.DraftSectionBatchCreate,
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    result = plan_profile_service.create_sections_from_drafts(
        db,
        workspace_hash=workspace.hash,
        project_id=project_id,
        drafts=[item.model_dump() for item in payload.sections],
    )
    return json_safe(result)


__all__ = ["router"]
