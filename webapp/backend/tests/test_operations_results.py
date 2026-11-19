"""Spec 14.1-14.3 / 16 / 17 results persisted to sessions, summaries and reports."""

from __future__ import annotations

from conftest import create_session, full_inputs

RAMP_PAYLOAD = {
    "readings": [
        {"elapsed_min": 0, "pressure_bar": 95.0, "cumulative_added_volume_m3": 10.0},
        {"elapsed_min": 30, "pressure_bar": 97.0, "cumulative_added_volume_m3": 11.0},
        {"elapsed_min": 60, "pressure_bar": 98.0, "cumulative_added_volume_m3": 12.5},
    ],
    "test_pressure_100_smys_bar": 100.0,
    "total_filled_volume_m3": 1000.0,
}
HOLD_PAYLOAD = {
    "readings": [
        {"elapsed_min": t, "pressure_bar": 100.0, "temperature_c": 12.0} for t in range(0, 121, 15)
    ],
    "target_pressure_bar": 100.0,
}
DEPRESSURIZATION_PAYLOAD = {
    "test_passed": True,
    "release_valve_diameter_in": 2,
    "pipe_equipment_checked": True,
    "environmental_impact_checked": True,
}
DISCHARGE_PAYLOAD = {
    "destination": "other_section",
    "used_discharge_pig": True,
    "hydraulic_load_measures_taken": True,
    "report_date": "2026-11-19",
    "report_time": "14:30",
    "pig_name": "PIG-07",
    "discharge_location": "KP 12+300",
    "duration_min": 95,
}


def test_operation_results_are_recomputed_and_summarised(client):
    session = create_session(client, inputs=full_inputs())
    expected = {
        "pressurization_ramp": (RAMP_PAYLOAD, "BASARISIZ"),
        "pressure_hold": (HOLD_PAYLOAD, "BASARILI"),
        "depressurization": (DEPRESSURIZATION_PAYLOAD, "BASARILI"),
        "discharge": (DISCHARGE_PAYLOAD, "BASARILI"),
    }
    for test_type, (payload, status) in expected.items():
        response = client.post(
            f"/api/sessions/{session['id']}/results",
            json={"test_type": test_type, "payload": payload},
        )
        assert response.status_code == 201, response.text
        assert response.json()["decision"]["status"] == status

    summary = client.get(f"/api/sessions/{session['id']}/summary").json()
    for test_type, (_payload, status) in expected.items():
        assert summary["tests"][test_type] == {"status": status, "count": 1}


def test_invalid_operation_payload_is_rejected(client):
    session = create_session(client, inputs=full_inputs())
    response = client.post(
        f"/api/sessions/{session['id']}/results",
        json={"test_type": "discharge", "payload": {"destination": "ocean"}},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "domain_validation_error"


def test_operation_results_appear_in_text_report(client):
    session = create_session(client, inputs=full_inputs())
    client.post(
        f"/api/sessions/{session['id']}/results",
        json={"test_type": "depressurization", "payload": DEPRESSURIZATION_PAYLOAD},
    )
    response = client.get(
        f"/api/sessions/{session['id']}/export", params={"format": "txt", "preview": True}
    )
    assert response.status_code == 200
    text = response.text
    assert "Basinc Dusurme" in text or "Basincin Dusurulmesi" in text


def test_operation_results_sync_into_dewatering_form_without_bumping_revision(client):
    session = create_session(client, inputs=full_inputs())
    initial_revision = session["revision"]

    dep_res = client.post(
        f"/api/sessions/{session['id']}/results",
        json={"test_type": "depressurization", "payload": DEPRESSURIZATION_PAYLOAD},
    )
    assert dep_res.status_code == 201
    assert dep_res.json()["session_revision"] == initial_revision

    dis_res = client.post(
        f"/api/sessions/{session['id']}/results",
        json={"test_type": "discharge", "payload": DISCHARGE_PAYLOAD},
    )
    assert dis_res.status_code == 201
    assert dis_res.json()["session_revision"] == initial_revision

    forms_resp = client.get(f"/api/sessions/{session['id']}/forms")
    assert forms_resp.status_code == 200
    forms_payload = forms_resp.json()
    dewatering = next(f for f in forms_payload["forms"] if f["form_code"] == "dewatering")
    assert dewatering["status"] == "passed"
    assert dewatering["form_date"] == DISCHARGE_PAYLOAD["report_date"]
    assert dewatering["extracted_data"]["pig_runs"][0]["pig_type"] == DISCHARGE_PAYLOAD["pig_name"]
    assert (
        dewatering["extracted_data"]["pig_runs"][0]["launch_time"]
        == DISCHARGE_PAYLOAD["report_time"]
    )

    findings_by_code = {f["code"]: f for f in dewatering["findings"]}
    assert findings_by_code["dw_depressurization"]["status"] == "passed"
    assert findings_by_code["dw_discharge"]["status"] == "passed"

    checkpoint = next(
        cp for cp in forms_payload["checkpoints"] if cp["key"] == "depressurize_discharge"
    )
    assert checkpoint["status"] == "passed"
    assert checkpoint["checked"] is True


def test_dewatering_form_update_evaluates_spec_16_17_and_persists_results(client):
    session = create_session(client, inputs=full_inputs())
    put_resp = client.put(
        f"/api/sessions/{session['id']}/forms/dewatering",
        json={
            "form_date": "2026-11-19",
            "extracted_data": {
                "pig_runs": [
                    {
                        "pig_type": "Bi-Di Boşaltma Pigi",
                        "launch_time": "08:00",
                        "receive_time": "09:40",
                        "duration_min": 100,
                        "note": "KP 12+300",
                    }
                ],
                "depressurization": DEPRESSURIZATION_PAYLOAD,
                "discharge": {
                    "destination": "other_section",
                    "hydraulic_load_measures_taken": True,
                    "discharge_location": "KP 12+300",
                },
            },
        },
    )
    assert put_resp.status_code == 200, put_resp.text
    form = put_resp.json()["form"]
    assert form["status"] == "passed"
    findings_by_code = {f["code"]: f for f in form["findings"]}
    assert findings_by_code["dw_depressurization"]["status"] == "passed"
    assert findings_by_code["dw_discharge"]["status"] == "passed"

    summary = client.get(f"/api/sessions/{session['id']}/summary").json()
    assert summary["tests"]["depressurization"] == {"status": "BASARILI", "count": 1}
    assert summary["tests"]["discharge"] == {"status": "BASARILI", "count": 1}

    txt = client.get(
        f"/api/sessions/{session['id']}/export", params={"format": "txt", "preview": True}
    ).text
    assert "Basincin Dusurulmesi" in txt or "Basinc Dusurme" in txt
    assert "Bosaltma" in txt


def test_dewatering_form_spec_16_17_violations_and_validation_errors(client):
    session = create_session(client, inputs=full_inputs())
    bad_resp = client.put(
        f"/api/sessions/{session['id']}/forms/dewatering",
        json={
            "form_date": "2026-11-19",
            "extracted_data": {
                "depressurization": {
                    "test_passed": True,
                    "release_valve_diameter_in": 3.0,
                    "pipe_equipment_checked": True,
                    "environmental_impact_checked": True,
                },
                "discharge": {
                    "destination": "watercourse",
                    "used_discharge_pig": False,
                    "hydraulic_load_measures_taken": True,
                },
            },
        },
    )
    assert bad_resp.status_code == 200, bad_resp.text
    body = bad_resp.json()
    assert body["form"]["status"] == "failed"
    findings_by_code = {f["code"]: f for f in body["form"]["findings"]}
    assert findings_by_code["dw_depressurization"]["status"] == "failed"
    assert findings_by_code["dw_discharge"]["status"] == "failed"
    checkpoint = next(
        cp for cp in body["forms_payload"]["checkpoints"] if cp["key"] == "depressurize_discharge"
    )
    assert checkpoint["status"] == "failed"

    invalid_resp = client.put(
        f"/api/sessions/{session['id']}/forms/dewatering",
        json={
            "extracted_data": {
                "depressurization": {
                    "test_passed": True,
                    "release_valve_diameter_in": 0,
                }
            }
        },
    )
    assert invalid_resp.status_code == 200, invalid_resp.text
    invalid_findings = {f["code"]: f for f in invalid_resp.json()["form"]["findings"]}
    assert invalid_findings["dw_depressurization"]["status"] == "failed"
    assert "Vana capi" in invalid_findings["dw_depressurization"]["message"]


def test_dewatering_form_pig_only_keeps_backward_compatibility(client):
    session = create_session(client, inputs=full_inputs())
    resp = client.put(
        f"/api/sessions/{session['id']}/forms/dewatering",
        json={
            "form_date": "2026-11-19",
            "extracted_data": {
                "pig_runs": [
                    {
                        "pig_type": "Boşaltma Pigi",
                        "launch_time": "09:00",
                        "receive_time": "10:40",
                        "duration_min": 100,
                    }
                ]
            },
        },
    )
    assert resp.status_code == 200, resp.text
    finding_codes = {f["code"] for f in resp.json()["form"]["findings"]}
    assert "dw_depressurization" not in finding_codes
    assert "dw_discharge" not in finding_codes


def test_classify_form_text_recognizes_cdb_024_dewatering_alias():
    from app.services.dossier import classify_form_text

    spec = classify_form_text("BOT-FRM-CDB-001-024\nTest Bolum No : BOLUM 1")
    assert spec is not None
    assert spec.code == "dewatering"
