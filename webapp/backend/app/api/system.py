"""System routes: health, meta, spec, stats."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session as OrmSession

from ..core.config import Settings
from ..db import get_db
from ..services import sessions as session_service
from ..services import system as system_service
from .deps import Workspace, get_settings, get_workspace

router = APIRouter(tags=["system"])


@router.get("/health")
def health(
    strict: int = Query(default=0, ge=0, le=1),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    payload = system_service.health_payload(settings)
    status_code = 200
    if strict and payload["status"] != "ok":
        status_code = 503
    return JSONResponse(status_code=status_code, content=payload)


@router.get("/meta")
def meta(settings: Settings = Depends(get_settings)) -> dict:
    return system_service.meta_payload(settings)


@router.get("/meta/spec")
def meta_spec() -> dict:
    return system_service.spec_payload()


@router.get("/stats")
def stats(
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    return session_service.stats(db, workspace.hash)


@router.get("/")
def api_index() -> dict:
    return {
        "service": "hydro-web",
        "api": "/api",
        "docs": "/docs",
    }


__all__ = ["router"]
