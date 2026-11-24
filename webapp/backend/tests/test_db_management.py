"""Tests for database migrations, rich project defaults, project data generation and DB admin."""

from __future__ import annotations

import io
import json
import sqlite3
import zipfile
from pathlib import Path

from app import db
from app.core import security
from app.core.config import Settings
from app.main import create_app
from app.models import Attachment, new_uuid
from app.services import storage
from fastapi.testclient import TestClient


def test_legacy_0001_schema_migrates_to_0002(tmp_path: Path):
    db_file = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute(
        """
        CREATE TABLE projects (
            id VARCHAR(36) PRIMARY KEY,
            workspace_id_hash VARCHAR(64),
            name VARCHAR(200) NOT NULL,
            client VARCHAR(200),
            description TEXT,
            created_at DATETIME,
            updated_at DATETIME,
            deleted_at DATETIME
        )
        """
    )
    conn.execute(
        "INSERT INTO projects (id, workspace_id_hash, name) VALUES (?, ?, ?)",
        ("p-legacy", "abc123", "Eski Proje"),
    )
    conn.commit()
    conn.close()

    settings = Settings(
        database_url=f"sqlite:///{db_file.as_posix()}",
        data_dir=tmp_path / "data",
        frontend_dist=tmp_path / "dist",
    )
    db.dispose_database()
    app = create_app(settings)
    with TestClient(app) as tc:
        health = tc.get("/api/health").json()
        assert health["db"]["ok"] is True
        assert health["db"]["migration"] == db.CURRENT_MIGRATION

    conn = sqlite3.connect(str(db_file))
    cols = {row[1] for row in conn.execute("PRAGMA table_info(projects)").fetchall()}
    assert {"code", "contractor", "supervisor", "pipeline_length_m", "status", "defaults"}.issubset(
        cols
    )
    row = conn.execute("SELECT name, status FROM projects WHERE id='p-legacy'").fetchone()
    assert row == ("Eski Proje", "active")
    migs = {row[0] for row in conn.execute("SELECT version FROM schema_migrations").fetchall()}
    assert {"0001", "0002"}.issubset(migs)
    alembic_revs = [
        row[0] for row in conn.execute("SELECT version_num FROM alembic_version").fetchall()
    ]
    assert alembic_revs == [db.CURRENT_MIGRATION]
    conn.close()
    db.dispose_database()


def test_project_rich_fields_and_section_defaults_inheritance(client, headers):
    created = client.post(
        "/api/projects",
        headers=headers,
        json={
            "name": "Doğu Anadolu İletim",
            "code": "DA-01",
            "client": "BOTAŞ",
            "contractor": "Yüklenici A.Ş.",
            "supervisor": "Kontrol Mühendislik",
            "pipeline_length_m": 36000,
            "status": "active",
            "defaults": {
                "outside_diameter_mm": 1016.0,
                "wall_thickness_mm": 12.7,
                "material_grade": "API 5L PSL2 X65 / L450 - SMYS 450 MPa",
                "smys_mpa": 450.0,
                "design_pressure_bar": 75.0,
                "location_class": "Class 2 - min 1.40 x dizayn basinci",
                "pump_location": "Baslangic noktasi",
                "k_factor": 1.03,
            },
        },
    )
    assert created.status_code == 201
    proj = created.json()
    assert proj["contractor"] == "Yüklenici A.Ş."
    assert proj["supervisor"] == "Kontrol Mühendislik"
    assert proj["pipeline_length_m"] == 36000.0
    assert proj["defaults"]["outside_diameter_mm"] == 1016.0

    # Empty section inherits defaults from project
    s1 = client.post(
        "/api/sessions",
        headers=headers,
        json={"name": "K-01", "project_id": proj["id"]},
    )
    assert s1.status_code == 201
    inputs1 = s1.json()["inputs"]
    assert inputs1["geometry"]["outside_diameter_mm"] == 1016.0
    assert inputs1["geometry"]["wall_thickness_mm"] == 12.7
    assert inputs1["section_profile"]["design_pressure_bar"] == 75.0
    assert inputs1["section_profile"]["smys_mpa"] == 450.0
    assert inputs1["location_class"] == "Class 2 - min 1.40 x dizayn basinci"
    assert inputs1["air"]["k_factor"] == 1.03

    # Explicit overrides are preserved
    s2 = client.post(
        "/api/sessions",
        headers=headers,
        json={
            "name": "K-02",
            "project_id": proj["id"],
            "inputs": {
                "geometry": {
                    "outside_diameter_mm": 610.0,
                    "wall_thickness_mm": 9.5,
                    "length_m": 8000,
                },
                "location_class": "Class 3 - min 1.50 x dizayn basinci",
            },
        },
    )
    assert s2.status_code == 201
    inputs2 = s2.json()["inputs"]
    assert inputs2["geometry"]["outside_diameter_mm"] == 610.0
    assert inputs2["location_class"] == "Class 3 - min 1.50 x dizayn basinci"
    # Unspecified default still fills
    assert inputs2["section_profile"]["smys_mpa"] == 450.0


def test_workspace_list_and_claim(client):
    ws_old = {"X-Session-ID": "old-browser-ws"}
    ws_new = {"X-Session-ID": "new-browser-ws"}

    p = client.post("/api/projects", headers=ws_old, json={"name": "Eski Tarayıcı Projesi"}).json()
    s = client.post(
        "/api/sessions", headers=ws_old, json={"name": "Kesit-1", "project_id": p["id"]}
    ).json()
    assert s["project_id"] == p["id"]

    # New browser doesn't see the project yet
    assert client.get("/api/projects", headers=ws_new).json()["total"] == 0

    listed = client.get("/api/system/workspaces", headers=ws_new).json()
    old_entry = next(item for item in listed["items"] if not item["is_current"])
    assert old_entry["project_count"] == 1
    assert old_entry["section_count"] == 1
    assert "Eski Tarayıcı Projesi" in old_entry["sample_projects"]

    # Blind claim by hash alone is denied by default (403)
    denied = client.post(
        "/api/system/workspaces/claim",
        headers=ws_new,
        json={"source_workspace_hash": old_entry["workspace_hash"]},
    )
    assert denied.status_code == 403

    # Claim with ownership proof (raw workspace key) succeeds cleanly
    claimed = client.post(
        "/api/system/workspaces/claim",
        headers=ws_new,
        json={
            "source_workspace_hash": old_entry["workspace_hash"],
            "source_workspace_key": ws_old["X-Session-ID"],
        },
    )
    assert claimed.status_code == 200
    assert claimed.json()["moved"]["projects"] == 1
    assert claimed.json()["moved"]["sessions"] == 1

    # Now new browser sees it!
    projs_new = client.get("/api/projects", headers=ws_new).json()
    assert projs_new["total"] == 1
    assert projs_new["items"][0]["id"] == p["id"]


def test_generate_sample_project_dataset_and_exports(client, headers):
    res = client.post(
        "/api/projects/generate-sample",
        headers=headers,
        json={"scenario": "mixed", "section_count": 3, "name": "Demo Hat", "code": "DM-01"},
    )
    assert res.status_code == 201
    body = res.json()
    proj_id = body["project"]["id"]
    assert body["project"]["section_count"] == 3
    assert len(body["sections"]) == 3

    dataset_res = client.get(f"/api/projects/{proj_id}/dataset", headers=headers)
    assert dataset_res.status_code == 200
    dataset = dataset_res.json()
    assert dataset["summary"]["section_count"] == 3
    assert dataset["summary"]["continuity_ok"] is True
    assert dataset["summary"]["total_length_m"] == 30000.0
    assert dataset["summary"]["forms_completion_pct"] == 100.0
    assert len(dataset["sections"]) == 3
    assert dataset["sections"][0]["overall_status"] == "BASARILI"
    assert dataset["sections"][2]["overall_status"] == "BASARISIZ"

    # Verify time series records exist
    first_sid = dataset["sections"][0]["session_id"]
    ts_res = client.get(f"/api/sessions/{first_sid}/time-series", headers=headers)
    assert ts_res.status_code == 200
    assert ts_res.json()["total"] == 25

    # Export XLSX, PDF, CSV, JSON
    for fmt, magic in (
        ("xlsx", b"PK\x03\x04"),
        ("pdf", b"%PDF-"),
        ("csv", b"\xef\xbb\xbf"),
        ("json", b"{"),
    ):
        exp = client.post(
            f"/api/projects/{proj_id}/export",
            headers=headers,
            json={"format": fmt},
        )
        assert exp.status_code == 200
        assert exp.content.startswith(magic)


def test_generate_sections_sync_forms_and_clone(client, headers):
    proj = client.post(
        "/api/projects",
        headers=headers,
        json={
            "name": "Toplu Üretim Hattı",
            "code": "TU-10",
            "client": "BOTAŞ",
            "contractor": "Alpha İnşaat",
            "defaults": {
                "outside_diameter_mm": 1219.2,
                "wall_thickness_mm": 14.3,
                "material_grade": "API 5L PSL2 X70 / L485 - SMYS 485 MPa",
                "smys_mpa": 485.0,
                "design_pressure_bar": 82.0,
            },
        },
    ).json()

    # Volume limit (12,500 m3) caps 48" pipe sections below 11,500 m
    gen = client.post(
        f"/api/projects/{proj['id']}/generate-sections",
        headers=headers,
        json={"total_length_m": 25000, "max_section_length_m": 20000, "respect_volume_limit": True},
    )
    assert gen.status_code == 201
    gen_body = gen.json()
    assert gen_body["created_count"] == 3

    dataset = client.get(f"/api/projects/{proj['id']}/dataset", headers=headers).json()
    assert dataset["summary"]["continuity_ok"] is True
    assert all(sec["internal_volume_m3"] <= 12500.0 for sec in dataset["sections"])

    # Sync forms without overwriting
    sync = client.post(
        f"/api/projects/{proj['id']}/sync-forms",
        headers=headers,
        json={"overwrite_existing": False, "form_codes": ["test_data", "filling"]},
    )
    assert sync.status_code == 200
    assert sync.json()["updated_forms"] >= 3

    # Clone as template vs full
    tpl = client.post(
        f"/api/projects/{proj['id']}/clone",
        headers=headers,
        json={"mode": "template", "name": "Şablon Kopya"},
    )
    assert tpl.status_code == 201
    assert tpl.json()["section_count"] == 3
    tpl_dataset = client.get(
        f"/api/projects/{tpl.json()['project']['id']}/dataset", headers=headers
    ).json()
    assert tpl_dataset["summary"]["forms_filled_total"] == 0

    full = client.post(
        f"/api/projects/{proj['id']}/clone",
        headers=headers,
        json={"mode": "full", "name": "Tam Kopya"},
    )
    assert full.status_code == 201
    full_dataset = client.get(
        f"/api/projects/{full.json()['project']['id']}/dataset", headers=headers
    ).json()
    assert full_dataset["summary"]["forms_filled_total"] >= 3


def test_project_archive_roundtrip_and_security(client, headers, settings):
    sample = client.post(
        "/api/projects/generate-sample",
        headers=headers,
        json={"scenario": "passing", "section_count": 2, "name": "Arşiv Kaynak", "code": "AR-01"},
    ).json()
    proj_id = sample["project"]["id"]
    sess_id = sample["sections"][0]["id"]
    ws_hash = security.workspace_hash("test-workspace")

    # Attach a real PDF under uploads_dir and link it cleanly
    pdf_bytes = b"%PDF-1.4\n1 0 obj <<>> endobj\ntrailer <<>>\n%%EOF\n"
    stored = storage.store_upload(
        uploads_root=settings.uploads_dir,
        workspace_hash=ws_hash,
        session_id=sess_id,
        original_name="form018.pdf",
        stream=io.BytesIO(pdf_bytes),
        max_bytes=settings.max_upload_bytes,
    )
    with db.session_scope() as session:
        session.add(
            Attachment(
                id=new_uuid(),
                workspace_id_hash=ws_hash,
                session_id=sess_id,
                filename=stored.filename,
                stored_path=stored.relative_path,
                mime=stored.mime,
                size_bytes=stored.size_bytes,
                sha256=stored.sha256,
                kind="report_pdf",
            )
        )

    arc_res = client.get(f"/api/projects/{proj_id}/archive", headers=headers)
    assert arc_res.status_code == 200
    assert arc_res.content.startswith(b"PK\x03\x04")

    # 1) Reject Zip-Slip attempt
    slip_buf = io.BytesIO()
    with zipfile.ZipFile(slip_buf, "w") as zf:
        zf.writestr("../../evil.txt", b"pwn")
    bad_slip = client.post(
        "/api/projects/import-archive",
        headers=headers,
        files={"file": ("evil.hydroproj.zip", slip_buf.getvalue(), "application/zip")},
    )
    assert bad_slip.status_code in (400, 422)

    # 2) Reject tampered SHA-256 against manifest
    tampered_buf = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(arc_res.content), "r") as z_in,
        zipfile.ZipFile(tampered_buf, "w", compression=zipfile.ZIP_DEFLATED) as z_out,
    ):
        for item in z_in.infolist():
            raw = z_in.read(item.filename)
            if item.filename == "project.json":
                obj = json.loads(raw.decode("utf-8"))
                obj["name"] = "TAMPERED"
                raw = json.dumps(obj).encode("utf-8")
            z_out.writestr(item.filename, raw)
    bad_hash = client.post(
        "/api/projects/import-archive",
        headers=headers,
        files={"file": ("tampered.hydroproj.zip", tampered_buf.getvalue(), "application/zip")},
    )
    assert bad_hash.status_code in (400, 422)

    # 3) Clean import into another workspace
    other_headers = {"X-Session-ID": "archive-target-ws"}
    imp = client.post(
        "/api/projects/import-archive",
        headers=other_headers,
        data={"target_project_name": "Arşivden Geri Yüklenen", "target_project_code": "AR-02"},
        files={"file": ("ar01.hydroproj.zip", arc_res.content, "application/zip")},
    )
    assert imp.status_code == 201
    imp_body = imp.json()
    assert imp_body["project"]["id"] != proj_id
    assert imp_body["imported_sections"] == 2
    assert imp_body["imported_forms"] >= 22
    assert imp_body["imported_attachments"] == 1
    assert imp_body["imported_results"] >= 6
    assert imp_body["imported_time_series"] == 50


def test_desktop_db_import(client, headers, tmp_path: Path):
    # Invalid bytes must return 400/422
    bad = client.post(
        "/api/import/desktop-db",
        headers=headers,
        files={"file": ("bad.db", b"not-a-sqlite-db" * 20, "application/octet-stream")},
    )
    assert bad.status_code in (400, 422)

    desktop_db = tmp_path / "desktop_hydro.db"
    conn = sqlite3.connect(str(desktop_db))
    conn.executescript(
        """
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            name TEXT,
            created_at TEXT,
            updated_at TEXT,
            notes TEXT,
            is_active INTEGER,
            inputs_json TEXT,
            wizard_state_json TEXT
        );
        CREATE TABLE geometry_records (
            id INTEGER PRIMARY KEY,
            session_id TEXT,
            outside_diameter_mm REAL,
            wall_thickness_mm REAL,
            length_m REAL,
            highest_elevation_m REAL,
            lowest_elevation_m REAL,
            design_pressure_bar REAL,
            segments_json TEXT
        );
        CREATE TABLE test_entries (
            id INTEGER PRIMARY KEY,
            session_id TEXT,
            test_type TEXT,
            inputs_json TEXT,
            result_json TEXT,
            decision_status TEXT,
            decision_title TEXT,
            decision_summary TEXT,
            evaluated_at TEXT
        );
        CREATE TABLE time_series_records (
            id INTEGER PRIMARY KEY,
            session_id TEXT,
            timestamp TEXT,
            pressure_bar REAL,
            temperature_c REAL,
            volume_m3 REAL,
            notes TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "d-sess-1",
            "Masaüstü Test Kesiti",
            "2026-10-01T10:00:00Z",
            "2026-10-01T11:00:00Z",
            "Saha notu",
            1,
            "{}",
            None,
        ),
    )
    conn.execute(
        "INSERT INTO geometry_records VALUES (1, 'd-sess-1', 1016.0, 12.7, 9000.0, 220.0, 175.0, 75.0, NULL)"
    )
    conn.execute(
        "INSERT INTO test_entries VALUES (1, 'd-sess-1', 'air', '{}', '{\"passed\": true}', 'BASARILI', 'Tamam', 'Ok', '2026-10-01T11:00:00Z')"
    )
    conn.execute(
        "INSERT INTO time_series_records VALUES (1, 'd-sess-1', '2026-10-01T10:30:00Z', 106.5, 15.2, 7100.0, 'saat 1')"
    )
    conn.commit()
    conn.close()

    res = client.post(
        "/api/import/desktop-db",
        headers=headers,
        data={"project_name": "Eski Masaüstü Projesi", "project_code": "DSK-1"},
        files={"file": ("hydro.db", desktop_db.read_bytes(), "application/octet-stream")},
    )
    assert res.status_code == 201
    body = res.json()
    assert body["project"]["name"] == "Eski Masaüstü Projesi"
    assert body["imported_sessions"] == 1
    assert body["imported_results"] == 1
    assert body["imported_time_series"] == 1


def test_db_backup_restore_and_admin_guard(headers, tmp_path: Path):
    live_dir = tmp_path / "live"
    live_settings = Settings(
        data_dir=live_dir,
        database_url=f"sqlite:///{live_dir}/hydro.db",
        auth_mode="none",
    )
    app = create_app(live_settings)
    try:
        file_client = TestClient(app)
        created = file_client.post(
            "/api/projects",
            headers=headers,
            json={"name": "Yedek Öncesi Proje", "code": "BKP-1"},
        )
        assert created.status_code == 201
        proj_before_id = created.json()["id"]

        stats_res = file_client.get("/api/system/db-stats", headers=headers)
        assert stats_res.status_code == 200
        stats_body = stats_res.json()
        assert stats_body["is_sqlite"] is True
        assert stats_body["schema_migration"] == db.CURRENT_MIGRATION
        assert stats_body["table_counts"]["projects"] >= 1

        bkp_res = file_client.post(
            "/api/system/db-backup", headers=headers, json={"reason": "smoke"}
        )
        assert bkp_res.status_code == 201
        bkp_name = bkp_res.json()["filename"]

        list_res = file_client.get("/api/system/db-backups", headers=headers)
        assert list_res.status_code == 200
        assert any(item["filename"] == bkp_name for item in list_res.json()["items"])

        dl_res = file_client.get(f"/api/system/db-backups/{bkp_name}", headers=headers)
        assert dl_res.status_code == 200
        assert dl_res.content.startswith(b"SQLite format 3\x00")

        # Mutate DB after backup
        after_proj = file_client.post(
            "/api/projects",
            headers=headers,
            json={"name": "Geri Alınacak Proje", "code": "TMP-9"},
        ).json()

        # Corrupt file restore must fail 400/422
        corrupt = file_client.post(
            "/api/system/db-restore",
            headers=headers,
            files={"file": ("corrupt.db", b"corrupt-bytes" * 20, "application/octet-stream")},
        )
        assert corrupt.status_code in (400, 422)

        # Restore valid backup by filename
        rst = file_client.post(
            "/api/system/db-restore",
            headers=headers,
            json={"backup_filename": bkp_name},
        )
        assert rst.status_code == 200
        assert rst.json()["restored"] is True
        assert rst.json()["pre_restore_backup"] is not None

        # After restore, pre-backup project exists and post-backup project is gone
        projects_after = file_client.get("/api/projects", headers=headers).json()["items"]
        ids_after = {item["id"] for item in projects_after}
        assert proj_before_id in ids_after
        assert after_proj["id"] not in ids_after
    finally:
        db.dispose_database()

    # auth_mode != 'none' blocks local DB admin endpoints
    guarded_dir = tmp_path / "guarded"
    guarded_app = create_app(
        Settings(
            data_dir=guarded_dir,
            database_url=f"sqlite:///{guarded_dir}/hydro.db",
            auth_mode="token",
        )
    )
    try:
        guarded_client = TestClient(guarded_app)
        denied = guarded_client.post("/api/system/db-backup", headers=headers)
        assert denied.status_code == 403
    finally:
        db.dispose_database()


def test_trash_restore_purge_and_maintenance(client, headers, settings):
    proj = client.post(
        "/api/projects",
        headers=headers,
        json={"name": "Çöp Kutusu Testi", "code": "TRS-1"},
    ).json()
    sess = client.post(
        "/api/sessions",
        headers=headers,
        json={"project_id": proj["id"], "name": "K-01 Kesiti"},
    ).json()

    # Soft delete project (cascades soft delete to section)
    del_res = client.delete(f"/api/projects/{proj['id']}", headers=headers)
    assert del_res.status_code == 204

    trash = client.get("/api/system/trash", headers=headers).json()
    assert any(
        item["entity_type"] == "project" and item["id"] == proj["id"] for item in trash["items"]
    )

    # Restore project
    rst = client.post(
        "/api/system/trash/restore",
        headers=headers,
        json={"entity_type": "project", "entity_id": proj["id"]},
    )
    assert rst.status_code == 200
    assert rst.json()["restored_sessions"] == 1
    assert client.get(f"/api/projects/{proj['id']}", headers=headers).status_code == 200
    assert client.get(f"/api/sessions/{sess['id']}", headers=headers).status_code == 200

    # Soft delete again then purge permanently
    client.delete(f"/api/projects/{proj['id']}", headers=headers)
    purge = client.delete(f"/api/system/trash/project/{proj['id']}", headers=headers)
    assert purge.status_code == 200
    trash_after = client.get("/api/system/trash", headers=headers).json()
    assert all(item["id"] != proj["id"] for item in trash_after["items"])

    # Cross-workspace orphan cleanup check: keep another workspace's file untouched!
    ws_b_hash = security.workspace_hash("other-workspace-b")
    valid_bytes = b"%PDF-1.4\n%%EOF\n"
    stored_b = storage.store_upload(
        uploads_root=settings.uploads_dir,
        workspace_hash=ws_b_hash,
        session_id=None,
        original_name="valid_b.pdf",
        stream=io.BytesIO(valid_bytes),
        max_bytes=settings.max_upload_bytes,
    )
    with db.session_scope() as session:
        session.add(
            Attachment(
                id=new_uuid(),
                workspace_id_hash=ws_b_hash,
                session_id=None,
                filename=stored_b.filename,
                stored_path=stored_b.relative_path,
                mime=stored_b.mime,
                size_bytes=stored_b.size_bytes,
                sha256=stored_b.sha256,
                kind="report_pdf",
            )
        )

    orphan_file = settings.uploads_dir / "orphan_temp.pdf"
    orphan_file.parent.mkdir(parents=True, exist_ok=True)
    orphan_file.write_bytes(b"orphan")
    export_temp = settings.exports_dir / "old_export.xlsx"
    export_temp.parent.mkdir(parents=True, exist_ok=True)
    export_temp.write_bytes(b"old")

    maint = client.post(
        "/api/system/db-maintenance",
        headers=headers,
        json={
            "checkpoint_wal": True,
            "vacuum": False,
            "clean_exports": True,
            "clean_orphan_uploads": True,
        },
    )
    assert maint.status_code == 200
    maint_body = maint.json()
    assert maint_body["integrity_status"] == "ok"
    assert maint_body["wal_checkpointed"] is True
    assert maint_body["removed_export_files"] >= 1
    assert maint_body["removed_orphan_files"] >= 1
    assert not orphan_file.exists()
    assert not export_temp.exists()
    assert stored_b.path.exists()


def test_prune_old_backups_and_backup_drill(tmp_path: Path):
    import os
    import time

    from app.services import db_admin

    from scripts.backup_drill import run_backup_drill

    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'drill_data' / 'hydro_web.db').as_posix()}",
        data_dir=tmp_path / "drill_data",
        frontend_dist=tmp_path / "dist",
    )
    drill_res = run_backup_drill(settings.data_dir)
    assert drill_res["status"] == "ok"
    assert drill_res["rto_ms"] >= 0

    backups_dir = settings.data_dir / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    # Create 5 synthetic backup files; oldest 2 are older than 40 days
    created_files: list[Path] = []
    now = time.time()
    for i in range(5):
        p = backups_dir / f"hydro_synthetic_{i}.db"
        p.write_bytes(b"SQLite format 3\x00" + b"\x00" * 16)
        age_s = (45 - i * 10) * 86_400 if i < 2 else (5 - i) * 86_400
        ts = now - age_s
        os.utime(p, (ts, ts))
        created_files.append(p)

    # Keep newest 3 backups; prune files older than 30 days beyond keep_last=3
    pruned = db_admin.prune_old_backups(settings, keep_last=3, max_age_days=30)
    assert pruned["kept"] == 3
    assert set(pruned["removed"]) == {"hydro_synthetic_0.db", "hydro_synthetic_1.db"}
    assert not created_files[0].exists()
    assert not created_files[1].exists()
    assert created_files[2].exists()
