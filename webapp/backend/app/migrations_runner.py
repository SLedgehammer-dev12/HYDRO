"""Programmatic Alembic migration runner, SQLite/Postgres safety guards, and legacy bridge."""

from __future__ import annotations

import logging
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect, text
from sqlalchemy.engine import Connection

BASELINE_REVISION = "0002"
HEAD_REVISION = "0003"
POSTGRES_ADVISORY_LOCK_KEY = 748291043

logger = logging.getLogger("hydro.web.migrations")


def resolve_migrations_dir() -> Path:
    """Resolve the Alembic migrations directory for source and PyInstaller frozen builds."""

    if getattr(sys, "frozen", False):
        candidates: list[Path] = []
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "webapp_migrations")
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "webapp_migrations")
        candidates.append(exe_dir / "_internal" / "webapp_migrations")
        for candidate in candidates:
            if (candidate / "env.py").is_file():
                return candidate
        return candidates[0]
    return Path(__file__).resolve().parents[1] / "migrations"


def build_alembic_config(connection: Connection) -> Config:
    """Create an in-memory Alembic ``Config`` bound to an existing connection."""

    cfg = Config()
    cfg.set_main_option("script_location", str(resolve_migrations_dir()))
    cfg.attributes["connection"] = connection
    cfg.attributes["configure_logger"] = False
    return cfg


def _set_sqlite_foreign_keys(conn: Connection, enabled: bool) -> None:
    """Toggle SQLite ``PRAGMA foreign_keys`` outside any open transaction."""

    if conn.in_transaction():
        conn.commit()
    value = "ON" if enabled else "OFF"
    conn.execution_options(isolation_level="AUTOCOMMIT").exec_driver_sql(
        f"PRAGMA foreign_keys={value}"
    )


def _check_sqlite_foreign_keys(conn: Connection) -> None:
    """Verify no foreign-key constraint violations remain after migrations."""

    rows = conn.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
    if rows:
        raise RuntimeError(f"SQLite foreign key integrity check failed: {len(rows)} violation(s)")


@contextmanager
def migration_connection_guard(conn: Connection) -> Iterator[None]:
    """Protect migrations on ``conn`` with SQLite FK toggles or Postgres advisory locks."""

    dialect = conn.dialect.name
    if dialect == "sqlite":
        _set_sqlite_foreign_keys(conn, False)
        succeeded = False
        try:
            yield
            if conn.in_transaction():
                conn.commit()
            succeeded = True
        except Exception:
            if conn.in_transaction():
                conn.rollback()
            raise
        finally:
            try:
                _set_sqlite_foreign_keys(conn, True)
            except Exception:
                logger.exception("Failed to re-enable SQLite PRAGMA foreign_keys")
            if succeeded:
                _check_sqlite_foreign_keys(conn)
        return

    if dialect == "postgresql":
        if conn.in_transaction():
            conn.commit()
        autocommit_conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        autocommit_conn.execute(
            text("SELECT pg_advisory_lock(:key)"),
            {"key": POSTGRES_ADVISORY_LOCK_KEY},
        )
        try:
            yield
            if conn.in_transaction():
                conn.commit()
        except Exception:
            if conn.in_transaction():
                conn.rollback()
            raise
        finally:
            if conn.in_transaction():
                conn.rollback()
            autocommit_conn.execute(
                text("SELECT pg_advisory_unlock(:key)"),
                {"key": POSTGRES_ADVISORY_LOCK_KEY},
            )
        return

    try:
        yield
        if conn.in_transaction():
            conn.commit()
    except Exception:
        if conn.in_transaction():
            conn.rollback()
        raise


def _ensure_column(conn: Connection, table: str, column_name: str, ddl_fragment: str) -> None:
    cols = {col["name"] for col in sa.inspect(conn).get_columns(table)}
    if column_name not in cols:
        conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN {ddl_fragment}'))


def _bridge_legacy_to_0002(conn: Connection) -> None:
    """Bring a pre-Alembic database up to the ``0002`` baseline schema on ``conn``."""

    from . import models

    if conn.in_transaction():
        conn.commit()
    with conn.begin():
        models.Base.metadata.create_all(bind=conn)
        table_names = set(sa.inspect(conn).get_table_names())
        if "projects" in table_names:
            _ensure_column(conn, "projects", "code", "\"code\" VARCHAR(64) DEFAULT ''")
            _ensure_column(conn, "projects", "contractor", '"contractor" VARCHAR(200)')
            _ensure_column(conn, "projects", "supervisor", '"supervisor" VARCHAR(200)')
            _ensure_column(conn, "projects", "pipeline_length_m", '"pipeline_length_m" FLOAT')
            _ensure_column(conn, "projects", "status", "\"status\" VARCHAR(24) DEFAULT 'active'")
            _ensure_column(conn, "projects", "defaults", '"defaults" JSON')
            conn.execute(text("UPDATE projects SET status = 'active' WHERE status IS NULL"))
            conn.execute(text("UPDATE projects SET defaults = '{}' WHERE defaults IS NULL"))
        if "ocr_analyses" in table_names:
            _ensure_column(conn, "ocr_analyses", "dossier", '"dossier" JSON')

        insp_after = sa.inspect(conn)
        refreshed_tables = set(insp_after.get_table_names())
        for table in models.Base.metadata.sorted_tables:
            if table.name not in refreshed_tables:
                continue
            existing_cols = {c["name"] for c in insp_after.get_columns(table.name)}
            for idx in table.indexes:
                if all(col.name in existing_cols for col in idx.columns):
                    idx.create(bind=conn, checkfirst=True)

        if "schema_migrations" in refreshed_tables:
            existing = {
                str(row[0])
                for row in conn.execute(text("SELECT version FROM schema_migrations")).fetchall()
            }
            now = models.utcnow()
            for version, desc in (
                ("0001", "Baseline schema with project code and OCR dossier"),
                ("0002", "Project engineering metadata and defaults"),
            ):
                if version not in existing:
                    conn.execute(
                        sa.insert(models.SchemaMigration).values(
                            version=version,
                            description=desc,
                            applied_at=now,
                        )
                    )


def get_current_revision(bind: Engine | Connection) -> str | None:
    """Return the active Alembic revision (or legacy ``schema_migrations`` version)."""

    insp = inspect(bind)
    if insp.has_table("alembic_version"):
        if isinstance(bind, Connection):
            rev = bind.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar()
            return str(rev) if rev else None
        with bind.connect() as conn:
            rev = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar()
            return str(rev) if rev else None
    if insp.has_table("schema_migrations"):
        if isinstance(bind, Connection):
            ver = bind.execute(text("SELECT max(version) FROM schema_migrations")).scalar()
            return str(ver) if ver else None
        with bind.connect() as conn:
            ver = conn.execute(text("SELECT max(version) FROM schema_migrations")).scalar()
            return str(ver) if ver else None
    return None


def run_migrations(engine: Engine, *, target: str = "head") -> str:
    """Initialize or upgrade the schema using Alembic on a single shared connection."""

    from . import models  # noqa: F401  (register mappers)

    with engine.connect() as conn:
        cfg = build_alembic_config(conn)
        with migration_connection_guard(conn):
            insp = sa.inspect(conn)
            current_rev = None
            if insp.has_table("alembic_version"):
                raw = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar()
                current_rev = str(raw) if raw else None
            table_names = set(insp.get_table_names())
            if conn.in_transaction():
                conn.commit()
            if current_rev:
                command.upgrade(cfg, target)
            elif "projects" in table_names or "sessions" in table_names:
                _bridge_legacy_to_0002(conn)
                command.stamp(cfg, BASELINE_REVISION)
                if conn.in_transaction():
                    conn.commit()
                command.upgrade(cfg, target)
            else:
                command.upgrade(cfg, target)

            if conn.in_transaction():
                conn.commit()
            rev = get_current_revision(conn)
    return rev or HEAD_REVISION


def downgrade_migrations(engine: Engine, target: str) -> str | None:
    """Downgrade migrations on ``engine`` with the same SQLite/Postgres guards."""

    with engine.connect() as conn:
        cfg = build_alembic_config(conn)
        with migration_connection_guard(conn):
            command.downgrade(cfg, target)
            if conn.in_transaction():
                conn.commit()
            return get_current_revision(conn)


__all__ = [
    "BASELINE_REVISION",
    "HEAD_REVISION",
    "POSTGRES_ADVISORY_LOCK_KEY",
    "build_alembic_config",
    "downgrade_migrations",
    "get_current_revision",
    "migration_connection_guard",
    "resolve_migrations_dir",
    "run_migrations",
]
