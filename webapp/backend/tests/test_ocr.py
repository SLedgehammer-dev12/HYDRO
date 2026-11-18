"""OCR endpoint tests (synthetic text-layer PDF; no Tesseract required)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import create_session, full_inputs


def _make_report_pdf(path: Path) -> Path:
    pytest.importorskip("reportlab")
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    lines = [
        "Hidrostatik Test Raporu",
        "Rapor No: BOT-2026-0142",
        "Tarih: 2026-11-15",
        "Operator: Ahmet Yilmaz",
        "Dis Cap: 406,4 mm",
        "Et Kalinligi: 8,74 mm",
        "Hat Uzunlugu: 10000 m",
        "Test Basinci: 80 bar",
        "Hava Icerik Testi",
        "Teorik Ilave Su: 0,00783 m3",
        "Fiili Ilave Su: 0,00775 m3",
        "A (hava): 44,971994",
        "Basinc Degisim Testi",
        "Baslangic Sicakligi: 20 C",
        "Bitis Sicakligi: 22 C",
        "Sicaklik Farki: 2 C",
        "Basinc Dususu: 0,55 bar",
        "A (basinc): 44,971994",
        "B Katsayisi: 188,661",
        "Sonuc: PASS",
        "Notlar: Test tamamlandi.",
    ]
    pdf = canvas.Canvas(str(path), pagesize=A4)
    y = 800
    for line in lines:
        pdf.drawString(50, y, line)
        y -= 22
    pdf.save()
    return path


def _make_encrypted_pdf(path: Path) -> Path | None:
    try:
        from pypdf import PdfWriter
    except ImportError:  # pragma: no cover
        return None
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    try:
        writer.encrypt("secret")
    except Exception:  # pragma: no cover - pypdf API drift
        return None
    with path.open("wb") as handle:
        writer.write(handle)
    return path


def _upload(client, path: Path, **data):
    content = path.read_bytes()
    return client.post(
        "/api/ocr/analyze",
        files={"file": (path.name, content, "application/pdf")},
        data={key: str(value) for key, value in data.items()},
    )


def test_ocr_status(client):
    body = client.get("/api/ocr/status").json()
    assert "available" in body
    assert isinstance(body["status_text"], str)
    assert body["limits"]["max_file_size_bytes"] == 500 * 1024 * 1024
    assert ".pdf" in body["limits"]["supported_extensions"]
    assert body["thresholds"]["low_confidence"] == 0.6
    assert body["thresholds"]["human_review_required"] is True
    assert body["queue"]["max_concurrency"] == 1
    assert body["mapping_profiles"]["count"] == 0


def test_ocr_analyze_detail_list_and_reuse(client, tmp_path, settings):
    pdf = _make_report_pdf(tmp_path / "report.pdf")
    session = create_session(client, inputs=full_inputs())

    response = client.post(
        "/api/ocr/analyze",
        files={"file": ("report.pdf", pdf.read_bytes(), "application/pdf")},
        data={
            "session_id": session["id"],
            "calculated": json.dumps(
                {
                    "pipe_od_mm": 406.4,
                    "wall_mm": 8.74,
                    "length_m": 10000.0,
                    "test_pressure_bar": 80.0,
                    "air_test": {"vpa_m3": 0.00775},
                }
            ),
        },
    )
    assert response.status_code == 201, response.text
    analysis = response.json()
    assert analysis["status"] == "succeeded"
    assert analysis["source"] == "pdf-text-layer"
    assert analysis["needs_human_review"] is True
    assert analysis["session_id"] == session["id"]
    assert analysis["page_count"] == 1
    assert analysis["character_count"] > 100
    assert analysis["report"]["pipe_od_mm"]["value"] == 406.4
    assert analysis["report"]["wall_mm"]["value"] == 8.74
    assert analysis["report"]["test_pressure_bar"]["value"] == 80.0
    assert analysis["report"]["air_test"]["vpa"]["value"] == 0.00775
    assert isinstance(analysis["discrepancies"], list)
    assert analysis["poll_url"].endswith(analysis["id"])
    assert analysis["filename"] == "report.pdf"

    detail = client.get(f"/api/ocr/analyses/{analysis['id']}")
    assert detail.status_code == 200
    assert detail.json()["id"] == analysis["id"]

    listed = client.get("/api/ocr/analyses", params={"session_id": session["id"]}).json()
    assert listed["total"] == 1
    assert listed["items"][0]["status"] == "succeeded"
    assert listed["items"][0]["discrepancies_count"] >= 0

    status = client.get("/api/ocr/status").json()
    assert status["queue"]["queued"] == 0
    assert status["queue"]["running"] == 0

    reused = client.post(
        "/api/ocr/analyze",
        files={"file": ("report.pdf", pdf.read_bytes(), "application/pdf")},
        data={"session_id": session["id"]},
    )
    assert reused.status_code == 200
    assert reused.json()["reused"] is True
    assert reused.json()["id"] == analysis["id"]

    stored = list((settings.data_dir / "uploads").rglob("*.pdf"))
    assert stored
    assert all(path.is_relative_to(settings.data_dir.resolve()) for path in stored)


def test_ocr_approve_and_apply(client, tmp_path):
    pdf = _make_report_pdf(tmp_path / "report.pdf")
    session = create_session(client, inputs=full_inputs())
    analysis = _upload(client, pdf, session_id=session["id"])
    assert analysis.status_code == 201, analysis.text
    analysis_id = analysis.json()["id"]

    approved = client.post(
        f"/api/ocr/analyses/{analysis_id}/approve",
        json={
            "fields": {
                "test_pressure_bar": {"value": 80.0, "unit": "bar", "approved": True},
                "pipe_od_mm": {"value": 406.4, "unit": "mm", "approved": True},
            },
            "reviewer_note": "Saha formu kontrol edildi.",
        },
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["approved_count"] == 2
    assert approved.json()["audit_event_id"]

    unknown = client.post(
        f"/api/ocr/analyses/{analysis_id}/approve",
        json={"fields": {"nope": {"value": 1, "approved": True}}},
    )
    assert unknown.status_code == 422
    assert unknown.json()["code"] == "unknown_field"

    applied = client.post(
        f"/api/ocr/analyses/{analysis_id}/apply",
        json={
            "session_id": session["id"],
            "fields": ["test_pressure_bar", "pipe_od_mm"],
            "overwrite": True,
        },
    )
    assert applied.status_code == 200, applied.text
    body = applied.json()
    assert body["session_id"] == session["id"]
    targets = {item["target"] for item in body["applied"]}
    assert "air.pressure_bar" in targets
    assert "pressure.pressure_bar" in targets
    assert "geometry.outside_diameter_mm" in targets
    assert body["session_revision"] >= 2

    session_after = client.get(f"/api/sessions/{session['id']}").json()
    assert session_after["inputs"]["air"]["pressure_bar"] == 80.0
    assert session_after["inputs"]["geometry"]["outside_diameter_mm"] == 406.4

    audit = client.get(f"/api/sessions/{session['id']}/audit").json()
    actions = {item["action"] for item in audit["items"]}
    assert "ocr.apply" in actions

    cancel = client.post(f"/api/ocr/analyses/{analysis_id}/cancel")
    assert cancel.status_code == 409
    assert cancel.json()["code"] == "not_cancellable"


def test_ocr_low_confidence_gate(client, tmp_path, settings):
    pdf = _make_report_pdf(tmp_path / "report.pdf")
    analysis = _upload(client, pdf)
    assert analysis.status_code == 201
    analysis_id = analysis.json()["id"]

    from app import db
    from app.models import OcrAnalysis

    factory = db.get_sessionmaker()
    with factory() as session:
        row = session.get(OcrAnalysis, analysis_id)
        report = dict(row.report)
        field = dict(report["test_pressure_bar"])
        field["confidence"] = 0.2
        report["test_pressure_bar"] = field
        row.report = report
        session.commit()

    blocked = client.post(
        f"/api/ocr/analyses/{analysis_id}/approve",
        json={"approve_all": True, "fields": {}},
    )
    assert blocked.status_code == 422
    assert blocked.json()["code"] == "low_confidence_unreviewed"
    assert "test_pressure_bar" in blocked.json()["details"]["fields"]

    allowed = client.post(
        f"/api/ocr/analyses/{analysis_id}/approve",
        json={
            "approve_all": True,
            "fields": {"test_pressure_bar": {"value": 80.0, "unit": "bar", "approved": True}},
        },
    )
    assert allowed.status_code == 200


def test_ocr_apply_requires_approval(client, tmp_path):
    pdf = _make_report_pdf(tmp_path / "report.pdf")
    session = create_session(client)
    analysis = _upload(client, pdf, session_id=session["id"])
    analysis_id = analysis.json()["id"]
    response = client.post(
        f"/api/ocr/analyses/{analysis_id}/apply",
        json={"session_id": session["id"]},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "field_not_approved"


def test_ocr_analyze_tolerates_workspace_id_as_session(client, tmp_path):
    pdf = _make_report_pdf(tmp_path / "report.pdf")
    response = _upload(client, pdf, session_id="4f6e1f0a-workspace-key")
    assert response.status_code == 201, response.text
    assert response.json()["session_id"] is None


def test_ocr_encrypted_pdf(client, tmp_path):
    encrypted = _make_encrypted_pdf(tmp_path / "encrypted.pdf")
    if encrypted is None:
        pytest.skip("pypdf encrypt unavailable")
    response = _upload(client, encrypted)
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "encrypted_pdf"
    assert response.json()["details"]["analysis_id"]


def test_ocr_upload_security(client):
    empty = client.post("/api/ocr/analyze", files={"file": ("empty.pdf", b"", "application/pdf")})
    assert empty.status_code == 422
    assert empty.json()["code"] == "empty_file"

    wrong_extension = client.post(
        "/api/ocr/analyze", files={"file": ("report.txt", b"%PDF-1.4", "text/plain")}
    )
    assert wrong_extension.status_code == 415
    assert wrong_extension.json()["code"] == "unsupported_format"

    wrong_mime = client.post(
        "/api/ocr/analyze", files={"file": ("report.pdf", b"hello", "application/pdf")}
    )
    assert wrong_mime.status_code == 415
    assert wrong_mime.json()["code"] == "unsupported_format"

    oversized = client.post(
        "/api/ocr/analyze",
        files={
            "file": (
                "big.pdf",
                b"%PDF-1.4\n" + (b"0" * (1024 * 1024 + 100)),
                "application/pdf",
            )
        },
    )
    assert oversized.status_code == 413
    assert oversized.json()["code"] == "file_too_large"


def test_ocr_path_traversal_filename_is_display_only(client, tmp_path, settings):
    pdf = _make_report_pdf(tmp_path / "report.pdf")
    response = client.post(
        "/api/ocr/analyze",
        files={"file": ("../../etc/evil.pdf", pdf.read_bytes(), "application/pdf")},
    )
    assert response.status_code == 201, response.text
    assert response.json()["attachment"]["filename"] == "evil.pdf"
    uploads_root = (settings.data_dir / "uploads").resolve()
    for path in uploads_root.rglob("*"):
        if path.is_file():
            assert path.resolve().is_relative_to(uploads_root)


def test_ocr_mapping_profiles_crud(client):
    created = client.post(
        "/api/ocr/mapping-profiles",
        json={
            "name": "BOT-FRM-CDB-001-021 R2",
            "format_key": "bot-frm-cdb-001-021",
            "mode": "pre_extract",
            "is_default": True,
            "mapping": {
                "schema_version": 1,
                "fields": {
                    "test_pressure_bar": {
                        "aliases": ["Test Basinci", "Ptest"],
                        "unit": "bar",
                        "required": True,
                    }
                },
            },
        },
    )
    assert created.status_code == 201, created.text
    profile = created.json()
    assert profile["is_default"] is True
    assert profile["mapping"]["fields"]["test_pressure_bar"]["unit"] == "bar"

    duplicate = client.post(
        "/api/ocr/mapping-profiles",
        json={
            "name": "Duplicate",
            "format_key": "bot-frm-cdb-001-021",
        },
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "format_key_exists"

    listed = client.get("/api/ocr/mapping-profiles").json()
    assert listed["total"] == 1 > 0
    assert listed["items"][0]["id"] == profile["id"]

    detail = client.get(f"/api/ocr/mapping-profiles/{profile['id']}").json()
    assert detail["format_key"] == "bot-frm-cdb-001-021"

    updated = client.put(
        f"/api/ocr/mapping-profiles/{profile['id']}",
        json={"name": "R3", "mode": "post_map"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "R3"
    assert updated.json()["mode"] == "post_map"

    invalid = client.post(
        "/api/ocr/mapping-profiles",
        json={
            "name": "Bad",
            "format_key": "bad",
            "mapping": {"fields": {"x": {"aliases": []}}},
        },
    )
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "invalid_mapping"

    default_delete = client.delete(f"/api/ocr/mapping-profiles/{profile['id']}")
    assert default_delete.status_code == 409
    assert default_delete.json()["code"] == "default_profile"

    second = client.post(
        "/api/ocr/mapping-profiles",
        json={"name": "Other", "format_key": "other"},
    ).json()
    assert client.delete(f"/api/ocr/mapping-profiles/{second['id']}").status_code == 204


def test_analyze_xlsx_report_and_magic_validation(client):
    import io
    import zipfile

    import openpyxl

    status_body = client.get("/api/ocr/status").json()
    assert ".xlsx" in status_body["limits"]["supported_extensions"]
    assert ".xls" in status_body["limits"]["supported_extensions"]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "hydrostatic test data"
    ws.append(["Test Bölüm No", ":", "BÖLÜM 5"])
    ws.append(["Boru Dış Çapı", ":", 355.6, "mm"])
    ws.append(["Boru Et Kalınlığı", ":", 5.2, "mm"])
    ws.append(["Test Bölüm Boyu", ":", 8802.34, "m"])
    ws.append(["Maks. Test Basıncı", ":", 131.68, "bar"])
    buf = io.BytesIO()
    wb.save(buf)
    xlsx_bytes = buf.getvalue()

    res = client.post(
        "/api/ocr/analyze",
        files={
            "file": (
                "rapor.xlsx",
                xlsx_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert res.status_code in (200, 201), res.text
    body = res.json()
    assert body["source"] == "spreadsheet"
    assert body["report"]["section_id"]["value"] == "BÖLÜM 5"
    assert body["report"]["pipe_od_mm"]["value"] == 355.6

    from app import db
    from app.models import Attachment, OcrAnalysis

    with db.get_sessionmaker()() as db_session:
        analysis_row = db_session.get(OcrAnalysis, body["id"])
        attachment_row = db_session.get(Attachment, analysis_row.attachment_id)
        assert attachment_row.kind == "report_spreadsheet"

    fake = client.post(
        "/api/ocr/analyze",
        files={
            "file": (
                "sahte.xlsx",
                b"not a zip",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert fake.status_code == 415
    assert fake.json()["code"] == "unsupported_format"

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as zf:
        zf.writestr("hello.txt", "not a workbook")
    non_wb = client.post(
        "/api/ocr/analyze",
        files={
            "file": (
                "sahte_zip.xlsx",
                zip_buf.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert non_wb.status_code == 422
    assert non_wb.json()["code"] == "corrupt_document"


def test_ocr_status_respects_hydro_max_upload_mb(client, monkeypatch):
    from hidrostatik_test.services.report_ocr import effective_max_file_size_bytes

    monkeypatch.setenv("HYDRO_MAX_UPLOAD_MB", "120")
    assert effective_max_file_size_bytes() == 120 * 1024 * 1024
    res = client.get("/api/ocr/status")
    assert res.status_code == 200
    assert res.json()["limits"]["max_file_size_bytes"] == 120 * 1024 * 1024

    monkeypatch.setenv("HYDRO_MAX_UPLOAD_MB", "999")
    assert effective_max_file_size_bytes() == 500 * 1024 * 1024


def test_ocr_apply_recomputes_results_and_form_slots(client, tmp_path):
    pdf = _make_report_pdf(tmp_path / "single_recomp.pdf")
    session = create_session(client, inputs=full_inputs())
    analysis = _upload(client, pdf, session_id=session["id"])
    assert analysis.status_code == 201, analysis.text
    analysis_id = analysis.json()["id"]

    approved = client.post(
        f"/api/ocr/analyses/{analysis_id}/approve",
        json={
            "fields": {
                "test_pressure_bar": {"value": 80.0, "unit": "bar", "approved": True},
                "pipe_od_mm": {"value": 406.4, "unit": "mm", "approved": True},
            }
        },
    )
    assert approved.status_code == 200

    applied = client.post(
        f"/api/ocr/analyses/{analysis_id}/apply",
        json={
            "session_id": session["id"],
            "fields": ["test_pressure_bar", "pipe_od_mm"],
            "overwrite": True,
        },
    )
    assert applied.status_code == 200, applied.text
    body = applied.json()
    assert set(body["persisted_result_types"]).issuperset({"air", "pressure"})

    forms_resp = client.get(f"/api/sessions/{session['id']}/forms")
    assert forms_resp.status_code == 200
    assert forms_resp.json()["summary"]["required_total"] == 11

    results_resp = client.get(f"/api/sessions/{session['id']}/results")
    assert results_resp.status_code == 200
    assert {"air", "pressure"}.issubset(
        {item["test_type"] for item in results_resp.json()["items"]}
    )


def test_ocr_status_refresh_and_text_layer_metadata(client):
    res = client.get("/api/ocr/status?refresh=true")
    assert res.status_code == 200
    body = res.json()
    assert body["text_layer"]["available"] is True
    assert "pypdf" in body["text_layer"]["engines"]
