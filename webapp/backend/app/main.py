"""FastAPI application factory."""

# ruff: noqa: E402 - repo-root bootstrap must run before importing domain modules.

from __future__ import annotations

import logging
import re
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from .core.config import (
    Settings,
    ensure_repo_on_path,
    normalize_host_header,
    safe_database_url,
)
from .core.metrics import METRICS

ensure_repo_on_path()

from hidrostatik_test import APP_VERSION

from . import db
from .api import (
    auth as auth_router,
)
from .api import (
    calculations as calculations_router,
)
from .api import (
    catalog as catalog_router,
)
from .api import (
    coefficients as coefficients_router,
)
from .api import (
    imports as imports_router,
)
from .api import (
    ocr as ocr_router,
)
from .api import (
    projects as projects_router,
)
from .api import (
    reports as reports_router,
)
from .api import (
    sessions as sessions_router,
)
from .api import (
    system as system_router,
)
from .api.deps import Workspace
from .core.auth import (
    SESSION_COOKIE_NAME,
    AuthPrincipal,
    issue_session_cookie,
    parse_session_cookie,
    set_session_cookie,
)
from .core.context import set_request_context
from .core.errors import (
    REQUEST_ID_HEADER,
    SESSION_HEADER,
    AppError,
    register_exception_handlers,
)
from .core.rate_limit import RATE_LIMITER
from .core.security import MAX_JSON_BODY_BYTES, actor_for, normalize_workspace, workspace_hash
from .services.ocr_queue import OCR_QUEUE

logger = logging.getLogger("hydro.web")

API_PREFIX = "/api"
_LOOPBACK_HOST_HEADERS = frozenset({"127.0.0.1", "localhost", "::1"})
_PUBLIC_AUTH_PATHS = frozenset(
    {
        f"{API_PREFIX}/health",
        f"{API_PREFIX}/meta",
        f"{API_PREFIX}/meta/spec",
        f"{API_PREFIX}/auth/me",
        f"{API_PREFIX}/auth/login",
        f"{API_PREFIX}/auth/callback",
        f"{API_PREFIX}/auth/logout",
    }
)
_DOCS_PATHS = frozenset({"/docs", "/redoc", "/openapi.json"})
_CSP_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' blob: data:; "
    "font-src 'self' data:; "
    "connect-src 'self' blob: data:; "
    "worker-src 'self' blob:; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "frame-ancestors 'none'; "
    "form-action 'self'"
)


def _sanitize_request_id(raw: str | None) -> str:
    if not raw:
        return str(uuid.uuid4())
    cleaned = re.sub(r"[^A-Za-z0-9._:-]", "", raw.strip())[:64]
    return cleaned or str(uuid.uuid4())


def _apply_security_headers(response, path: str, request_id: str, raw_workspace: str) -> None:  # noqa: ANN001
    response.headers[REQUEST_ID_HEADER] = request_id
    response.headers[SESSION_HEADER] = raw_workspace
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    if path not in _DOCS_PATHS and not path.startswith("/docs/"):
        response.headers["Content-Security-Policy"] = _CSP_POLICY


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    s = app.state.settings
    if getattr(s, "ocr_worker_mode", "inline") == "inline":
        try:
            recovered = OCR_QUEUE.recover_interrupted_jobs(db.get_sessionmaker())
        except Exception:
            recovered = 0
        if recovered:
            logger.warning(
                "Marked %d stale queued/running OCR jobs as worker_interrupted", recovered
            )
    if not s.has_enforced_auth and not s.is_loopback_host:
        logger.warning(
            "SECURITY WARNING: HYDRO Web running without enforced app auth on host=%s. "
            "Remote DB/updater admin endpoints are disabled; enforce reverse-proxy auth!",
            s.host,
        )
    if s.auth_mode != "none" and not s.has_enforced_auth:
        logger.warning(
            "SECURITY WARNING: HYDRO_AUTH_MODE=%s configured, but no app auth middleware is enforced.",
            s.auth_mode,
        )
    if "*" in s.cors_origins:
        logger.warning(
            "SECURITY WARNING: Wildcard '*' configured in HYDRO_CORS_ORIGINS; restrict to explicit origins."
        )
    logger.info(
        "HYDRO web ready: db=%s data_dir=%s frontend=%s",
        safe_database_url(s.database_url),
        s.data_dir,
        "built" if (s.frontend_dist / "index.html").exists() else "absent",
    )
    try:
        yield
    finally:
        OCR_QUEUE.shutdown(wait=True)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or Settings.from_env()
    resolved.ensure_directories()

    RATE_LIMITER.reset()
    db.configure_database(resolved.database_url)
    if resolved.auto_migrate:
        db.init_db()
    OCR_QUEUE.configure(resolved.ocr_max_concurrency)

    app = FastAPI(
        title="HYDRO Web API",
        version=APP_VERSION,
        description=(
            "Hidrostatik test degerlendirme API'si. Hesaplama motoru "
            "hidrostatik_test paketinden import edilir."
        ),
        lifespan=_lifespan,
    )
    app.state.settings = resolved
    app.state.instance_id = uuid.uuid4().hex

    @app.middleware("http")
    async def _context_middleware(request, call_next):  # noqa: ANN001
        raw_workspace = normalize_workspace(request.headers.get(SESSION_HEADER))
        request_id = _sanitize_request_id(request.headers.get(REQUEST_ID_HEADER))
        hashed = workspace_hash(raw_workspace)
        request.state.request_id = request_id
        request.state.principal: AuthPrincipal | None = None
        actor = actor_for(raw_workspace)

        path = request.url.path
        needs_cookie_refresh = False
        if resolved.has_enforced_auth:
            parsed_auth = parse_session_cookie(
                request.cookies.get(SESSION_COOKIE_NAME),
                resolved,
            )
            if parsed_auth is not None:
                principal, needs_cookie_refresh = parsed_auth
                request.state.principal = principal
                raw_workspace = principal.workspace or f"user:{principal.sub}"
                hashed = workspace_hash(raw_workspace)
                actor = principal.actor

        request.state.workspace = Workspace(raw=raw_workspace, hash=hashed, actor=actor)
        set_request_context(request_id, hashed, actor)

        client_host = (request.client.host if request.client else "").strip().lower()
        host_name = normalize_host_header(request.headers.get("host"))
        allowed_hosts: set[str] | None = None
        if resolved.trusted_hosts:
            allowed_hosts = set(resolved.trusted_hosts)
        elif resolved.is_loopback_host:
            allowed_hosts = set(_LOOPBACK_HOST_HEADERS)

        if allowed_hosts is not None:
            if client_host == "testclient":
                allowed_hosts.add("testserver")
            if host_name not in allowed_hosts:
                denied = JSONResponse(
                    status_code=400,
                    content={
                        "code": "invalid_host",
                        "message": "Gecersiz Host basligi.",
                        "details": {},
                        "request_id": request_id,
                    },
                )
                _apply_security_headers(denied, path, request_id, raw_workspace)
                return denied

        if (
            resolved.has_enforced_auth
            and request.method != "OPTIONS"
            and path.startswith(f"{API_PREFIX}/")
            and path not in _PUBLIC_AUTH_PATHS
            and request.state.principal is None
        ):
            unauth = JSONResponse(
                status_code=401,
                content={
                    "code": "authentication_required",
                    "message": "Bu islem icin kimlik dogrulamasi (oturum) gereklidir.",
                    "details": {},
                    "request_id": request_id,
                },
            )
            _apply_security_headers(unauth, path, request_id, raw_workspace)
            return unauth

        content_type = request.headers.get("content-type", "").lower()
        if request.method in {"POST", "PUT", "PATCH"} and "multipart/form-data" not in content_type:
            raw_cl = request.headers.get("content-length")
            if raw_cl is not None:
                try:
                    if int(raw_cl) > MAX_JSON_BODY_BYTES:
                        too_large = JSONResponse(
                            status_code=413,
                            content={
                                "code": "payload_too_large",
                                "message": "Istek govdesi izin verilen 32 MB sinirini asiyor.",
                                "details": {"max_bytes": MAX_JSON_BODY_BYTES},
                                "request_id": request_id,
                            },
                        )
                        _apply_security_headers(too_large, path, request_id, raw_workspace)
                        return too_large
                except ValueError:
                    pass

        track_db = path.startswith(f"{API_PREFIX}/") and path not in {
            f"{API_PREFIX}/health",
            f"{API_PREFIX}/system/db-restore",
        }
        if track_db and not db.enter_request():
            restoring_resp = JSONResponse(
                status_code=503,
                headers={"Retry-After": "2"},
                content={
                    "code": "db_restoring",
                    "message": "Veritabani geri yukleme islemi suruyor; lutfen birkac saniye sonra tekrar deneyin.",
                    "details": {"retry_after_s": 2},
                    "request_id": request_id,
                },
            )
            _apply_security_headers(restoring_resp, path, request_id, raw_workspace)
            return restoring_resp

        req_started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            if track_db:
                db.exit_request()
        if path.startswith(f"{API_PREFIX}/"):
            METRICS.record_request(
                response.status_code,
                (time.perf_counter() - req_started) * 1000.0,
            )
        _apply_security_headers(response, path, request_id, raw_workspace)
        if "text/html" in response.headers.get("content-type", ""):
            response.headers["Cache-Control"] = "no-cache"
        elif (
            request.method in {"GET", "HEAD"}
            and response.status_code == 200
            and path.startswith("/assets/")
        ):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif path.startswith(f"{API_PREFIX}/") and "cache-control" not in response.headers:
            response.headers["Cache-Control"] = "no-store"
        if (
            needs_cookie_refresh
            and request.state.principal is not None
            and path != f"{API_PREFIX}/auth/logout"
        ):
            set_session_cookie(
                response,
                issue_session_cookie(request.state.principal, resolved),
                resolved,
            )
        return response

    app.add_middleware(GZipMiddleware, minimum_size=1000)

    if resolved.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(resolved.cors_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            allow_headers=[
                "Content-Type",
                SESSION_HEADER,
                REQUEST_ID_HEADER,
                "If-Match",
                "Idempotency-Key",
                "X-Hydro-Admin-Token",
            ],
            expose_headers=[REQUEST_ID_HEADER, SESSION_HEADER, "ETag", "Location", "X-Total-Count"],
        )

    register_exception_handlers(app)

    app.include_router(system_router.router, prefix=API_PREFIX)
    app.include_router(auth_router.router, prefix=API_PREFIX)
    app.include_router(catalog_router.router, prefix=API_PREFIX)
    app.include_router(coefficients_router.router, prefix=API_PREFIX)
    app.include_router(calculations_router.router, prefix=API_PREFIX)
    app.include_router(sessions_router.router, prefix=API_PREFIX)
    app.include_router(projects_router.router, prefix=API_PREFIX)
    app.include_router(reports_router.router, prefix=API_PREFIX)
    app.include_router(imports_router.router, prefix=API_PREFIX)
    app.include_router(ocr_router.router, prefix=API_PREFIX)

    @app.api_route(
        f"{API_PREFIX}/{{path:path}}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        include_in_schema=False,
    )
    def api_not_found(path: str) -> dict:
        raise AppError(
            "not_found",
            f"API yolu bulunamadi: /api/{path}",
            status_code=404,
            details={"path": f"/api/{path}"},
        )

    dist = resolved.frontend_dist
    index_file = dist / "index.html"
    if index_file.is_file():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="frontend")
    else:

        @app.get("/", include_in_schema=False)
        def api_only_root() -> JSONResponse:
            return JSONResponse(
                {
                    "service": "hydro-web",
                    "status": "api_only",
                    "message": (
                        "Frontend build bulunamadi. API /api altinda calisiyor; "
                        "arayuz icin webapp/frontend icinde 'npm run build' calistirin."
                    ),
                    "api": API_PREFIX,
                    "docs": "/docs",
                }
            )

    return app


__all__ = ["API_PREFIX", "create_app"]
