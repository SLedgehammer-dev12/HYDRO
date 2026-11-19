#!/usr/bin/env python3
"""Single entry point for the HYDRO web application.

Usage:
    python3 webapp/run_web.py                 # 127.0.0.1:8080
    python3 webapp/run_web.py --host 0.0.0.0 --port 8080
    python3 webapp/run_web.py --open-browser  # open the UI after start

Environment:
    HYDRO_HOST / HYDRO_PORT
    HYDRO_DATABASE_URL (alias HYDRO_DB_URL)
    HYDRO_DATA_DIR
    HYDRO_FRONTEND_DIST
    HYDRO_CORS_ORIGINS
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
import webbrowser
from dataclasses import replace
from pathlib import Path

WEBAPP_DIR = Path(__file__).resolve().parent
REPO_ROOT = WEBAPP_DIR.parent
BACKEND_DIR = WEBAPP_DIR / "backend"

for path in (str(BACKEND_DIR), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    from app.core.config import Settings

    env = Settings.from_env()
    parser = argparse.ArgumentParser(
        description="HYDRO web sunucusunu baslatir (FastAPI + uvicorn)."
    )
    parser.add_argument("--host", default=env.host, help="Bind adresi (varsayilan 127.0.0.1)")
    parser.add_argument("--port", type=int, default=env.port, help="Port (varsayilan 8080)")
    parser.add_argument(
        "--database-url",
        default=None,
        help="SQLAlchemy URL (varsayilan SQLite: <data-dir>/hydro_web.db)",
    )
    parser.add_argument(
        "--data-dir",
        default=str(env.data_dir),
        help="Upload/export kok dizini (varsayilan webapp/data)",
    )
    parser.add_argument(
        "--frontend-dist",
        default=str(env.frontend_dist),
        help="Statik frontend dizini (varsayilan webapp/frontend/dist)",
    )
    parser.add_argument(
        "--open-browser",
        action="store_true",
        default=os.environ.get("HYDRO_OPEN_BROWSER", "").lower() in {"1", "true", "yes"},
        help="Sunucu basladiktan sonra tarayiciyi ac",
    )
    parser.add_argument(
        "--log-level", default=env.log_level, help="uvicorn log seviyesi (varsayilan INFO)"
    )
    return parser.parse_args(argv)


def validate_bind_security(settings) -> str | None:  # noqa: ANN001
    """Reject unauthenticated binding to non-loopback interfaces unless explicitly allowed."""

    from app.core.config import validate_bind_security as _validate_bind_security

    return _validate_bind_security(settings)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    from app.core.config import Settings, safe_database_url
    from app.main import create_app

    settings = Settings.from_env()
    data_dir = Path(args.data_dir)
    database_url = (
        args.database_url
        or os.environ.get("HYDRO_DATABASE_URL")
        or os.environ.get("HYDRO_DB_URL")
        or os.environ.get("DATABASE_URL")
        or f"sqlite:///{(data_dir / 'hydro_web.db').as_posix()}"
    )
    settings = replace(
        settings,
        host=args.host,
        port=int(args.port),
        database_url=database_url,
        data_dir=data_dir,
        frontend_dist=Path(args.frontend_dist),
        log_level=str(args.log_level).upper(),
    )
    bind_err = validate_bind_security(settings)
    if bind_err is not None:
        print(bind_err, file=sys.stderr)
        return 2
    settings.ensure_directories()

    if settings.ocr_lang:
        os.environ.setdefault("HYDRO_OCR_LANG", settings.ocr_lang)
    if settings.tesseract_cmd:
        os.environ.setdefault("HYDRO_TESSERACT_CMD", settings.tesseract_cmd)

    app = create_app(settings)

    url_host = "127.0.0.1" if settings.host in {"0.0.0.0", "::"} else settings.host
    url = f"http://{url_host}:{settings.port}"

    print(f"HYDRO Web: {url}")
    print(f"  db        : {safe_database_url(settings.database_url)}")
    print(f"  data      : {settings.data_dir}")
    print(
        "  frontend  : "
        + (
            str(settings.frontend_dist)
            if (settings.frontend_dist / "index.html").is_file()
            else "build yok (API-only)"
        )
    )
    if settings.host in {"0.0.0.0", "::"}:
        print(
            "  UYARI     : Sunucu tum arayuzlere acik. MVP'de kimlik dogrulama yok; "
            "yalnizca guvenilir agda veya reverse proxy arkasinda calistirin."
        )

    if args.open_browser:

        def _open() -> None:
            time.sleep(1.0)
            try:
                webbrowser.open(url)
            except Exception:
                pass

        threading.Thread(target=_open, daemon=True).start()

    import uvicorn

    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        workers=1,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
