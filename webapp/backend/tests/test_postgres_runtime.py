"""PostgreSQL runtime & Alembic migration smoke tests (activated when HYDRO_TEST_POSTGRES_URL is set)."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from app import db
from app.core.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient

POSTGRES_URL = (os.environ.get("HYDRO_TEST_POSTGRES_URL") or "").strip()


@pytest.mark.skipif(not POSTGRES_URL, reason="HYDRO_TEST_POSTGRES_URL not set")
def test_postgres_migrations_and_core_crud_flow(tmp_path: Path) -> None:
    db.dispose_database()
    settings = Settings(
        database_url=POSTGRES_URL,
        data_dir=tmp_path / "pg_data",
        frontend_dist=tmp_path / "dist",
        rate_limit_enabled=False,
    )
    app = create_app(settings)
    headers = {"X-Session-ID": f"pg-smoke-{uuid.uuid4().hex[:8]}"}
    sample_code = f"PG-{uuid.uuid4().hex[:6].upper()}"
    created_project_id: str | None = None

    try:
        with TestClient(app) as client:
            health = client.get("/api/health")
            assert health.status_code == 200, health.text
            health_json = health.json()
            assert health_json["db"]["dialect"] == "postgresql"
            assert health_json["db"]["migration"] == db.CURRENT_MIGRATION

            proj_res = client.post(
                "/api/projects",
                headers=headers,
                json={"name": "Postgres Test Pipeline", "code": f"P-{uuid.uuid4().hex[:4]}"},
            )
            assert proj_res.status_code == 201, proj_res.text
            created_project_id = proj_res.json()["id"]

            sample1 = client.post(
                "/api/projects/generate-sample",
                headers=headers,
                json={"scenario": "mixed", "section_count": 1, "code": sample_code},
            )
            assert sample1.status_code == 201, sample1.text
            sample1_json = sample1.json()
            assert sample1_json["reused"] is False
            sample_project_id = sample1_json["project"]["id"]
            sample_session_id = sample1_json["sections"][0]["id"]

            sample2 = client.post(
                "/api/projects/generate-sample",
                headers=headers,
                json={"scenario": "mixed", "section_count": 1, "code": sample_code},
            )
            assert sample2.status_code == 201, sample2.text
            assert sample2.json()["reused"] is True
            assert sample2.json()["project"]["id"] == sample_project_id

            sess_res = client.post(
                "/api/sessions",
                headers=headers,
                json={"name": "PG Section 1", "project_id": created_project_id},
            )
            assert sess_res.status_code == 201, sess_res.text
            sess_id = sess_res.json()["id"]

            upd_res = client.patch(
                f"/api/sessions/{sess_id}",
                headers=headers,
                json={"notes": "verified on postgresql"},
            )
            assert upd_res.status_code == 200, upd_res.text

            form_get = client.get(f"/api/sessions/{sess_id}/forms/cleaning", headers=headers)
            assert form_get.status_code == 200, form_get.text
            etag = form_get.headers["etag"]

            form_put = client.put(
                f"/api/sessions/{sess_id}/forms/cleaning",
                headers={**headers, "If-Match": etag},
                json={"form_date": "2026-11-24", "extracted_data": {"notes": "pg-form"}},
            )
            assert form_put.status_code == 200, form_put.text

            ts_res = client.post(
                f"/api/sessions/{sample_session_id}/time-series/batch",
                headers=headers,
                json={
                    "mode": "append",
                    "records": [
                        {
                            "timestamp": "2026-11-24T10:00:00Z",
                            "pressure_bar": 110.0,
                            "temperature_c": 15.0,
                            "volume_m3": 0.0,
                            "notes": "pg smoke",
                        }
                    ],
                },
            )
            assert ts_res.status_code in (200, 201), ts_res.text

            assert client.delete(
                f"/api/projects/{created_project_id}", headers=headers
            ).status_code in (
                200,
                204,
            )
            assert client.delete(
                f"/api/projects/{sample_project_id}", headers=headers
            ).status_code in (
                200,
                204,
            )
    finally:
        db.dispose_database()
