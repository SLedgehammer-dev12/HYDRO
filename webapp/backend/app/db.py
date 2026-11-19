"""SQLAlchemy 2.0 engine/session management.

SQLite is the default (WAL, foreign keys on). The same models work on
PostgreSQL by changing ``HYDRO_DATABASE_URL`` (e.g.
``postgresql+psycopg://user:pass@host/db``). Schema lifecycle is managed by
Alembic via :mod:`app.migrations_runner`.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from . import migrations_runner

CURRENT_MIGRATION = migrations_runner.HEAD_REVISION

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


def init_db() -> str:
    """Run Alembic migrations (with legacy ``0001``/``0002`` bridge when needed)."""

    return migrations_runner.run_migrations(get_engine())


def current_schema_version() -> str | None:
    """Return active database revision from ``alembic_version`` (or legacy fallback)."""

    return migrations_runner.get_current_revision(get_engine())


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
    try:
        engine = get_engine()
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        migration: str | None = None
        try:
            migration = current_schema_version()
        except Exception:
            migration = None
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
    "current_schema_version",
    "database_health",
    "dispose_database",
    "get_db",
    "get_engine",
    "get_sessionmaker",
    "init_db",
    "session_scope",
]
