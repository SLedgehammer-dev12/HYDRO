"""System routes: health, meta, spec, stats."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session as OrmSession

from hidrostatik_test.services.updater import UpdateError

from ..core.config import Settings
from ..core.errors import AppError
from ..db import get_db
from ..services import sessions as session_service
from ..services import system as system_service
from ..services.web_updater import WEB_UPDATE_MANAGER, get_web_runtime_context
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


@router.get("/update/status")
def update_status() -> dict:
    return WEB_UPDATE_MANAGER.get_status()


@router.post("/update/check")
def update_check(force: bool = Query(default=True)) -> dict:
    return WEB_UPDATE_MANAGER.check_for_updates(force=bool(force))


@router.post("/update/download", status_code=202)
def update_download(
    asset_name: str | None = Query(default=None),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        return WEB_UPDATE_MANAGER.start_download(
            data_dir=settings.data_dir,
            asset_name=asset_name,
        )
    except UpdateError as exc:
        raise AppError("update_download_failed", str(exc), status_code=502) from exc


@router.get("/update/download/file")
def update_download_file() -> FileResponse:
    try:
        target = WEB_UPDATE_MANAGER.get_verified_download_path()
    except UpdateError as exc:
        raise AppError("update_not_downloaded", str(exc), status_code=409) from exc
    return FileResponse(
        path=target,
        media_type="application/octet-stream",
        filename=target.name,
    )


@router.post("/update/apply")
def update_apply(settings: Settings = Depends(get_settings)) -> dict:
    runtime = get_web_runtime_context()
    if not runtime.get("can_self_install"):
        raise AppError(
            "self_install_unavailable",
            "Otomatik yerinde kurulum yalnizca paketli HydroWeb (.dmg / .exe) uygulamasinda kullanilabilir. Dogrulanmis paketi indirip elle kurabilirsiniz.",
            status_code=409,
        )
    try:
        return WEB_UPDATE_MANAGER.apply_update(data_dir=settings.data_dir)
    except UpdateError as exc:
        raise AppError("update_apply_failed", str(exc), status_code=422) from exc


@router.get("/")
def api_index() -> dict:
    return {
        "service": "hydro-web",
        "api": "/api",
        "docs": "/docs",
    }


__all__ = ["router"]
