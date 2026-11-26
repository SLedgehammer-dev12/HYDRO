#!/usr/bin/env python3
"""Automated SQLite backup + isolated restore & integrity verification drill."""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "webapp" / "backend"
for _p in (str(BACKEND_DIR), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def prune_old_backups(
    backups_dir: Path,
    *,
    retain_days: int = 30,
    max_backups: int = 30,
) -> int:
    """Prune stale drill/auto ``.db`` backups beyond age or count limits."""

    if not backups_dir.is_dir():
        return 0
    files = sorted(
        (p for p in backups_dir.iterdir() if p.is_file() and p.suffix == ".db"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    cutoff = time.time() - max(1, int(retain_days)) * 86400.0
    removed = 0
    for idx, path in enumerate(files):
        too_many = max_backups > 0 and idx >= max_backups
        too_old = path.stat().st_mtime < cutoff
        if too_many or too_old:
            path.unlink(missing_ok=True)
            removed += 1
    return removed


def run_postgres_verify_drill(database_url: str) -> dict[str, Any]:
    """Verify PostgreSQL connectivity and Alembic head parity without data mutation."""

    from app import migrations_runner
    from sqlalchemy import create_engine, text

    started = time.monotonic()
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            rev_row = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
            revision = str(rev_row[0]) if rev_row else ""
            if revision != migrations_runner.HEAD_REVISION:
                raise RuntimeError(
                    f"PostgreSQL Alembic revision mismatch: {revision!r} != {migrations_runner.HEAD_REVISION!r}"
                )
    finally:
        engine.dispose()

    return {
        "status": "ok",
        "dialect": "postgresql",
        "revision": migrations_runner.HEAD_REVISION,
        "rto_ms": round((time.monotonic() - started) * 1000.0, 1),
    }


def run_backup_drill(
    data_dir: Path,
    *,
    retain_days: int = 30,
    max_backups: int = 30,
) -> dict[str, Any]:
    """Create a backup from ``data_dir``, restore to staging, migrate, and check integrity."""
    from app import db as db_mod
    from app import migrations_runner
    from app.core.config import Settings
    from app.services import db_admin

    started = time.monotonic()
    db_file = data_dir / "hydro_web.db"
    settings = Settings(
        database_url=f"sqlite:///{db_file.resolve().as_posix()}",
        data_dir=data_dir,
        frontend_dist=ROOT / "webapp" / "frontend" / "dist",
    )
    settings.ensure_directories()

    db_mod.dispose_database()
    db_mod.configure_database(settings.database_url)
    db_mod.init_db()
    try:
        backup_info = db_admin.create_db_backup(settings, reason="drill")
        backup_path = db_admin.resolve_backup_path(settings, str(backup_info["filename"]))

        with tempfile.TemporaryDirectory(prefix="hydro_drill_stage_") as stage_dir:
            staged_db = Path(stage_dir) / "staged_hydro.db"
            shutil.copy2(backup_path, staged_db)
            db_admin._validate_sqlite_backup_file(staged_db)
            db_admin._verify_and_migrate_staging_sqlite(staged_db)

            conn = sqlite3.connect(str(staged_db))
            try:
                ic = conn.execute("PRAGMA integrity_check").fetchone()
                if not ic or str(ic[0]).lower() != "ok":
                    raise RuntimeError(f"PRAGMA integrity_check failed: {ic}")
                rev_row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
                revision = str(rev_row[0]) if rev_row else ""
                if revision != migrations_runner.HEAD_REVISION:
                    raise RuntimeError(
                        f"Alembic revision mismatch: {revision!r} != {migrations_runner.HEAD_REVISION!r}"
                    )
            finally:
                conn.close()

        pruned_count = prune_old_backups(
            backup_path.parent,
            retain_days=retain_days,
            max_backups=max_backups,
        )
    finally:
        db_mod.dispose_database()

    rto_ms = round((time.monotonic() - started) * 1000.0, 1)
    return {
        "status": "ok",
        "backup_filename": backup_info["filename"],
        "size_bytes": backup_info["size_bytes"],
        "revision": migrations_runner.HEAD_REVISION,
        "pruned_count": pruned_count,
        "rto_ms": rto_ms,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Target data directory containing hydro_web.db.",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Run the drill against an isolated temporary directory.",
    )
    parser.add_argument(
        "--retain-days",
        type=int,
        default=30,
        help="Delete backups older than this many days (default: 30).",
    )
    parser.add_argument(
        "--max-backups",
        type=int,
        default=30,
        help="Keep at most this many newest backups (default: 30).",
    )
    parser.add_argument(
        "--database-url",
        type=str,
        default=None,
        help="Optional PostgreSQL URL to verify connectivity and Alembic head parity.",
    )
    args = parser.parse_args(argv)

    if args.database_url:
        res = run_postgres_verify_drill(args.database_url)
        print(f"POSTGRES_DRILL_OK rev={res['revision']} rto_ms={res['rto_ms']}")
        return 0

    if args.smoke or args.data_dir is None:
        with tempfile.TemporaryDirectory(prefix="hydro_drill_smoke_") as tmp_dir:
            res = run_backup_drill(
                Path(tmp_dir),
                retain_days=args.retain_days,
                max_backups=args.max_backups,
            )
    else:
        res = run_backup_drill(
            args.data_dir,
            retain_days=args.retain_days,
            max_backups=args.max_backups,
        )

    print(
        f"BACKUP_DRILL_OK filename={res['backup_filename']} "
        f"size={res['size_bytes']} rev={res['revision']} "
        f"pruned={res['pruned_count']} rto_ms={res['rto_ms']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
