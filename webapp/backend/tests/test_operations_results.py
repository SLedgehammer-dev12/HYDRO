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
