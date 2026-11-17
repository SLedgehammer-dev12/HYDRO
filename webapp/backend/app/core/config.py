"""Application settings.

Environment variables (all optional):

``HYDRO_HOST`` / ``HYDRO_PORT`` (aliases: ``HYDRO_WEB_HOST`` / ``HYDRO_WEB_PORT``)
    uvicorn bind address and port.
``HYDRO_DATABASE_URL`` (alias: ``HYDRO_DB_URL``)
    SQLAlchemy URL. Defaults to ``sqlite:///<repo>/webapp/data/hydro_web.db``.
``HYDRO_DATA_DIR``
    upload/export root. Defaults to ``<repo>/webapp/data``.
``HYDRO_FRONTEND_DIST``
    static root. Defaults to ``<repo>/webapp/frontend/dist``.
``HYDRO_CORS_ORIGINS``
    comma separated origin list. Empty means same-origin only.
``HYDRO_MAX_UPLOAD_MB``
    OCR upload limit in MB (default 500, clamped 1..500).
``HYDRO_OCR_ENABLED``
    queue/worker switch (default true).
``HYDRO_OCR_LANG``
    Tesseract language hint (default ``tur+eng``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

WEBAPP_DIR = Path(__file__).resolve().parents[3]
REPO_ROOT = WEBAPP_DIR.parent
DEFAULT_DATA_DIR = WEBAPP_DIR / "data"
DEFAULT_FRONTEND_DIST = WEBAPP_DIR / "frontend" / "dist"

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def _env(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value is not None and value.strip() != "":
            return value.strip()
    return None


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _default_database_url(data_dir: Path) -> str:
    return f"sqlite:///{(data_dir / 'hydro_web.db').as_posix()}"


@dataclass(frozen=True)
class Settings:
    """Immutable runtime settings."""

    host: str = "127.0.0.1"
    port: int = 8080
    database_url: str = ""
    data_dir: Path = DEFAULT_DATA_DIR
    frontend_dist: Path = DEFAULT_FRONTEND_DIST
    cors_origins: tuple[str, ...] = ()
    max_upload_mb: int = 500
    ocr_enabled: bool = True
    ocr_lang: str = "tur+eng"
    tesseract_cmd: str = ""
    ocr_timeout_s: int = 600
    auth_mode: str = "none"
    scene_vertical_exaggeration: float = 3.0
    log_level: str = "INFO"
    extra: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        data_dir = Path(self.data_dir).expanduser().resolve()
        object.__setattr__(self, "data_dir", data_dir)
        object.__setattr__(
            self,
            "frontend_dist",
            Path(self.frontend_dist).expanduser().resolve(),
        )
        if not self.database_url:
            object.__setattr__(self, "database_url", _default_database_url(data_dir))

    # -- derived paths ----------------------------------------------------
    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def max_upload_bytes(self) -> int:
        return min(max(1, self.max_upload_mb), 500) * 1024 * 1024

    @property
    def repo_root(self) -> Path:
        return REPO_ROOT

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(_env("HYDRO_DATA_DIR") or DEFAULT_DATA_DIR)
        frontend_dist = Path(_env("HYDRO_FRONTEND_DIST") or DEFAULT_FRONTEND_DIST)
        database_url = _env(
            "HYDRO_DATABASE_URL", "HYDRO_DB_URL", "DATABASE_URL"
        ) or _default_database_url(data_dir.resolve())
        raw_origins = _env("HYDRO_CORS_ORIGINS") or ""
        origins = tuple(item.strip() for item in raw_origins.split(",") if item.strip())
        return cls(
            host=_env("HYDRO_HOST", "HYDRO_WEB_HOST") or "127.0.0.1",
            port=_env_int("HYDRO_PORT", _env_int("HYDRO_WEB_PORT", 8080)),
            database_url=database_url,
            data_dir=data_dir,
            frontend_dist=frontend_dist,
            cors_origins=origins,
            max_upload_mb=_env_int("HYDRO_MAX_UPLOAD_MB", 500),
            ocr_enabled=_env_bool("HYDRO_OCR_ENABLED", True),
            ocr_lang=_env("HYDRO_OCR_LANG") or "tur+eng",
            tesseract_cmd=_env("HYDRO_TESSERACT_CMD") or "",
            ocr_timeout_s=_env_int("HYDRO_OCR_TIMEOUT_S", 600),
            auth_mode=_env("HYDRO_AUTH_MODE") or "none",
            scene_vertical_exaggeration=float(_env("HYDRO_SCENE_VERTICAL_EXAGGERATION") or 3.0),
            log_level=_env("HYDRO_LOG_LEVEL") or "INFO",
        )

    def ensure_directories(self) -> None:
        for path in (self.data_dir, self.uploads_dir, self.exports_dir):
            path.mkdir(parents=True, exist_ok=True)


def ensure_repo_on_path() -> None:
    """Make ``hidrostatik_test`` importable without ``pip install -e .``."""

    import sys

    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


__all__ = [
    "DEFAULT_DATA_DIR",
    "DEFAULT_FRONTEND_DIST",
    "REPO_ROOT",
    "Settings",
    "WEBAPP_DIR",
    "ensure_repo_on_path",
]
