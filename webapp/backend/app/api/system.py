"""System routes: health, meta, spec, stats."""

from __future__ import annotations

import hmac
from typing import Any, Literal

from fastapi import APIRouter, Body, Depends, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session as OrmSession

from hidrostatik_test.services.updater import UpdateError

from .. import schemas
from ..core import security
from ..core.config import Settings
from ..core.errors import AppError, validation_error
from ..core.rate_limit import enforce_rate_limit
from ..core.timeutil import json_safe
from ..db import get_db
from ..services import db_admin as db_admin_service
from ..services import sessions as session_service
from ..services import system as system_service
from ..services.web_updater import WEB_UPDATE_MANAGER, get_web_runtime_context
from .deps import Workspace, get_settings, get_workspace

router = APIRouter(tags=["system"])
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "testclient"})
_PROXY_HEADERS = (
    "x-forwarded-for",
    "forwarded",
    "x-real-ip",
    "cf-connecting-ip",
    "true-client-ip",
    "x-forwarded-host",
    "x-forwarded-proto",
)
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_HIDDEN_RUNTIME_KEYS = frozenset({"executable_path", "install_dir", "app_bundle"})


def _sanitize_update_payload(payload: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(payload)
    runtime = payload.get("runtime")
    if isinstance(runtime, dict):
        cleaned["runtime"] = {
            key: value for key, value in runtime.items() if key not in _HIDDEN_RUNTIME_KEYS
        }
    job = payload.get("job")
    if isinstance(job, dict):
        job_copy = dict(job)
        if "verified_path" in job_copy:
            job_copy["verified_path"] = ""
        cleaned["job"] = job_copy
    return cleaned


def _require_same_origin(request: Request, settings: Settings) -> None:
    sec_fetch_site = request.headers.get("sec-fetch-site", "").strip().lower()
    if sec_fetch_site == "cross-site":
        raise AppError(
            "cross_site_forbidden",
            "Siteler arasi yonetim istegi guvenlik nedeniyle reddedildi.",
            status_code=403,
        )
    origin = request.headers.get("origin", "").strip().rstrip("/").lower()
    if not origin:
        return
    host = request.headers.get("host", "").strip()
    allowed = {item.strip().rstrip("/").lower() for item in settings.cors_origins if item.strip()}
    if host:
        allowed.add(f"{request.url.scheme}://{host}".lower())
    if origin not in allowed:
        raise AppError(
            "cross_site_forbidden",
            "Farkli kokenli yonetim istegi guvenlik nedeniyle reddedildi.",
            status_code=403,
        )


def _require_local_admin(request: Request, settings: Settings) -> None:
    if request.method.upper() not in _SAFE_METHODS:
        _require_same_origin(request, settings)

    admin_token = request.headers.get("X-Hydro-Admin-Token", "").strip()
    configured_token = (settings.local_admin_token or "").strip()

    if configured_token:
        if not admin_token or not hmac.compare_digest(admin_token, configured_token):
            raise AppError(
                "admin_token_required",
                "Veritabani yonetim islemleri icin gecerli X-Hydro-Admin-Token gereklidir.",
                status_code=403,
            )
        return

    if settings.auth_mode != "none":
        raise AppError(
            "admin_disabled",
            "Veritabani yonetim islemleri bu kimlik kipinde yerel yonetici jetonu gerektirir.",
            status_code=403,
        )

    if not settings.is_loopback_host:
        raise AppError(
            "local_admin_loopback_only",
            "Sunucu uzak arayuzlere acikken kimlik dogrulamasiz veritabani yonetimi kapalidir.",
            status_code=403,
        )

    if any(request.headers.get(header) for header in _PROXY_HEADERS):
        raise AppError(
            "local_admin_loopback_only",
            "Proxy uzerinden gelen veritabani yonetim istegi reddedildi.",
            status_code=403,
        )

    client_host = (request.client.host if request.client else "").strip().lower()
    if client_host not in _LOOPBACK_HOSTS:
        raise AppError(
            "local_admin_loopback_only",
            "Veritabani yonetim islemleri yalnizca yerel loopback baglantisindan kullanilabilir.",
            status_code=403,
        )


@router.get("/health")
def health(
    request: Request,
    strict: int = Query(default=0, ge=0, le=1),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    instance_id = getattr(request.app.state, "instance_id", None)
    payload = system_service.health_payload(settings, instance_id=instance_id)
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
def update_status(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict:
    _require_local_admin(request, settings)
    return _sanitize_update_payload(WEB_UPDATE_MANAGER.get_status())


@router.post("/update/check")
def update_check(
    request: Request,
    force: bool = Query(default=True),
    settings: Settings = Depends(get_settings),
) -> dict:
    _require_local_admin(request, settings)
    enforce_rate_limit(request, settings, bucket="update_op", limit=30)
    return _sanitize_update_payload(WEB_UPDATE_MANAGER.check_for_updates(force=bool(force)))


@router.post("/update/download", status_code=202)
def update_download(
    request: Request,
    asset_name: str | None = Query(default=None),
    settings: Settings = Depends(get_settings),
) -> dict:
    _require_local_admin(request, settings)
    enforce_rate_limit(request, settings, bucket="update_op", limit=30)
    try:
        return _sanitize_update_payload(
            WEB_UPDATE_MANAGER.start_download(
                data_dir=settings.data_dir,
                asset_name=asset_name,
            )
        )
    except UpdateError as exc:
        raise AppError("update_download_failed", str(exc), status_code=502) from exc


@router.get("/update/download/file")
def update_download_file(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    _require_local_admin(request, settings)
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
def update_apply(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict:
    _require_local_admin(request, settings)
    enforce_rate_limit(request, settings, bucket="update_op", limit=30)
    runtime = get_web_runtime_context()
    if not runtime.get("can_self_install"):
        raise AppError(
            "self_install_unavailable",
            "Otomatik yerinde kurulum yalnizca paketli HydroWeb (.dmg / .exe) uygulamasinda kullanilabilir. Dogrulanmis paketi indirip elle kurabilirsiniz.",
            status_code=409,
        )
    try:
        return _sanitize_update_payload(WEB_UPDATE_MANAGER.apply_update(data_dir=settings.data_dir))
    except UpdateError as exc:
        raise AppError("update_apply_failed", str(exc), status_code=422) from exc


@router.get("/system/workspaces")
def list_db_workspaces(
    request: Request,
    db: OrmSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    _require_local_admin(request, settings)
    return json_safe(db_admin_service.list_workspaces(db, workspace.hash))


@router.post("/system/workspaces/claim")
def claim_db_workspace(
    request: Request,
    payload: schemas.WorkspaceClaimRequest,
    db: OrmSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    _require_local_admin(request, settings)
    enforce_rate_limit(request, settings, bucket="workspace_claim", limit=30)
    if payload.source_workspace_key is not None:
        expected_hash = security.workspace_hash(
            security.normalize_workspace(payload.source_workspace_key)
        )
        if not hmac.compare_digest(expected_hash, payload.source_workspace_hash.strip().lower()):
            raise AppError(
                "workspace_claim_forbidden",
                "Girilen kaynak calisma alani anahtari hedef ozet ile eslesmiyor.",
                status_code=403,
            )
    elif not settings.allow_workspace_claim:
        raise AppError(
            "workspace_claim_disabled",
            "Kor calisma alani devralma güvenlik nedeniyle kapalidir; kaynak X-Session-ID anahtarini girin.",
            status_code=403,
        )
    return json_safe(
        db_admin_service.claim_workspace(
            db,
            source_workspace_hash=payload.source_workspace_hash,
            target_workspace_hash=workspace.hash,
        )
    )


@router.get("/system/db-stats")
def get_db_stats(
    request: Request,
    db: OrmSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    _require_local_admin(request, settings)
    return json_safe(db_admin_service.get_db_stats(db, settings, workspace.hash))


@router.get("/system/db-backups")
def list_db_backups(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict:
    _require_local_admin(request, settings)
    return json_safe(db_admin_service.list_db_backups(settings))


@router.post("/system/db-backup", status_code=201)
def create_db_backup(
    request: Request,
    payload: schemas.DbBackupRequest | None = Body(default=None),
    settings: Settings = Depends(get_settings),
) -> dict:
    _require_local_admin(request, settings)
    enforce_rate_limit(request, settings, bucket="db_admin", limit=30)
    reason = payload.reason if payload is not None else "manual"
    return json_safe(db_admin_service.create_db_backup(settings, reason=reason))


@router.get("/system/db-backups/{filename}")
def download_db_backup(
    request: Request,
    filename: str,
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    _require_local_admin(request, settings)
    target = db_admin_service.resolve_backup_path(settings, filename)
    return FileResponse(path=target, media_type="application/octet-stream", filename=target.name)


@router.post("/system/db-restore")
async def restore_db_backup(
    request: Request,
    settings: Settings = Depends(get_settings),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    # Intentionally do NOT depend on get_db() so no open SQLAlchemy session holds locks during SQLite replace.
    _require_local_admin(request, settings)
    enforce_rate_limit(request, settings, bucket="db_admin", limit=30)
    content_type = request.headers.get("content-type", "").lower()
    backup_bytes: bytes | None = None
    backup_filename: str | None = None
    if "multipart/form-data" in content_type:
        form = await request.form()
        uploaded = form.get("file")
        if isinstance(uploaded, UploadFile) or hasattr(uploaded, "read"):
            backup_bytes = await security.read_upload_bounded(uploaded, settings.max_upload_bytes)
        raw_name = form.get("backup_filename")
        if isinstance(raw_name, str) and raw_name.strip():
            backup_filename = raw_name.strip()
    else:
        try:
            body = await request.json()
        except Exception as exc:
            raise AppError(
                "invalid_request",
                "Geri yukleme icin gecerli bir dosya veya JSON body gonderin.",
                status_code=400,
            ) from exc
        if not isinstance(body, dict):
            raise validation_error("JSON govdesi nesne olmalidir.", field="body")
        try:
            parsed = schemas.DbRestoreRequest(**body)
        except (TypeError, ValidationError) as exc:
            raise validation_error(
                "Geri yukleme parametreleri gecersiz.",
                field="backup_filename",
            ) from exc
        backup_filename = parsed.backup_filename

    return json_safe(
        db_admin_service.restore_db_backup(
            settings,
            backup_bytes=backup_bytes,
            backup_filename=backup_filename,
            workspace_hash=workspace.hash,
        )
    )


@router.get("/system/trash")
def list_trash(
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    return json_safe(db_admin_service.list_trash(db, workspace.hash))


@router.post("/system/trash/restore")
def restore_trash_item(
    payload: schemas.TrashRestoreRequest,
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    return json_safe(
        db_admin_service.restore_trash_item(
            db,
            workspace.hash,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
        )
    )


@router.delete("/system/trash/{entity_type}/{entity_id}")
def purge_trash_item(
    entity_type: Literal["project", "session"],
    entity_id: str,
    db: OrmSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    return json_safe(
        db_admin_service.purge_trash_item(
            db,
            settings,
            workspace.hash,
            entity_type=entity_type,
            entity_id=entity_id,
        )
    )


@router.post("/system/db-maintenance")
def run_db_maintenance(
    request: Request,
    payload: schemas.DbMaintenanceRequest,
    db: OrmSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    _require_local_admin(request, settings)
    return json_safe(
        db_admin_service.run_db_maintenance(
            db,
            settings,
            workspace.hash,
            checkpoint_wal=payload.checkpoint_wal,
            vacuum=payload.vacuum,
            clean_exports=payload.clean_exports,
            clean_orphan_uploads=payload.clean_orphan_uploads,
        )
    )


@router.get("/")
def api_index() -> dict:
    return {
        "service": "hydro-web",
        "api": "/api",
        "docs": "/docs",
    }


__all__ = ["router"]
