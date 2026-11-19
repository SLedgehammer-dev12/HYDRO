"""SQLAlchemy 2.0 engine/session management.

SQLite is the default (WAL, foreign keys on). The same models work on
PostgreSQL by changing ``HYDRO_DATABASE_URL`` (e.g.
``postgresql+psycopg://user:pass@host/db``).
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import Engine, create_engine, event, func, inspect, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

CURRENT_MIGRATION = "0002"

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
_current_url: str | None = None


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def _is_memory(url: str) -> bool:
    return _is_sqlite(url) and (":memory:" in url or url.endswith("sqlite://"))


def _install_sqlite_pragmas(engine: Engine, *, memory: bool) -> None:
    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_connection, _connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA foreign_keys=ON")
            if not memory:
                try:
                    cursor.execute("PRAGMA journal_mode=WAL")
                    cursor.execute("PRAGMA synchronous=NORMAL")
                except Exception:
                    cursor.execute("PRAGMA journal_mode=DELETE")
        finally:
            cursor.close()


def configure_database(database_url: str) -> Engine:
    """(Re)create the global engine for ``database_url``."""

    global _engine, _session_factory, _current_url

    if _engine is not None and _current_url == database_url:
        return _engine

    if _engine is not None:
        _engine.dispose()

    kwargs: dict[str, object] = {"future": True, "pool_pre_ping": True}
    if _is_sqlite(database_url):
        kwargs["connect_args"] = {"check_same_thread": False}
        if _is_memory(database_url):
            kwargs["poolclass"] = StaticPool

    engine = create_engine(database_url, **kwargs)
    if _is_sqlite(database_url):
        _install_sqlite_pragmas(engine, memory=_is_memory(database_url))

    _engine = engine
    _session_factory = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    _current_url = database_url
    return engine


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("Database is not configured. Call configure_database() first.")
    return _engine


def get_sessionmaker() -> sessionmaker[Session]:
    if _session_factory is None:
        raise RuntimeError("Database is not configured. Call configure_database() first.")
    return _session_factory


def _ensure_column(
    inspector,  # noqa: ANN001
    table: str,
    column_name: str,
    ddl_fragment: str,
) -> None:
    columns = {column["name"] for column in inspector.get_columns(table)}
    if column_name not in columns:
        with get_engine().begin() as connection:
            connection.execute(text(f'ALTER TABLE "{table}" ADD COLUMN {ddl_fragment}'))


def _record_migration(version: str, description: str) -> None:
    from .models import SchemaMigration, utcnow

    factory = get_sessionmaker()
    db = factory()
    try:
        if db.get(SchemaMigration, version) is None:
            db.add(
                SchemaMigration(
                    version=version,
                    description=description,
                    applied_at=utcnow(),
                )
            )
            db.commit()
    finally:
        db.close()


def _apply_migrations() -> None:
    """Apply additive idempotent migrations and record versions in ``schema_migrations``."""

    inspector = inspect(get_engine())
    table_names = set(inspector.get_table_names())
    if "projects" in table_names:
        _ensure_column(inspector, "projects", "code", "\"code\" VARCHAR(64) DEFAULT ''")
    if "ocr_analyses" in table_names:
        _ensure_column(inspector, "ocr_analyses", "dossier", '"dossier" JSON')
    _record_migration("0001", "Baseline schema with project code and OCR dossier")

    inspector = inspect(get_engine())
    if "projects" in set(inspector.get_table_names()):
        _ensure_column(inspector, "projects", "contractor", '"contractor" VARCHAR(200)')
        _ensure_column(inspector, "projects", "supervisor", '"supervisor" VARCHAR(200)')
        _ensure_column(inspector, "projects", "pipeline_length_m", '"pipeline_length_m" FLOAT')
        _ensure_column(inspector, "projects", "status", "\"status\" VARCHAR(24) DEFAULT 'active'")
        _ensure_column(inspector, "projects", "defaults", '"defaults" JSON')
        with get_engine().begin() as connection:
            connection.execute(text("UPDATE projects SET status = 'active' WHERE status IS NULL"))
            connection.execute(text("UPDATE projects SET defaults = '{}' WHERE defaults IS NULL"))
    _record_migration("0002", "Project engineering metadata and defaults")


def init_db() -> None:
    """Create tables and apply incremental additive migrations."""

    from . import models  # noqa: F401  (register mappers)

    models.Base.metadata.create_all(bind=get_engine())
    _apply_migrations()


def dispose_database() -> None:
    global _engine, _session_factory, _current_url
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
    _current_url = None


def get_db() -> Iterator[Session]:
    """FastAPI dependency: yield a scoped session."""

    factory = get_sessionmaker()
    session = factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    factory = get_sessionmaker()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def database_health() -> dict[str, object]:
    from .models import SchemaMigration

    try:
        engine = get_engine()
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        migration: str | None = CURRENT_MIGRATION
        try:
            with session_scope() as db:
                latest = db.scalar(select(func.max(SchemaMigration.version)))
                if latest:
                    migration = str(latest)
        except Exception:
            migration = CURRENT_MIGRATION
        return {
            "ok": True,
            "dialect": engine.dialect.name,
            "migration": migration,
        }
    except Exception as exc:  # pragma: no cover - depends on environment
        return {
            "ok": False,
            "dialect": "unknown",
            "migration": None,
            "error": type(exc).__name__,
        }


__all__ = [
    "CURRENT_MIGRATION",
    "configure_database",
    "database_health",
    "dispose_database",
    "get_db",
    "get_engine",
    "get_sessionmaker",
    "init_db",
    "session_scope",
]
