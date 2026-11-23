"""Project CRUD routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session as OrmSession

from .. import schemas
from ..core import security
from ..core.config import Settings
from ..core.rate_limit import enforce_rate_limit
from ..core.timeutil import json_safe
from ..db import get_db
from ..services import dossier as dossier_service
from ..services import plan_profile as plan_profile_service
from ..services import project_archive as project_archive_service
from ..services import project_data as project_data_service
from ..services import projects as project_service
from ..services import scene as scene_service
from .deps import Workspace, get_settings, get_workspace

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


@router.post("/generate-sample", status_code=201)
def generate_sample_project(
    payload: schemas.SampleProjectGenerateRequest,
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    return json_safe(
        project_data_service.generate_sample_project(
            db,
            workspace.hash,
            scenario=payload.scenario,
            section_count=payload.section_count,
            name=payload.name,
            code=payload.code,
            include_time_series=payload.include_time_series,
            include_forms=payload.include_forms,
        )
    )


@router.post("/import-archive", status_code=201)
async def import_project_archive(
    request: Request,
    file: UploadFile = File(...),
    target_project_name: str | None = Form(default=None),
    target_project_code: str | None = Form(default=None),
    include_attachments: bool = Form(default=True),
    db: OrmSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    enforce_rate_limit(request, settings, bucket="project_import", limit=30)
    archive_bytes = await security.read_upload_bounded(
        file, min(settings.max_upload_bytes, project_archive_service.MAX_ARCHIVE_BYTES)
    )
    return json_safe(
        project_archive_service.import_project_archive(
            db,
            settings,
            workspace.hash,
            archive_bytes,
            target_project_name=target_project_name,
            target_project_code=target_project_code,
            include_attachments=include_attachments,
        )
    )


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
    settings: Settings = Depends(get_settings),
) -> Response:
    project = project_service.get_project(db, project_id, workspace.hash)
    project_service.delete_project(db, project, hard=hard, uploads_dir=settings.uploads_dir)
    return Response(status_code=204)


@router.post("/plan-profile/scan")
def scan_plan_profile(
    request: Request,
    file: UploadFile = File(...),
    max_section_length_m: float = Form(default=12_000.0),
    max_elevation_diff_m: float | None = Form(default=None),
    language: str | None = Form(default=None),
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
    settings: Settings = Depends(get_settings),
) -> dict:
    enforce_rate_limit(request, settings, bucket="plan_profile_scan", limit=30)
    payload = plan_profile_service.scan_plan_profile_upload(
        file_name=file.filename,
        stream=file.file,
        max_section_length_m=max_section_length_m,
        max_elevation_diff_m=max_elevation_diff_m,
        language=language,
        max_bytes=settings.max_upload_bytes,
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


@router.get("/{project_id}/dataset")
def get_project_dataset(
    project_id: str,
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    project = project_service.get_project(db, project_id, workspace.hash)
    return json_safe(project_data_service.build_project_dataset(db, project, workspace.hash))


@router.post("/{project_id}/export")
def export_project_dataset(
    project_id: str,
    payload: schemas.ProjectExportRequest,
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    project = project_service.get_project(db, project_id, workspace.hash)
    dataset = project_data_service.build_project_dataset(db, project, workspace.hash)
    out_path, media_type, download_name = project_data_service.export_project_dataset(
        settings, dataset, fmt=payload.format
    )
    return FileResponse(path=out_path, media_type=media_type, filename=download_name)


@router.post("/{project_id}/generate-sections", status_code=201)
def generate_project_sections(
    project_id: str,
    payload: schemas.ProjectGenerateSectionsRequest,
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    project = project_service.get_project(db, project_id, workspace.hash)
    return json_safe(
        project_data_service.generate_project_sections(db, project, workspace.hash, payload)
    )


@router.post("/{project_id}/sync-forms")
def sync_project_forms(
    project_id: str,
    payload: schemas.ProjectSyncFormsRequest,
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    project = project_service.get_project(db, project_id, workspace.hash)
    return json_safe(
        project_data_service.sync_project_forms(
            db,
            project,
            workspace.hash,
            overwrite_existing=payload.overwrite_existing,
            form_codes=payload.form_codes,
        )
    )


@router.post("/{project_id}/clone", status_code=201)
def clone_project(
    project_id: str,
    payload: schemas.ProjectCloneRequest,
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    project = project_service.get_project(db, project_id, workspace.hash)
    return json_safe(
        project_data_service.clone_project(
            db,
            project,
            workspace.hash,
            name=payload.name,
            code=payload.code,
            mode=payload.mode,
        )
    )


@router.get("/{project_id}/archive")
def export_project_archive(
    request: Request,
    project_id: str,
    include_attachments: bool = Query(default=True),
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
    settings: Settings = Depends(get_settings),
) -> Response:
    enforce_rate_limit(request, settings, bucket="project_archive", limit=15)
    zip_bytes, download_name = project_archive_service.export_project_archive(
        db,
        settings,
        workspace.hash,
        project_id,
        include_attachments=include_attachments,
    )
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{download_name}"'},
    )


__all__ = ["router"]
