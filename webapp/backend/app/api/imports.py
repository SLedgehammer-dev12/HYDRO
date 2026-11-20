"""Desktop snapshot and desktop SQLite database import routes."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile
from pydantic import Field
from sqlalchemy.orm import Session as OrmSession

from ..core import security
from ..core.config import Settings
from ..core.errors import AppError
from ..core.rate_limit import enforce_rate_limit
from ..core.timeutil import json_safe
from ..db import get_db
from ..schemas import StrictModel
from ..services import audit
from ..services import project_archive as project_archive_service
from ..services import sessions as session_service
from ..services import snapshot as snapshot_service
from .deps import Workspace, get_settings, get_workspace

router = APIRouter(prefix="/import", tags=["import"])


class DesktopSnapshotImport(StrictModel):
    name: str | None = Field(default=None, max_length=200)
    project_id: str | None = Field(default=None, max_length=64)
    snapshot: dict


@router.post("/desktop-snapshot", status_code=201)
def import_desktop_snapshot(
    payload: DesktopSnapshotImport,
    request: Request,
    response: Response,
    db: OrmSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    enforce_rate_limit(request, settings, bucket="desktop_snapshot_import", limit=60)
    if (
        len(json.dumps(payload.snapshot, ensure_ascii=False).encode("utf-8"))
        > settings.max_upload_bytes
    ):
        raise AppError(
            "payload_too_large",
            "Snapshot JSON boyutu azami yukleme sinirini asiyor.",
            status_code=413,
        )
    clean_name = payload.name or None
    clean_project_id = payload.project_id or None
    new_inputs, mapping = snapshot_service.apply_snapshot({}, payload.snapshot, mode="replace")
    session = session_service.create_session(
        db,
        workspace_hash=workspace.hash,
        name=clean_name,
        project_id=clean_project_id,
        inputs=new_inputs,
        commit=False,
    )
    audit.record(
        db,
        action="snapshot.import",
        entity_type="session",
        entity_id=session.id,
        session_id=session.id,
        workspace_hash=workspace.hash,
        after={"mapping": mapping, "project_id": clean_project_id},
    )
    db.commit()
    db.refresh(session)
    response.headers["Location"] = f"/api/sessions/{session.id}"
    response.headers["ETag"] = f'"{session.revision}"'
    return json_safe(
        {
            "session": session_service.serialize_session(session),
            "mapping": mapping,
        }
    )


@router.post("/desktop-db", status_code=201)
async def import_desktop_db(
    request: Request,
    file: UploadFile = File(...),
    project_name: str | None = Form(default=None),
    project_code: str | None = Form(default=None),
    db: OrmSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    enforce_rate_limit(request, settings, bucket="desktop_db_import", limit=30)
    db_bytes = await security.read_upload_bounded(file, settings.max_upload_bytes)
    return json_safe(
        project_archive_service.import_desktop_db(
            db,
            settings,
            workspace.hash,
            db_bytes,
            project_name=project_name,
            project_code=project_code,
        )
    )


__all__ = ["router"]
