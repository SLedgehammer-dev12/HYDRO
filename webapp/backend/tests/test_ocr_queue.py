"""Tests for async OCR queue execution, cooperative cancel, timeouts, language, and recovery."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from app import db
from app.core.config import Settings
from app.main import create_app
from app.models import Attachment, OcrAnalysis, new_uuid
from app.services.ocr_queue import OCR_QUEUE
from fastapi.testclient import TestClient

from hidrostatik_test.services import report_ocr


def _make_report_pdf(path: Path) -> Path:
    pytest.importorskip("reportlab")
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    lines = [
        "Hidrostatik Test Raporu",
        "Rapor No: BOT-2026-0991",
        "Tarih: 2026-11-19",
        "Operator: Ayse Demir",
        "Dis Cap: 406,4 mm",
        "Et Kalinligi: 8,74 mm",
        "Hat Uzunlugu: 10000 m",
        "Test Basinci: 80 bar",
        "Hava Icerik Testi",
        "Vp: 7,83 L",
        "Vpa: 7,75 L",
        "A (hava): 44,971994",
        "Sonuc: PASS",
    ]
    pdf = canvas.Canvas(str(path), pagesize=A4)
    y = 800
    for line in lines:
        pdf.drawString(50, y, line)
        y -= 22
    pdf.save()
    return path


def _poll_until_terminal(client: TestClient, analysis_id: str, *, timeout_s: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout_s
    last: dict = {}
    while time.monotonic() < deadline:
        res = client.get(f"/api/ocr/analyses/{analysis_id}")
        assert res.status_code == 200, res.text
        last = res.json()
        if last["status"] in {"succeeded", "failed", "cancelled"}:
            return last
        time.sleep(0.05)
    raise AssertionError(f"OCR analysis {analysis_id} timed out polling: {last}")


def test_async_mode_and_prefer_header_enqueue_and_complete(client: TestClient, tmp_path: Path):
    pdf1 = _make_report_pdf(tmp_path / "async_one.pdf")
    res1 = client.post(
        "/api/ocr/analyze",
        files={"file": ("async_one.pdf", pdf1.read_bytes(), "application/pdf")},
        data={"async_mode": "true"},
    )
    assert res1.status_code == 202, res1.text
    job1 = res1.json()
    assert job1["status"] in {"queued", "running"}
    assert job1["poll_url"] == f"/api/ocr/analyses/{job1['analysis_id']}"
    assert isinstance(job1["estimated_wait_s"], int)
    assert job1["estimated_wait_s"] >= 1
    assert job1["reused"] is False

    done1 = _poll_until_terminal(client, job1["analysis_id"])
    assert done1["status"] == "succeeded"
    assert done1["report"]["pipe_od_mm"]["value"] == 406.4
    assert isinstance(done1.get("dossier"), dict)

    # Prefer: respond-async without async_mode form flag should also return 202
    pdf2 = _make_report_pdf(tmp_path / "async_two.pdf")
    res2 = client.post(
        "/api/ocr/analyze",
        headers={"Prefer": "respond-async"},
        files={"file": ("async_two.pdf", (pdf2.read_bytes() + b"\n%second"), "application/pdf")},
    )
    assert res2.status_code == 202, res2.text
    job2 = res2.json()
    done2 = _poll_until_terminal(client, job2["analysis_id"])
    assert done2["status"] == "succeeded"


def test_async_duplicate_upload_while_running_reuses_same_analysis(
    client: TestClient, tmp_path: Path
):
    pdf = _make_report_pdf(tmp_path / "dup.pdf")
    content = pdf.read_bytes()
    entered = threading.Event()
    release = threading.Event()
    real_analyze = report_ocr.analyze_report

    def _slow_analyze(*args, **kwargs):
        entered.set()
        release.wait(timeout=5.0)
        return real_analyze(*args, **kwargs)

    try:
        with patch("app.services.ocr.analyze_report", side_effect=_slow_analyze):
            first = client.post(
                "/api/ocr/analyze",
                files={"file": ("dup.pdf", content, "application/pdf")},
                data={"async_mode": "true"},
            )
            assert first.status_code == 202, first.text
            assert entered.wait(timeout=3.0)
            analysis_id = first.json()["analysis_id"]

            second = client.post(
                "/api/ocr/analyze",
                files={"file": ("dup.pdf", content, "application/pdf")},
                data={"async_mode": "true"},
            )
            assert second.status_code == 200, second.text
            assert second.json()["reused"] is True
            assert second.json()["analysis_id"] == analysis_id
            assert isinstance(second.json().get("estimated_wait_s"), int)
    finally:
        release.set()

    done = _poll_until_terminal(client, analysis_id)
    assert done["status"] == "succeeded"


def test_async_cancel_sets_cancel_event_and_prevents_overwrite(client: TestClient, tmp_path: Path):
    pdf = _make_report_pdf(tmp_path / "cancel_me.pdf")
    entered = threading.Event()
    saw_cancel_event = threading.Event()
    allow_return = threading.Event()

    def _cancellable_worker(path, calculated=None, **kwargs):
        cancel_event = kwargs.get("cancel_event")
        entered.set()
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if cancel_event is not None and cancel_event.is_set():
                saw_cancel_event.set()
                raise report_ocr.ReportOcrError(
                    "OCR analizi iptal edildi.", report_ocr.ERROR_CANCELLED
                )
            if allow_return.is_set():
                break
            time.sleep(0.02)
        return report_ocr.analyze_report(path, calculated)

    try:
        with patch("app.services.ocr.analyze_report", side_effect=_cancellable_worker):
            res = client.post(
                "/api/ocr/analyze",
                files={"file": ("cancel_me.pdf", pdf.read_bytes(), "application/pdf")},
                data={"async_mode": "true"},
            )
            assert res.status_code == 202, res.text
            analysis_id = res.json()["analysis_id"]
            assert entered.wait(timeout=3.0)

            cancel_res = client.post(f"/api/ocr/analyses/{analysis_id}/cancel")
            assert cancel_res.status_code == 202, cancel_res.text
            assert cancel_res.json()["status"] == "cancelled"
            assert saw_cancel_event.wait(timeout=3.0)

            done = _poll_until_terminal(client, analysis_id)
            assert done["status"] == "cancelled"
    finally:
        allow_return.set()


def test_timeout_and_language_forwarded_without_env_mutation(tmp_path: Path):
    db.dispose_database()
    custom_settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'queue.db'}",
        data_dir=tmp_path / "data",
        frontend_dist=tmp_path / "dist",
        max_upload_mb=1,
        ocr_timeout_s=42,
        ocr_max_concurrency=2,
    )
    application = create_app(custom_settings)
    pdf = _make_report_pdf(tmp_path / "timeout_lang.pdf")
    seen_calls: list[dict] = []
    real_analyze = report_ocr.analyze_report

    def _inspecting_analyze(path, calculated=None, **kwargs):
        seen_calls.append(dict(kwargs))
        return real_analyze(path, calculated, **kwargs)

    os.environ.pop("HYDRO_OCR_LANG", None)
    with TestClient(application) as local_client:
        status_res = local_client.get("/api/ocr/status")
        assert status_res.status_code == 200
        assert status_res.json()["queue"]["max_concurrency"] == 2

        with patch("app.services.ocr.analyze_report", side_effect=_inspecting_analyze):
            res = local_client.post(
                "/api/ocr/analyze",
                files={"file": ("timeout_lang.pdf", pdf.read_bytes(), "application/pdf")},
                data={"async_mode": "true", "language": "eng"},
            )
            assert res.status_code == 202, res.text
            done = _poll_until_terminal(local_client, res.json()["analysis_id"])
            assert done["status"] == "succeeded"

        assert "HYDRO_OCR_LANG" not in os.environ
        assert len(seen_calls) == 1
        assert seen_calls[0]["language"] == "eng"
        assert seen_calls[0]["timeout_seconds"] == 42.0
        assert seen_calls[0]["cancel_event"] is not None

        def _raise_timeout(*args, **kwargs):
            raise report_ocr.ReportOcrError("OCR zaman asimi.", report_ocr.ERROR_TIMEOUT)

        pdf2 = _make_report_pdf(tmp_path / "timeout_fail.pdf")
        with patch("app.services.ocr.analyze_report", side_effect=_raise_timeout):
            res2 = local_client.post(
                "/api/ocr/analyze",
                files={
                    "file": ("timeout_fail.pdf", pdf2.read_bytes() + b"\n%t2", "application/pdf")
                },
                data={"async_mode": "true"},
            )
            assert res2.status_code == 202, res2.text
            failed = _poll_until_terminal(local_client, res2.json()["analysis_id"])
            assert failed["status"] == "failed"
            assert failed["error"]["code"] == "ocr_timeout"

    db.dispose_database()


def test_recover_interrupted_jobs_marks_stale_rows_on_startup(tmp_path: Path):
    db.dispose_database()
    db_url = f"sqlite:///{tmp_path / 'recover.db'}"
    cfg = Settings(
        database_url=db_url,
        data_dir=tmp_path / "data",
        frontend_dist=tmp_path / "dist",
    )
    app1 = create_app(cfg)
    with TestClient(app1):
        with db.get_sessionmaker()() as s:
            att = Attachment(
                id=new_uuid(),
                workspace_id_hash="ws-stale",
                filename="stale.pdf",
                stored_path="stale.pdf",
                mime="application/pdf",
                size_bytes=100,
                sha256="abc" * 21 + "a",
                kind="pdf",
            )
            s.add(att)
            s.flush()
            s.add(
                OcrAnalysis(
                    id="stale-running-1",
                    workspace_id_hash="ws-stale",
                    attachment_id=att.id,
                    status="running",
                    needs_human_review=True,
                )
            )
            s.commit()

    # Recreating the app runs lifespan startup recovery
    app2 = create_app(cfg)
    with TestClient(app2):
        with db.get_sessionmaker()() as s:
            recovered = s.get(OcrAnalysis, "stale-running-1")
            assert recovered is not None
            assert recovered.status == "failed"
            assert recovered.error_code == "worker_interrupted"
            assert recovered.finished_at is not None

    OCR_QUEUE.configure(1)
    db.dispose_database()


def test_async_upload_validation_errors_remain_synchronous_4xx(client: TestClient):
    empty = client.post(
        "/api/ocr/analyze",
        files={"file": ("empty.pdf", b"", "application/pdf")},
        data={"async_mode": "true"},
    )
    assert empty.status_code == 422
    assert empty.json()["code"] == "empty_file"

    bad_ext = client.post(
        "/api/ocr/analyze",
        files={"file": ("bad.txt", b"%PDF-1.4", "text/plain")},
        data={"async_mode": "true"},
    )
    assert bad_ext.status_code == 415
    assert bad_ext.json()["code"] == "unsupported_format"

    bad_calc = client.post(
        "/api/ocr/analyze",
        files={"file": ("ok.pdf", b"%PDF-1.4\n%", "application/pdf")},
        data={"async_mode": "true", "calculated": "{not-json"},
    )
    assert bad_calc.status_code == 400
    assert bad_calc.json()["code"] == "invalid_calculated"
