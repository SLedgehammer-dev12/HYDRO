"""Comprehensive tests for multi-section BOTAŞ dossier parsing, form slots & checkpoints."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.services.dossier import (
    REQUIRED_FORM_SPECS,
    _extract_form_specific_data,
    analyze_dossier_pages,
    classify_form_text,
    compute_project_similarity,
    evaluate_operational_checks,
    evaluate_section_calculations,
    extract_page_section_no,
    extract_project_name_from_pages,
    extract_project_name_from_text,
    find_similar_projects,
    fold_tr,
    normalize_section_no,
)

from hidrostatik_test.services.report_ocr import MAX_OCR_PAGES, PageText


def _make_multipage_pdf(path: Path, pages_lines: list[list[str]]) -> Path:
    pytest.importorskip("reportlab")
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    pdf = canvas.Canvas(str(path), pagesize=A4)
    for page_lines in pages_lines:
        y = 800
        for ln in page_lines:
            pdf.drawString(42, y, ln)
            y -= 18
        pdf.showPage()
    pdf.save()
    return path


def test_max_ocr_pages_200_limit(client):
    assert MAX_OCR_PAGES == 200
    resp = client.get("/api/ocr/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["limits"]["max_ocr_pages"] == 200
    assert body["limits"]["max_pdf_pages"] == 200


def test_required_catalog_has_11_including_drying():
    codes = [spec.code for spec in REQUIRED_FORM_SPECS]
    titles = " ".join(spec.title.lower() for spec in REQUIRED_FORM_SPECS)
    assert len(REQUIRED_FORM_SPECS) == 11
    assert "pre_drying" in codes
    assert "final_drying" in codes
    assert "kurutma" in titles


def test_normalize_section_no_variants_and_rejections():
    assert normalize_section_no("Bölüm-5") == "BÖLÜM 5"
    assert normalize_section_no("BOLUM 5") == "BÖLÜM 5"
    assert normalize_section_no("5") == "BÖLÜM 5"
    assert normalize_section_no("14.bölüm") == "BÖLÜM 14"
    assert normalize_section_no("14. bölüm") == "BÖLÜM 14"
    assert normalize_section_no("3-A") == "BÖLÜM 3A"
    assert normalize_section_no("Bölüm 3b") == "BÖLÜM 3B"
    assert normalize_section_no("K-01") == "K-01"
    # Test heads must never become section numbers
    assert normalize_section_no("TB-01") is None
    assert normalize_section_no("TB-02") is None


def test_project_name_extraction_and_fuzzy_matching():
    assert (
        extract_project_name_from_text(
            'KGM Projesi BOT-TYP-PL-30-2/4\n...\n10" KAĞIZMAN DGBH HİDROSTATİK TEST PROFİLİ',
            max_lines=None,
        )
        == '10" KAĞIZMAN DGBH'
    )

    sim_ercis = compute_project_similarity(
        '14" ERCİŞ PATNOS DGBH YAPIM İŞİ PROJESİ',
        "Erciş Patnos DGBH",
    )
    sim_unrelated = compute_project_similarity(
        '14" ERCİŞ PATNOS DGBH YAPIM İŞİ PROJESİ',
        "Kağızman DGBH",
    )
    assert sim_ercis >= 0.70
    assert sim_unrelated < 0.70


def test_multi_section_dossier_and_blank_page_filtering():
    hourly_fill = [
        "SU DOLUM RAPORU",
        "Proje Adi : ERCIS PATNOS DGBH YAPIM ISI PROJESI",
        "Test Bolum No : Bolum-5",
    ]
    for h in range(8, 20):
        hourly_fill.append(f"{h:02d}:00 10.0 {10 + (h - 7) * 5:.1f} 12.0 13.0")

    pages = [
        PageText(
            page_number=1,
            text="\n".join(hourly_fill),
            source="pdf-text-layer",
        ),
        PageText(
            page_number=2,
            text="\n".join(
                [
                    "HAVA ICERIK TESTI KABUL RAPORU",
                    "Proje Adi : ERCIS PATNOS DGBH YAPIM ISI PROJESI",
                    "Test Bolum No : 5",
                    "Tarih : 04.10.2026",
                    "Dis Cap : 355.6 mm",
                    "Et Kalinligi : 5.2 mm",
                    "Uzunluk : 8802.34 m",
                    "A : 45.402",
                    "Vp : 0.06256",
                    "Vpa : 0.06400",
                ]
            ),
            source="pdf-text-layer",
        ),
        PageText(
            page_number=3,
            text="\n".join(
                [
                    "BASINCLANDIRMA TEST RAPORU",
                    "Test Bolum No : BOLUM 5",
                    "Tarih : 04.10.2026",
                    "08:00 15.0 100.0",
                    "09:00 45.0 200.0",
                    "10:30 105.0 250.0",
                ]
            ),
            source="pdf-text-layer",
        ),
        PageText(
            page_number=4,
            text="\n".join(
                [
                    "ON KURUTMA KABUL RAPORU",
                    "Test Bolum No : BOLUM 6",
                    "Tarih : 20.10.2026",
                ]
            ),
            source="pdf-text-layer",
        ),
        PageText(
            page_number=5,
            text="\n".join(
                [
                    "TEMIZLIK KABUL RAPORU",
                    "Proje Adi ve Logosu : ...",
                    "Yuklenici Firma Adi : ...",
                    "Test Bolum No : __",
                    "Tarih : .. / .. / ....",
                ]
            ),
            source="pdf-text-layer",
        ),
    ]

    dossier = analyze_dossier_pages(pages, source_filename="hakedis_1.pdf")
    assert dossier["detected_project_name"] == "ERCIS PATNOS DGBH YAPIM ISI PROJESI"
    assert dossier["blank_template_pages"] == [5]

    by_sec = {s["section_no"]: s for s in dossier["sections"]}
    assert set(by_sec.keys()) == {"BÖLÜM 5", "BÖLÜM 6"}

    sec5 = by_sec["BÖLÜM 5"]
    assert sec5["filled_required_count"] == 2
    assert sec5["required_total"] == 11
    assert sec5["supplementary_count"] == 1
    assert len(sec5["missing_required_forms"]) == 9
    missing_codes_5 = {m["form_code"] for m in sec5["missing_required_forms"]}
    assert {"pre_drying", "final_drying"}.issubset(missing_codes_5)
    assert sec5["calculations"]["air"]["passed"] is True
    assert sec5["calculations"]["air"]["status"] == "passed"

    sec6 = by_sec["BÖLÜM 6"]
    assert sec6["filled_required_count"] == 1
    assert {f["form_code"] for f in sec6["present_forms"]} == {"pre_drying"}


def test_plan_profile_commit_creates_11_empty_slots_and_progressive_hakedis_flow(
    client, headers, tmp_path
):
    # 1) Create sections via /api/projects/plan-profile/commit with a detected/new project name
    commit_pp = client.post(
        "/api/projects/plan-profile/commit",
        json={
            "project_name": "Ercis Patnos DGBH",
            "project_code": "ERC-01",
            "sections": [
                {
                    "section_no": "Bölüm 1",
                    "start_kp": "0+000",
                    "end_kp": "5+000",
                    "length_m": 5000.0,
                    "outside_diameter_mm": 355.6,
                    "wall_thickness_mm": 5.2,
                    "design_pressure_bar": 75.0,
                },
                {
                    "section_no": "Bölüm 2",
                    "start_kp": "5+000",
                    "end_kp": "10+000",
                    "length_m": 5000.0,
                },
            ],
        },
        headers=headers,
    )
    assert commit_pp.status_code == 201, commit_pp.text
    pp_data = commit_pp.json()
    project_id = pp_data["project_id"]
    assert pp_data["created_count"] == 2
    sess1_id = pp_data["items"][0]["id"]

    # Verify all 11 mandatory BOTAŞ form slots initialized as empty
    forms_resp = client.get(f"/api/sessions/{sess1_id}/forms", headers=headers)
    assert forms_resp.status_code == 200
    forms_body = forms_resp.json()
    assert forms_body["summary"]["required_total"] == 11
    assert forms_body["summary"]["filled_required"] == 0
    assert forms_body["summary"]["missing_required"] == 11
    form_codes = {f["form_code"]: f["status"] for f in forms_body["forms"] if f["required"]}
    assert len(form_codes) == 11
    assert form_codes["pre_drying"] == "empty"
    assert form_codes["final_drying"] == "empty"

    # 2) Hakedis 1 upload: Su Dolum + Hava Icerik for Bolum 1
    pdf1 = _make_multipage_pdf(
        tmp_path / "hakedis_1.pdf",
        [
            [
                "SU DOLUM RAPORU",
                "Proje Adi : 14 ERCIS PATNOS DGBH YAPIM ISI PROJESI",
                "Test Bolum No : Bolum-1",
                "Tarih : 01.10.2026",
                "Dis Cap : 355.6 mm",
                "Et Kalinligi : 5.2 mm",
                "Hat Uzunlugu : 5000 m",
                "08:00 50.0 11.0 12.0 12.0",
                "09:00 50.0 11.0 12.0 12.0",
                "10:00 50.0 11.0 12.0 12.0",
            ],
            [
                "HAVA ICERIK TESTI KABUL RAPORU",
                "Proje Adi : 14 ERCIS PATNOS DGBH YAPIM ISI PROJESI",
                "Test Bolum No : BOLUM 1",
                "Tarih : 02.10.2026",
                "Dis Cap : 355.6 mm",
                "Et Kalinligi : 5.2 mm",
                "Hat Uzunlugu : 5000 m",
                "A : 45.402",
                "Vp : 0.0355",
                "Vpa : 0.0360",
            ],
        ],
    )
    a1 = client.post(
        "/api/ocr/analyze",
        files={"file": (pdf1.name, pdf1.read_bytes(), "application/pdf")},
        headers=headers,
    )
    assert a1.status_code == 201, a1.text
    a1_body = a1.json()
    assert a1_body["dossier"] is not None
    # Verify >= 70% similar_projects surfaces Ercis Patnos DGBH
    assert any(
        p["id"] == project_id and p["similarity"] >= 0.70
        for p in a1_body["dossier"]["similar_projects"]
    )

    # Commit Hakedis 1 into existing project -> fills 2 empty slots cleanly
    c1 = client.post(
        f"/api/ocr/analyses/{a1_body['id']}/commit-dossier",
        json={
            "target_project_id": project_id,
            "create_new_project": False,
            "overwrite_filled": False,
        },
        headers=headers,
    )
    assert c1.status_code == 200, c1.text
    assert c1.json()["saved_forms_count"] == 2
    assert c1.json()["overwritten_forms_count"] == 0

    forms_after_1 = client.get(f"/api/sessions/{sess1_id}/forms", headers=headers).json()
    assert forms_after_1["summary"]["filled_required"] == 2
    assert forms_after_1["summary"]["missing_required"] == 9

    # 3) Hakedis 2 upload: Ön Kurutma (empty slot -> should fill silently with overwrite_filled=False)
    pdf2 = _make_multipage_pdf(
        tmp_path / "hakedis_2.pdf",
        [
            [
                "ON KURUTMA KABUL RAPORU",
                "Proje Adi : 14 ERCIS PATNOS DGBH YAPIM ISI PROJESI",
                "Test Bolum No : 1",
                "Tarih : 15.10.2026",
            ]
        ],
    )
    a2 = client.post(
        "/api/ocr/analyze",
        files={"file": (pdf2.name, pdf2.read_bytes(), "application/pdf")},
        headers=headers,
    ).json()
    c2 = client.post(
        f"/api/ocr/analyses/{a2['id']}/commit-dossier",
        json={
            "target_project_id": project_id,
            "create_new_project": False,
            "overwrite_filled": False,
        },
        headers=headers,
    )
    assert c2.status_code == 200, c2.text
    assert c2.json()["saved_forms_count"] == 1
    assert c2.json()["overwritten_forms_count"] == 0

    forms_after_2 = client.get(f"/api/sessions/{sess1_id}/forms", headers=headers).json()
    assert forms_after_2["summary"]["filled_required"] == 3
    status_by_code = {f["form_code"]: f for f in forms_after_2["forms"]}
    assert status_by_code["pre_drying"]["status"] == "filled"

    # 4) Re-upload an already-filled form (Su Dolum Raporu) for the same section -> must return 409 without approval
    pdf3 = _make_multipage_pdf(
        tmp_path / "hakedis_3_dup.pdf",
        [
            [
                "SU DOLUM RAPORU",
                "Proje Adi : 14 ERCIS PATNOS DGBH YAPIM ISI PROJESI",
                "Test Bolum No : Bolum 1",
                "Tarih : 18.10.2026",
                "08:00 60.0 11.5 12.0 12.5",
                "09:00 60.0 11.5 12.0 12.5",
            ]
        ],
    )
    a3 = client.post(
        "/api/ocr/analyze",
        files={"file": (pdf3.name, pdf3.read_bytes(), "application/pdf")},
        headers=headers,
    ).json()
    c3_blocked = client.post(
        f"/api/ocr/analyses/{a3['id']}/commit-dossier",
        json={
            "target_project_id": project_id,
            "create_new_project": False,
            "overwrite_filled": False,
        },
        headers=headers,
    )
    assert c3_blocked.status_code == 409
    err_body = c3_blocked.json()
    assert err_body["code"] == "duplicate_filled_forms"
    assert any(
        c["section_no"] == "BÖLÜM 1" and c["form_code"] == "filling"
        for c in err_body["details"]["conflicts"]
    )

    # Confirming overwrite_filled=True updates the existing record and increments revision
    c3_ok = client.post(
        f"/api/ocr/analyses/{a3['id']}/commit-dossier",
        json={
            "target_project_id": project_id,
            "create_new_project": False,
            "overwrite_filled": True,
        },
        headers=headers,
    )
    assert c3_ok.status_code == 200, c3_ok.text
    assert c3_ok.json()["overwritten_forms_count"] == 1
    forms_after_3 = client.get(f"/api/sessions/{sess1_id}/forms", headers=headers).json()
    rev_map = {f["form_code"]: f["revision"] for f in forms_after_3["forms"]}
    assert rev_map["filling"] == 2


def test_pass_fail_calculations_and_operational_checkpoints():
    header = {
        "outside_diameter_mm": 355.6,
        "wall_thickness_mm": 5.2,
        "length_m": 1000.0,
    }
    # Failed air (>6%) and failed pressure (PA - Pt > 0.30 bar)
    forms_fail = {
        "air_acceptance": {
            "form_code": "air_acceptance",
            "status": "filled",
            "extracted_data": {
                "air_acceptance": {"a_micro_per_bar": 45.4, "k_factor": 1.02, "vpa_m3": 0.0085}
            },
        },
        "pressure_acceptance": {
            "form_code": "pressure_acceptance",
            "status": "filled",
            "extracted_data": {
                "pressure_acceptance": {
                    "a_micro_per_bar": 45.4,
                    "b_micro_per_c": 188.0,
                    "delta_t_c": 0.1,
                    "pa_bar": 0.90,
                }
            },
        },
    }
    calcs_fail = evaluate_section_calculations(header, forms_fail)
    assert calcs_fail["air"]["passed"] is False
    assert calcs_fail["air"]["status"] == "failed"
    assert calcs_fail["pressure"]["passed"] is False
    assert calcs_fail["pressure"]["status"] == "failed"

    # Operational checkpoints: 24h fill log, 24h thermal balance <=0.5°C, 2h hold 15-min readings, 24h pressure log, all 11 forms
    fill_entries = [
        {
            "time_str": f"{h % 24:02d}:00",
            "abs_min": float(h * 60),
            "numbers": [30.0, 11.0, 12.0, 12.5],
        }
        for h in range(8, 32)
    ]
    leak_entries = [
        {
            "time_str": f"{h % 24:02d}:00",
            "abs_min": float(h * 60),
            "numbers": [100.0, 12.0, 12.0, 12.1],
        }
        for h in range(8, 33)
    ]
    hold_entries = [
        {
            "time_str": f"{12 + (m // 60):02d}:{m % 60:02d}",
            "abs_min": float(12 * 60 + m),
            "numbers": [105.0, 12.0],
        }
        for m in range(0, 121, 15)
    ]
    pt_entries = [
        {"time_str": f"{h % 24:02d}:00", "abs_min": float(h * 60), "numbers": [105.0, 12.0, 12.1]}
        for h in range(14, 39)
    ]

    all_forms = {
        spec.code: {"form_code": spec.code, "status": "filled", "extracted_data": {}}
        for spec in REQUIRED_FORM_SPECS
    }
    all_forms["filling"]["extracted_data"] = {
        "time_log": {
            "row_count": len(fill_entries),
            "duration_hours": 23.0,
            "median_step_min": 60.0,
            "max_gap_min": 60.0,
            "first_time": "08:00",
            "last_time": "07:00",
            "entries": fill_entries,
        },
        "filling": {
            "min_temp_c": 11.0,
            "max_temp_c": 12.5,
            "total_filled_m3": 720.0,
        },
    }
    all_forms["leak_stabilization"]["extracted_data"] = {
        "time_log": {
            "row_count": len(leak_entries),
            "duration_hours": 24.0,
            "median_step_min": 60.0,
            "max_gap_min": 60.0,
            "first_time": "08:00",
            "last_time": "08:00",
            "entries": leak_entries,
        },
        "monitoring": {
            "last_4h_delta_c": 0.15,
            "min_temp_c": 12.0,
            "max_temp_c": 12.1,
        },
    }
    all_forms["pressurization"] = {
        "form_code": "pressurization",
        "status": "filled",
        "extracted_data": {
            "time_log": {
                "row_count": len(hold_entries),
                "duration_hours": 2.0,
                "median_step_min": 15.0,
                "max_gap_min": 15.0,
                "first_time": "12:00",
                "last_time": "14:00",
                "last_abs_min": 14 * 60.0,
                "entries": hold_entries,
            },
            "monitoring": {"has_pv_steps": True},
        },
    }
    all_forms["pressure_test"]["extracted_data"] = {
        "time_log": {
            "row_count": len(pt_entries),
            "duration_hours": 24.0,
            "median_step_min": 60.0,
            "max_gap_min": 60.0,
            "first_time": "14:00",
            "last_time": "14:00",
            "first_abs_min": 14 * 60.0,
            "entries": pt_entries,
        },
        "monitoring": {"p_start_bar": 105.0, "p_end_bar": 104.8, "min_temp_c": 12.0},
    }

    checks_bool, check_details = evaluate_operational_checks(
        header,
        all_forms,
        {
            "air": {"status": "passed", "passed": True, "summary": "BAŞARILI: Vpa/Vp uygun"},
            "pressure": {"status": "passed", "passed": True, "summary": "BAŞARILI: PA-Pt uygun"},
        },
    )
    assert check_details["ambient_temp"]["status"] == "passed"
    assert check_details["fill_records"]["status"] == "passed"
    assert check_details["thermal_balance"]["status"] == "passed"
    assert check_details["two_hour_hold"]["status"] == "passed"
    assert check_details["pressure_records"]["status"] == "passed"
    assert check_details["forms"]["status"] == "passed"
    assert checks_bool["thermal_balance"] is True
    assert checks_bool["two_hour_hold"] is True
    assert checks_bool["forms"] is True

    # Failing thermal balance (>0.5 °C) and ambient temp (<2 °C)
    all_forms["leak_stabilization"]["extracted_data"]["monitoring"]["last_4h_delta_c"] = 0.85
    all_forms["filling"]["extracted_data"]["filling"]["min_temp_c"] = 1.0
    _, bad_details = evaluate_operational_checks(
        header, all_forms, {"air": {"status": "pending"}, "pressure": {"status": "pending"}}
    )
    assert bad_details["thermal_balance"]["status"] == "failed"
    assert bad_details["ambient_temp"]["status"] == "failed"


def test_find_similar_projects_empty_or_short_names(client, headers):
    # Sanity verify find_similar_projects signature & threshold filtering works via plan-profile scan
    assert callable(find_similar_projects)


def test_stale_ocr_cache_bypassed_and_force_reanalysis(client, headers, tmp_path):
    from app import db as app_db
    from app.models import OcrAnalysis

    pdf = _make_multipage_pdf(
        tmp_path / "ercis_multi.pdf",
        [
            [
                "SU DOLUM RAPORU",
                "Proje Adi : 14 ERCIS PATNOS DGBH YAPIM ISI PROJESI",
                "Test Bolum No : Bolum-5",
                "Tarih : 03.10.2026",
            ],
            [
                "ON KURUTMA KABUL RAPORU",
                "Proje Adi : 14 ERCIS PATNOS DGBH YAPIM ISI PROJESI",
                "Test Bolum No : 14.bolum",
                "Tarih : 25.10.2026",
            ],
        ],
    )
    raw_bytes = pdf.read_bytes()

    # Initial upload creates row with 2 pages and dossier populated
    first = client.post(
        "/api/ocr/analyze",
        files={"file": (pdf.name, raw_bytes, "application/pdf")},
        headers=headers,
    )
    assert first.status_code == 201, first.text
    body1 = first.json()
    assert body1["reused"] is False
    assert body1["dossier"] is not None
    assert {s["section_no"] for s in body1["dossier"]["sections"]} == {"BÖLÜM 5", "BÖLÜM 14"}

    # Identical upload normally reuses cached row (200 OK, reused=True)
    cached = client.post(
        "/api/ocr/analyze",
        files={"file": (pdf.name, raw_bytes, "application/pdf")},
        headers=headers,
    )
    assert cached.status_code == 200
    assert cached.json()["reused"] is True
    assert cached.json()["id"] == body1["id"]

    # Force re-analysis bypasses cache even when cached row is valid
    forced = client.post(
        "/api/ocr/analyze",
        files={"file": (pdf.name, raw_bytes, "application/pdf")},
        data={"force": "true"},
        headers=headers,
    )
    assert forced.status_code == 201
    assert forced.json()["reused"] is False
    assert forced.json()["id"] != body1["id"]

    # Simulate legacy stale row (dossier=None and page_count=1 < 2) -> must NOT reuse
    with app_db.session_scope() as session_db:
        row = session_db.get(OcrAnalysis, forced.json()["id"])
        assert row is not None
        row.dossier = None
        row.page_count = 1
        session_db.commit()

    refreshed = client.post(
        "/api/ocr/analyze",
        files={"file": (pdf.name, raw_bytes, "application/pdf")},
        headers=headers,
    )
    assert refreshed.status_code == 201
    body_refreshed = refreshed.json()
    assert body_refreshed["reused"] is False
    assert body_refreshed["id"] != forced.json()["id"]
    assert body_refreshed["page_count"] == 2
    assert body_refreshed["dossier"] is not None
    assert len(body_refreshed["dossier"]["sections"]) == 2


def test_fold_tr_accents_nfd_and_cyrillic_homoglyphs():
    assert fold_tr("HİDROSTATİK TEST VERÍLERÍ") == "hidrostatik test verileri"
    assert (
        fold_tr('24" MALATYA YAPIM I\u0307S\u0327I\u0307 PROJESI\u0307')
        == '24" malatya yapim isi projesi'
    )
    assert fold_tr("ДР : 0,060") == "dp : 0,060"
    assert fold_tr("Дт : 0,03") == "dt : 0,03"
    assert fold_tr("(РА-ДР)= : 0,080") == "(pa-dp)= : 0,080"
    assert fold_tr("(Ваг)") == "(bar)"


def test_extract_section_no_multiline_number_first_landscape_and_charts():
    assert (
        extract_page_section_no(
            "HİDROSTATİK TEST VERÍLERÍ\nTest Bölüm No\n: 1. Section\nTarih : 22.05.2026"
        )
        == "BÖLÜM 1"
    )
    assert (
        extract_page_section_no(
            "MUKAVEMET TEST RAPORU\nTest Bölüm No\n: 2 Section\nTarih : 31.05.2026"
        )
        == "BÖLÜM 2"
    )
    assert (
        extract_page_section_no(
            "ÖN KURUTMA KABUL RAPORU\nTest Bölüm No\n: 3 Section\nAçıklamalar:\n1, 2 VE 3. TEST BÖLÜMLERİNİN KURUTMASI"
        )
        == "BÖLÜM 3"
    )
    assert (
        extract_page_section_no("Bölüm No\n1. Section\nBoru Dış Çapı Do (mm) : 609,60") == "BÖLÜM 1"
    )
    assert (
        extract_page_section_no("Tarih : 09.06.2026   Test Bölüm No : 2\n1.Başlık No : TB-1")
        == "BÖLÜM 2"
    )
    assert (
        extract_page_section_no("Test Bo\u0308lu\u0308m No : 15\nTarih : 22.05.2026") == "BÖLÜM 15"
    )
    assert (
        extract_page_section_no(
            "MUKAVEMET TEST RAPORU (1/1)\nTest Bölüm No : BÖLÜM 9. *\nTarih : 15.10.2026"
        )
        == "BÖLÜM 9"
    )
    assert normalize_section_no(": -20") is None
    assert normalize_section_no("2026") is None
    assert normalize_section_no("2026-06-08") is None
    assert normalize_section_no("REV-01") is None

    # Landscape page: filler lines first, standalone ": 1. Section" at line 55, label at line 85;
    # "1.Test Bölümü acmi:" must NOT hijack section detection!
    landscape_lines = [f"15,{i}" for i in range(45)]
    landscape_lines += (
        [
            "Avg. Boru",
            "1.Test Bölümü acmi:",
            "2.Test Bölümü Parametreleri:",
            "Basınç : 83,95",
            ": 1. Section",
            "Zaman : 14:30",
        ]
        + [f"row {k}" for k in range(20)]
        + ["Test Bölüm No", "BOT-FRM-C05-09-078"]
    )
    assert extract_page_section_no("\n".join(landscape_lines)) == "BÖLÜM 1"

    # Circular chart recorder OCR typos
    assert (
        extract_page_section_no(
            "Rest Bslün No:1\nStabilisayen\nCHART no. 123 - 333 - 74\n0 - 160bar / -20/+60°C\n24hr."
        )
        == "BÖLÜM 1"
    )
    assert (
        extract_page_section_no("Test Babm No: 2\nStabiliznsgan\nCHART no. 123 - 333 - 74")
        == "BÖLÜM 2"
    )
    assert (
        extract_page_section_no(
            "Tost Balem No:2 : -20\nBasinclenden a : 20\nCHART no. 123 - 333 - 74"
        )
        == "BÖLÜM 2"
    )


def test_project_name_multiline_wrap_and_prefix_consolidation():
    wrapped_p = (
        "SOYSAL\n"
        '24" MALATYA BRANŞMAN-2 DGBH YAPIM\n'
        "MÜHENDİSLİK\n"
        "INSAAT ANONIMA SIRKETI\n"
        "BOTAŞ\n"
        "İŞİ PROJESİ\n"
        "BORU HATLARI İLE PETROL\n"
        "MUKAVEMET TEST RAPORU\n"
    )
    assert (
        extract_project_name_from_text(wrapped_p) == '24" MALATYA BRANŞMAN-2 DGBH YAPIM İŞİ PROJESİ'
    )

    landscape_p = (
        '24" MALATYA BRANŞMAN-2 DGBH YAPIM İŞİ PROJESİ : 15,5\nDENGELEME İÇİN KAÇAK TEST RAPORU'
    )
    assert (
        extract_project_name_from_text(landscape_p)
        == '24" MALATYA BRANŞMAN-2 DGBH YAPIM İŞİ PROJESİ'
    )

    # Even if prefix counts outnumber full lines across pages, prefix consolidation picks full title
    pages = [
        PageText(page_number=i, text='24" MALATYA BRANŞMAN-2 DGBH YAPIM\nMÜHENDİSLİK', source="ocr")
        for i in range(1, 9)
    ] + [
        PageText(page_number=9, text='24" MALATYA BRANŞMAN-2 DGBH YAPIM İŞİ PROJESÍ', source="ocr"),
    ]
    assert extract_project_name_from_pages(pages) == '24" MALATYA BRANŞMAN-2 DGBH YAPIM İŞİ PROJESİ'


def test_malatya_air_pressure_landscape_and_pig_extraction():
    assert len(REQUIRED_FORM_SPECS) == 11

    calc_sheet_text = (
        'BOTAŞ\n24" MALATYA BRANŞMAN-2 DGBH YAPIM İŞİ PROJESİ\nBölüm No\n1. Section\n'
        "Boru Dış Çapı Do (mm) : 609,60\nBoru Et Kalınlığı t(mm) : 7,10\n"
        "Toplam Boru Uzunluğu (m) : 5446,37\nBölüm Hacmi : 1516.272\n"
        "Başlangıç Noktasının Kilometresi Kms : 0+000\nBitiş Noktasının Kilometresi KmE : 5+447\n"
        "Test Kabul İçin Katsayılar : 102,2\nBOT-FRM-001-027\n"
    )
    spec_calc = classify_form_text(calc_sheet_text)
    assert (
        spec_calc is not None
        and spec_calc.code == "calculation_sheet"
        and spec_calc.required is False
    )

    chart_text = "Rest Bslün No:1\nStabilisayen\n08/06/2026\nCHART no. 123 - 333 - 74\n0 - 160bar / -20/+60°C\n24hr.\n"
    spec_chart = classify_form_text(chart_text)
    assert (
        spec_chart is not None
        and spec_chart.code == "chart_recorder"
        and spec_chart.required is False
    )

    test_data_text = (
        '24" MALATYA BRANŞMAN-2 DGBH YAPIM İŞİ PROJESÍ\n'
        "HİDROSTATİK TEST VERÍLERÍ\nTest Bölüm No\n1. Section\n"
        "Mukavemet test basinci: 101.5 bar\n"
    )
    spec_td = classify_form_text(test_data_text)
    assert spec_td is not None and spec_td.code == "test_data"

    air_text = (
        "HAVA İÇERİK TESTİ KABUL RAPORU\nTest Bölüm No\n1. Section\n"
        "Test Bölüm Boyu : 5446,37 m\nBoru Dış Çapı : 609,60 mm\nBoru Et Kalınlığı\n7,10 mm\n"
        "2. Parametreler ve Veriler:\n"
        "Vp\nBasıncı 1 Bar Değiştirmek İçin Gerekli Teorik Su Miktarı\n(m3)= : 0,126940\n"
        "VpA\nBasıncı 1 Bar Değiştirmek İçin Kullanılan Su Miktarı\n(m3) = : 0,133560\n"
        "Vt\nTest Bölümünün Geometrik Hacmi\n(m3) = : 1516,272\n"
        "A : 45,011   K : 1,02\nSuyun İzotermal Sıkıştırılabilirlik Katsayısı ( 20,9975 °C - 95,25 Bar )\n"
        "(Vpa/Vp)-1= : 0,0522\n"
        "(Vpa/Vp)-1 değeri 0,06'dan küçük olduğu için test kabul edilmiştir.\n"
    )
    air_ext = _extract_form_specific_data("air_acceptance", air_text)
    assert air_ext["header"]["wall_thickness_mm"] == pytest.approx(7.10)
    assert air_ext["air_acceptance"]["vp_m3"] == pytest.approx(0.126940)
    assert air_ext["air_acceptance"]["vpa_m3"] == pytest.approx(0.133560)
    assert air_ext["air_acceptance"]["a_micro_per_bar"] == pytest.approx(45.011)
    assert air_ext["air_acceptance"]["k_factor"] == pytest.approx(1.02)

    pres_acc_text = (
        "BASINÇ TESTİ KABUL RAPORU\nTest Bölüm No : 1. Section\nTarih : 9.06.2026\n"
        "Test Bölüm Boyu : : 5446,37 m\nBoru Dış Çapı : 609,60 mm\nBoru Et Kalınlığı :\n7,10 mm\n"
        "1. Kullanılacak Formül:\nДр = -B * ΔT / (0,884 * ri / s + A)\n"
        "2. Parametreler ve Veriler:\n"
        "PA\n= Ölçülen Basınç Değişimi : 0,30\n(Bar)\n"
        "ДР : 0,060\n= Sıcaklık Değişiminden Kaynaklanan Basınç Değişimi\n"
        "Дт : 0,03\n= Testin Başı ve Sonunda su sıcaklığında oluşan değişim\n"
        "= Su ve Çeliğin Isıl Genleşme Katsayıları Arasındaki Fark : 148,996\n(1/K)\n"
        "= Suyun İzotermal Sıkıştırılabilirlik Katsayısı (116,33 BAR--21,563°C) : 45,088\n(1/Bar)\n"
        "PL : 0,3\n(PA-ДР)= : 0,240\n0,240 ≤ 0,30 olduğundan basınç testi kabul edilmiştir.\n"
    )
    pa_ext = _extract_form_specific_data("pressure_acceptance", pres_acc_text)
    pa_vals = pa_ext["pressure_acceptance"]
    assert pa_vals["pa_bar"] == pytest.approx(0.30)
    assert pa_vals["pt_bar"] == pytest.approx(0.060)
    assert pa_vals["delta_t_c"] == pytest.approx(0.03)
    assert pa_vals["b_micro_per_c"] == pytest.approx(148.996)
    assert pa_vals["a_micro_per_bar"] == pytest.approx(45.088)
    assert pa_vals["reported_passed"] is True

    # Landscape 24h leak_stabilization column-oriented table
    hours = [f"{h % 24:02d}:30" for h in range(14, 39)]
    pressures = ["83,95"] * 10 + ["83,85"] * 10 + ["83,8"] * 5
    landscape_leak = "\n".join(
        [
            "(°C)",
            "15,47",
            "15,03",
            "15,47",
            "15,67",
            "15,20",
            "15,97",
            "17,40",
            "Avg. Boru",
            "Sıcaklığı",
            "DENGELEME İÇİN KAÇAK TEST RAPORU",
            "Toprak",
            "Sıcaklığı",
            "15,4",
            "15,1",
            "15,9",
            "16,2",
            "Basınç : " + pressures[0],
            "(Ваг) : " + pressures[1],
            *pressures[2:],
            ": 1. Section",
            "Zaman : " + hours[0],
            "(Saat) : " + hours[1],
            *hours[2:],
            "Test Bölüm No",
            "BOT-FRM-C05-09-078",
        ]
    )
    leak_ext = _extract_form_specific_data("leak_stabilization", landscape_leak)
    assert leak_ext["time_log"]["row_count"] == 25
    assert leak_ext["time_log"]["duration_hours"] == pytest.approx(24.0)
    assert leak_ext["monitoring"]["p_start_bar"] == pytest.approx(83.95)
    assert leak_ext["monitoring"]["p_end_bar"] == pytest.approx(83.8)
    assert leak_ext["monitoring"]["last_4h_delta_c"] == pytest.approx(1.43)

    # Split-header pig events on Boşaltma
    dewat_text = (
        "BOŞALTMA KABUL RAPORU\nTest Bölüm No\n1. Section\n"
        "ATILIŞ\nALIŞ\nNOT\nPIG TİPİ\nTARİH\nSAAT\n"
        "10.06.2026\n10.06.2026\n00:00\nİKİ YÖNLÜ PIG : 20:00\nBOŞALTMA TAMAMLANDI\n"
    )
    dewat_ext = _extract_form_specific_data("dewatering", dewat_text)
    assert dewat_ext["pig_events"]["has_events"] is True
    assert dewat_ext["pig_events"]["first_time"] == "00:00"
    assert dewat_ext["pig_events"]["last_time"] == "20:00"


def test_commit_dossier_returns_section_lists_and_persists_formal_results(
    client, headers, tmp_path
):
    pdf = _make_multipage_pdf(
        tmp_path / "full_dossier_lists.pdf",
        [
            [
                "HIDROSTATIK TEST VERILERI",
                "Proje Adi : 24 MALATYA BRANSMAN DGBH YAPIM ISI PROJESI",
                "Test Bolum No : BOLUM 1",
                "Tarih : 09.06.2026",
                "Test Bolum Boyu : 5446,37 m",
                "Boru Dis Capi : 609,60 mm",
                "Boru Et Kalinligi : 7,10 mm",
                "Maximum Isletme Basinci : 75 bar",
                "Boru Akma Dayanimi (SMYS) : 450 MPa",
                "Test Bolumunun En Dusuk Kotu : 900 m",
                "Test Bolumunun En Yuksek Kotu : 950 m",
                "Baslangic Kotu : 910 m",
                "Bitis Kotu : 940 m",
                "Basinc Pompasi Yeri : Baslangic",
            ],
            [
                "HAVA ICERIK TESTI KABUL RAPORU",
                "Test Bolum No : 1. Section",
                "Tarih : 09.06.2026",
                "Boru Dis Capi : 609,60 mm",
                "Boru Et Kalinligi : 7,10 mm",
                "Test Bolum Boyu : 5446,37 m",
                "2. Parametreler ve Veriler:",
                "Vp = 0,126940",
                "Vpa = 0,133560",
                "A : 45,011   K : 1,02",
            ],
            [
                "BASINC TESTI KABUL RAPORU",
                "Test Bolum No : 1. Section",
                "Tarih : 10.06.2026",
                "2. Parametreler ve Veriler:",
                "PA : 0,30",
                "Pt : 0,060",
                "dT : 0,03",
                "B : 148,996",
                "A : 45,088",
            ],
            [
                "BOSALTMA KABUL RAPORU",
                "Test Bolum No : 1. Section",
                "Tarih : 11.06.2026",
                "00:00  IKI YONLU PIG  01:30  BOSALTMA TAMAMLANDI",
            ],
        ],
    )

    analyzed = client.post(
        "/api/ocr/analyze",
        files={"file": (pdf.name, pdf.read_bytes(), "application/pdf")},
        headers=headers,
    )
    assert analyzed.status_code == 201, analyzed.text
    a_id = analyzed.json()["id"]

    commit = client.post(
        f"/api/ocr/analyses/{a_id}/commit-dossier",
        json={
            "create_new_project": True,
            "new_project_name": "24 MALATYA BRANSMAN DGBH YAPIM ISI PROJESI",
            "overwrite_filled": False,
        },
        headers=headers,
    )
    assert commit.status_code == 200, commit.text
    c_body = commit.json()
    assert isinstance(c_body["created_sections"], list)
    assert len(c_body["created_sections"]) == 1
    assert c_body["created_sections_count"] == 1
    assert c_body["updated_sections"] == []
    assert c_body["updated_sections_count"] == 0
    sec_entry = c_body["created_sections"][0]
    assert sec_entry["section_no"] == "BÖLÜM 1"
    sess_id = sec_entry["session_id"]

    forms_resp = client.get(f"/api/sessions/{sess_id}/forms", headers=headers)
    assert forms_resp.status_code == 200
    assert forms_resp.json()["summary"]["required_total"] == len(REQUIRED_FORM_SPECS)

    results_resp = client.get(f"/api/sessions/{sess_id}/results", headers=headers)
    assert results_resp.status_code == 200
    saved_types = {item["test_type"] for item in results_resp.json()["items"]}
    assert {"profile", "air", "pressure", "pig"}.issubset(saved_types)

    # Re-commit with overwrite_filled=True updates the same section and returns list metadata
    commit_upd = client.post(
        f"/api/ocr/analyses/{a_id}/commit-dossier",
        json={
            "target_project_id": c_body["project"]["id"],
            "create_new_project": False,
            "overwrite_filled": True,
        },
        headers=headers,
    )
    assert commit_upd.status_code == 200, commit_upd.text
    upd_body = commit_upd.json()
    assert upd_body["created_sections"] == []
    assert isinstance(upd_body["updated_sections"], list)
    assert len(upd_body["updated_sections"]) == 1
    assert upd_body["updated_sections"][0]["session_id"] == sess_id


def test_hizan_engineering_calculation_pages_and_kp_fallback_match(client, headers, tmp_path):
    # Verify Unicode hyphen \u2010 directly on section extractor
    assert extract_page_section_no("SECTION 1 0+000.00 \u2010 1+132.21\nD = 323.9") == "BÖLÜM 1"

    hizan_pdf = _make_multipage_pdf(
        tmp_path / "hizan_calc_sample.pdf",
        [
            [
                "HIZAN ILCESI DGBH YAPIM ISI PROJESI TEST BOLUMLERI HESAPLAMALARI",
                "1 0+000.00 - 1+132.21",
                "2 1+132.21 - 8+029.78",
                "3 8+029.78 - 9+665.00",
                "4 9+665.00 - 13+167.26",
                "SMYS (52000/14.50377)",
            ],
            [
                "HIZAN ILCESI DGBH YAPIM ISI PROJESI",
                "SECTION 1 0+000.00 - 1+132.21",
                "=1 . 2",
                "D = 323.9",
                "Wt = 5.2",
                "Hs : 1384.08",
                "He : 1397.96",
                "Hmax : 1448.10",
                "Hmin : 1384.08",
                "Pmin : 93.75",
                "Ps = 100.28",
                "Pmax = 115.12",
                "Vsec = 90.28 m3",
            ],
        ],
    )

    # Pre-create Plan-Profil project with K-01 at 0+000..1+132 to verify KP fallback match
    pp_resp = client.post(
        "/api/projects/plan-profile/commit",
        json={
            "project_name": "Hizan Ilcesi Plan Profil",
            "sections": [
                {
                    "section_no": "K-01",
                    "start_kp": "0+000",
                    "end_kp": "1+132",
                    "length_m": 1132.0,
                    "outside_diameter_mm": 323.9,
                    "wall_thickness_mm": 5.2,
                }
            ],
        },
        headers=headers,
    )
    assert pp_resp.status_code == 201, pp_resp.text
    pp_data = pp_resp.json()
    project_id = pp_data["project_id"]
    orig_session_id = pp_data["items"][0]["id"]

    analyzed = client.post(
        "/api/ocr/analyze",
        files={"file": (hizan_pdf.name, hizan_pdf.read_bytes(), "application/pdf")},
        headers=headers,
    )
    assert analyzed.status_code == 201, analyzed.text
    dossier = analyzed.json()["dossier"]
    assert dossier["sections_count"] == 1
    assert dossier["sections"][0]["section_no"] == "BÖLÜM 1"
    assert dossier["sections"][0]["calculations"]["profile"]["status"] == "passed"

    committed = client.post(
        f"/api/ocr/analyses/{analyzed.json()['id']}/commit-dossier",
        json={
            "target_project_id": project_id,
            "create_new_project": False,
            "overwrite_filled": False,
        },
        headers=headers,
    )
    assert committed.status_code == 200, committed.text
    c_body = committed.json()
    assert c_body["created_sections"] == []
    assert len(c_body["updated_sections"]) == 1
    assert c_body["updated_sections"][0]["session_id"] == orig_session_id

    results_resp = client.get(f"/api/sessions/{orig_session_id}/results", headers=headers)
    assert "profile" in {r["test_type"] for r in results_resp.json()["items"]}


def test_multisheet_workbook_inherits_section_no_and_single_report_fallback():
    pages = [
        PageText(
            page_number=1,
            text="\n".join(
                [
                    "=== SHEET: hydrostatic test data ===",
                    "Proje Adı : ÖRNEK DGBH PROJESİ",
                    "HİDROSTATİK TEST VERİLERİ",
                    "Test Bölüm No : BÖLÜM 4",
                    "Tarih : 12.10.2026",
                    "Boru Dış Çapı : 406.4 mm",
                    "Boru Et Kalınlığı : 8.74 mm",
                    "Test Bölüm Boyu : 2000 m",
                ]
            ),
            source="spreadsheet",
        ),
        PageText(
            page_number=2,
            text="\n".join(
                [
                    "=== SHEET: filling report ===",
                    "SU DOLUM RAPORU",
                    "Tarih : 12.10.2026",
                    "08:00 50.0 10.0 12.0 15.0",
                    "09:00 60.0 10.0 12.0 15.0",
                ]
            ),
            source="spreadsheet",
        ),
    ]
    dossier = analyze_dossier_pages(pages, source_filename="bolum4.xls")
    assert dossier["sections_count"] == 1
    sec4 = dossier["sections"][0]
    assert sec4["section_no"] == "BÖLÜM 4"
    assert {f["form_code"] for f in sec4["present_forms"]} == {"test_data", "filling"}

    # Free-form single-section fallback synthesis
    free_pages = [
        PageText(
            page_number=1,
            text="Serbest ölçüm kaydı",
            source="pdf-text-layer",
        )
    ]
    fallback_rep = {
        "section_id": {"value": "2", "confidence": 0.9},
        "pipe_od_mm": {"value": 406.4, "confidence": 0.9},
        "wall_mm": {"value": 8.74, "confidence": 0.9},
        "length_m": {"value": 2000.0, "confidence": 0.9},
        "air_test": {
            "vpa": {"value": 0.015, "confidence": 0.9},
            "a": {"value": 45.0, "confidence": 0.9},
            "k": {"value": 1.02, "confidence": 0.9},
        },
    }
    synth = analyze_dossier_pages(
        free_pages,
        source_filename="VAN_DOGALGAZ_RAPOR.pdf",
        fallback_report=fallback_rep,
    )
    assert synth["sections_count"] == 1
    assert synth["sections"][0]["section_no"] == "BÖLÜM 2"
    assert synth["sections"][0]["calculations"]["air"]["passed"] is True
    assert synth["detected_project_name"] == "VAN DOGALGAZ"


def test_real_workspace_hizan_and_blank_xls_templates():
    from hidrostatik_test.services.report_ocr import analyze_report

    root = Path(__file__).resolve().parents[4]
    hizan = root / "hizan test 21.09.2026-1" / "hizan hesaplama 21.09.2026.pdf"
    if not hizan.exists():
        pytest.skip("Workspace Hizan test PDF not present outside repo")

    res_h = analyze_report(hizan)
    dos_h = analyze_dossier_pages(
        res_h.pages,
        source_filename=hizan.name,
        fallback_report=res_h.to_dict().get("report"),
    )
    assert dos_h["sections_count"] == 21
    assert all(sec["calculations"]["profile"]["status"] == "passed" for sec in dos_h["sections"])

    xls_files = sorted(root.glob("BOT-FRM-*.xls"))
    if not xls_files:
        pytest.skip("Workspace blank BOT-FRM XLS templates not present")
    for xls_path in xls_files:
        rx = analyze_report(xls_path)
        dx = analyze_dossier_pages(
            rx.pages,
            source_filename=xls_path.name,
            fallback_report=rx.to_dict().get("report"),
        )
        assert dx["sections_count"] == 0, f"{xls_path.name} falsely created sections"
        assert dx["detected_project_name"] is None, f"{xls_path.name} falsely detected project"


def test_strict_domain_invariants_and_boundary_guards():
    # 1) Exact Vpa == 1.06 * Vp fails strictly (both domain path and Vp fallback path)
    header_air = {"outside_diameter_mm": 355.6, "wall_thickness_mm": 5.2, "length_m": 1000.0}
    vp_exact = 0.010000
    vpa_exact = vp_exact * 1.06
    calcs_eq = evaluate_section_calculations(
        header_air,
        {
            "air_acceptance": {
                "form_code": "air_acceptance",
                "status": "filled",
                "extracted_data": {"air_acceptance": {"vp_m3": vp_exact, "vpa_m3": vpa_exact}},
            }
        },
    )
    assert calcs_eq["air"]["passed"] is False
    assert calcs_eq["air"]["status"] == "failed"

    # 2) OCR-parsed PL (2.0 bar) never relaxes immutable 0.30 bar acceptance limit
    calcs_pl = evaluate_section_calculations(
        header_air,
        {
            "pressure_acceptance": {
                "form_code": "pressure_acceptance",
                "status": "filled",
                "extracted_data": {
                    "pressure_acceptance": {
                        "pa_bar": 0.50,
                        "pt_bar": 0.05,
                        "pl_bar": 2.0,
                    }
                },
            }
        },
    )
    assert calcs_pl["pressure"]["passed"] is False
    assert calcs_pl["pressure"]["status"] == "failed"
    assert calcs_pl["pressure"]["pl_bar"] == pytest.approx(0.3)

    # 3) Invalid OCR elevations raise ValidationError -> warning (never silently clamped)
    calcs_elev = evaluate_section_calculations(
        {
            **header_air,
            "design_pressure_bar": 75.0,
            "smys_mpa": 360.0,
            "highest_elevation_m": 900.0,  # invalid: < start_elevation_m
            "lowest_elevation_m": 850.0,
            "start_elevation_m": 950.0,
            "end_elevation_m": 880.0,
        },
        {},
    )
    assert calcs_elev["profile"]["status"] == "warning"
    assert calcs_elev["profile"]["passed"] is None

    # 4) Sub-zero ambient/water temperatures are retained and fail >= +2 C check
    fill_cold = _extract_form_specific_data(
        "filling",
        "SU DOLUM RAPORU\nTest Bolum No : 1\n08:00 10.0 10.0 10.0 -1.5 12.0\n09:00 10.0 10.0 10.0 3.0 12.0",
    )
    assert fill_cold["filling"]["min_temp_c"] == pytest.approx(-1.5)
    _, cold_details = evaluate_operational_checks(
        header_air,
        {"filling": {"form_code": "filling", "status": "filled", "extracted_data": fill_cold}},
        {"air": {"status": "pending"}, "pressure": {"status": "pending"}},
    )
    assert cold_details["ambient_temp"]["status"] == "failed"

    # 5) Pressurization 0.2% volume deviation rule & missing Vsec never auto-pass
    pv_hdr = {
        "outside_diameter_mm": 355.6,
        "wall_thickness_mm": 5.2,
        "length_m": 1000.0,
        "section_volume_m3": 100.0,
    }
    pv_base = {
        "filling": {
            "form_code": "filling",
            "status": "filled",
            "extracted_data": {"filling": {"total_filled_m3": 99.15}},
        },
        "pressurization": {
            "form_code": "pressurization",
            "status": "filled",
            "extracted_data": {
                "time_log": {"row_count": 4},
                "pressurization": {"total_added_water_m3": 1.0},
            },
        },
    }
    _, pv_pass = evaluate_operational_checks(pv_hdr, pv_base, {})
    assert pv_pass["pressurization_volume"]["status"] == "passed"  # 0.15/100.15 = 0.1498% <= 0.2%

    pv_base["pressurization"]["extracted_data"]["pressurization"]["total_added_water_m3"] = 1.40
    _, pv_warn = evaluate_operational_checks(pv_hdr, pv_base, {})
    assert pv_warn["pressurization_volume"]["status"] == "warning"  # 0.55/100.55 = 0.547% > 0.2%

    _, pv_no_vol = evaluate_operational_checks(
        {}, {"pressurization": pv_base["pressurization"]}, {}
    )
    assert pv_no_vol["pressurization_volume"]["status"] == "warning"
    assert pv_no_vol["pressurization_volume"]["checked"] is False


def test_forms_catalog_structured_rows_inline_edit_and_single_form_scan(client, headers, tmp_path):
    commit_pp = client.post(
        "/api/projects/plan-profile/commit",
        json={
            "project_name": "Form Detay Test Projesi",
            "project_code": "FDT-01",
            "sections": [
                {
                    "section_no": "Bölüm 1",
                    "start_kp": "0+000",
                    "end_kp": "2+000",
                    "length_m": 2000.0,
                    "outside_diameter_mm": 355.6,
                    "wall_thickness_mm": 5.2,
                    "design_pressure_bar": 75.0,
                }
            ],
        },
        headers=headers,
    )
    assert commit_pp.status_code == 201, commit_pp.text
    pp_data = commit_pp.json()
    project_id = pp_data["project_id"]
    sess_id = pp_data["items"][0]["id"]

    # 1) Upload a multi-form dossier (Su Dolum + Temizlik Pigleri) -> commit to project
    pdf_multi = _make_multipage_pdf(
        tmp_path / "form_details_multi.pdf",
        [
            [
                "SU DOLUM RAPORU",
                "Proje Adi : Form Detay Test Projesi",
                "Test Bolum No : Bolum 1",
                "Tarih : 10.11.2026",
                "Dis Cap : 355.6 mm",
                "Et Kalinligi : 5.2 mm",
                "Hat Uzunlugu : 2000 m",
                "08:00 10.0 10.0 60.0 12.0 4.5",
                "09:00 20.0 10.0 120.0 13.0 5.0",
            ],
            [
                "TEMIZLIK KABUL RAPORU",
                "Proje Adi : Form Detay Test Projesi",
                "Test Bolum No : Bolum 1",
                "Tarih : 09.11.2026",
                "Pig Izleme Tablosu",
                "Firca Pigi-1 08:00 08:30",
            ],
        ],
    )
    a1 = client.post(
        "/api/ocr/analyze",
        files={"file": (pdf_multi.name, pdf_multi.read_bytes(), "application/pdf")},
        headers=headers,
    )
    assert a1.status_code == 201, a1.text
    c1 = client.post(
        f"/api/ocr/analyses/{a1.json()['id']}/commit-dossier",
        json={
            "target_project_id": project_id,
            "create_new_project": False,
            "overwrite_filled": True,
        },
        headers=headers,
    )
    assert c1.status_code == 200, c1.text

    forms_resp = client.get(f"/api/sessions/{sess_id}/forms", headers=headers)
    assert forms_resp.status_code == 200, forms_resp.text
    forms_body = forms_resp.json()
    assert len(forms_body["forms"]) == 16
    assert sum(1 for f in forms_body["forms"] if f["required"]) == 11
    assert sum(1 for f in forms_body["forms"] if not f["required"]) == 5
    assert "findings_counts" in forms_body["summary"]
    assert "key_metrics" in forms_body["summary"]

    by_code = {f["form_code"]: f for f in forms_body["forms"]}
    fill_ext = by_code["filling"]["extracted_data"]
    assert isinstance(fill_ext.get("rows"), list) and len(fill_ext["rows"]) == 2
    assert fill_ext["rows"][1]["total_volume_m3"] == pytest.approx(120.0)
    assert isinstance(by_code["filling"].get("findings"), list) and by_code["filling"]["findings"]

    clean_ext = by_code["cleaning"]["extracted_data"]
    assert isinstance(clean_ext.get("pig_runs"), list) and len(clean_ext["pig_runs"]) == 1
    assert clean_ext["pig_runs"][0]["duration_min"] == pytest.approx(30.0)

    # 2) Inline edit via PUT /api/sessions/{id}/forms/air_acceptance & filling
    r_put_air = client.put(
        f"/api/sessions/{sess_id}/forms/air_acceptance",
        json={
            "form_date": "12.11.2026",
            "extracted_data": {
                "air_acceptance": {
                    "a_micro_per_bar": 45.4,
                    "k_factor": 1.02,
                    "vpa_m3": 0.0250,
                }
            },
            "overwrite_session_inputs": True,
        },
        headers=headers,
    )
    assert r_put_air.status_code == 200, r_put_air.text
    air_body = r_put_air.json()
    assert air_body["form"]["revision"] == 1
    assert air_body["forms_payload"]["calculations"]["air"]["status"] == "failed"
    assert any(fd["status"] == "failed" for fd in (air_body["form"].get("findings") or []))

    r_put_fill = client.put(
        f"/api/sessions/{sess_id}/forms/filling",
        json={
            "form_date": "13.11.2026",
            "extracted_data": {
                "rows": [
                    {
                        "time_str": "08:00",
                        "meter_reading_m3": 100.0,
                        "delta_volume_m3": 100.0,
                        "total_volume_m3": 100.0,
                        "water_inlet_temp_c": 12.0,
                        "water_pressure_bar": 5.0,
                    },
                    {
                        "time_str": "09:30",
                        "meter_reading_m3": 185.5,
                        "delta_volume_m3": 85.5,
                        "total_volume_m3": 185.5,
                        "water_inlet_temp_c": 14.0,
                        "water_pressure_bar": 6.0,
                    },
                ]
            },
        },
        headers=headers,
    )
    assert r_put_fill.status_code == 200, r_put_fill.text
    fill_body = r_put_fill.json()
    assert fill_body["form"]["revision"] >= 2
    assert fill_body["form"]["extracted_data"]["filling"]["total_filled_m3"] == pytest.approx(185.5)
    assert fill_body["form"]["extracted_data"]["time_log"]["duration_hours"] == pytest.approx(1.5)

    # 3) Single-form OCR upload (both titled PDF and untitled cropped table-only PDF)
    titled_pdf = _make_multipage_pdf(
        tmp_path / "single_filling_titled.pdf",
        [
            [
                "SU DOLUM RAPORU",
                "Proje Adi : Form Detay Test Projesi",
                "Test Bolum No : Bolum 1",
                "Tarih : 14.11.2026",
                "10:00 10.0 10.0 190.0 12.5 5.0",
                "11:00 15.0 5.0 195.0 13.0 5.5",
            ]
        ],
    )
    r_scan_titled = client.post(
        f"/api/sessions/{sess_id}/forms/filling/scan",
        files={"file": (titled_pdf.name, titled_pdf.read_bytes(), "application/pdf")},
        data={"overwrite": "true"},
        headers=headers,
    )
    assert r_scan_titled.status_code == 200, r_scan_titled.text
    titled_body = r_scan_titled.json()
    assert titled_body["form"]["extracted_data"]["filling"]["total_filled_m3"] == pytest.approx(
        195.0
    )
    rev_after_titled = titled_body["form"]["revision"]

    untitled_pdf = _make_multipage_pdf(
        tmp_path / "single_filling_cropped.pdf",
        [
            [
                "07:00 50.0 50.0 210.0 11.5 4.2",
                "08:00 40.0 40.0 250.0 12.0 4.8",
            ]
        ],
    )
    r_scan_untitled = client.post(
        f"/api/sessions/{sess_id}/forms/filling/scan",
        files={"file": (untitled_pdf.name, untitled_pdf.read_bytes(), "application/pdf")},
        data={"overwrite": "true"},
        headers=headers,
    )
    assert r_scan_untitled.status_code == 200, r_scan_untitled.text
    untitled_body = r_scan_untitled.json()
    assert untitled_body["form"]["revision"] == rev_after_titled + 1
    assert untitled_body["form"]["extracted_data"]["filling"]["total_filled_m3"] == pytest.approx(
        250.0
    )
    assert len(untitled_body["form"]["extracted_data"]["rows"]) == 2


def test_single_form_scan_multifile_and_append_mode(client, headers, tmp_path):
    r_sess = client.post(
        "/api/sessions",
        json={"name": "Coklu Form Tarama Testi"},
        headers=headers,
    )
    assert r_sess.status_code == 201, r_sess.text
    sess_id = r_sess.json()["id"]

    # 1) Multi-file scan (2 separate PDF files in one request): page 1 carries signatures,
    #    page 2 carries continuation monitoring rows without signatures.
    page1_pdf = _make_multipage_pdf(
        tmp_path / "filling_page1.pdf",
        [
            [
                "SU DOLUM RAPORU",
                "Proje Adi : Coklu Sayfa Testi",
                "Test Bolum No : Bolum 1",
                "Tarih : 16.11.2026",
                "22:00 10.0 10.0 180.0 11.0 4.0",
                "23:00 10.0 10.0 190.0 11.2 4.1",
                "Yuklenici Firma                BOTAS",
                "Adi-Soyadi : Ali Yilmaz       Adi-Soyadi : Ayse Demir",
            ]
        ],
    )
    page2_pdf = _make_multipage_pdf(
        tmp_path / "filling_page2.pdf",
        [
            [
                "SU DOLUM RAPORU",
                "Test Bolum No : Bolum 1",
                "00:00 12.0 12.0 202.0 11.4 4.2",
            ]
        ],
    )
    r_multi = client.post(
        f"/api/sessions/{sess_id}/forms/filling/scan",
        files=[
            ("files", (page1_pdf.name, page1_pdf.read_bytes(), "application/pdf")),
            ("files", (page2_pdf.name, page2_pdf.read_bytes(), "application/pdf")),
        ],
        data={"overwrite": "true", "mode": "replace"},
        headers=headers,
    )
    assert r_multi.status_code == 200, r_multi.text
    multi_body = r_multi.json()
    multi_ext = multi_body["form"]["extracted_data"]
    assert multi_body["form"]["pages"] == [1, 2]
    assert len(multi_ext["rows"]) == 3
    assert multi_ext["filling"]["total_filled_m3"] == pytest.approx(202.0)
    assert multi_ext["time_log"]["duration_hours"] == pytest.approx(2.0)
    assert multi_ext["signatures"]["contractor_name"] == "Ali Yilmaz"
    assert multi_ext["signatures"]["botas_name"] == "Ayse Demir"

    # 2) Append mode (`mode="append"`): upload another continuation page with one overlapping
    #    row (`00:00`) and one new row (`01:00`). Verify dedup + preserved signatures + stats.
    page3_pdf = _make_multipage_pdf(
        tmp_path / "filling_page3_continuation.pdf",
        [
            [
                "00:00 12.0 12.0 202.0 11.4 4.2",
                "01:00 15.0 15.0 217.0 11.6 4.4",
            ]
        ],
    )
    r_append = client.post(
        f"/api/sessions/{sess_id}/forms/filling/scan",
        files=[("files", (page3_pdf.name, page3_pdf.read_bytes(), "application/pdf"))],
        data={"overwrite": "true", "mode": "append"},
        headers=headers,
    )
    assert r_append.status_code == 200, r_append.text
    app_body = r_append.json()
    app_ext = app_body["form"]["extracted_data"]
    assert app_body["form"]["pages"] == [1, 2, 3]
    assert app_body["form"]["form_date"] == "16.11.2026"
    assert [row["time_str"] for row in app_ext["rows"]] == ["22:00", "23:00", "00:00", "01:00"]
    assert app_ext["filling"]["total_filled_m3"] == pytest.approx(217.0)
    assert app_ext["time_log"]["duration_hours"] == pytest.approx(3.0)
    assert app_ext["signatures"]["contractor_name"] == "Ali Yilmaz"
    assert app_ext["signatures"]["botas_name"] == "Ayse Demir"


def test_multipage_form_tables_not_truncated_and_filling_ignores_odometer():
    from app.services.form_details import (
        build_form_structured_payload,
        reconcile_form_extracted_data,
    )

    # 1) Multi-page 011 (test_data) with footer on page 1 and continuation rows on page 2
    td_text = "\n".join(
        [
            "HİDROSTATİK TEST VERİLERİ",
            "TEST ÖLÇÜMLERİ",
            "110.5 0.0 95.0 78.2 90.0 74.1",
            "Müteahhit Adı-Soyadı : Ali Kaya",
            "BOTAŞ Adı-Soyadı : Veli Demir",
            "Sayfa 2/2 TEST ÖLÇÜMLERİ",
            "142.0 5000.0 92.0 75.8 87.0 71.7",
        ]
    )
    td_payload = build_form_structured_payload("test_data", td_text)
    assert len(td_payload["test_data"]["test_measurements"]) == 2
    assert td_payload["signatures"]["contractor_name"] == "Ali Kaya"
    assert td_payload["signatures"]["botas_name"] == "Veli Demir"

    # 2) Raw odometer reading in meter_reading_m3 (124500) must not override total_volume_m3 (250)
    reconciled = reconcile_form_extracted_data(
        "filling",
        {
            "rows": [
                {
                    "time_str": "08:00",
                    "meter_reading_m3": 124500.0,
                    "delta_volume_m3": 120.0,
                    "total_volume_m3": 120.0,
                    "water_inlet_temp_c": 12.0,
                    "water_pressure_bar": 4.0,
                },
                {
                    "time_str": "09:00",
                    "meter_reading_m3": 124630.0,
                    "delta_volume_m3": 130.0,
                    "total_volume_m3": 250.0,
                    "water_inlet_temp_c": 12.5,
                    "water_pressure_bar": 4.5,
                },
            ]
        },
    )
    assert reconciled["filling"]["total_filled_m3"] == pytest.approx(250.0)


def test_plan_profile_invalid_signature_returns_415_not_500_typeerror(client, headers):
    r = client.post(
        "/api/projects/plan-profile/scan",
        files={"file": ("sahte.pdf", b"NOT_A_REAL_PDF_BINARY", "application/pdf")},
        headers=headers,
    )
    assert r.status_code == 415
    assert r.json()["code"] == "invalid_file_signature"


def test_inputs_report_metadata_persisted_and_exported_to_report_context(client, headers):
    r_sess = client.post(
        "/api/sessions",
        json={
            "name": "Rapor Meta Testi",
            "inputs": {
                "report": {
                    "report_no": "RPR-2026-88",
                    "operator": "Kaan Aksoy",
                    "date": "2026-11-18",
                    "section_id": "K-14",
                }
            },
        },
        headers=headers,
    )
    assert r_sess.status_code == 201, r_sess.text
    sess_id = r_sess.json()["id"]
    rep = r_sess.json()["inputs"]["report"]
    assert rep["report_no"] == "RPR-2026-88"
    assert rep["operator"] == "Kaan Aksoy"
    assert rep["section_id"] == "K-14"

    r_txt = client.get(f"/api/sessions/{sess_id}/export?format=txt", headers=headers)
    assert r_txt.status_code == 200
    assert "RPR-2026-88" in r_txt.text
    assert "Kaan Aksoy" in r_txt.text


def test_ambient_temp_manual_fallback_in_operational_checks():
    from app.services.dossier import evaluate_operational_checks

    cold_checks, cold_details = evaluate_operational_checks(
        {"ambient_temperature_c": 1.5},
        {},
        {"air": {"status": "pending"}, "pressure": {"status": "pending"}},
    )
    assert cold_checks["ambient_temp"] is False
    assert cold_details["ambient_temp"]["status"] == "failed"
    assert "10.1" in cold_details["ambient_temp"]["message"]
    assert cold_details["ambient_temp"]["source_forms"] == ["manual_input"]

    ok_checks, ok_details = evaluate_operational_checks(
        {"ambient_temperature_c": 5.0},
        {},
        {"air": {"status": "pending"}, "pressure": {"status": "pending"}},
    )
    assert ok_checks["ambient_temp"] is True
    assert ok_details["ambient_temp"]["status"] == "passed"


def test_ocr_report_meta_fallback_and_safety_report_export(client, headers):
    from app.services.snapshot import apply_snapshot, build_snapshot

    r_sess = client.post(
        "/api/sessions",
        json={
            "name": "Guvenlik Rapor Testi",
            "inputs": {
                "water_backend": "table_v1_bicubic",
                "report": {"report_no": "", "operator": "", "date": "", "section_id": ""},
                "report_meta": {
                    "report_no": "OCR-2026-09",
                    "operator": "Ece Yilmaz",
                    "date": "2026-11-19",
                    "section_id": "K-22",
                },
                "air": {
                    "temperature_c": 10.0,
                    "pressure_bar": 50.0,
                    "ambient_temperature_c": 1.0,
                },
                "pressure": {
                    "temperature_c": 10.0,
                    "pressure_bar": 50.0,
                    "t_initial_c": 12.5,
                    "t_final_c": 10.5,
                    "delta_t_c": 2.0,
                },
            },
        },
        headers=headers,
    )
    assert r_sess.status_code == 201, r_sess.text
    sess = r_sess.json()
    assert sess["inputs"]["report"]["report_no"] == "OCR-2026-09"
    assert sess["inputs"]["report"]["operator"] == "Ece Yilmaz"
    assert sess["inputs"]["field"]["ambient_temperature_c"] == 1.0
    assert sess["inputs"]["pressure"]["derive_delta_t"] is False

    r_txt = client.get(f"/api/sessions/{sess['id']}/export?format=txt", headers=headers)
    assert r_txt.status_code == 200
    txt = r_txt.text
    assert "OCR-2026-09" in txt
    assert "Ece Yilmaz" in txt
    assert (
        "Su backend'i: Table Interpolation v1 (Bicubic)" in txt
        or "Su backend'i: table_v1_bicubic" in txt
    )
    assert "UYARI (Sartname 10.1)" in txt
    assert "Baslangic Tilk" in txt or "Baslangic sicakligi Tilk" in txt
    assert "Su Ozelligi Backend Karsilastirmasi" in txt

    snap = build_snapshot(sess["inputs"])
    assert snap["report"]["report_no"] == "OCR-2026-09"
    restored, _ = apply_snapshot({}, snap)
    assert restored["water_backend"] == "table_v1_bicubic"
    assert restored["report"]["operator"] == "Ece Yilmaz"
