"""FastAPI application factory."""

# ruff: noqa: E402 - repo-root bootstrap must run before importing domain modules.

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .core.config import Settings, ensure_repo_on_path

ensure_repo_on_path()

from . import db
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
from .core.context import set_request_context
from .core.errors import (
    REQUEST_ID_HEADER,
    SESSION_HEADER,
    AppError,
    register_exception_handlers,
)
from .core.security import actor_for, normalize_workspace, workspace_hash

logger = logging.getLogger("hydro.web")

API_PREFIX = "/api"


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info(
        "HYDRO web ready: db=%s data_dir=%s frontend=%s",
        app.state.settings.database_url,
        app.state.settings.data_dir,
        "built" if (app.state.settings.frontend_dist / "index.html").exists() else "absent",
    )
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or Settings.from_env()
    resolved.ensure_directories()

    db.configure_database(resolved.database_url)
    db.init_db()

    app = FastAPI(
        title="HYDRO Web API",
        version="1.0.0",
        description=(
            "Hidrostatik test degerlendirme API'si. Hesaplama motoru "
            "hidrostatik_test paketinden import edilir."
        ),
        lifespan=_lifespan,
    )
    app.state.settings = resolved

    @app.middleware("http")
    async def _context_middleware(request, call_next):  # noqa: ANN001
        raw_workspace = normalize_workspace(request.headers.get(SESSION_HEADER))
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        hashed = workspace_hash(raw_workspace)
        request.state.request_id = request_id
        request.state.workspace = Workspace(
            raw=raw_workspace, hash=hashed, actor=actor_for(raw_workspace)
        )
        set_request_context(request_id, hashed, actor_for(raw_workspace))
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers[SESSION_HEADER] = raw_workspace
        return response

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
            ],
            expose_headers=[REQUEST_ID_HEADER, SESSION_HEADER, "ETag", "X-Total-Count"],
        )

    register_exception_handlers(app)

    app.include_router(system_router.router, prefix=API_PREFIX)
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
