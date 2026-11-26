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
``HYDRO_AUTO_MIGRATE``
    run Alembic migrations automatically in ``create_app()`` (default true).
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

_IS_FROZEN = bool(getattr(sys, "frozen", False))
if _IS_FROZEN:
    _FROZEN_ROOT = Path(
        getattr(sys, "_MEIPASS", None) or Path(sys.executable).resolve().parent
    ).resolve()
    WEBAPP_DIR = _FROZEN_ROOT
    REPO_ROOT = _FROZEN_ROOT
else:
    WEBAPP_DIR = Path(__file__).resolve().parents[3]
    REPO_ROOT = WEBAPP_DIR.parent


def _default_data_dir() -> Path:
    """Resolve mutable application data directory (safe outside read-only frozen bundles)."""
    if getattr(sys, "frozen", False):
        if sys.platform == "darwin":
            return Path.home() / "Library" / "Application Support" / "HYDRO-Web"
        if sys.platform == "win32":
            base = os.environ.get("LOCALAPPDATA")
            if base and base.strip():
                return Path(base.strip()) / "HYDRO-Web"
            return Path.home() / "AppData" / "Local" / "HYDRO-Web"
        xdg = os.environ.get("XDG_DATA_HOME")
        if xdg and xdg.strip():
            return Path(xdg.strip()) / "hydro-web"
        return Path.home() / ".local" / "share" / "hydro-web"
    return WEBAPP_DIR / "data"


def _default_frontend_dist() -> Path:
    """Resolve static frontend bundle directory for source and PyInstaller frozen builds."""
    if getattr(sys, "frozen", False):
        candidates: list[Path] = []
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "webapp_frontend_dist")
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "webapp_frontend_dist")
        candidates.append(exe_dir / "_internal" / "webapp_frontend_dist")
        for candidate in candidates:
            if (candidate / "index.html").is_file():
                return candidate
        return candidates[0]
    return WEBAPP_DIR / "frontend" / "dist"


DEFAULT_DATA_DIR = _default_data_dir()
DEFAULT_FRONTEND_DIST = _default_frontend_dist()

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def _parse_csv(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _parse_role_map(raw: str | None) -> dict[str, str]:
    """Parse ``HYDRO_OIDC_ROLE_MAP`` ('group=role,...' or JSON object)."""

    if not raw or not raw.strip():
        return {}
    text = raw.strip()
    out: dict[str, str] = {}
    if text.startswith("{"):
        try:
            loaded = json.loads(text)
        except json.JSONDecodeError:
            return {}
        if isinstance(loaded, dict):
            for key, val in loaded.items():
                k = str(key).strip().lower()
                v = str(val).strip().lower()
                if k and v:
                    out[k] = v
        return out
    for entry in text.split(","):
        if "=" not in entry:
            continue
        k, v = entry.split("=", 1)
        k_clean = k.strip().lower()
        v_clean = v.strip().lower()
        if k_clean and v_clean:
            out[k_clean] = v_clean
    return out


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
    data_dir: Path = field(default_factory=_default_data_dir)
    frontend_dist: Path = field(default_factory=_default_frontend_dist)
    cors_origins: tuple[str, ...] = ()
    max_upload_mb: int = 500
    ocr_enabled: bool = True
    ocr_lang: str = "tur+eng"
    tesseract_cmd: str = ""
    ocr_timeout_s: int = 600
    ocr_max_concurrency: int = 1
    ocr_worker_mode: str = "inline"
    auth_mode: str = "none"
    auth_session_secret: str = ""
    auth_cookie_secure: bool = False
    auth_session_ttl_s: int = 28800
    auth_idle_timeout_s: int = 3600
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_redirect_uri: str = ""
    oidc_role_claim: str = "role"
    oidc_role_map: dict[str, str] = field(default_factory=dict)
    allow_remote: bool = False
    allow_workspace_claim: bool = False
    local_admin_token: str = ""
    trusted_hosts: tuple[str, ...] = ()
    rate_limit_enabled: bool = True
    auto_migrate: bool = True
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
        if self.trusted_hosts:
            normalized_hosts = tuple(
                h for h in (normalize_host_header(item) for item in self.trusted_hosts) if h
            )
            object.__setattr__(self, "trusted_hosts", normalized_hosts)

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

    @property
    def is_loopback_host(self) -> bool:
        return self.host.strip().lower() in {"127.0.0.1", "localhost", "::1"}

    @property
    def has_enforced_auth(self) -> bool:
        mode = self.auth_mode.strip().lower()
        if mode == "oidc":
            return bool(
                self.auth_session_secret.strip()
                and self.oidc_issuer.strip()
                and self.oidc_client_id.strip()
            )
        return False

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(_env("HYDRO_DATA_DIR") or _default_data_dir())
        frontend_dist = Path(_env("HYDRO_FRONTEND_DIST") or _default_frontend_dist())
        database_url = _env(
            "HYDRO_DATABASE_URL", "HYDRO_DB_URL", "DATABASE_URL"
        ) or _default_database_url(data_dir.expanduser().resolve())
        origins = _parse_csv(_env("HYDRO_CORS_ORIGINS"))
        trusted_hosts = tuple(host.lower() for host in _parse_csv(_env("HYDRO_TRUSTED_HOSTS")))
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
            ocr_max_concurrency=max(1, min(_env_int("HYDRO_OCR_MAX_CONCURRENCY", 1), 4)),
            ocr_worker_mode=(
                "external"
                if (_env("HYDRO_OCR_WORKER_MODE") or "").lower() == "external"
                else "inline"
            ),
            auth_mode=_env("HYDRO_AUTH_MODE") or "none",
            auth_session_secret=_env("HYDRO_AUTH_SESSION_SECRET") or "",
            auth_cookie_secure=_env_bool("HYDRO_AUTH_COOKIE_SECURE", False),
            auth_session_ttl_s=max(300, _env_int("HYDRO_AUTH_SESSION_TTL_S", 28800)),
            auth_idle_timeout_s=max(60, _env_int("HYDRO_AUTH_IDLE_TIMEOUT_S", 3600)),
            oidc_issuer=_env("HYDRO_OIDC_ISSUER") or "",
            oidc_client_id=_env("HYDRO_OIDC_CLIENT_ID") or "",
            oidc_client_secret=_env("HYDRO_OIDC_CLIENT_SECRET") or "",
            oidc_redirect_uri=_env("HYDRO_OIDC_REDIRECT_URI") or "",
            oidc_role_claim=_env("HYDRO_OIDC_ROLE_CLAIM") or "role",
            oidc_role_map=_parse_role_map(_env("HYDRO_OIDC_ROLE_MAP")),
            allow_remote=_env_bool("HYDRO_ALLOW_REMOTE", False),
            allow_workspace_claim=_env_bool("HYDRO_ALLOW_WORKSPACE_CLAIM", False),
            local_admin_token=_env("HYDRO_LOCAL_ADMIN_TOKEN") or "",
            trusted_hosts=trusted_hosts,
            rate_limit_enabled=_env_bool("HYDRO_RATE_LIMIT_ENABLED", True),
            auto_migrate=_env_bool("HYDRO_AUTO_MIGRATE", True),
            scene_vertical_exaggeration=float(_env("HYDRO_SCENE_VERTICAL_EXAGGERATION") or 3.0),
            log_level=_env("HYDRO_LOG_LEVEL") or "INFO",
        )

    def ensure_directories(self) -> None:
        for path in (self.data_dir, self.uploads_dir, self.exports_dir):
            path.mkdir(parents=True, exist_ok=True)


def normalize_host_header(raw_host: str | None) -> str:
    """Normalize an incoming or configured Host value by stripping brackets and ports."""

    value = (raw_host or "").strip().lower()
    if not value:
        return ""
    if value.startswith("["):
        end = value.find("]")
        return value[1:end] if end > 0 else ""
    if ":" in value:
        return value.split(":", 1)[0]
    return value


def validate_bind_security(settings: Settings) -> str | None:
    """Reject unsupported HYDRO_AUTH_MODE values and non-loopback binds without explicit opt-in."""

    mode = settings.auth_mode.strip().lower()
    if mode != "none" and not settings.has_enforced_auth:
        return (
            f"HATA: HYDRO_AUTH_MODE='{settings.auth_mode}' ayarlandi ancak bu surumde uygulama "
            "duzeyinde kimlik dogrulama ara yazilimi uygulanmamistir. Guvenlik nedeniyle sunucu "
            "baslatilmadi; yalnizca HYDRO_AUTH_MODE=none kullanin."
        )

    if (
        not settings.is_loopback_host
        and not settings.has_enforced_auth
        and not settings.allow_remote
    ):
        return (
            "HATA: Uygulama duzeyinde kimlik dogrulamasi etkin degilken 0.0.0.0 veya dis "
            "arayuzlere baglanma guvenlik nedeniyle engellendi. Yalnizca yetkili reverse "
            "proxy arkasinda calistiriyorsaniz HYDRO_ALLOW_REMOTE=1 ile acin."
        )
    return None


def safe_database_url(database_url: str) -> str:
    """Return a log-safe database URL with any embedded password redacted."""

    try:
        from sqlalchemy.engine.url import make_url

        return make_url(database_url).render_as_string(hide_password=True)
    except Exception:
        return "<database_url>"


def ensure_repo_on_path() -> None:
    """Make ``hidrostatik_test`` importable without ``pip install -e .``."""

    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass and str(meipass) not in sys.path:
            sys.path.insert(0, str(meipass))
    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


__all__ = [
    "DEFAULT_DATA_DIR",
    "DEFAULT_FRONTEND_DIST",
    "REPO_ROOT",
    "Settings",
    "WEBAPP_DIR",
    "_default_data_dir",
    "_default_frontend_dist",
    "ensure_repo_on_path",
    "normalize_host_header",
    "safe_database_url",
    "validate_bind_security",
]
