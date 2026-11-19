"""Tests for Alembic production migrations, legacy bridge, rollback-safe restore and Postgres/SQLite guards."""

from __future__ import annotations

import io
import logging
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from app import db, migrations_runner
from app.core.config import Settings
from app.main import create_app
from app.models import (
    Attachment,
    AuditEvent,
    Base,
    HydroSession,
    OcrAnalysis,
    OcrMappingProfile,
    Project,
    SectionForm,
    TimeSeriesRecord,
    utcnow,
)
from app.models import (
    TestResult as TestResultModel,
)
from fastapi.testclient import TestClient
from sqlalchemy import inspect

_DUPLICATE_PAIRS: tuple[tuple[str, str, str], ...] = (
    ("test_results", "ix_results_type", "ix_test_results_test_type"),
    ("test_results", "ix_results_decision", "ix_test_results_decision_status"),
    ("attachments", "ix_attachments_session", "ix_attachments_session_id"),
    ("attachments", "ix_attachments_sha", "ix_attachments_sha256"),
    ("ocr_analyses", "ix_ocr_attachment", "ix_ocr_analyses_attachment_id"),
    ("section_forms", "ix_section_forms_project", "ix_section_forms_project_id"),
    ("audit_events", "ix_audit_action", "ix_audit_events_action"),
)

_ALL_APP_TABLES = frozenset(
    {
        "schema_migrations",
        "projects",
        "sessions",
        "test_results",
        "time_series",
        "attachments",
        "ocr_mapping_profiles",
        "ocr_analyses",
        "section_forms",
        "audit_events",
    }
)


def _sqlite_indexes(db_path: Path, table: str) -> set[str]:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(f'PRAGMA index_list("{table}")').fetchall()
        return {str(row[1]) for row in rows}
    finally:
        conn.close()


def _seed_all_tables(session_factory) -> dict[str, str]:
    now = utcnow()
    ws = "a" * 64
    with session_factory() as s:
        proj = Project(
            id="proj-1", workspace_id_hash=ws, code="P1", name="Test Hat", defaults={"k": 1}
        )
        s.add(proj)
        s.flush()

        sess = HydroSession(
            id="sess-1",
            project_id=proj.id,
            workspace_id_hash=ws,
            name="Kesit 1",
            inputs={"od": 406.4},
            result_summary={"air": "BASARILI"},
        )
        s.add(sess)
        s.flush()

        tr = TestResultModel(
            id="tr-1",
            session_id=sess.id,
            test_type="air",
            inputs={"v": 1},
            result={"r": 2},
            decision_status="BASARILI",
            computed_at=now,
        )
        ts = TimeSeriesRecord(
            id="ts-1",
            session_id=sess.id,
            timestamp=now,
            pressure_bar=100.0,
            temperature_c=20.0,
        )
        att = Attachment(
            id="att-1",
            workspace_id_hash=ws,
            session_id=sess.id,
            filename="rapor.pdf",
            stored_path="att-1.pdf",
            mime="application/pdf",
            size_bytes=512,
            sha256="b" * 64,
        )
        prof = OcrMappingProfile(
            id="prof-1",
            workspace_id_hash=ws,
            name="Standart",
            format_key="fmt-1",
        )
        s.add_all([tr, ts, att, prof])
        s.flush()

        ana = OcrAnalysis(
            id="ana-1",
            workspace_id_hash=ws,
            session_id=sess.id,
            attachment_id=att.id,
            mapping_profile_id=prof.id,
            status="done",
        )
        s.add(ana)
        s.flush()

        form = SectionForm(
            id="form-1",
            workspace_id_hash=ws,
            project_id=proj.id,
            session_id=sess.id,
            form_code="test_data",
            form_title="Test Verileri",
            analysis_id=ana.id,
            attachment_id=att.id,
        )
        audit_ev = AuditEvent(
            id="aud-1",
            workspace_id_hash=ws,
            session_id=sess.id,
            action="test.seed",
        )
        s.add_all([form, audit_ev])
        s.commit()
    return {"project_id": "proj-1", "session_id": "sess-1"}


def test_fresh_upgrade_matches_orm_metadata_zero_drift(tmp_path: Path):
    db_file = tmp_path / "fresh.db"
    db.dispose_database()
    try:
        engine = db.configure_database(f"sqlite:///{db_file.as_posix()}")
        rev = db.init_db()
        assert rev == "0003"
        tables = set(inspect(engine).get_table_names())
        assert _ALL_APP_TABLES.issubset(tables)
        assert "alembic_version" in tables

        with engine.connect() as conn:
            mc = MigrationContext.configure(conn, opts={"compare_type": True})
            assert compare_metadata(mc, Base.metadata) == []
    finally:
        db.dispose_database()


def test_0003_drops_exact_7_duplicate_indexes_and_preserves_surviving_7(tmp_path: Path):
    db_file = tmp_path / "dups.db"
    db.dispose_database()
    try:
        engine = db.configure_database(f"sqlite:///{db_file.as_posix()}")
        rev = migrations_runner.run_migrations(engine, target="0002")
        assert rev == "0002"
        for table, dup_idx, surviving_idx in _DUPLICATE_PAIRS:
            idxs = _sqlite_indexes(db_file, table)
            assert dup_idx in idxs
            assert surviving_idx in idxs

        rev2 = migrations_runner.run_migrations(engine, target="head")
        assert rev2 == "0003"
        for table, dup_idx, surviving_idx in _DUPLICATE_PAIRS:
            idxs = _sqlite_indexes(db_file, table)
            assert dup_idx not in idxs
            assert surviving_idx in idxs
    finally:
        db.dispose_database()


def test_0003_downgrade_and_reupgrade_preserves_data(tmp_path: Path):
    db_file = tmp_path / "roundtrip.db"
    db.dispose_database()
    try:
        engine = db.configure_database(f"sqlite:///{db_file.as_posix()}")
        assert migrations_runner.run_migrations(engine, target="head") == "0003"
        seeded = _seed_all_tables(db.get_sessionmaker())

        assert migrations_runner.downgrade_migrations(engine, "0002") == "0002"
        for table, dup_idx, surviving_idx in _DUPLICATE_PAIRS:
            idxs = _sqlite_indexes(db_file, table)
            assert dup_idx in idxs
            assert surviving_idx in idxs

        with db.get_sessionmaker()() as s:
            assert s.get(Project, seeded["project_id"]).defaults == {"k": 1}
            assert s.get(SectionForm, "form-1").form_code == "test_data"
            assert s.get(AuditEvent, "aud-1").action == "test.seed"

        assert migrations_runner.run_migrations(engine, target="head") == "0003"
        for table, dup_idx, _surviving in _DUPLICATE_PAIRS:
            assert dup_idx not in _sqlite_indexes(db_file, table)
    finally:
        db.dispose_database()


def test_0002_baseline_fk_table_creation_order_and_downgrade_base(tmp_path: Path):
    # Compile offline Postgres DDL to verify FK table order strictly (ocr_mapping_profiles before ocr_analyses)
    buf = io.StringIO()
    cfg = Config(output_buffer=buf)
    cfg.set_main_option("script_location", str(migrations_runner.resolve_migrations_dir()))
    cfg.set_main_option("sqlalchemy.url", "postgresql+psycopg://hydro:pass@localhost/hydro")
    command.upgrade(cfg, "0002", sql=True)
    ddl = buf.getvalue()
    assert "PRAGMA" not in ddl
    pos_profiles = ddl.index("CREATE TABLE ocr_mapping_profiles")
    pos_analyses = ddl.index("CREATE TABLE ocr_analyses")
    pos_projects = ddl.index("CREATE TABLE projects")
    pos_sessions = ddl.index("CREATE TABLE sessions")
    assert pos_projects < pos_sessions
    assert pos_profiles < pos_analyses

    # Online SQLite upgrade -> downgrade base -> upgrade head with foreign keys enabled
    db_file = tmp_path / "base_rt.db"
    db.dispose_database()
    try:
        engine = db.configure_database(f"sqlite:///{db_file.as_posix()}")
        assert migrations_runner.run_migrations(engine, target="0002") == "0002"
        migrations_runner.downgrade_migrations(engine, "base")
        remaining = set(inspect(engine).get_table_names()) - {"alembic_version"}
        assert remaining == set()
        assert migrations_runner.run_migrations(engine, target="head") == "0003"
        assert _ALL_APP_TABLES.issubset(set(inspect(engine).get_table_names()))
    finally:
        db.dispose_database()


@pytest.mark.parametrize(
    "case",
    [
        "partial_0001_projects",
        "0001_with_ocr",
        "full_legacy_0002",
        "empty_alembic_version",
        "at_0002",
    ],
)
def test_legacy_bridge_matrix(tmp_path: Path, case: str):
    db_file = tmp_path / f"{case}.db"
    db.dispose_database()
    try:
        url = f"sqlite:///{db_file.as_posix()}"
        legacy_projects_ddl = (
            "CREATE TABLE projects ("
            "id VARCHAR(36) PRIMARY KEY, workspace_id_hash VARCHAR(64), "
            "name VARCHAR(200) NOT NULL, client VARCHAR(200), description TEXT, "
            "created_at DATETIME, updated_at DATETIME, deleted_at DATETIME)"
        )
        if case == "partial_0001_projects":
            c = sqlite3.connect(str(db_file))
            c.execute(legacy_projects_ddl)
            c.execute(
                "INSERT INTO projects VALUES "
                "('p1', 'w1', 'Eski Hat', NULL, NULL, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', NULL)"
            )
            c.commit()
            c.close()
        elif case == "0001_with_ocr":
            c = sqlite3.connect(str(db_file))
            c.execute(legacy_projects_ddl)
            c.execute(
                "CREATE TABLE ocr_analyses ("
                "id VARCHAR(36) PRIMARY KEY, workspace_id_hash VARCHAR(64) NOT NULL, "
                "session_id VARCHAR(36), attachment_id VARCHAR(36) NOT NULL, "
                "mapping_profile_id VARCHAR(36), status VARCHAR(16) NOT NULL, "
                "source VARCHAR(32), page_count INTEGER NOT NULL, "
                "character_count INTEGER NOT NULL, confidence FLOAT, report JSON, "
                "discrepancies JSON NOT NULL, issues JSON NOT NULL, warnings JSON NOT NULL, "
                "needs_human_review BOOLEAN NOT NULL, approved_fields JSON, "
                "error_code VARCHAR(64), error_message TEXT, "
                "created_at DATETIME NOT NULL, started_at DATETIME, finished_at DATETIME)"
            )
            c.execute("CREATE INDEX ix_ocr_attachment ON ocr_analyses (attachment_id)")
            c.execute(
                "INSERT INTO projects VALUES "
                "('p2', 'w1', 'Hat OCR', NULL, NULL, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', NULL)"
            )
            c.commit()
            c.close()
        elif case in {"full_legacy_0002", "empty_alembic_version"}:
            eng = db.configure_database(url)
            assert migrations_runner.run_migrations(eng, target="0002") == "0002"
            with db.get_sessionmaker()() as s:
                s.add(Project(id="p-keep", workspace_id_hash="w" * 64, name="Korunan Hat"))
                s.commit()
            db.dispose_database()
            c = sqlite3.connect(str(db_file))
            if case == "full_legacy_0002":
                c.execute("DROP TABLE alembic_version")
            else:
                c.execute("DELETE FROM alembic_version")
            c.execute(
                "INSERT OR IGNORE INTO schema_migrations VALUES ('0001', 'Baseline', '2026-01-01T00:00:00Z'), ('0002', 'Meta', '2026-01-01T00:00:00Z')"
            )
            c.commit()
            c.close()
        elif case == "at_0002":
            eng = db.configure_database(url)
            assert migrations_runner.run_migrations(eng, target="0002") == "0002"
            db.dispose_database()

        db.configure_database(url)
        assert db.init_db() == "0003"
        assert db.current_schema_version() == "0003"

        for table, dup_idx, surviving_idx in _DUPLICATE_PAIRS:
            idxs = _sqlite_indexes(db_file, table)
            assert dup_idx not in idxs
            assert surviving_idx in idxs

        if case in {"full_legacy_0002", "empty_alembic_version"}:
            with db.get_sessionmaker()() as s:
                assert s.get(Project, "p-keep").name == "Korunan Hat"
        if case in {"partial_0001_projects", "0001_with_ocr"}:
            with db.get_sessionmaker()() as s:
                p = s.get(Project, "p1" if case == "partial_0001_projects" else "p2")
                assert p.status == "active"
                assert p.defaults == {}
    finally:
        db.dispose_database()


def test_sqlite_foreign_keys_toggled_outside_tx_and_restored_on_error(tmp_path: Path):
    db_file = tmp_path / "fk_guard.db"
    db.dispose_database()
    try:
        engine = db.configure_database(f"sqlite:///{db_file.as_posix()}")
        observed_during_guard: list[int] = []
        with engine.connect() as conn:
            assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
            with migrations_runner.migration_connection_guard(conn):
                fk_value = conn.exec_driver_sql("PRAGMA foreign_keys").scalar()
                assert fk_value is not None
                observed_during_guard.append(int(fk_value))
            assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        assert observed_during_guard == [0]

        with engine.connect() as conn:
            with pytest.raises(RuntimeError, match="forced"):
                with migrations_runner.migration_connection_guard(conn):
                    raise RuntimeError("forced")
            assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
    finally:
        db.dispose_database()


def test_postgres_advisory_lock_acquire_and_release_on_success_and_error():
    executed: list[tuple[str, Any]] = []

    class _FakeDialect:
        name = "postgresql"

    class _FakeConn:
        dialect = _FakeDialect()

        def __init__(self, *, fail_in_tx: bool = False) -> None:
            self._in_tx = fail_in_tx

        def in_transaction(self) -> bool:
            return self._in_tx

        def commit(self) -> None:
            self._in_tx = False
            executed.append(("COMMIT", None))

        def rollback(self) -> None:
            self._in_tx = False
            executed.append(("ROLLBACK", None))

        def execution_options(self, **kwargs: Any):
            executed.append(("EXEC_OPTS", kwargs))
            return self

        def execute(self, stmt, params=None):  # noqa: ANN001
            executed.append((str(stmt), params))

    conn_ok = _FakeConn()
    with migrations_runner.migration_connection_guard(conn_ok):  # type: ignore[arg-type]
        pass
    sql_texts = [s for s, _ in executed]
    assert any("pg_advisory_lock" in s for s in sql_texts)
    assert any("pg_advisory_unlock" in s for s in sql_texts)
    assert not any("PRAGMA" in s for s in sql_texts)

    executed.clear()
    conn_err = _FakeConn(fail_in_tx=True)
    with pytest.raises(ValueError, match="boom"):
        with migrations_runner.migration_connection_guard(conn_err):  # type: ignore[arg-type]
            conn_err._in_tx = True
            raise ValueError("boom")
    err_sql = [s for s, _ in executed]
    assert "ROLLBACK" in err_sql
    assert err_sql.index("ROLLBACK") < next(
        i for i, s in enumerate(err_sql) if "pg_advisory_unlock" in s
    )
    assert -(2**63) <= migrations_runner.POSTGRES_ADVISORY_LOCK_KEY < 2**63


def test_hydro_auto_migrate_flag(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HYDRO_AUTO_MIGRATE", "0")
    s_env = Settings.from_env()
    assert s_env.auto_migrate is False

    db_file = tmp_path / "no_auto.db"
    app = create_app(
        Settings(
            data_dir=tmp_path / "d1",
            database_url=f"sqlite:///{db_file.as_posix()}",
            auto_migrate=False,
        )
    )
    try:
        tc = TestClient(app)
        health = tc.get("/api/health").json()
        assert health["db"]["ok"] is True
        assert health["db"]["migration"] is None
        assert inspect(db.get_engine()).get_table_names() == []
    finally:
        db.dispose_database()


def test_restore_db_backup_future_revision_and_broken_fk_roll_back_422(tmp_path: Path):
    data_dir = tmp_path / "data"
    live_db = data_dir / "hydro_web.db"
    app = create_app(
        Settings(
            data_dir=data_dir,
            database_url=f"sqlite:///{live_db.as_posix()}",
        )
    )
    ws = {"X-Session-ID": "restore-ws"}
    try:
        tc = TestClient(app)
        created = tc.post("/api/projects", headers=ws, json={"name": "Canli Proje"})
        assert created.status_code == 201
        live_proj_id = created.json()["id"]

        # 1) Future revision backup -> 422 and rollback via multipart + backup_filename
        future_db = tmp_path / "future.db"
        conn = sqlite3.connect(str(future_db))
        conn.execute("CREATE TABLE projects (id VARCHAR(36) PRIMARY KEY, name VARCHAR(200))")
        conn.execute("INSERT INTO projects VALUES ('p-future', 'Gelecek Surum')")
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)")
        conn.execute("INSERT INTO alembic_version VALUES ('9999_future')")
        conn.commit()
        conn.close()

        res_future = tc.post(
            "/api/system/db-restore",
            headers=ws,
            files={"file": ("future.db", future_db.read_bytes(), "application/octet-stream")},
        )
        assert res_future.status_code == 422
        assert res_future.json()["code"] == "validation_error"

        # 2) Backup with orphaned FK row -> 422 and rollback
        broken_fk_db = tmp_path / "broken_fk.db"
        # Copy current valid live schema into broken_fk_db and inject an orphaned test_results row
        src_live = sqlite3.connect(str(live_db))
        dst_broken = sqlite3.connect(str(broken_fk_db))
        src_live.backup(dst_broken)
        dst_broken.execute("PRAGMA foreign_keys=OFF")
        dst_broken.execute(
            "INSERT INTO test_results (id, session_id, test_type, inputs, result, decision_status, decision_title, decision_summary, decision_rule, decision, engine_version, computed_at, created_at) "
            "VALUES ('orphan-1', 'nonexistent-session', 'air', '{}', '{}', 'BEKLIYOR', '', '', '', '{}', '1', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
        )
        dst_broken.commit()
        dst_broken.close()
        src_live.close()

        res_fk = tc.post(
            "/api/system/db-restore",
            headers=ws,
            files={"file": ("broken_fk.db", broken_fk_db.read_bytes(), "application/octet-stream")},
        )
        assert res_fk.status_code == 422
        assert res_fk.json()["code"] == "validation_error"

        # Live app must still contain live_proj_id and accept new writes cleanly
        items = tc.get("/api/projects", headers=ws).json()["items"]
        ids = {item["id"] for item in items}
        assert live_proj_id in ids
        assert "p-future" not in ids
        health = tc.get("/api/health").json()
        assert health["db"]["ok"] is True
        assert health["db"]["migration"] == "0003"
        assert (
            tc.post("/api/projects", headers=ws, json={"name": "Sonraki Kayit"}).status_code == 201
        )
    finally:
        db.dispose_database()


def test_restore_db_backup_from_legacy_0002_upgrades_to_0003(tmp_path: Path):
    # Create a legacy pre-0003 backup containing project P_OLD
    old_db = tmp_path / "old_0002.db"
    db.dispose_database()
    old_eng = db.configure_database(f"sqlite:///{old_db.as_posix()}")
    migrations_runner.run_migrations(old_eng, target="0002")
    with db.get_sessionmaker()() as s:
        from app.core import security as sec

        s.add(
            Project(
                id="p-old",
                workspace_id_hash=sec.workspace_hash("ws-old"),
                name="Yedekten Donen Proje",
            )
        )
        s.commit()
    db.dispose_database()
    old_bytes = old_db.read_bytes()

    data_dir = tmp_path / "live"
    live_db = data_dir / "hydro_web.db"
    app = create_app(Settings(data_dir=data_dir, database_url=f"sqlite:///{live_db.as_posix()}"))
    try:
        tc = TestClient(app)
        res = tc.post(
            "/api/system/db-restore",
            headers={"X-Session-ID": "ws-old"},
            files={"file": ("old.db", old_bytes, "application/octet-stream")},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["restored"] is True
        assert body["stats"]["schema_migration"] == "0003"
        projects = tc.get("/api/projects", headers={"X-Session-ID": "ws-old"}).json()["items"]
        assert any(p["id"] == "p-old" for p in projects)
    finally:
        db.dispose_database()


def test_idempotent_init_db_cwd_independent_and_preserves_loggers(tmp_path: Path, monkeypatch):
    app_logger = logging.getLogger("hydro.web")
    app_logger.disabled = False
    dummy_handler = logging.NullHandler()
    app_logger.addHandler(dummy_handler)

    monkeypatch.chdir(tmp_path)
    db.dispose_database()
    try:
        db.configure_database("sqlite:///:memory:")
        assert db.init_db() == "0003"
        assert db.init_db() == "0003"
        assert db.init_db() == "0003"
        assert app_logger.disabled is False
        assert dummy_handler in app_logger.handlers
    finally:
        app_logger.removeHandler(dummy_handler)
        db.dispose_database()


def test_frozen_migrations_dir_resolution_and_cli_roundtrip(tmp_path: Path, monkeypatch):
    meipass = tmp_path / "meipass"
    (meipass / "webapp_migrations").mkdir(parents=True)
    (meipass / "webapp_migrations" / "env.py").write_text("# frozen", encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)
    assert migrations_runner.resolve_migrations_dir() == meipass / "webapp_migrations"

    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)

    repo_root = Path(__file__).resolve().parents[3]
    cli_db = tmp_path / "cli_test.db"
    env = {**os.environ, "HYDRO_DATABASE_URL": f"sqlite:///{cli_db.as_posix()}"}
    for cmd in (
        [sys.executable, "-m", "alembic", "-c", "webapp/backend/alembic.ini", "upgrade", "head"],
        [sys.executable, "-m", "alembic", "-c", "webapp/backend/alembic.ini", "downgrade", "0002"],
        [sys.executable, "-m", "alembic", "-c", "webapp/backend/alembic.ini", "upgrade", "head"],
    ):
        proc = subprocess.run(
            cmd, cwd=str(repo_root), env=env, capture_output=True, text=True, check=False
        )
        assert proc.returncode == 0, f"cmd={cmd}\nstdout={proc.stdout}\nstderr={proc.stderr}"
