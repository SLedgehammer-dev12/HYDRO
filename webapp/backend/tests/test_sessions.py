"""Session, result, time-series, scene, snapshot and export tests."""

from __future__ import annotations

import json

from conftest import (
    air_payload,
    create_session,
    full_inputs,
    pressure_payload,
    profile_payload,
)


def test_session_crud_and_etag(client):
    created = client.post("/api/sessions", json={"name": "Bolum 12"})
    assert created.status_code == 201
    session = created.json()
    assert session["name"] == "Bolum 12"
    assert session["status"] == "draft"
    assert session["revision"] == 1
    assert session["inputs"]["schema_version"] == 1
    assert created.headers["Location"] == f"/api/sessions/{session['id']}"

    fetched = client.get(f"/api/sessions/{session['id']}")
    assert fetched.status_code == 200
    assert fetched.headers["ETag"] == '"1"'

    updated = client.put(
        f"/api/sessions/{session['id']}",
        json={"name": "Bolum 13", "status": "active"},
        headers={"If-Match": '"1"'},
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["name"] == "Bolum 13"
    assert body["status"] == "active"
    assert body["revision"] == 2
    assert updated.headers["ETag"] == '"2"'

    conflict = client.put(
        f"/api/sessions/{session['id']}",
        json={"name": "Stale"},
        headers={"If-Match": '"1"'},
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "revision_conflict"
    assert conflict.json()["details"]["current"]["name"] == "Bolum 13"

    listed = client.get("/api/sessions").json()
    assert listed["total"] == 1
    assert listed["items"][0]["name"] == "Bolum 13"

    duplicate = client.post(f"/api/sessions/{session['id']}/duplicate", json={})
    assert duplicate.status_code == 201
    assert duplicate.json()["name"] == "Bolum 13 (kopya)"
    assert duplicate.json()["status"] == "draft"
    assert duplicate.json()["revision"] == 1

    deleted = client.delete(f"/api/sessions/{session['id']}")
    assert deleted.status_code == 204
    assert client.get(f"/api/sessions/{session['id']}").status_code == 404
    assert client.get("/api/sessions").json()["total"] == 1
    with_deleted = client.get("/api/sessions", params={"include_deleted": True}).json()
    assert with_deleted["total"] == 2


def test_session_default_name_and_partial_inputs(client):
    first = client.post("/api/sessions", json={}).json()
    assert first["name"] == "Oturum 1"
    assert first["inputs"]["geometry"]["outside_diameter_mm"] is None
    second = client.post("/api/sessions", json={}).json()
    assert second["name"] == "Oturum 2"


def test_session_inputs_deep_merge_and_null_clear(client):
    session = create_session(client, inputs=full_inputs())
    revision = session["revision"]
    response = client.put(
        f"/api/sessions/{session['id']}",
        json={
            "inputs": {
                "air": {"actual_added_water_m3": 0.0078},
                "geometry": {"length_m": 5000.0},
                "field": {"pig_distance_m": None},
            }
        },
        headers={"If-Match": f'"{revision}"'},
    )
    assert response.status_code == 200
    inputs = response.json()["inputs"]
    assert inputs["air"]["actual_added_water_m3"] == 0.0078
    assert inputs["air"]["temperature_c"] == 20.0
    assert inputs["geometry"]["length_m"] == 5000.0
    assert inputs["geometry"]["outside_diameter_mm"] == 406.4
    assert inputs["field"]["pig_distance_m"] is None


def test_workspace_isolation(client):
    session = create_session(client)
    other = client.get(
        f"/api/sessions/{session['id']}", headers={"X-Session-ID": "other-workspace"}
    )
    assert other.status_code == 404
    other_list = client.get("/api/sessions", headers={"X-Session-ID": "other-workspace"}).json()
    assert other_list["total"] == 0


def test_result_is_recomputed_not_trusted(client):
    session = create_session(client, inputs=full_inputs())
    payload = air_payload()
    payload["passed"] = False  # client-supplied display value must be ignored
    payload["theoretical_added_water_m3"] = 999.0
    response = client.post(
        f"/api/sessions/{session['id']}/results",
        json={"test_type": "air", "payload": payload},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["test_type"] == "air"
    assert body["result"]["passed"] is True
    assert body["result"]["theoretical_added_water_m3"] != 999.0
    assert body["decision"]["status"] == "BASARILI"
    assert body["session_revision"] >= 1

    listed = client.get(
        f"/api/sessions/{session['id']}/results", params={"test_type": "air"}
    ).json()
    assert listed["total"] == 1
    assert listed["items"][0]["inputs"]["session_snapshot"]["air"]["pressure_bar"] == 112.0

    detail = client.get(f"/api/sessions/{session['id']}").json()
    assert detail["status"] == "active"
    assert detail["result_summary"]["air"]["status"] == "BASARILI"

    summary = client.get(f"/api/sessions/{session['id']}/summary").json()
    assert summary["tests"]["air"] == {"status": "BASARILI", "count": 1}
    assert summary["checklist"] == {"checked": 2, "total": 11, "progress": 2 / 11}
    assert summary["profile"]["feasible"] is True
    assert summary["scene"]["segment_count"] == 1


def test_result_types(client):
    session = create_session(client, inputs=full_inputs())
    cases = [
        ("pressure", pressure_payload()),
        ("profile", profile_payload()),
        (
            "pig",
            {"mode": "Temizlik pigi", "distance_m": 5000.0, "travel_time_min": 45.0},
        ),
        (
            "pressurization",
            {
                "initial_volume_m3": 10.0,
                "added_volume_m3": 0.5,
                "theoretical_volume_m3": 10.48,
                "pressure_bar": 80.05,
                "expected_pressure_bar": 80.0,
            },
        ),
        (
            "thermal_balance",
            {
                "records": [
                    {
                        "timestamp": "2026-11-14T08:00:00Z",
                        "pressure_bar": 80.0,
                        "temperature_c": 18.2,
                    },
                    {
                        "timestamp": "2026-11-15T12:00:00Z",
                        "pressure_bar": 80.0,
                        "temperature_c": 18.1,
                    },
                ]
            },
        ),
        ("coefficient_a", {"temperature_c": 20.0, "pressure_bar": 80.0, "backend": "table_v1"}),
        ("coefficient_b", {"temperature_c": 20.0, "pressure_bar": 80.0}),
    ]
    for test_type, payload in cases:
        response = client.post(
            f"/api/sessions/{session['id']}/results",
            json={"test_type": test_type, "payload": payload},
        )
        assert response.status_code == 201, (test_type, response.text)
        assert response.json()["decision"]["status"] in {
            "BASARILI",
            "BASARISIZ",
            "DOGRULANAMADI",
            "BEKLIYOR",
            "KATSAYI GUNCELLENMELI",
        }


def test_time_series_crud_and_summary(client):
    session = create_session(client)
    records = [
        ("2026-11-14T06:00:00Z", 80.0, 18.0),
        ("2026-11-15T08:00:00Z", 80.1, 18.2),
        ("2026-11-15T12:00:00Z", 80.1, 18.25),
    ]
    ids = []
    for timestamp, pressure, temperature in records:
        response = client.post(
            f"/api/sessions/{session['id']}/time-series",
            json={
                "timestamp": timestamp,
                "pressure_bar": pressure,
                "temperature_c": temperature,
                "volume_m3": 10.4,
                "notes": "Manuel kayit",
            },
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["record"]["source"] == "manual"
        assert body["summary"]["record_count"] >= 1
        ids.append(body["record"]["id"])

    listed = client.get(f"/api/sessions/{session['id']}/time-series").json()
    assert listed["total"] == 3
    assert listed["items"][0]["timestamp"].endswith("Z")

    filtered = client.get(
        f"/api/sessions/{session['id']}/time-series",
        params={"from": "2026-11-15T00:00:00Z"},
    ).json()
    assert filtered["total"] == 2

    summary = client.get(f"/api/sessions/{session['id']}/time-series/summary").json()
    assert summary["record_count"] == 3
    assert summary["duration_hours"] == 30.0
    assert summary["balanced"] in {True, False}
    assert summary["average_temperature_c"] is not None
    assert summary["first_timestamp"].startswith("2026-11-14")

    deleted = client.delete(f"/api/sessions/{session['id']}/time-series/{ids[0]}")
    assert deleted.status_code == 204
    assert client.get(f"/api/sessions/{session['id']}/time-series").json()["total"] == 2
    assert (
        client.delete(f"/api/sessions/{session['id']}/time-series/does-not-exist").status_code
        == 404
    )


def test_scene_contract(client):
    session = create_session(client, inputs=full_inputs())
    response = client.get(f"/api/sessions/{session['id']}/scene")
    assert response.status_code == 200
    scene = response.json()
    assert scene["schema_version"] == 1
    assert scene["extent"]["station_end_m"] == 12000.0
    assert scene["extent"]["bounding_radius_m"] == 6000.0
    assert len(scene["segments"]) == 1
    segment = scene["segments"][0]
    assert segment["index"] == 1
    assert segment["nps_label"].startswith("NPS 16")
    assert segment["od_mm"] == 406.4
    assert segment["wt_mm"] == 8.74
    assert segment["pressure_at_100_smys_bar"] > 0
    assert segment["pressure_bar"] is not None
    assert segment["utilization"] is not None
    assert segment["status"] in {"ok", "warning", "critical", "unknown"}
    assert scene["equipment"]["pump"]["side"] == "start"
    assert scene["equipment"]["test_head"]["station_m"] == 1.0
    assert scene["equipment"]["pig"]["speed_m_per_s"] > 0
    assert scene["ranges"]["pressure_bar"]["min"] <= scene["ranges"]["pressure_bar"]["max"]
    assert "yaklasik" in " ".join(scene["warnings"]).lower()
    assert scene["totals"]["internal_volume_m3"] > 0


def test_scene_requires_geometry(client):
    session = create_session(client)
    response = client.get(f"/api/sessions/{session['id']}/scene")
    assert response.status_code == 422
    assert response.json()["code"] == "incomplete_geometry"
    assert response.json()["details"]["missing"]


def test_scene_segments_chain_and_profile_points(client):
    inputs = full_inputs(
        segments=[
            {
                "outside_diameter_mm": 406.4,
                "wall_thickness_mm": 8.74,
                "length_m": 1000.0,
                "nps_label": "NPS 16",
                "schedule_label": "Sch 20",
            },
            {
                "outside_diameter_mm": 323.9,
                "wall_thickness_mm": 6.35,
                "length_m": 500.0,
                "nps_label": "NPS 12",
                "schedule_label": "Sch 20",
            },
        ],
        profile_points=[
            {"station_m": 0.0, "elevation_m": 200.0},
            {"station_m": 700.0, "elevation_m": 260.0},
            {"station_m": 1500.0, "elevation_m": 210.0},
        ],
    )
    session = create_session(client, inputs=inputs)
    scene = client.get(f"/api/sessions/{session['id']}/scene").json()
    assert len(scene["segments"]) == 2
    assert scene["segments"][0]["station_end_m"] == 1000.0
    assert scene["segments"][1]["station_start_m"] == 1000.0
    assert scene["segments"][1]["station_end_m"] == 1500.0
    assert scene["approximate_profile"] is False
    assert len(scene["profile_points"]) == 3
    assert len(scene["equipment"]["valves"]) == 3


def test_audit_events(client):
    session = create_session(client, inputs=full_inputs())
    client.post(
        f"/api/sessions/{session['id']}/results",
        json={"test_type": "air", "payload": air_payload()},
    )
    body = client.get(f"/api/sessions/{session['id']}/audit").json()
    actions = {item["action"] for item in body["items"]}
    assert "session.create" in actions
    assert "result.create" in actions
    assert all(item["actor"].startswith("anonymous:") for item in body["items"])
    filtered = client.get(
        f"/api/sessions/{session['id']}/audit", params={"action": "result.create"}
    ).json()
    assert filtered["total"] == 1


def test_export_preview_and_files(client):
    session = create_session(client, inputs=full_inputs())
    client.post(
        f"/api/sessions/{session['id']}/results",
        json={"test_type": "air", "payload": air_payload()},
    )

    preview = client.get(
        f"/api/sessions/{session['id']}/export",
        params={"format": "txt", "preview": True},
    )
    assert preview.status_code == 200
    content = preview.json()["content"]
    assert "Hidrostatik Test Degerlendirme Raporu" in content
    assert "Nihai Karar" in content
    assert "Hava Icerik Testi durumu: BASARILI" in content
    assert "[X]" in content

    expected = {
        "txt": "text/plain; charset=utf-8",
        "pdf": "application/pdf",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    for fmt, content_type in expected.items():
        response = client.get(f"/api/sessions/{session['id']}/export", params={"format": fmt})
        assert response.status_code == 200, (fmt, response.text)
        assert response.headers["content-type"].startswith(content_type)
        assert len(response.content) > 100
        assert "attachment" in response.headers["content-disposition"]

    bad = client.get(f"/api/sessions/{session['id']}/export", params={"format": "doc"})
    assert bad.status_code == 422
    assert bad.json()["code"] == "validation_error"


def test_snapshot_roundtrip(client):
    original = create_session(client, name="Kaynak", inputs=full_inputs())
    snapshot_response = client.get(f"/api/sessions/{original['id']}/snapshot")
    assert snapshot_response.status_code == 200
    assert "attachment" in snapshot_response.headers["content-disposition"]
    snapshot = snapshot_response.json()
    assert snapshot["schema_version"] == 1
    assert snapshot["geometry"] == {
        "outside_diameter_mm": "406.4",
        "wall_thickness_mm": "8.74",
        "length_m": "12000",
    }
    assert snapshot["modes"]["air_a_mode"] == "Otomatik"
    assert snapshot["modes"]["pressure_b_source"] == "Kurum ici tablo (varsayilan)"
    assert snapshot["air"]["pressure_rise_bar"] == "1"

    target = create_session(client, name="Hedef")
    applied = client.post(
        f"/api/sessions/{target['id']}/snapshot",
        json={"snapshot": snapshot, "mode": "replace"},
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["id"] == target["id"]
    assert applied.json()["inputs"]["geometry"]["length_m"] == 12000.0
    mapping = applied.json()["mapping"]
    assert mapping["converted"] > 20
    assert mapping["invalid_fields"] == []

    target_inputs = client.get(f"/api/sessions/{target['id']}").json()["inputs"]
    assert target_inputs["geometry"]["outside_diameter_mm"] == 406.4
    assert target_inputs["geometry"]["length_m"] == 12000.0
    assert target_inputs["section_profile"]["smys_mpa"] == 450.0
    assert target_inputs["air"]["actual_added_water_m3"] == 0.00775
    assert target_inputs["pressure"]["b_micro_per_c"] == 188.661
    assert target_inputs["modes"]["air_a_mode"] == "auto"
    assert target_inputs["modes"]["pressure_b_source"] == "institutional"
    assert target_inputs["modes"]["steel_model"] == "volumetric"
    assert target_inputs["checks"]["ambient_temp"] is True

    again = client.get(f"/api/sessions/{target['id']}/snapshot").json()
    assert again["geometry"] == snapshot["geometry"]
    assert again["air"] == snapshot["air"]
    assert again["pressure"] == snapshot["pressure"]
    assert again["modes"] == snapshot["modes"]


def test_snapshot_merge_preserves_existing(client):
    target = create_session(client, inputs=full_inputs())
    applied = client.post(
        f"/api/sessions/{target['id']}/snapshot",
        json={
            "snapshot": {
                "schema_version": 1,
                "air": {"actual_added_water_m3": "0.008"},
                "geometry": {"length_m": ""},
                "field": {"pig_speed_m_per_s": "1.851852"},
            },
            "mode": "merge",
        },
    )
    assert applied.status_code == 200
    body = applied.json()
    assert body["mapping"]["skipped"] == ["field.pig_speed_m_per_s"]
    inputs = body["session"]["inputs"]
    assert inputs["air"]["actual_added_water_m3"] == 0.008
    assert inputs["geometry"]["length_m"] == 12000.0


def test_snapshot_invalid_schema(client):
    target = create_session(client)
    response = client.post(
        f"/api/sessions/{target['id']}/snapshot",
        json={"snapshot": {"schema_version": 99}, "mode": "merge"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "invalid_snapshot"


def test_import_desktop_snapshot(client):
    response = client.post(
        "/api/import/desktop-snapshot",
        json={
            "name": "Masaustu",
            "snapshot": {
                "schema_version": 1,
                "geometry": {
                    "outside_diameter_mm": "406.4",
                    "wall_thickness_mm": "8.74",
                    "length_m": "1000",
                },
                "air": {"actual_added_water_m3": "0,00775"},
                "modes": {"air_a_mode": "Otomatik"},
            },
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["session"]["name"] == "Masaustu"
    assert body["session"]["inputs"]["geometry"]["length_m"] == 1000.0
    # Turkish decimal comma is accepted by the shared parser.
    assert body["session"]["inputs"]["air"]["actual_added_water_m3"] == 0.00775


def test_stats(client):
    session = create_session(client, inputs=full_inputs())
    client.post(
        f"/api/sessions/{session['id']}/results",
        json={"test_type": "air", "payload": air_payload()},
    )
    client.post(
        f"/api/sessions/{session['id']}/time-series",
        json={
            "timestamp": "2026-11-15T12:00:00Z",
            "pressure_bar": 80.0,
            "temperature_c": 18.0,
        },
    )
    body = client.get("/api/stats").json()
    assert body["total_sessions"] == 1
    assert body["total_tests"] == 1
    assert body["time_series_records"] == 1
    assert body["by_status"]["BASARILI"] == 1
    assert body["by_type"]["air"] == 1
    assert "ocr" in body


def test_free_report_export(client):
    response = client.post(
        "/api/reports/export",
        json={
            "format": "pdf",
            "title": "Test Raporu",
            "metadata": {"Surum": "1.7.3"},
            "geometry_data": {"Dis cap": "406.40"},
            "test_results": {"Hava Karar": "BASARILI"},
            "checklist": [{"checked": True, "label": "Form", "ref": "21"}],
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.content.startswith(b"%PDF")

    empty = client.post(
        "/api/reports/export",
        json={"format": "txt", "title": "Bos"},
    )
    assert empty.status_code == 422
    assert empty.json()["code"] == "validation_error"


def test_json_snapshot_is_serialisable(client):
    session = create_session(client, inputs=full_inputs())
    snapshot = client.get(f"/api/sessions/{session['id']}/snapshot").json()
    text = json.dumps(snapshot, ensure_ascii=False)
    assert "NaN" not in text
    assert "Infinity" not in text


def test_scene_custom_equipment_and_approximate_warning(client):
    default_session = create_session(client, inputs=full_inputs())
    default_scene = client.get(f"/api/sessions/{default_session['id']}/scene").json()
    assert default_scene["is_custom_equipment"] is False
    assert any("ekipman" in w.lower() for w in default_scene["warnings"])

    inputs = full_inputs(
        geometry={"outside_diameter_mm": 406.4, "wall_thickness_mm": 8.74, "length_m": 1000.0},
        profile_points=[
            {"station_m": 0.0, "elevation_m": 100.0},
            {"station_m": 1000.0, "elevation_m": 200.0},
        ],
        equipment=[
            {"id": "eq-v1", "kind": "mainline", "label": "Giris Vanasi", "station_m": 0.0},
            {"id": "eq-p1", "type": "pump", "label": "Ana Pompa", "station_m": 100.0},
            {"id": "eq-h1", "type": "test-head", "label": "Test Basligi", "distance_m": 150.0},
            {"id": "eq-g1", "type": "gauge", "label": "Orta Olcer", "station_m": 500.0},
            {"id": "eq-blank", "type": "valve", "label": "   ", "station_m": 200.0},
        ],
    )
    updated = client.put(
        f"/api/sessions/{default_session['id']}",
        json={"inputs": inputs},
        headers={"If-Match": f'"{default_session["revision"]}"'},
    )
    assert updated.status_code == 200, updated.text
    assert len(updated.json()["inputs"]["equipment"]) == 5

    scene = client.get(f"/api/sessions/{default_session['id']}/scene").json()
    assert scene["approximate_profile"] is False
    assert scene["is_custom_equipment"] is True
    assert not any("ekipman" in w.lower() for w in scene["warnings"])
    custom = {item["id"]: item for item in scene["custom_equipment"]}
    assert "eq-blank" not in custom
    assert custom["eq-v1"]["type"] == "valve"
    assert custom["eq-h1"]["distance_m"] == 150.0
    assert custom["eq-g1"]["elevation_m"] == 150.0

    # A single distinct profile_point must still fall back to approximate_profile=True
    single_pt = client.put(
        f"/api/sessions/{default_session['id']}",
        json={"inputs": {"profile_points": [{"station_m": 100.0, "elevation_m": 150.0}]}},
        headers={"If-Match": f'"{updated.json()["revision"]}"'},
    )
    assert single_pt.status_code == 200, single_pt.text
    single_scene = client.get(f"/api/sessions/{default_session['id']}/scene").json()
    assert single_scene["approximate_profile"] is True


def test_ambient_temperature_symmetric_patch_clear_and_backend_case_insensitive(client):
    from app.services.snapshot import resolve_backend_key

    assert resolve_backend_key("Table Interpolation v1 (bicubic)") in (
        "table_v1_bicubic",
        None,
    )
    assert resolve_backend_key("  table interpolation v1 ") == "table_v1"

    sess = create_session(client, name="Ambient Mirror")
    p1 = client.put(
        f"/api/sessions/{sess['id']}",
        json={"inputs": {"air": {"ambient_temperature_c": 1.5}}},
        headers={"If-Match": f'"{sess["revision"]}"'},
    )
    assert p1.status_code == 200, p1.text
    assert p1.json()["inputs"]["air"]["ambient_temperature_c"] == 1.5
    assert p1.json()["inputs"]["field"]["ambient_temperature_c"] == 1.5

    p2 = client.put(
        f"/api/sessions/{sess['id']}",
        json={"inputs": {"field": {"ambient_temperature_c": 6.0}}},
        headers={"If-Match": f'"{p1.json()["revision"]}"'},
    )
    assert p2.status_code == 200, p2.text
    assert p2.json()["inputs"]["air"]["ambient_temperature_c"] == 6.0
    assert p2.json()["inputs"]["field"]["ambient_temperature_c"] == 6.0

    p3 = client.put(
        f"/api/sessions/{sess['id']}",
        json={"inputs": {"air": {"ambient_temperature_c": None}}},
        headers={"If-Match": f'"{p2.json()["revision"]}"'},
    )
    assert p3.status_code == 200, p3.text
    assert p3.json()["inputs"]["air"]["ambient_temperature_c"] is None
    assert p3.json()["inputs"]["field"]["ambient_temperature_c"] is None


def test_import_desktop_snapshot_with_project_and_mapping(client):
    project_res = client.post("/api/projects", json={"name": "Snapshot Projesi", "code": "SNP-01"})
    assert project_res.status_code == 201, project_res.text
    project_id = project_res.json()["id"]

    response = client.post(
        "/api/import/desktop-snapshot",
        json={
            "name": "Kesit JSON",
            "project_id": project_id,
            "snapshot": {
                "schema_version": 1,
                "water_backend_option": "Table Interpolation v1",
                "geometry": {
                    "outside_diameter_mm": "406.4",
                    "wall_thickness_mm": "8.74",
                    "length_m": "12000",
                },
                "pressure": {"derive_delta_t": True, "t_initial_c": "22", "t_final_c": "20"},
                "report": {
                    "report_no": "RPT-42",
                    "operator": "Muhendis",
                    "date": "2026-11-20",
                    "section_id": "K-09",
                },
                "field": {"pig_speed_m_per_s": "1.5"},
            },
        },
    )
    assert response.status_code == 201, response.text
    sess = response.json()["session"]
    mapping = response.json()["mapping"]

    assert response.headers["Location"] == f"/api/sessions/{sess['id']}"
    assert response.headers["ETag"] == f'"{sess["revision"]}"'
    assert sess["project_id"] == project_id
    assert sess["inputs"]["water_backend"] == "table_v1"
    assert sess["inputs"]["pressure"]["derive_delta_t"] is True
    assert sess["inputs"]["report"] == {
        "report_no": "RPT-42",
        "operator": "Muhendis",
        "date": "2026-11-20",
        "section_id": "K-09",
    }
    assert sess["inputs"]["section_meta"]["section_no"] == "K-09"
    # 1 water_backend + 3 geometry + 3 pressure (derive_delta_t, t_initial, t_final) + 4 report = 11 (no double-count)
    assert mapping["converted"] == 11
    assert mapping["skipped"] == ["field.pig_speed_m_per_s"]
    assert mapping["invalid_fields"] == []

    # Project association must initialize BOTAŞ form slots and audit trail
    forms = client.get(f"/api/sessions/{sess['id']}/forms")
    assert forms.status_code == 200
    assert len(forms.json()["forms"]) >= 11

    audit_items = client.get(f"/api/sessions/{sess['id']}/audit").json()["items"]
    assert any(item["action"] == "snapshot.import" for item in audit_items)

    missing_proj = client.post(
        "/api/import/desktop-snapshot",
        json={"project_id": "does-not-exist", "snapshot": {"schema_version": 1}},
    )
    assert missing_proj.status_code == 404

    other_ws = client.post(
        "/api/import/desktop-snapshot",
        headers={"X-Session-ID": "other-workspace"},
        json={"project_id": project_id, "snapshot": {"schema_version": 1}},
    )
    assert other_ws.status_code == 404


def test_optimistic_concurrency_409_diff_across_put_snapshot_and_results(client):
    session = create_session(client, name="Eszamanli Kesit", inputs=full_inputs())
    rev1 = session["revision"]

    # Client A updates to rev2
    client_a = client.put(
        f"/api/sessions/{session['id']}",
        json={
            "name": "Eszamanli Kesit A",
            "inputs": {
                "geometry": {"length_m": 15000.0},
                "air": {"actual_added_water_m3": 0.009},
            },
        },
        headers={"If-Match": f'"{rev1}"'},
    )
    assert client_a.status_code == 200
    rev2 = client_a.json()["revision"]
    assert rev2 == 2

    # Client B sends stale PUT with If-Match: "1" changing length_m and checks.air_content_limit
    client_b = client.put(
        f"/api/sessions/{session['id']}",
        json={
            "inputs": {
                "geometry": {"length_m": 18000.0},
                "checks": {"air_content_limit": True},
            }
        },
        headers={"If-Match": f'"{rev1}"'},
    )
    assert client_b.status_code == 409
    err_b = client_b.json()
    assert err_b["code"] == "revision_conflict"
    assert err_b["details"]["expected_revision"] == 1
    assert err_b["details"]["current_revision"] == 2
    assert err_b["details"]["current"]["name"] == "Eszamanli Kesit A"
    diff_by_path = {entry["path"]: entry for entry in err_b["details"]["diff"]}
    assert diff_by_path["geometry.length_m"] == {
        "path": "geometry.length_m",
        "incoming": 18000.0,
        "server": 15000.0,
    }
    assert diff_by_path["checks.air_content_limit"] == {
        "path": "checks.air_content_limit",
        "incoming": True,
        "server": False,
    }
    assert "air.actual_added_water_m3" not in diff_by_path

    # Stale snapshot upload also yields 409 + diff
    stale_snap = client.post(
        f"/api/sessions/{session['id']}/snapshot",
        json={
            "mode": "merge",
            "snapshot": {"schema_version": 1, "geometry": {"length_m": "20000"}},
        },
        headers={"If-Match": f'"{rev1}"'},
    )
    assert stale_snap.status_code == 409
    snap_diff = {e["path"]: e for e in stale_snap.json()["details"]["diff"]}
    assert snap_diff["geometry.length_m"]["incoming"] == 20000.0
    assert snap_diff["geometry.length_m"]["server"] == 15000.0

    # Retry snapshot upload with rev2 succeeds
    ok_snap = client.post(
        f"/api/sessions/{session['id']}/snapshot",
        json={
            "mode": "merge",
            "snapshot": {"schema_version": 1, "geometry": {"length_m": "20000"}},
        },
        headers={"If-Match": f'"{rev2}"'},
    )
    assert ok_snap.status_code == 200
    rev3 = ok_snap.json()["revision"]
    assert rev3 == 3

    # Stale result creation yields 409, and valid rev3 succeeds without bumping revision
    stale_res = client.post(
        f"/api/sessions/{session['id']}/results",
        json={"test_type": "air", "payload": air_payload()},
        headers={"If-Match": f'"{rev2}"'},
    )
    assert stale_res.status_code == 409
    assert stale_res.json()["details"]["current_revision"] == 3

    ok_res = client.post(
        f"/api/sessions/{session['id']}/results",
        json={"test_type": "air", "payload": air_payload()},
        headers={"If-Match": f'"{rev3}"'},
    )
    assert ok_res.status_code == 201
    assert ok_res.headers["ETag"] == '"3"'
    assert ok_res.json()["session_revision"] == 3


def test_snapshot_merge_ambient_diff_bool_segments_and_invalid_fields(client):
    # Project with defaults inherited by desktop snapshot import
    proj = client.post(
        "/api/projects",
        json={
            "name": "Varsayilanli Proje",
            "defaults": {"smys_mpa": 485.0, "material_grade": "API 5L X70"},
        },
    ).json()

    imported = client.post(
        "/api/import/desktop-snapshot",
        json={
            "name": "   ",
            "project_id": proj["id"],
            "snapshot": {
                "schema_version": 1,
                "air": {"temperature_c": True},
                "pressure": {"derive_delta_t": "maybe"},
                "geometry": {"outside_diameter_mm": "406.4", "wall_thickness_mm": "8.74"},
                "geometry_segments": [
                    {
                        "outside_diameter_mm": "406.4",
                        "wall_thickness_mm": "8.74",
                        "length_m": "",
                    },
                    {
                        "outside_diameter_mm": "406.4",
                        "wall_thickness_mm": "8.74",
                        "length_m": "5000",
                    },
                ],
                "field": {"ambient_temperature_c": "4.0"},
            },
        },
    )
    assert imported.status_code == 201, imported.text
    imp_body = imported.json()
    assert imp_body["session"]["inputs"]["section_profile"]["smys_mpa"] == 485.0
    assert imp_body["session"]["inputs"]["material_grade"] == "API 5L X70"
    assert imp_body["session"]["inputs"]["air"]["ambient_temperature_c"] == 4.0
    assert imp_body["session"]["inputs"]["field"]["ambient_temperature_c"] == 4.0
    # geometry (2) + valid segment (3) + field.ambient (1) = 6 (dropped partial segment NOT counted)
    assert imp_body["mapping"]["converted"] == 6
    assert "air.temperature_c" in imp_body["mapping"]["invalid_fields"]
    assert "pressure.derive_delta_t" in imp_body["mapping"]["invalid_fields"]
    assert "geometry_segments[0].length_m" in imp_body["mapping"]["invalid_fields"]

    # Whitespace-only project_id becomes None -> standalone session without 404
    standalone = client.post(
        "/api/import/desktop-snapshot",
        json={"project_id": "   ", "snapshot": {"schema_version": 1}},
    )
    assert standalone.status_code == 201
    assert standalone.json()["session"]["project_id"] is None

    # Merge snapshot updating ONLY field.ambient_temperature_c must update both mirrors & keep location_class
    sess_id = imp_body["session"]["id"]
    rev1 = imp_body["session"]["revision"]
    merged = client.post(
        f"/api/sessions/{sess_id}/snapshot",
        json={
            "mode": "merge",
            "snapshot": {
                "schema_version": 1,
                "location_class": "",
                "field": {"ambient_temperature_c": "1.2"},
            },
        },
        headers={"If-Match": f'"{rev1}"'},
    )
    assert merged.status_code == 200, merged.text
    merged_sess = merged.json()["session"]
    assert merged_sess["inputs"]["field"]["ambient_temperature_c"] == 1.2
    assert merged_sess["inputs"]["air"]["ambient_temperature_c"] == 1.2
    assert merged_sess["inputs"]["location_class"].startswith("Class 1")

    # Single-transaction audit record exists
    audits = client.get(
        f"/api/sessions/{sess_id}/audit", params={"action": "snapshot.apply"}
    ).json()
    assert audits["total"] == 1

    # Conflict PUT changing nothing on segments (start_station_m omitted vs None) produces NO segments diff
    stale_put = client.put(
        f"/api/sessions/{sess_id}",
        json={
            "inputs": {
                "field": {"ambient_temperature_c": "0"},
                "segments": [
                    {
                        "outside_diameter_mm": 406.4,
                        "wall_thickness_mm": 8.74,
                        "length_m": 5000.0,
                        "nps_label": "-",
                        "schedule_label": "Elle giris",
                        "start_station_m": None,
                    }
                ],
            }
        },
        headers={"If-Match": f'"{rev1}"'},
    )
    assert stale_put.status_code == 409
    diff_map = {e["path"]: e for e in stale_put.json()["details"]["diff"]}
    assert "segments" not in diff_map
    assert diff_map["field.ambient_temperature_c"] == {
        "path": "field.ambient_temperature_c",
        "incoming": 0.0,
        "server": 1.2,
    }

    # Mode=replace 409 diff
    stale_replace = client.post(
        f"/api/sessions/{sess_id}/snapshot",
        json={
            "mode": "replace",
            "snapshot": {"schema_version": 1, "material_grade": "API 5L X60"},
        },
        headers={"If-Match": f'"{rev1}"'},
    )
    assert stale_replace.status_code == 409
    rep_map = {e["path"]: e for e in stale_replace.json()["details"]["diff"]}
    assert rep_map["material_grade"]["incoming"] == "API 5L X60"


def test_session_per_segment_smys_scene_snapshot_conflict_and_txt_report(client):
    inputs = full_inputs(
        segments=[
            {
                "outside_diameter_mm": 406.4,
                "wall_thickness_mm": 8.74,
                "length_m": 1000.0,
                "nps_label": "NPS 16",
                "schedule_label": "Sch 20",
                "material_grade": "API 5L X65",
                "smys_mpa": 450.0,
            },
            {
                "outside_diameter_mm": 406.4,
                "wall_thickness_mm": 8.74,
                "length_m": 500.0,
                "nps_label": "NPS 16",
                "schedule_label": "Sch 20",
                "material_grade": "API 5L X42",
                "smys_mpa": 290.0,
            },
        ],
    )
    session = create_session(client, inputs=inputs)

    # 3D scene computes per-segment SMYS and utilization
    scene = client.get(f"/api/sessions/{session['id']}/scene").json()
    assert len(scene["segments"]) == 2
    assert scene["segments"][0]["smys_mpa"] == 450.0
    assert scene["segments"][0]["grade"] == "API 5L X65"
    assert scene["segments"][1]["smys_mpa"] == 290.0
    assert scene["segments"][1]["grade"] == "API 5L X42"
    assert scene["segments"][1]["utilization"] > scene["segments"][0]["utilization"]

    # Snapshot export & re-import round-trip preserves per-segment SMYS & grade
    snap = client.get(f"/api/sessions/{session['id']}/snapshot").json()
    assert snap["geometry_segments"][0]["smys_mpa"] == "450"
    assert snap["geometry_segments"][1]["smys_mpa"] == "290"
    assert snap["geometry_segments"][1]["material_grade"] == "API 5L X42"

    imported = client.post(
        "/api/import/desktop-snapshot",
        json={"snapshot": snap},
    )
    assert imported.status_code == 201, imported.text
    imp_segs = imported.json()["session"]["inputs"]["segments"]
    assert imp_segs[1]["smys_mpa"] == 290.0
    assert imp_segs[1]["material_grade"] == "API 5L X42"

    # Invalid segment smys_mpa in snapshot is recorded in invalid_fields
    bad_snap = client.post(
        "/api/import/desktop-snapshot",
        json={
            "snapshot": {
                "schema_version": 1,
                "geometry_segments": [
                    {
                        "outside_diameter_mm": "406.4",
                        "wall_thickness_mm": "8.74",
                        "length_m": "500",
                        "smys_mpa": "-100",
                    }
                ],
            }
        },
    )
    assert bad_snap.status_code == 201
    assert "geometry_segments[0].smys_mpa" in bad_snap.json()["mapping"]["invalid_fields"]

    # 409 diff detects per-segment SMYS change
    bump = client.put(
        f"/api/sessions/{session['id']}",
        json={"notes": "Rev 2"},
        headers={"If-Match": f'"{session["revision"]}"'},
    )
    assert bump.status_code == 200
    stale_seg = client.put(
        f"/api/sessions/{session['id']}",
        json={
            "inputs": {
                "segments": [
                    {
                        "outside_diameter_mm": 406.4,
                        "wall_thickness_mm": 8.74,
                        "length_m": 1000.0,
                        "nps_label": "NPS 16",
                        "schedule_label": "Sch 20",
                        "material_grade": "API 5L X65",
                        "smys_mpa": 450.0,
                    },
                    {
                        "outside_diameter_mm": 406.4,
                        "wall_thickness_mm": 8.74,
                        "length_m": 500.0,
                        "nps_label": "NPS 16",
                        "schedule_label": "Sch 20",
                        "material_grade": "API 5L X52",
                        "smys_mpa": 360.0,
                    },
                ]
            }
        },
        headers={"If-Match": f'"{session["revision"]}"'},
    )
    assert stale_seg.status_code == 409
    assert any(entry["path"] == "segments" for entry in stale_seg.json()["details"]["diff"])

    # TXT export renders per-segment SMYS and grade
    txt_res = client.get(
        f"/api/sessions/{session['id']}/export",
        params={"format": "txt", "preview": True},
    )
    assert txt_res.status_code == 200
    body = txt_res.json()
    txt = body["content"]
    assert "SMYS 290 MPa" in txt
    assert "API 5L X42" in txt
    assert "Segment SMYS araligi (MPa): 290 - 450" in txt

    # Non-string material_grade and bool section_profile.smys_mpa guards
    weird_snap = client.post(
        "/api/import/desktop-snapshot",
        json={
            "snapshot": {
                "schema_version": 1,
                "geometry_segments": [
                    {
                        "outside_diameter_mm": "406.4",
                        "wall_thickness_mm": "8.74",
                        "length_m": "500",
                        "material_grade": 123,
                    }
                ],
            }
        },
    )
    assert weird_snap.status_code == 201
    assert "geometry_segments[0].material_grade" in weird_snap.json()["mapping"]["invalid_fields"]

    # Segment with custom numeric SMYS & no grade does not inherit top-level material_grade in 3D scene
    custom_sess = create_session(
        client,
        inputs=full_inputs(
            material_grade="API 5L X65",
            section_profile={
                "smys_mpa": True,  # ignored as invalid bool by as_positive_float
                "highest_elevation_m": 100.0,
                "lowest_elevation_m": 100.0,
                "start_elevation_m": 100.0,
                "end_elevation_m": 100.0,
                "design_pressure_bar": 80.0,
            },
            segments=[
                {
                    "outside_diameter_mm": 406.4,
                    "wall_thickness_mm": 8.74,
                    "length_m": 500.0,
                    "smys_mpa": 305.0,
                    "material_grade": "",
                }
            ],
        ),
    )
    custom_scene = client.get(f"/api/sessions/{custom_sess['id']}/scene").json()
    assert custom_scene["segments"][0]["smys_mpa"] == 305.0
    assert custom_scene["segments"][0]["grade"] is None
