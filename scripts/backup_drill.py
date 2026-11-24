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


def run_backup_drill(data_dir: Path) -> dict[str, Any]:
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
    finally:
        db_mod.dispose_database()

    rto_ms = round((time.monotonic() - started) * 1000.0, 1)
    return {
        "status": "ok",
        "backup_filename": backup_info["filename"],
        "size_bytes": backup_info["size_bytes"],
        "revision": migrations_runner.HEAD_REVISION,
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
    args = parser.parse_args(argv)

    if args.smoke or args.data_dir is None:
        with tempfile.TemporaryDirectory(prefix="hydro_drill_smoke_") as tmp_dir:
            res = run_backup_drill(Path(tmp_dir))
    else:
        res = run_backup_drill(args.data_dir)

    print(
        f"BACKUP_DRILL_OK filename={res['backup_filename']} "
        f"size={res['size_bytes']} rev={res['revision']} rto_ms={res['rto_ms']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
