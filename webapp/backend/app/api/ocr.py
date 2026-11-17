"""OCR routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from sqlalchemy.orm import Session as OrmSession

from .. import schemas
from ..core.config import Settings
from ..core.timeutil import json_safe
from ..db import get_db
from ..services import dossier as dossier_service
from ..services import ocr as ocr_service
from .deps import Workspace, get_settings, get_workspace

router = APIRouter(prefix="/ocr", tags=["ocr"])


@router.post("/analyze", status_code=201)
def analyze(
    response: Response,
    file: UploadFile = File(...),
    calculated: str | None = Form(default=None),
    session_id: str | None = Form(default=None),
    mapping_profile_id: str | None = Form(default=None),
    language: str | None = Form(default=None),
    force: bool = Form(default=False),
    db: OrmSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    analysis, reused = ocr_service.analyze_upload(
        db,
        settings,
        workspace.hash,
        file_name=file.filename,
        stream=file.file,
        calculated_raw=calculated or None,
        session_id=session_id or None,
        mapping_profile_id=mapping_profile_id or None,
        language=language or None,
        force=bool(force),
    )
    response.status_code = 200 if reused else 201
    payload = ocr_service.detail_payload(db, analysis)
    payload["reused"] = reused
    return json_safe(payload)


@router.get("/status")
def status(
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    return json_safe(ocr_service.status_payload(db, workspace.hash))


@router.get("/analyses")
def list_analyses(
    session_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    return json_safe(
        ocr_service.list_analyses(
            db,
            workspace.hash,
            session_id=session_id,
            status=status,
            limit=limit,
            offset=offset,
        )
    )


@router.get("/analyses/{analysis_id}")
def get_analysis(
    analysis_id: str,
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    analysis = ocr_service.get_analysis(db, workspace.hash, analysis_id)
    return json_safe(ocr_service.detail_payload(db, analysis))


@router.post("/analyses/{analysis_id}/cancel", status_code=202)
def cancel_analysis(
    analysis_id: str,
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    analysis = ocr_service.get_analysis(db, workspace.hash, analysis_id)
    return ocr_service.cancel_analysis(db, analysis)


@router.post("/analyses/{analysis_id}/approve")
def approve_analysis(
    analysis_id: str,
    payload: schemas.OcrApproveRequest,
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    analysis = ocr_service.get_analysis(db, workspace.hash, analysis_id)
    return ocr_service.approve(
        db,
        analysis,
        fields=payload.fields,
        approve_all=payload.approve_all,
        reviewer_note=payload.reviewer_note,
    )


@router.post("/analyses/{analysis_id}/apply")
def apply_analysis(
    analysis_id: str,
    payload: schemas.OcrApplyRequest,
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    analysis = ocr_service.get_analysis(db, workspace.hash, analysis_id)
    return json_safe(
        ocr_service.apply_to_session(
            db,
            analysis,
            session_id=payload.session_id,
            field_names=payload.fields,
            overwrite=payload.overwrite,
        )
    )


@router.post("/analyses/{analysis_id}/commit-dossier")
def commit_dossier(
    analysis_id: str,
    payload: schemas.OcrDossierCommitRequest,
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    analysis = ocr_service.get_analysis(db, workspace.hash, analysis_id)
    return json_safe(
        dossier_service.commit_dossier_to_project(
            db,
            analysis,
            workspace_hash=workspace.hash,
            target_project_id=payload.target_project_id,
            create_new_project=payload.create_new_project,
            new_project_name=payload.new_project_name,
            new_project_code=payload.new_project_code,
            overwrite_filled=payload.overwrite_filled,
            selected_sections=payload.selected_sections,
        )
    )


@router.get("/mapping-profiles")
def list_mapping_profiles(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    return json_safe(ocr_service.list_profiles(db, workspace.hash, limit=limit, offset=offset))


@router.post("/mapping-profiles", status_code=201)
def create_mapping_profile(
    payload: schemas.MappingProfileCreate,
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    profile = ocr_service.create_profile(
        db, workspace.hash, payload.model_dump(exclude_unset=False)
    )
    return json_safe(ocr_service.profile_payload(profile))


@router.get("/mapping-profiles/{profile_id}")
def get_mapping_profile(
    profile_id: str,
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    profile = ocr_service.get_profile(db, workspace.hash, profile_id)
    return json_safe(ocr_service.profile_payload(profile))


@router.put("/mapping-profiles/{profile_id}")
def update_mapping_profile(
    profile_id: str,
    payload: schemas.MappingProfileUpdate,
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    profile = ocr_service.get_profile(db, workspace.hash, profile_id)
    profile = ocr_service.update_profile(
        db, profile, changes=payload.model_dump(exclude_unset=True)
    )
    return json_safe(ocr_service.profile_payload(profile))


@router.delete("/mapping-profiles/{profile_id}", status_code=204)
def delete_mapping_profile(
    profile_id: str,
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> Response:
    profile = ocr_service.get_profile(db, workspace.hash, profile_id)
    ocr_service.delete_profile(db, profile)
    return Response(status_code=204)


__all__ = ["router"]
