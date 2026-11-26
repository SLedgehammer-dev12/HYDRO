"""Tests for persistent DB-backed OCR worker queue (R3)."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from app import db
from app.core import security
from app.core.config import Settings
from app.core.timeutil import utcnow
from app.main import create_app
from app.models import Attachment, OcrAnalysis, new_uuid
from app.services import ocr as ocr_service
from app.worker import ocr as ocr_worker
from fastapi.testclient import TestClient

from hidrostatik_test.domain.report_schema import HydrotestReport
from hidrostatik_test.services.report_ocr import OcrAnalysisResult, PageText


def _fake_success_result() -> OcrAnalysisResult:
    return OcrAnalysisResult(
        path="scan.pdf",
        source="ocr",
        page_count=1,
        character_count=120,
        confidence=0.95,
        report=HydrotestReport(),
        discrepancies=(),
        issues=(),
        warnings=(),
        pages=(PageText(page_number=1, text="test", source="ocr"),),
    )


def test_external_worker_enqueue_claim_and_execute(tmp_path: Path):
    db_file = tmp_path / "ext_ocr.db"
    settings = Settings(
        database_url=f"sqlite:///{db_file.as_posix()}",
        data_dir=tmp_path / "data",
        frontend_dist=tmp_path / "dist",
        ocr_worker_mode="external",
    )
    app = create_app(settings)
    headers = {"X-Session-ID": "ext-worker-ws"}

    try:
        with TestClient(app) as client:
            pdf_bytes = b"%PDF-1.4\n1 0 obj <<>> endobj\ntrailer <<>>\n%%EOF\n"
            res = client.post(
                "/api/ocr/analyze",
                headers={**headers, "Prefer": "respond-async"},
                files={"file": ("scan.pdf", pdf_bytes, "application/pdf")},
            )
            assert res.status_code == 202, res.text
            job_id = res.json()["analysis_id"]

            # In external mode, job stays queued until external worker runs
            detail_before = client.get(f"/api/ocr/analyses/{job_id}", headers=headers)
            assert detail_before.status_code == 200
            assert detail_before.json()["status"] == "queued"

            with db.session_scope() as s:
                row = s.get(OcrAnalysis, job_id)
                assert row is not None
                assert row.job_payload is not None
                assert row.cancel_requested is False

            with patch(
                "app.worker.ocr.analyze_report",
                return_value=_fake_success_result(),
            ):
                processed = ocr_worker.run_once(settings, worker_id="worker-unit-1")
                assert processed is True
                idle = ocr_worker.run_once(settings, worker_id="worker-unit-1")
                assert idle is False

            detail_after = client.get(f"/api/ocr/analyses/{job_id}", headers=headers)
            assert detail_after.status_code == 200
            body_after = detail_after.json()
            assert body_after["status"] == "succeeded"
            assert body_after["confidence"] == 0.95
    finally:
        db.dispose_database()


def test_reclaim_expired_leases_and_cancel_requested(tmp_path: Path):
    db_file = tmp_path / "lease_ocr.db"
    settings = Settings(
        database_url=f"sqlite:///{db_file.as_posix()}",
        data_dir=tmp_path / "data",
        frontend_dist=tmp_path / "dist",
        ocr_worker_mode="external",
    )
    db.dispose_database()
    db.configure_database(settings.database_url)
    db.init_db()
    ws_hash = security.workspace_hash("lease-ws")

    try:
        with db.session_scope() as s:
            att = Attachment(
                id=new_uuid(),
                workspace_id_hash=ws_hash,
                session_id=None,
                filename="a.pdf",
                stored_path="a.pdf",
                mime="application/pdf",
                size_bytes=10,
                sha256="deadbeef",
                kind="report_pdf",
            )
            s.add(att)
            s.flush()

            expired_retryable = OcrAnalysis(
                id="job-requeue",
                workspace_id_hash=ws_hash,
                attachment_id=att.id,
                status="running",
                attempts=1,
                max_attempts=3,
                worker_id="dead-worker",
                lease_until=utcnow() - timedelta(minutes=5),
            )
            expired_exhausted = OcrAnalysis(
                id="job-fail",
                workspace_id_hash=ws_hash,
                attachment_id=att.id,
                status="running",
                attempts=3,
                max_attempts=3,
                worker_id="dead-worker",
                lease_until=utcnow() - timedelta(minutes=5),
            )
            cancelled_job = OcrAnalysis(
                id="job-cancel",
                workspace_id_hash=ws_hash,
                attachment_id=att.id,
                status="queued",
                attempts=0,
                max_attempts=3,
            )
            s.add_all([expired_retryable, expired_exhausted, cancelled_job])
            s.commit()

            ocr_service.cancel_analysis(s, cancelled_job)
            assert cancelled_job.cancel_requested is True

            claimed = ocr_worker.claim_next_job(s, worker_id="worker-2", lease_seconds=120)
            assert claimed is not None
            # Only expired_retryable is eligible (cancelled_job has cancel_requested=True, expired_exhausted failed)
            assert claimed.id == "job-requeue"
            assert claimed.attempts == 2
            assert claimed.worker_id == "worker-2"

            failed_row = s.get(OcrAnalysis, "job-fail")
            assert failed_row is not None
            assert failed_row.status == "failed"
            assert failed_row.error_code == "worker_lease_expired"
    finally:
        db.dispose_database()


def test_ocr_detail_payload_includes_suggested_fixes(tmp_path: Path):
    db_file = tmp_path / "suggest_ocr.db"
    settings = Settings(
        database_url=f"sqlite:///{db_file.as_posix()}",
        data_dir=tmp_path / "data",
        frontend_dist=tmp_path / "dist",
    )
    db.dispose_database()
    db.configure_database(settings.database_url)
    db.init_db()
    ws_hash = security.workspace_hash("suggest-ws")

    try:
        with db.session_scope() as s:
            att = Attachment(
                id=new_uuid(),
                workspace_id_hash=ws_hash,
                session_id=None,
                filename="scan.pdf",
                stored_path="scan.pdf",
                mime="application/pdf",
                size_bytes=10,
                sha256="deadbeef",
                kind="report_pdf",
            )
            s.add(att)
            s.flush()

            row = OcrAnalysis(
                id="ana-suggest-1",
                workspace_id_hash=ws_hash,
                attachment_id=att.id,
                status="succeeded",
                source="ocr",
                report={
                    "air_test": {
                        "a": {"value": 4497.0, "confidence": 0.9},
                        "k": {"value": 102.0, "confidence": 0.85},
                    },
                    "pressure_test": {
                        "t_final": {"value": 16.2, "confidence": 0.95},
                    },
                },
            )
            s.add(row)
            s.commit()

            detail = ocr_service.detail_payload(s, row)
            fixes = detail.get("suggested_fixes") or []
            by_field = {item["field"]: item for item in fixes}
            assert set(by_field) == {"air_test.a", "air_test.k"}
            assert by_field["air_test.a"]["suggested_value"] == 44.97
            assert by_field["air_test.k"]["suggested_value"] == 1.02
    finally:
        db.dispose_database()


def test_ocr_queue_overview_and_retry_failed_job(tmp_path: Path):
    db_file = tmp_path / "queue_dlq_ocr.db"
    settings = Settings(
        database_url=f"sqlite:///{db_file.as_posix()}",
        data_dir=tmp_path / "data",
        frontend_dist=tmp_path / "dist",
        ocr_worker_mode="external",
    )
    app = create_app(settings)
    headers = {"X-Session-ID": "queue-dlq-ws"}

    try:
        with TestClient(app) as client:
            pdf_bytes = b"%PDF-1.4\n1 0 obj <<>> endobj\ntrailer <<>>\n%%EOF\n"
            res = client.post(
                "/api/ocr/analyze",
                headers={**headers, "Prefer": "respond-async"},
                files={"file": ("dlq.pdf", pdf_bytes, "application/pdf")},
            )
            assert res.status_code == 202, res.text
            job_id = res.json()["analysis_id"]

            # Simulate exhausted dead-letter failure on that job while keeping uploaded file intact
            with db.session_scope() as s:
                row = s.get(OcrAnalysis, job_id)
                assert row is not None
                row.status = "failed"
                row.attempts = 3
                row.error_code = "worker_lease_expired"
                row.error_message = "Lease expired"
                s.commit()

            q_res = client.get("/api/ocr/queue", headers=headers)
            assert q_res.status_code == 200, q_res.text
            q_body = q_res.json()
            assert q_body["worker_mode"] == "external"
            assert q_body["counts"]["failed"] == 1
            assert q_body["dead_letter_count"] == 1
            assert q_body["dead_letter"][0]["id"] == job_id
            assert q_body["dead_letter"][0]["error_code"] == "worker_lease_expired"

            retry_res = client.post(f"/api/ocr/analyses/{job_id}/retry", headers=headers)
            assert retry_res.status_code == 202, retry_res.text
            assert retry_res.json()["status"] == "queued"

            q_after = client.get("/api/ocr/queue", headers=headers).json()
            assert q_after["counts"]["queued"] == 1
            assert q_after["counts"]["failed"] == 0
            assert q_after["oldest_queued_age_s"] is not None

            # Already queued job cannot be retried again -> 409 not_retryable
            conflict = client.post(f"/api/ocr/analyses/{job_id}/retry", headers=headers)
            assert conflict.status_code == 409
            assert conflict.json()["code"] == "not_retryable"
    finally:
        db.dispose_database()
