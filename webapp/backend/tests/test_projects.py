"""Project CRUD, section counting and session attachment tests."""

from __future__ import annotations

OTHER_WORKSPACE = {"X-Session-ID": "other-workspace"}


def _create_project(api, headers, **payload):
    response = api.post("/api/projects", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def _create_session(api, headers, **payload):
    response = api.post("/api/sessions", json=payload or {"name": "Oturum Test"}, headers=headers)
    assert response.status_code in {200, 201}, response.text
    return response.json()


def test_project_create_and_list(client, headers):
    project = _create_project(client, headers, name="Kuzey Hatti", code="KH-01", client="ACME")
    assert project["section_count"] == 0
    assert project["code"] == "KH-01"
    assert project["client"] == "ACME"
    assert project["created_at"] and project["updated_at"]

    listed = client.get("/api/projects", headers=headers)
    assert listed.status_code == 200
    assert listed.headers["X-Total-Count"] == "1"
    body = listed.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == project["id"]
    assert body["items"][0]["section_count"] == 0


def test_session_attach_and_project_detail(client, headers):
    project = _create_project(client, headers, name="Proje A")
    session = _create_session(client, headers, name="Bolum 1", project_id=project["id"])
    assert session["project_id"] == project["id"]

    detail = client.get(f"/api/projects/{project['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["section_count"] == 1

    listed = client.get("/api/sessions", params={"project_id": project["id"]}, headers=headers)
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == session["id"]


def test_session_project_reassignment_and_detach(client, headers):
    first = _create_project(client, headers, name="P1")
    second = _create_project(client, headers, name="P2")
    session = _create_session(client, headers, name="S", project_id=first["id"])

    moved = client.put(
        f"/api/sessions/{session['id']}",
        json={"project_id": second["id"]},
        headers=headers,
    )
    assert moved.status_code == 200
    assert moved.json()["project_id"] == second["id"]
    assert client.get(f"/api/projects/{first['id']}", headers=headers).json()["section_count"] == 0
    assert client.get(f"/api/projects/{second['id']}", headers=headers).json()["section_count"] == 1

    detached = client.put(
        f"/api/sessions/{session['id']}", json={"project_id": None}, headers=headers
    )
    assert detached.status_code == 200
    fetched = client.get(f"/api/sessions/{session['id']}", headers=headers).json()
    assert fetched["project_id"] is None


def test_project_update_fields(client, headers):
    project = _create_project(client, headers, name="Eski", code="E-1", client="Eski Musteri")
    updated = client.put(
        f"/api/projects/{project['id']}",
        json={"name": "Yeni", "code": "Y-2", "client": "Yeni Musteri"},
        headers=headers,
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["name"] == "Yeni"
    assert body["code"] == "Y-2"
    assert body["client"] == "Yeni Musteri"

    partial = client.put(
        f"/api/projects/{project['id']}",
        json={"description": "aciklama"},
        headers=headers,
    ).json()
    assert partial["description"] == "aciklama"
    assert partial["name"] == "Yeni"
    assert partial["code"] == "Y-2"
    assert partial["client"] == "Yeni Musteri"

    cleared = client.put(
        f"/api/projects/{project['id']}",
        json={"client": None, "code": None},
        headers=headers,
    ).json()
    assert cleared["client"] is None
    assert cleared["code"] == ""


def test_project_q_filter(client, headers):
    _create_project(client, headers, name="Alpha Hatti", code="AL-1", client="Kuzey Enerji")
    _create_project(client, headers, name="Beta Hatti", code="BE-2", client="Guney Enerji")

    assert client.get("/api/projects", params={"q": "alpha"}, headers=headers).json()["total"] == 1
    assert client.get("/api/projects", params={"q": "be-2"}, headers=headers).json()["total"] == 1
    assert (
        client.get("/api/projects", params={"q": "guney enerji"}, headers=headers).json()["total"]
        == 1
    )
    assert client.get("/api/projects", params={"q": "yok"}, headers=headers).json()["total"] == 0


def test_project_workspace_isolation(client, headers):
    project = _create_project(client, headers, name="Gizli")

    assert client.get(f"/api/projects/{project['id']}", headers=OTHER_WORKSPACE).status_code == 404
    assert (
        client.put(
            f"/api/projects/{project['id']}",
            json={"name": "Ele Gecir"},
            headers=OTHER_WORKSPACE,
        ).status_code
        == 404
    )
    assert (
        client.delete(f"/api/projects/{project['id']}", headers=OTHER_WORKSPACE).status_code == 404
    )
    assert client.get("/api/projects", headers=OTHER_WORKSPACE).json()["total"] == 0

    foreign_session = client.post(
        "/api/sessions",
        json={"name": "Yabanci", "project_id": project["id"]},
        headers=OTHER_WORKSPACE,
    )
    assert foreign_session.status_code == 404


def test_project_delete_soft_and_detach(client, headers):
    project = _create_project(client, headers, name="Silinecek")
    session = _create_session(client, headers, name="S", project_id=project["id"])
    other_project = _create_project(client, headers, name="Kalacak")
    other_session = _create_session(client, headers, name="Diger", project_id=other_project["id"])
    standalone_session = _create_session(client, headers, name="Bagimsiz")

    deleted = client.delete(f"/api/projects/{project['id']}", headers=headers)
    assert deleted.status_code == 204
    assert client.get(f"/api/projects/{project['id']}", headers=headers).status_code == 404
    assert client.get("/api/projects", headers=headers).json()["total"] == 1

    assert client.get(f"/api/sessions/{session['id']}", headers=headers).status_code == 404
    listed_ids = {
        item["id"] for item in client.get("/api/sessions", headers=headers).json()["items"]
    }
    assert session["id"] not in listed_ids
    assert other_session["id"] in listed_ids
    assert standalone_session["id"] in listed_ids


def test_project_name_validation(client, headers):
    created = client.post("/api/projects", json={"name": "   "}, headers=headers)
    assert created.status_code == 422
    assert created.json()["code"] == "validation_error"

    project = _create_project(client, headers, name="Gecerli")
    updated = client.put(f"/api/projects/{project['id']}", json={"name": "  "}, headers=headers)
    assert updated.status_code == 422
    assert updated.json()["code"] == "validation_error"


def test_project_section_kp_meta_persisted_and_listed(client, headers):
    project = _create_project(client, headers, name="KP Test Projesi", code="PRJ-KP")
    first = client.post(
        "/api/sessions",
        json={
            "name": "K-01 · KP 0+000–12+000",
            "project_id": project["id"],
            "inputs": {
                "section_meta": {
                    "section_no": "K-01",
                    "description": "Birinci kesit",
                    "start_kp": "0+000",
                    "end_kp": "12+000",
                    "location": "KP 0+000 – 12+000",
                }
            },
        },
        headers=headers,
    )
    assert first.status_code == 201

    second = client.post(
        "/api/sessions",
        json={
            "name": "K-02 · KP 12+000–24+500",
            "project_id": project["id"],
            "inputs": {
                "section_meta": {
                    "section_no": "K-02",
                    "description": "Ikinci kesit",
                    "start_kp": "12+000",
                    "end_kp": "24+500",
                    "location": "KP 12+000 – 24+500",
                }
            },
        },
        headers=headers,
    )
    assert second.status_code == 201

    listed = client.get(f"/api/sessions?project_id={project['id']}", headers=headers).json()[
        "items"
    ]
    by_no = {item["section_meta"]["section_no"]: item["section_meta"] for item in listed}
    assert by_no["K-01"]["start_kp"] == "0+000"
    assert by_no["K-01"]["end_kp"] == "12+000"
    assert by_no["K-02"]["start_kp"] == "12+000"
    assert by_no["K-02"]["end_kp"] == "24+500"
    assert by_no["K-01"]["end_kp"] == by_no["K-02"]["start_kp"]


def _make_simple_pdf_bytes(lines: list[str]) -> bytes:
    """Minimal geçerli tek sayfalı PDF (gömülü metin katmanlı) üretir."""
    escaped = [line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") for line in lines]
    ops = ["BT", "/F1 11 Tf", "50 750 Td", "14 TL"]
    for idx, line in enumerate(escaped):
        if idx == 0:
            ops.append(f"({line}) Tj")
        else:
            ops.append(f"T* ({line}) Tj")
    ops.append("ET")
    stream_bytes = "\n".join(ops).encode("latin-1", errors="ignore")

    objs: list[bytes] = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n",
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
        f"5 0 obj\n<< /Length {len(stream_bytes)} >>\nstream\n".encode("ascii")
        + stream_bytes
        + b"\nendstream\nendobj\n",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objs:
        offsets.append(len(out))
        out.extend(obj)
    xref_pos = len(out)
    out.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode("ascii"))
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    out.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode(
            "ascii"
        )
    )
    return bytes(out)


def test_plan_profile_pdf_scan_and_batch_create(client, headers):
    pdf_bytes = _make_simple_pdf_bytes(
        [
            "BOTAS PLAN PROFIL PAFTASI - DOGU HATTI",
            "Outside Diameter: 406.4 mm   Wall Thickness: 8.74 mm   Design Pressure: 80 bar   Grade: X65",
            "KP 0+000   Kot: 200.0 m",
            "KP 6+000   Kot: 245.5 m",
            "KP 12+000  Kot: 310.0 m",
            "KP 18+000  Kot: 275.0 m",
            "KP 24+000  Kot: 190.0 m",
        ]
    )

    scan_res = client.post(
        "/api/projects/plan-profile/scan",
        files={"file": ("plan_profile_dogu.pdf", pdf_bytes, "application/pdf")},
        data={"max_section_length_m": "12000"},
        headers=headers,
    )
    assert scan_res.status_code == 200, scan_res.text
    scanned = scan_res.json()
    assert scanned["min_kp"] == "0+000"
    assert scanned["max_kp"] == "24+000"
    assert scanned["total_length_m"] == 24000.0
    assert scanned["continuity_ok"] is True
    drafts = scanned["draft_sections"]
    assert len(drafts) == 2
    assert drafts[0]["section_no"] == "K-01"
    assert drafts[0]["start_kp"] == "0+000"
    assert drafts[0]["end_kp"] == "12+000"
    assert drafts[0]["start_elevation_m"] == 200.0
    assert drafts[0]["end_elevation_m"] == 310.0
    assert drafts[1]["section_no"] == "K-02"
    assert drafts[1]["start_kp"] == "12+000"
    assert drafts[1]["end_kp"] == "24+000"
    assert drafts[0]["end_kp"] == drafts[1]["start_kp"]

    project = _create_project(client, headers, name="Plan Profil Projesi", code="PP-01")
    batch_res = client.post(
        f"/api/projects/{project['id']}/sections/batch",
        json={"sections": drafts},
        headers=headers,
    )
    assert batch_res.status_code == 201, batch_res.text
    batch_data = batch_res.json()
    assert batch_data["created_count"] == 2

    sessions = client.get(f"/api/sessions?project_id={project['id']}", headers=headers).json()[
        "items"
    ]
    assert len(sessions) == 2
    by_no = {s["section_meta"]["section_no"]: s["section_meta"] for s in sessions}
    assert by_no["K-01"]["end_kp"] == by_no["K-02"]["start_kp"] == "12+000"


def test_plan_profile_dxf_scan_and_pipe_meta(client, headers):
    import io

    import ezdxf

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_text('TYPICAL DRAWING 48" GAS PIPELINE', dxfattribs={"insert": (0, 200)})
    msp.add_text("ÖLÇÜLERİ : 10''", dxfattribs={"insert": (-500, -900)})
    msp.add_text("ZEMİN", dxfattribs={"insert": (-500, -600)})
    msp.add_text("PAFTA ARALIGI : 0+000 - 4+000", dxfattribs={"insert": (-500, -700)})
    msp.add_text("YOL GECISI : 0+117,1 - 0+266,6", dxfattribs={"insert": (200, -300)})

    for idx in range(5):
        x = idx * 1000.0
        kp = f"{idx}+000"
        elev = f"{600.0 + idx * 15:.3f}"
        msp.add_text(kp, dxfattribs={"insert": (x, -455.0)})
        msp.add_text(elev, dxfattribs={"insert": (x, -604.0)})

    buf = io.StringIO()
    doc.write(buf)
    dxf_bytes = buf.getvalue().encode("utf-8")

    scan_res = client.post(
        "/api/projects/plan-profile/scan",
        files={"file": ("00_04_test.dxf", dxf_bytes, "application/dxf")},
        data={"max_section_length_m": "4000"},
        headers=headers,
    )
    assert scan_res.status_code == 200, scan_res.text
    scanned = scan_res.json()
    assert scanned["extraction_method"] == "dxf-ezdxf"
    assert scanned["strategy"] == "auto_split"
    assert len(scanned["draft_sections"]) == 1
    assert scanned["station_count"] == 5
    assert scanned["elevation_point_count"] == 5
    assert scanned["pipe_meta"]["outside_diameter_mm"] == 273.1
    assert scanned["total_length_m"] == 4000.0
    assert scanned["draft_sections"][0]["start_elevation_m"] == 600.0
    assert scanned["draft_sections"][0]["end_elevation_m"] == 660.0


def _make_cad_vector_pdf_bytes() -> bytes:
    """Sentetik CAD vektör plan-profil PDF'i (KP ızgarası + BÖLÜM 1/2 + dikey ayırıcılar)."""
    ops: list[str] = ["BT /F1 10 Tf 1 0 0 1 60 170 Tm (0) Tj ET"]
    # KP 0 etiketi + 1+000 .. 10+000 etiketleri (1 km = 60 pt, x0 = 120)
    for km in range(1, 11):
        kx = 60 + km * 60
        ops.append(f"BT /F1 10 Tf 1 0 0 1 {kx} 170 Tm ({km}+000) Tj ET")
    ops.append("BT /F1 10 Tf 1 0 0 1 160 550 Tm (BOLUM 1) Tj ET")
    ops.append("BT /F1 10 Tf 1 0 0 1 450 550 Tm (BOLUM 2) Tj ET")

    # 500 m dikey ızgara çizgileri (y=200..470)
    for half_km in range(0, 21):
        gx = 60 + half_km * 30
        ops.append(f"{gx} 200 m {gx} 470 l S")

    # Bölüm sınır çizgileri (KP 0+000=60, 4+250=315, 10+000=660; y=200..580)
    for dx in (60, 315, 660):
        ops.append(f"{dx} 200 m {dx} 580 l S")

    stream_bytes = "\n".join(ops).encode("latin-1")
    objs: list[bytes] = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 800 700] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n",
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
        f"5 0 obj\n<< /Length {len(stream_bytes)} >>\nstream\n".encode("ascii")
        + stream_bytes
        + b"\nendstream\nendobj\n",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objs:
        offsets.append(len(out))
        out.extend(obj)
    xref_pos = len(out)
    out.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode("ascii"))
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    out.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode(
            "ascii"
        )
    )
    return bytes(out)


def test_plan_profile_cad_vector_pdf_reads_bolum_boundaries(client, headers):
    from pathlib import Path

    # 1) Sentetik vektör CAD PDF testi: max_section_length_m=3000 olsa bile pafta sınırları okunur
    pdf_bytes = _make_cad_vector_pdf_bytes()
    scan_res = client.post(
        "/api/projects/plan-profile/scan",
        files={"file": ("sentetik_cad_profil.pdf", pdf_bytes, "application/pdf")},
        data={"max_section_length_m": "3000"},
        headers=headers,
    )
    assert scan_res.status_code == 200, scan_res.text
    scanned = scan_res.json()
    assert scanned["strategy"] == "cad_profile"
    assert scanned["extraction_method"] == "pdf-cad-vector"
    drafts = scanned["draft_sections"]
    assert [(d["section_no"], d["start_kp"], d["end_kp"]) for d in drafts] == [
        ("BÖLÜM 1", "0+000", "4+250"),
        ("BÖLÜM 2", "4+250", "10+000"),
    ]

    # 2) Gerçek Kağızman DGBH paftası diskte mevcutsa 8 bölümün tam KP sınırlarını doğrula
    kagizman_pdf = Path(
        "/Users/macbook/Documents/Kodlama/HYDRO/Kağızman DGBH Hidrostatik Test Profili-Model A0.pdf"
    )
    if kagizman_pdf.is_file():
        real_res = client.post(
            "/api/projects/plan-profile/scan",
            files={"file": (kagizman_pdf.name, kagizman_pdf.read_bytes(), "application/pdf")},
            data={"max_section_length_m": "12000"},
            headers=headers,
        )
        assert real_res.status_code == 200, real_res.text
        real_data = real_res.json()
        assert real_data["strategy"] == "cad_profile"
        assert real_data["extraction_method"] == "pdf-cad-vector"
        assert real_data["pipe_meta"]["outside_diameter_mm"] == 273.1
        real_drafts = real_data["draft_sections"]
        assert len(real_drafts) == 8
        assert [
            (d["section_no"], d["start_kp"], d["end_kp"], d["length_m"]) for d in real_drafts
        ] == [
            ("BÖLÜM 1", "0+000", "18+280", 18280.0),
            ("BÖLÜM 2", "18+280", "32+239", 13959.0),
            ("BÖLÜM 3", "32+239", "37+732", 5493.0),
            ("BÖLÜM 4", "37+732", "48+500", 10768.0),
            ("BÖLÜM 5", "48+500", "50+500", 2000.0),
            ("BÖLÜM 6", "50+500", "53+500", 3000.0),
            ("BÖLÜM 7", "53+500", "54+500", 1000.0),
            ("BÖLÜM 8", "54+500", "57+563", 3063.0),
        ]
        assert all(len(d["profile_points"]) >= 3 for d in real_drafts)
        sec1_labels = [lm["label"] for lm in real_drafts[0]["landmarks"]]
        assert "Katranlı Pig İstasyonu" in sec1_labels
        assert "Sulu Dere" in sec1_labels
        assert any("ARAS NEHR" in lm["label"].upper() for lm in real_drafts[7]["landmarks"])

        proj = _create_project(client, headers, name="Kağızman 3D Test", code="KGZ-3D")
        first_batch = client.post(
            f"/api/projects/{proj['id']}/sections/batch",
            json={"sections": real_drafts},
            headers=headers,
        )
        assert first_batch.status_code == 201, first_batch.text
        first_data = first_batch.json()
        assert first_data["created_count"] == 8
        assert first_data["updated_count"] == 0

        sess_list = client.get(f"/api/sessions?project_id={proj['id']}", headers=headers).json()[
            "items"
        ]
        assert len(sess_list) == 8
        first_detail = client.get(f"/api/sessions/{sess_list[0]['id']}", headers=headers).json()
        assert first_detail["inputs"]["segments"] == []
        assert len(first_detail["inputs"]["profile_points"]) >= 3

        second_batch = client.post(
            f"/api/projects/{proj['id']}/sections/batch",
            json={"sections": real_drafts},
            headers=headers,
        )
        assert second_batch.status_code == 201, second_batch.text
        assert second_batch.json()["updated_count"] == 8
        sess_after = client.get(f"/api/sessions?project_id={proj['id']}", headers=headers).json()[
            "items"
        ]
        assert len(sess_after) == 8


def test_plan_profile_dxf_reads_bolum_dividers_before_auto_split(client, headers):
    import io

    import ezdxf

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    for km in range(0, 11):
        msp.add_text(f"{km}+000", dxfattribs={"insert": (km * 1000.0, -455.0)})
    msp.add_text("BÖLÜM 1", dxfattribs={"insert": (2000.0, 120.0)})
    msp.add_text("BÖLÜM 2", dxfattribs={"insert": (7000.0, 120.0)})
    for dx in (0.0, 4350.0, 10000.0):
        msp.add_line((dx, -460.0), (dx, 180.0))

    buf = io.StringIO()
    doc.write(buf)
    dxf_bytes = buf.getvalue().encode("utf-8")

    scan_res = client.post(
        "/api/projects/plan-profile/scan",
        files={"file": ("bolumlu_profil.dxf", dxf_bytes, "application/dxf")},
        data={"max_section_length_m": "3000"},
        headers=headers,
    )
    assert scan_res.status_code == 200, scan_res.text
    scanned = scan_res.json()
    assert scanned["strategy"] == "cad_profile"
    drafts = scanned["draft_sections"]
    assert [(d["section_no"], d["start_kp"], d["end_kp"]) for d in drafts] == [
        ("BÖLÜM 1", "0+000", "4+350"),
        ("BÖLÜM 2", "4+350", "10+000"),
    ]


def _make_single_section_cad_pdf_bytes(
    *,
    bolum_label: str | None,
    kp_ticks: list[tuple[int, str]],
    elev_start_m: float = 680.0,
) -> bytes:
    """Sentetik tek bölümlü CAD vektör plan-profil PDF'i (kot ekseni + profil gridleri)."""
    ops: list[str] = []
    if len(kp_ticks) >= 2:
        min_km = kp_ticks[0][0]
        max_km = kp_ticks[-1][0]
        span_km = max(1.0, (max_km - min_km) / 1000.0)
        x_start = 100.0
        x_end = 700.0
        px_per_m = (x_end - x_start) / max(1.0, float(max_km - min_km))
        for m_val, text in kp_ticks:
            kx = x_start + (m_val - min_km) * px_per_m
            ops.append(f"BT /F1 10 Tf 1 0 0 1 {kx:.1f} 170 Tm ({text}) Tj ET")
            if m_val == 0 and text == "0":
                continue

        # Kot ekseni: 500, 600, 700, 800, 900 -> y = 200, 260, 320, 380, 440
        for step_idx in range(5):
            el = 500 + step_idx * 100
            ey = 200 + step_idx * 60
            ops.append(f"BT /F1 9 Tf 1 0 0 1 55 {ey} Tm ({el}) Tj ET")

        # Profil boyunca dikey zemin kotu grid çizgileri (y=200..top_y)
        n_steps = max(8, int(span_km * 2))
        for i in range(n_steps + 1):
            frac = i / float(n_steps)
            gx = x_start + frac * (x_end - x_start)
            elev = elev_start_m + 140.0 * (0.5 - abs(frac - 0.5))
            top_y = 200.0 + (elev - 500.0) * 0.6
            ops.append(f"{gx:.1f} 200 m {gx:.1f} {top_y:.1f} l S")

    if bolum_label:
        ops.append(f"BT /F1 12 Tf 1 0 0 1 360 550 Tm ({bolum_label}) Tj ET")

    stream_bytes = "\n".join(ops).encode("latin-1")
    objs: list[bytes] = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 800 700] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n",
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
        f"5 0 obj\n<< /Length {len(stream_bytes)} >>\nstream\n".encode("ascii")
        + stream_bytes
        + b"\nendstream\nendobj\n",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objs:
        offsets.append(len(out))
        out.extend(obj)
    xref_pos = len(out)
    out.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode("ascii"))
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    out.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode(
            "ascii"
        )
    )
    return bytes(out)


def test_single_section_cad_pdf_and_dxf_preserve_bolum_and_profile(client, headers):
    import io

    import ezdxf

    # 1) Tek bölümlü CAD vektör PDF (BOLUM 1, KP 0+000..6+000, kot ekseni + profil)
    pdf_b1 = _make_single_section_cad_pdf_bytes(
        bolum_label="BOLUM 1",
        kp_ticks=[(0, "0")] + [(km * 1000, f"{km}+000") for km in range(1, 7)],
        elev_start_m=680.0,
    )
    res_b1 = client.post(
        "/api/projects/plan-profile/scan",
        files={"file": ("pafta_bolum1.pdf", pdf_b1, "application/pdf")},
        data={"max_section_length_m": "12000"},
        headers=headers,
    )
    assert res_b1.status_code == 200, res_b1.text
    b1 = res_b1.json()
    assert b1["strategy"] == "cad_profile"
    assert b1["extraction_method"] == "pdf-cad-vector"
    assert len(b1["draft_sections"]) == 1
    assert b1["draft_sections"][0]["section_no"] == "BÖLÜM 1"
    assert b1["draft_sections"][0]["start_kp"] == "0+000"
    assert b1["draft_sections"][0]["end_kp"] == "6+000"
    assert len(b1["draft_sections"][0]["profile_points"]) >= 3

    # 2) max_section_length_m=12000 iken 14.500 m tek bölüm (6+000..20+500) bölünmeden kalmalı
    ticks_b2 = (
        [(6000, "6+000")] + [(km * 1000, f"{km}+000") for km in range(8, 20)] + [(20500, "20+500")]
    )
    pdf_b2 = _make_single_section_cad_pdf_bytes(
        bolum_label="BOLUM 2",
        kp_ticks=ticks_b2,
        elev_start_m=700.0,
    )
    res_b2 = client.post(
        "/api/projects/plan-profile/scan",
        files={"file": ("pafta_bolum2.pdf", pdf_b2, "application/pdf")},
        data={"max_section_length_m": "12000"},
        headers=headers,
    )
    assert res_b2.status_code == 200, res_b2.text
    b2 = res_b2.json()
    assert b2["strategy"] == "cad_profile"
    assert len(b2["draft_sections"]) == 1
    assert b2["draft_sections"][0]["section_no"] == "BÖLÜM 2"
    assert b2["draft_sections"][0]["start_kp"] == "6+000"
    assert b2["draft_sections"][0]["end_kp"] == "20+500"
    assert b2["draft_sections"][0]["length_m"] == 14500.0

    # 3) Metin PDF'te açık tek kesit tanımı 14.500 m olsa bile max_section_length=12000 ile bölünmez
    explicit_pdf = _make_simple_pdf_bytes(
        [
            "TEST PROJESI PLAN PROFIL",
            "Bölüm 4: KP 0+000 - KP 14+500",
            "KP 0+000   Kot: 300.0 m",
            "KP 7+000   Kot: 360.0 m",
            "KP 14+500  Kot: 310.0 m",
        ]
    )
    res_exp = client.post(
        "/api/projects/plan-profile/scan",
        files={"file": ("tek_kesit_14500.pdf", explicit_pdf, "application/pdf")},
        data={"max_section_length_m": "12000"},
        headers=headers,
    )
    assert res_exp.status_code == 200, res_exp.text
    assert res_exp.json()["strategy"] == "explicit"
    assert len(res_exp.json()["draft_sections"]) == 1
    assert res_exp.json()["draft_sections"][0]["length_m"] == 14500.0

    # 4) Tek bölümlü DXF (BÖLÜM 3, KP 20+500..26+000)
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    dxf_stations = [20500, 21000, 22000, 23000, 24000, 25000, 26000]
    for st in dxf_stations:
        km = st // 1000
        rem = st % 1000
        x = float(st)
        msp.add_text(f"{km}+{rem:03d}", dxfattribs={"insert": (x, -455.0)})
        msp.add_text(f"{640.0 + (st - 20500) * 0.01:.2f}", dxfattribs={"insert": (x, -604.0)})
    msp.add_text("BÖLÜM 3", dxfattribs={"insert": (23000.0, 120.0)})
    buf = io.StringIO()
    doc.write(buf)
    res_dxf = client.post(
        "/api/projects/plan-profile/scan",
        files={"file": ("bolum3.dxf", buf.getvalue().encode("utf-8"), "application/dxf")},
        data={"max_section_length_m": "12000"},
        headers=headers,
    )
    assert res_dxf.status_code == 200, res_dxf.text
    b3 = res_dxf.json()
    assert b3["strategy"] == "cad_profile"
    assert len(b3["draft_sections"]) == 1
    assert b3["draft_sections"][0]["section_no"] == "BÖLÜM 3"
    assert b3["draft_sections"][0]["start_kp"] == "20+500"
    assert b3["draft_sections"][0]["end_kp"] == "26+000"
    assert len(b3["draft_sections"][0]["profile_points"]) >= 4


def test_sequential_single_sheets_append_without_overwrite_and_project_scene(client, headers):
    project = _create_project(client, headers, name="Çoklu Pafta Hattı", code="CP-01")

    sheets = [
        ("0+000", "5+000", 5000.0, [(0.0, 410.0), (2500.0, 465.0), (5000.0, 430.0)]),
        ("5+000", "11+000", 6000.0, [(0.0, 430.0), (3000.0, 510.0), (6000.0, 470.0)]),
        ("11+000", "16+500", 5500.0, [(0.0, 470.0), (2800.0, 445.0), (5500.0, 495.0)]),
    ]
    for s_kp, e_kp, length_m, pts in sheets:
        commit_res = client.post(
            "/api/projects/plan-profile/commit",
            json={
                "project_id": project["id"],
                "sections": [
                    {
                        "section_no": "K-01",
                        "start_kp": s_kp,
                        "end_kp": e_kp,
                        "length_m": length_m,
                        "outside_diameter_mm": 609.6,
                        "wall_thickness_mm": 7.1,
                        "design_pressure_bar": 75.0,
                        "smys_mpa": 450.0,
                        "profile_points": [{"station_m": x, "elevation_m": y} for x, y in pts],
                    }
                ],
            },
            headers=headers,
        )
        assert commit_res.status_code == 201, commit_res.text

    listed = client.get(f"/api/sessions?project_id={project['id']}", headers=headers).json()[
        "items"
    ]
    assert len(listed) == 3
    by_no = {item["section_meta"]["section_no"]: item for item in listed}
    assert sorted(by_no.keys()) == ["K-01", "K-02", "K-03"]
    assert by_no["K-01"]["section_meta"]["start_kp"] == "0+000"
    assert by_no["K-02"]["section_meta"]["start_kp"] == "5+000"
    assert by_no["K-03"]["section_meta"]["start_kp"] == "11+000"

    for item in listed:
        forms_res = client.get(f"/api/sessions/{item['id']}/forms", headers=headers)
        assert forms_res.status_code == 200
        assert forms_res.json()["summary"]["required_total"] == 11

    scene_res = client.get(f"/api/projects/{project['id']}/scene", headers=headers)
    assert scene_res.status_code == 200, scene_res.text
    scene = scene_res.json()
    assert scene["section_count"] == 3
    assert scene["total_length_m"] == 16500.0
    assert scene["start_kp_m"] == 0.0
    assert scene["continuity_ok"] is True
    assert scene["is_survey_profile"] is True
    assert len(scene["segments"]) >= 6
    assert all(seg.get("session_id") for seg in scene["segments"])
    assert scene["profile_points"][0][0] == 0.0
    assert scene["profile_points"][-1][0] == 16500.0
    assert [sec["section_no"] for sec in scene["sections"]] == ["K-01", "K-02", "K-03"]

    assert (
        client.get(f"/api/projects/{project['id']}/scene", headers=OTHER_WORKSPACE).status_code
        == 404
    )

    # Arada +1500 m KP boşluğu bırakan 4. bölüm eklenince continuity_ok False olmalı
    gap_res = client.post(
        "/api/projects/plan-profile/commit",
        json={
            "project_id": project["id"],
            "sections": [
                {
                    "section_no": "K-01",
                    "start_kp": "18+000",
                    "end_kp": "20+000",
                    "length_m": 2000.0,
                    "outside_diameter_mm": 609.6,
                    "wall_thickness_mm": 7.1,
                    "profile_points": [
                        {"station_m": 0.0, "elevation_m": 500.0},
                        {"station_m": 2000.0, "elevation_m": 520.0},
                    ],
                }
            ],
        },
        headers=headers,
    )
    assert gap_res.status_code == 201, gap_res.text
    gap_scene = client.get(f"/api/projects/{project['id']}/scene", headers=headers).json()
    assert gap_scene["section_count"] == 4
    assert gap_scene["continuity_ok"] is False
    assert any("boşluğu" in w for w in gap_scene["warnings"])

    # Bitiş KP'si eksik (ör. yalnızca start_kp='0+001') bölüm K-01 üzerine binmeden ucuna eklenmeli
    partial_res = client.post(
        "/api/sessions",
        json={
            "name": "BÖLÜM 5 · Kısmi KP",
            "project_id": project["id"],
            "inputs": {
                "section_meta": {
                    "section_no": "BÖLÜM 5",
                    "start_kp": "0+001",
                    "end_kp": "",
                },
                "geometry": {
                    "outside_diameter_mm": 609.6,
                    "wall_thickness_mm": 7.1,
                    "length_m": 2000.0,
                },
            },
        },
        headers=headers,
    )
    assert partial_res.status_code == 201, partial_res.text
    partial_scene = client.get(f"/api/projects/{project['id']}/scene", headers=headers).json()
    assert partial_scene["section_count"] == 5
    assert partial_scene["sections"][-1]["section_no"] == "BÖLÜM 5"
    assert partial_scene["sections"][-1]["start_m"] >= 20000.0


def test_sideways_activity_profile_pdf_and_ym_em_resolution(client, headers, monkeypatch):
    import io

    import pytest

    fitz = pytest.importorskip("fitz")
    from app.services import plan_profile as pp_service

    from hidrostatik_test.services.report_ocr import PageText

    # Sentetik dikey (842x1191) vektör pafta PDF'i üret
    doc = fitz.open()
    page = doc.new_page(width=842, height=1191)
    shape = page.new_shape()
    for x in (180.0, 220.0, 260.0):
        shape.draw_line(fitz.Point(x, 100.0), fitz.Point(x, 900.0))
    for i, width in enumerate((120.0, 95.0, 140.0, 210.0, 185.0, 260.0, 230.0, 175.0)):
        y = 160.0 + i * 90.0
        shape.draw_line(fitz.Point(260.0, y), fitz.Point(260.0 + width, y))
    shape.finish(color=(0, 0, 0), width=1.0)
    shape.commit()
    pdf_bytes = doc.tobytes()
    doc.close()

    # Senaryo 1: SECTION O1 + ": EM0-960:00" + Hs/He/Hmax/Hmin + YM/EM çakışması
    s1_ocr = """
    HİDROSTATİK TEST AKTİVETİSİ PROFİLİ SECTION O1
    Hs: 1772.97
    VEM: 0+000.00
    YM: 0+000.00
    Hmin: 1766.65
    Hmax: 1779.40
    He: 1779.18
    5.2 mm
    379.76 m
    6.4 mm
    17.00 m
    KP: 0+000.00 & КР: 1+132.21
    HİZAN İLÇESİ DOĞAL GAZ BORU HATLARI YAPIM İŞİ PROJESİ : EM0-960:00
    """
    monkeypatch.setattr(
        pp_service,
        "ocr_pdf_page_rotated",
        lambda *_args, **_kwargs: PageText(page_number=1, text=s1_ocr, source="ocr"),
    )
    res1 = client.post(
        "/api/projects/plan-profile/scan",
        files={"file": ("1.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        headers=headers,
    )
    assert res1.status_code == 200, res1.text
    b1 = res1.json()
    assert b1["detected_project_name"] == "HİZAN İLÇESİ DOĞAL GAZ BORU HATLARI YAPIM İŞİ PROJESİ"
    assert b1["strategy"] == "cad_profile"
    assert len(b1["draft_sections"]) == 1
    d1 = b1["draft_sections"][0]
    assert d1["section_no"] == "BÖLÜM 1"
    assert abs(d1["start_m"] - 0.0) < 0.1
    assert abs(d1["end_m"] - 1132.21) < 0.2
    assert d1["start_elevation_m"] == 1772.97
    assert d1["end_elevation_m"] == 1779.18
    assert d1["highest_elevation_m"] == 1779.4
    assert d1["lowest_elevation_m"] == 1766.65
    assert d1["wall_thickness_mm"] == 5.2
    assert len(d1["profile_points"]) >= 6

    # Senaryo 2: Section 10'daki YM antet yazım hatası ('M:23+714.7 vs M:24+094.51)
    s10_ocr = """
    HİDROSTATİK TEST AKTİVETİSİ PROFİLİ SECTION 10
    Hs: 1724.88
    M: 24+094.51
    'M: 23+714.7
    Hmin: 1710.14
    Hmax: 1920.14
    He: 1920.14
    5.20 mm
    1583.59 m
    KP: 23+714.71 & KP: 27+361.37
    HİZAN İLÇESİ DOĞAL GAZ BORU HATLARI YAPIM İŞİ PROJESİ
    """
    monkeypatch.setattr(
        pp_service,
        "ocr_pdf_page_rotated",
        lambda *_args, **_kwargs: PageText(page_number=1, text=s10_ocr, source="ocr"),
    )
    res10 = client.post(
        "/api/projects/plan-profile/scan",
        files={"file": ("10.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        headers=headers,
    )
    assert res10.status_code == 200, res10.text
    d10 = res10.json()["draft_sections"][0]
    assert d10["section_no"] == "BÖLÜM 10"
    assert abs(d10["start_m"] - 24094.51) < 0.2
    assert abs(d10["end_m"] - 27361.37) < 0.2

    # Senaryo 3: Section 21 kopyala-yapıştır antet hatası + kırpılmış min: 2037. kontrolü
    s21_ocr = """
    HİDROSTATİK TEST AKTİVETİSİ PROFİLİ SECTION 21
    Hs: 1677.44
    EM: 47+896.88
    He: 1613.33
    VEM: 49+329.15
    Hmax: 1677.44
    Hmin: 1547.20
    KP: 47+393.04 & КР: 47+896.88
    HİZAN İLÇESİ DOĞAL GAZ BORU HATLARI YAPIM İŞİ PROJESİ
    """
    monkeypatch.setattr(
        pp_service,
        "ocr_pdf_page_rotated",
        lambda *_args, **_kwargs: PageText(page_number=1, text=s21_ocr, source="ocr"),
    )
    res21 = client.post(
        "/api/projects/plan-profile/scan",
        files={"file": ("21.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        headers=headers,
    )
    assert res21.status_code == 200, res21.text
    d21 = res21.json()["draft_sections"][0]
    assert d21["section_no"] == "BÖLÜM 21"
    assert abs(d21["start_m"] - 47896.88) < 0.2
    assert abs(d21["end_m"] - 49329.15) < 0.2

    elevs_12 = pp_service._extract_activity_profile_elevations(
        "He: 2037.33\nHs: 2130.14\nHmax: 2247.33\nmin: 2037."
    )
    assert elevs_12["lowest_elevation_m"] == 2037.33


def test_hizan_real_sheets_scan_commit_and_3d_scene(client, headers):
    from pathlib import Path

    import pytest

    from hidrostatik_test.services.report_ocr import ocr_available

    hizan_dir = Path("/Users/macbook/Documents/Kodlama/HYDRO/hizan test 21.09.2026-1")
    if not hizan_dir.exists() or not ocr_available():
        pytest.skip("Hizan örnek paftaları veya OCR motoru yok")

    sample_drafts = []
    for name in ("1.pdf", "10.pdf", "12.pdf", "20.pdf", "21.pdf"):
        with (hizan_dir / name).open("rb") as handle:
            res = client.post(
                "/api/projects/plan-profile/scan",
                files={"file": (name, handle, "application/pdf")},
                headers=headers,
            )
        assert res.status_code == 200, res.text
        body = res.json()
        assert len(body["draft_sections"]) == 1
        draft = body["draft_sections"][0]
        assert draft["start_elevation_m"] is not None
        assert draft["lowest_elevation_m"] is not None
        assert len(draft["profile_points"]) >= 10
        sample_drafts.append(draft)

    commit = client.post(
        "/api/projects/plan-profile/commit",
        json={
            "project_name": "HİZAN İLÇESİ DOĞAL GAZ BORU HATLARI YAPIM İŞİ PROJESİ",
            "sections": sample_drafts,
        },
        headers=headers,
    )
    assert commit.status_code == 201, commit.text
    c_body = commit.json()
    assert c_body["created_count"] == 5
    project_id = c_body["project"]["id"]

    sessions = client.get(f"/api/sessions?project_id={project_id}", headers=headers).json()["items"]
    assert len(sessions) == 5
    for sess in sessions:
        forms = client.get(f"/api/sessions/{sess['id']}/forms", headers=headers).json()
        assert forms["summary"]["required_total"] == 11

    scene = client.get(f"/api/projects/{project_id}/scene", headers=headers).json()
    assert scene["section_count"] == 5
    assert scene["is_survey_profile"] is True
    assert len(scene["profile_points"]) >= 40
    # 20.pdf (47+393..47+896,9) ile 21.pdf (47+896,9..49+329,2) ardışık olduğu için 3D sahnede bağlanmalı
    sec20 = next(s for s in scene["sections"] if s["section_no"] == "BÖLÜM 20")
    sec21 = next(s for s in scene["sections"] if s["section_no"] == "BÖLÜM 21")
    assert abs(sec21["start_m"] - sec20["end_m"]) <= 1.0


def test_project_scene_equipment_warnings_and_template_clone(client, headers):
    project = _create_project(client, headers, name="3D Ekipman Projesi", code="3D-01")
    s1 = _create_session(
        client,
        headers,
        name="Bölüm 1",
        project_id=project["id"],
        inputs={
            "section_meta": {"section_no": "B-01", "start_kp": "0+000", "end_kp": "1+000"},
            "geometry": {
                "outside_diameter_mm": 406.4,
                "wall_thickness_mm": 8.74,
                "length_m": 1000.0,
            },
            "section_profile": {
                "start_elevation_m": 100.0,
                "end_elevation_m": 200.0,
                "highest_elevation_m": 200.0,
                "lowest_elevation_m": 100.0,
                "design_pressure_bar": 80.0,
                "smys_mpa": 450.0,
            },
        },
    )

    approx_scene = client.get(f"/api/projects/{project['id']}/scene", headers=headers).json()
    assert approx_scene["is_survey_profile"] is False
    assert approx_scene["is_custom_equipment"] is False
    joined_warnings = " ".join(approx_scene["warnings"])
    assert "profile_points" in joined_warnings
    assert "equipment" in joined_warnings

    upd = client.put(
        f"/api/sessions/{s1['id']}",
        json={
            "inputs": {
                "profile_points": [
                    {"station_m": 0.0, "elevation_m": 100.0},
                    {"station_m": 1000.0, "elevation_m": 200.0},
                ],
                "equipment": [
                    {"id": "s1-pump", "type": "pump", "label": "Ana Pompa", "station_m": 0.0},
                    {"id": "s1-gauge", "kind": "gauge", "label": "Orta Olcer", "station_m": 500.0},
                ],
            }
        },
        headers={**headers, "If-Match": f'"{s1["revision"]}"'},
    )
    assert upd.status_code == 200, upd.text

    commit_res = client.post(
        "/api/projects/plan-profile/commit",
        json={
            "project_id": project["id"],
            "sections": [
                {
                    "section_no": "B-02",
                    "start_kp": "1+000",
                    "end_kp": "2+000",
                    "length_m": 1000.0,
                    "outside_diameter_mm": 406.4,
                    "wall_thickness_mm": 8.74,
                    "profile_points": [
                        {"station_m": 0.0, "elevation_m": 200.0},
                        {"station_m": 1000.0, "elevation_m": 300.0},
                    ],
                    "equipment": [
                        {
                            "id": "s2-valve",
                            "type": "valve",
                            "label": "Bitis Vanasi",
                            "station_m": 800.0,
                            "status": "warning",
                        }
                    ],
                }
            ],
        },
        headers=headers,
    )
    assert commit_res.status_code == 201, commit_res.text

    real_scene = client.get(f"/api/projects/{project['id']}/scene", headers=headers).json()
    assert real_scene["is_survey_profile"] is True
    assert real_scene["is_custom_equipment"] is True
    assert not any("profile_points" in w or "equipment" in w for w in real_scene["warnings"])
    eq_by_id = {item["id"]: item for item in real_scene["equipment"]}
    assert eq_by_id["s1-gauge"]["distance_m"] == 500.0
    assert eq_by_id["s1-gauge"]["elevation_m"] == 150.0
    assert eq_by_id["s2-valve"]["distance_m"] == 1800.0
    assert eq_by_id["s2-valve"]["elevation_m"] == 280.0
    assert eq_by_id["s2-valve"]["status"] == "warning"

    clone_res = client.post(
        f"/api/projects/{project['id']}/clone",
        json={"mode": "template", "name": "3D Şablon Kopya"},
        headers=headers,
    )
    assert clone_res.status_code == 201, clone_res.text
    cloned_id = clone_res.json()["project"]["id"]
    cloned_sessions = client.get(f"/api/sessions?project_id={cloned_id}", headers=headers).json()[
        "items"
    ]
    b01_meta = next(s for s in cloned_sessions if s["name"] == "Bölüm 1")
    b01_clone = client.get(f"/api/sessions/{b01_meta['id']}", headers=headers).json()
    assert len(b01_clone["inputs"]["equipment"]) == 2
    assert b01_clone["inputs"]["equipment"][1]["id"] == "s1-gauge"


def test_project_scene_mixed_sections_duplicate_eq_ids_and_recommit_preserve(client, headers):
    project = _create_project(client, headers, name="Karışık Kesit Projesi", code="3D-MIX")
    # Bölüm 1: gerçek kot profili ve varsayılan benzeri statik ID'li ekipman
    s1 = _create_session(
        client,
        headers,
        name="B-01",
        project_id=project["id"],
        inputs={
            "section_meta": {"section_no": "B-01", "start_kp": "0+000", "end_kp": "1+000"},
            "geometry": {
                "outside_diameter_mm": 406.4,
                "wall_thickness_mm": 8.74,
                "length_m": 1000.0,
            },
            "profile_points": [
                {"station_m": 0.0, "elevation_m": 100.0},
                {"station_m": 1000.0, "elevation_m": 200.0},
            ],
            "equipment": [
                {"id": "eq-valve-start", "type": "valve", "label": "S1 Vana", "station_m": 0.0},
            ],
        },
    )
    # Bölüm 2: kot profili ve ekipmanı yok -> karışık sahne yaklaşıklık bayraklarını korumalı
    _create_session(
        client,
        headers,
        name="B-02",
        project_id=project["id"],
        inputs={
            "section_meta": {"section_no": "B-02", "start_kp": "1+000", "end_kp": "2+000"},
            "geometry": {
                "outside_diameter_mm": 406.4,
                "wall_thickness_mm": 8.74,
                "length_m": 1000.0,
            },
            "section_profile": {
                "start_elevation_m": 200.0,
                "end_elevation_m": 240.0,
                "highest_elevation_m": 240.0,
                "lowest_elevation_m": 200.0,
            },
        },
    )

    mixed_scene = client.get(f"/api/projects/{project['id']}/scene", headers=headers).json()
    assert mixed_scene["is_survey_profile"] is False
    assert mixed_scene["is_custom_equipment"] is False
    joined_warnings = " ".join(mixed_scene["warnings"])
    assert "profile_points" in joined_warnings
    assert "equipment" in joined_warnings
    # Kısmi ekipmanda sınır vanası korunmalı
    assert any(item["id"] == "eq-boundary-1" for item in mixed_scene["equipment"])

    # Bölüm 2'ye aynı 'eq-valve-start' ID'si ile ekipman ve profile_points eklendiğinde ID çakışmamalı
    sessions = client.get(f"/api/sessions?project_id={project['id']}", headers=headers).json()[
        "items"
    ]
    b02_meta = next(s for s in sessions if s["name"] == "B-02")
    b02_detail = client.get(f"/api/sessions/{b02_meta['id']}", headers=headers).json()
    upd2 = client.put(
        f"/api/sessions/{b02_meta['id']}",
        json={
            "inputs": {
                "profile_points": [
                    {"station_m": 0.0, "elevation_m": 200.0},
                    {"station_m": 1000.0, "elevation_m": 240.0},
                ],
                "equipment": [
                    {"id": "eq-valve-start", "type": "valve", "label": "S2 Vana", "station_m": 0.0},
                ],
            }
        },
        headers={**headers, "If-Match": f'"{b02_detail["revision"]}"'},
    )
    assert upd2.status_code == 200, upd2.text

    full_scene = client.get(f"/api/projects/{project['id']}/scene", headers=headers).json()
    assert full_scene["is_survey_profile"] is True
    assert full_scene["is_custom_equipment"] is True
    eq_ids = [item["id"] for item in full_scene["equipment"]]
    assert len(eq_ids) == 2
    assert len(set(eq_ids)) == 2

    # B-01 yeniden plan-profile commit edildiğinde (equipment boşsa) mevcut ekipmanı korunmalı
    recommit = client.post(
        "/api/projects/plan-profile/commit",
        json={
            "project_id": project["id"],
            "sections": [
                {
                    "section_no": "B-01",
                    "start_kp": "0+000",
                    "end_kp": "1+000",
                    "length_m": 1000.0,
                    "outside_diameter_mm": 406.4,
                    "wall_thickness_mm": 8.74,
                    "profile_points": [
                        {"station_m": 0.0, "elevation_m": 102.0},
                        {"station_m": 1000.0, "elevation_m": 202.0},
                    ],
                }
            ],
        },
        headers=headers,
    )
    assert recommit.status_code == 201, recommit.text
    s1_after = client.get(f"/api/sessions/{s1['id']}", headers=headers).json()
    assert len(s1_after["inputs"]["equipment"]) == 1
    assert s1_after["inputs"]["equipment"][0]["label"] == "S1 Vana"


def test_project_scene_respects_per_segment_smys(client, headers):
    proj = client.post(
        "/api/projects", json={"name": "Karma Kalite Koridor"}, headers=headers
    ).json()
    sess = client.post(
        "/api/sessions",
        json={
            "name": "K-01",
            "project_id": proj["id"],
            "inputs": {
                "section_meta": {"section_no": "K-01", "start_kp": "0+000", "end_kp": "1+000"},
                "section_profile": {
                    "smys_mpa": 450.0,
                    "highest_elevation_m": 100.0,
                    "lowest_elevation_m": 100.0,
                    "start_elevation_m": 100.0,
                    "end_elevation_m": 100.0,
                },
                "field": {"monitored_pressure_bar": 135.0},
                "segments": [
                    {
                        "outside_diameter_mm": 406.4,
                        "wall_thickness_mm": 8.74,
                        "length_m": 500.0,
                        "smys_mpa": 450.0,
                        "material_grade": "API 5L X65",
                    },
                    {
                        "outside_diameter_mm": 406.4,
                        "wall_thickness_mm": 8.74,
                        "length_m": 500.0,
                        "smys_mpa": 290.0,
                        "material_grade": "API 5L X42",
                    },
                ],
                "profile_points": [
                    {"station_m": 0.0, "elevation_m": 100.0},
                    {"station_m": 1000.0, "elevation_m": 100.0},
                ],
            },
        },
        headers=headers,
    )
    assert sess.status_code == 201, sess.text
    scene = client.get(f"/api/projects/{proj['id']}/scene", headers=headers).json()
    assert len(scene["segments"]) >= 2
    first_half = next(s for s in scene["segments"] if s["end_m"] <= 500.5)
    second_half = next(s for s in scene["segments"] if s["start_m"] >= 499.5)
    assert first_half["smys_mpa"] == 450.0
    assert second_half["smys_mpa"] == 290.0
    assert second_half["grade"] == "API 5L X42"
    assert second_half["utilization"] > 0.9
    assert first_half["utilization"] < 0.75


def test_slice3_cad_48in_mainline_od_project_name_and_elevasyon_profile():
    import pytest
    from app.services import dossier as dossier_service
    from app.services.plan_profile import _extract_pipe_meta, parse_plan_profile_text

    cad_text = "\n".join(
        [
            "Plan Profil",
            "BORU HATTI GÜZERGAHI VE SOME NOKTASI",
            "ET KALINLIĞI",
            "14.3 mm",
            "ÖLÇÜLERİ : 10''",
            'DIAMETER PIPELINE (< 16") OPEN CUT',
            'DIAMETER PIPELINE (> 16") OPEN CUT',
            'TYPICAL DRAWING FAULT CROSSING 48" GAS PIPELINE',
            '( Ø 48" )',
            "BATI KARADENİZ DOĞAL GAZ BORU HATTI FAZ-2 ETÜT VE MÜHENDİSLİK İŞİ",
        ]
    )
    pipe_meta = _extract_pipe_meta(cad_text)
    project_name = dossier_service.extract_project_name_from_text(cad_text, max_lines=None)
    assert pipe_meta["outside_diameter_mm"] == pytest.approx(1219.2)
    assert pipe_meta["wall_thickness_mm"] == pytest.approx(14.3)
    assert project_name == "BATI KARADENİZ DOĞAL GAZ BORU HATTI FAZ-2 ETÜT VE MÜHENDİSLİK İŞİ"

    elev_text = "\n".join(
        [
            "12'' HİZAN İLÇESİ DGBH 4. BÖLÜM ELEVASYON (MAX KOT FARKI: 188. 816MT)",
            "İNDİRGENMİŞ KOT  KM  SAHA ALIM KODU",
            "1973.699 9650.080 1999.699",
            "1910.250 10120.500 1936.250",
            "1784.883 10973.420 1810.883",
        ]
    )
    res = parse_plan_profile_text(elev_text, file_name="ELEVASYON.pdf")
    assert res["pipe_meta"]["outside_diameter_mm"] == pytest.approx(323.9)
    assert len(res["draft_sections"]) == 1
    sec = res["draft_sections"][0]
    assert sec["section_no"] == "BÖLÜM 4"
    assert sec["start_m"] == pytest.approx(9650.08, abs=0.2)
    assert sec["end_m"] == pytest.approx(10973.42, abs=0.2)
    assert sec["start_elevation_m"] == pytest.approx(1973.7, abs=0.2)
    assert sec["lowest_elevation_m"] == pytest.approx(1784.9, abs=0.2)


def test_prune_stale_demo_projects_soft_deletes_only_expired_demos(tmp_path):
    from datetime import timedelta

    from app import db
    from app.core import security
    from app.core.config import Settings
    from app.core.timeutil import utcnow
    from app.models import Project
    from app.services import db_admin

    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'demo_ttl.db').as_posix()}",
        data_dir=tmp_path / "data",
        frontend_dist=tmp_path / "dist",
    )
    db.dispose_database()
    db.configure_database(settings.database_url)
    db.init_db()
    ws_hash = security.workspace_hash("demo-ttl-ws")
    old_ts = utcnow() - timedelta(days=10)
    fresh_ts = utcnow() - timedelta(days=1)

    try:
        with db.session_scope() as s:
            s.add_all(
                [
                    Project(
                        id="p-old-demo",
                        workspace_id_hash=ws_hash,
                        code="DEMO-OLD",
                        name="Old Demo",
                        created_at=old_ts,
                        updated_at=old_ts,
                    ),
                    Project(
                        id="p-fresh-demo",
                        workspace_id_hash=ws_hash,
                        code="DEMO-FRESH",
                        name="Fresh Demo",
                        created_at=fresh_ts,
                        updated_at=fresh_ts,
                    ),
                    Project(
                        id="p-old-prod",
                        workspace_id_hash=ws_hash,
                        code="PRJ-48",
                        name="Production Line",
                        created_at=old_ts,
                        updated_at=old_ts,
                    ),
                ]
            )
            s.commit()

            pruned = db_admin.prune_stale_demo_projects(s, max_age_days=7)
            assert pruned == 1
            assert s.get(Project, "p-old-demo").deleted_at is not None
            assert s.get(Project, "p-fresh-demo").deleted_at is None
            assert s.get(Project, "p-old-prod").deleted_at is None
    finally:
        db.dispose_database()


def test_rdp_thin_points_preserves_peaks_valleys_and_project_section_meta(client, headers):
    from app.services.scene import _thin_points

    # 120 noktalı profil: keskin bir tepe (420 m) ve vadi (95 m) içeren veri
    pts = [(float(i * 100), 200.0) for i in range(120)]
    pts[37] = (3700.0, 420.0)
    pts[82] = (8200.0, 95.0)
    pts[60] = (6000.0, 260.0)

    thinned = _thin_points(pts, 12, required_xs={6000.0})
    assert len(thinned) <= 12
    assert thinned[0] == pts[0]
    assert thinned[-1] == pts[-1]
    assert (3700.0, 420.0) in thinned
    assert (8200.0, 95.0) in thinned
    assert (6000.0, 260.0) in thinned

    # build_project_scene sections_summary zenginleştirilmiş alanları döndürmeli
    proj = client.post("/api/projects", json={"name": "RDP Özet Hat"}, headers=headers).json()
    _create_session(
        client,
        headers,
        name="K-01",
        project_id=proj["id"],
        inputs={
            "section_meta": {"section_no": "K-01", "start_kp": "0+000", "end_kp": "2+000"},
            "geometry": {
                "outside_diameter_mm": 406.4,
                "wall_thickness_mm": 8.74,
                "length_m": 2000.0,
            },
            "profile_points": [
                {"station_m": 0.0, "elevation_m": 120.0},
                {"station_m": 900.0, "elevation_m": 290.0},
                {"station_m": 1600.0, "elevation_m": 85.0},
                {"station_m": 2000.0, "elevation_m": 150.0},
            ],
        },
    )
    scene = client.get(f"/api/projects/{proj['id']}/scene", headers=headers).json()
    assert len(scene["sections"]) == 1
    sec = scene["sections"][0]
    assert sec["od_mm"] == 406.4
    assert sec["wt_mm"] == 8.74
    assert sec["min_elevation_m"] == 85.0
    assert sec["max_elevation_m"] == 290.0
    assert sec["start_elevation_m"] == 120.0
    assert sec["end_elevation_m"] == 150.0


def test_filter_cad_vertical_spikes_removes_isolated_needles_and_keeps_real_peaks():
    from app.services.plan_profile import _filter_cad_vertical_spikes

    pts = [
        (0.0, 1891.5),
        (5000.0, 1878.0),
        (7500.0, 2441.9),  # izole CAD çerçeve sıçraması (+550 m tek nokta)
        (10000.0, 1896.4),
        (33500.0, 2404.7),
        (33829.0, 2441.9),  # gerçek sürekli dağ zirvesi
        (34000.0, 2420.6),
    ]
    filtered = _filter_cad_vertical_spikes(pts)
    assert (7500.0, 2441.9) not in filtered
    assert (33829.0, 2441.9) in filtered
