"""Desktop snapshot import route."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session as OrmSession

from ..core.timeutil import json_safe
from ..db import get_db
from ..services import sessions as session_service
from ..services import snapshot as snapshot_service
from .deps import Workspace, get_workspace

router = APIRouter(prefix="/import", tags=["import"])


class DesktopSnapshotImport(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str | None = Field(default=None, max_length=200)
    snapshot: dict


@router.post("/desktop-snapshot", status_code=201)
def import_desktop_snapshot(
    payload: DesktopSnapshotImport,
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    new_inputs, mapping = snapshot_service.apply_snapshot({}, payload.snapshot, mode="replace")
    session = session_service.create_session(
        db,
        workspace_hash=workspace.hash,
        name=payload.name,
        inputs=session_service.normalize_inputs(new_inputs),
    )
    return json_safe(
        {
            "session": session_service.serialize_session(session),
            "mapping": mapping,
        }
    )


__all__ = ["router"]
