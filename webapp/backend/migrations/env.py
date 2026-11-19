"""Alembic environment configuration for HYDRO Web backend."""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool

if not getattr(sys, "frozen", False):
    BACKEND_ROOT = Path(__file__).resolve().parents[1]
    REPO_ROOT = BACKEND_ROOT.parents[1]
    for candidate in (str(BACKEND_ROOT), str(REPO_ROOT)):
        if candidate not in sys.path:
            sys.path.insert(0, candidate)

from app.core.config import Settings  # noqa: E402
from app.migrations_runner import migration_connection_guard  # noqa: E402
from app.models import Base  # noqa: E402

config = context.config
if config.config_file_name and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _include_object(_obj, name: str | None, type_: str, _reflected: bool, _compare_to) -> bool:
    return not (type_ == "table" and name == "alembic_version")


def _resolve_database_url() -> str:
    for key in ("HYDRO_DATABASE_URL", "HYDRO_DB_URL", "DATABASE_URL"):
        val = (os.environ.get(key) or "").strip()
        if val:
            return val
    url = config.get_main_option("sqlalchemy.url")
    if url:
        return url
    return Settings.from_env().database_url


def run_migrations_offline() -> None:
    url = _resolve_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=url.startswith("sqlite"),
        compare_type=True,
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_migrations_on_connection(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=(connection.dialect.name == "sqlite"),
        compare_type=True,
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    borrowed = config.attributes.get("connection")
    if borrowed is not None:
        _run_migrations_on_connection(borrowed)
        return

    url = _resolve_database_url()
    engine = create_engine(url, poolclass=pool.NullPool, future=True)
    try:
        with engine.connect() as conn:
            with migration_connection_guard(conn):
                _run_migrations_on_connection(conn)
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
