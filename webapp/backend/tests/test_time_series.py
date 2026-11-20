"""Backend tests for Section 12 & 15 time series, batch ops, Form 018/021 sync, and reports."""

from __future__ import annotations

import pytest
from conftest import create_session, full_inputs


def _hourly_records(hours: int = 24, *, p0: float = 85.0, t0: float = 16.0) -> list[dict]:
    records = []
    for hour in range(hours + 1):
        day = 14 + (hour // 24)
        hh = hour % 24
        temp = t0 + (0.25 if hour >= hours - 3 else 0.0)
        records.append(
            {
                "timestamp": f"2026-11-{day:02d}T{hh:02d}:00:00Z",
                "pressure_bar": round(p0 - hour * 0.01, 3),
                "temperature_c": round(temp, 3),
                "volume_m3": round(100.0 + hour * 0.05, 3),
                "notes": f"Saat {hour}",
            }
        )
    return records


def test_batch_replace_append_clear_and_enriched_summary(client):
    session = create_session(client, name="TS Session", inputs=full_inputs())
    sid = session["id"]

    # Append 25 hourly readings (0..24)
    res1 = client.post(
        f"/api/sessions/{sid}/time-series/batch",
        json={"records": _hourly_records(24), "mode": "append", "source": "excel"},
    )
    assert res1.status_code == 201, res1.text
    body1 = res1.json()
    assert body1["inserted"] == 25
    assert body1["total"] == 25
    assert body1["items"][0]["source"] == "excel"

    summary = body1["summary"]
    assert summary["duration_hours"] == 24.0
    assert summary["balanced"] is True
    assert summary["recording_passed"] is True
    assert summary["recording_interval_ok"] is True
    assert summary["max_gap_hours"] == 1.0
    assert summary["pressure_change_pa_bar"] == pytest.approx(0.24)
    assert summary["temperature_change_dt_c"] == pytest.approx(-0.25)
    assert summary["volume_delta_m3"] == pytest.approx(1.2)
    assert summary["decision"]["status"] == "BASARILI"
    assert summary["recording_decision"]["status"] == "BASARILI"

    # Replace with 3 gapped points -> interval fails (12h gap > 2h)
    res2 = client.post(
        f"/api/sessions/{sid}/time-series/batch",
        json={
            "mode": "replace",
            "records": [
                {"timestamp": "2026-11-14T00:00:00Z", "pressure_bar": 80.0, "temperature_c": 15.0},
                {"timestamp": "2026-11-14T12:00:00Z", "pressure_bar": 80.0, "temperature_c": 15.0},
                {"timestamp": "2026-11-15T00:00:00Z", "pressure_bar": 79.5, "temperature_c": 15.0},
            ],
        },
    )
    assert res2.status_code == 201, res2.text
    body2 = res2.json()
    assert body2["total"] == 3
    assert body2["summary"]["recording_duration_ok"] is True
    assert body2["summary"]["recording_interval_ok"] is False
    assert body2["summary"]["recording_passed"] is False
    assert body2["summary"]["max_gap_hours"] == 12.0
    assert body2["summary"]["recording_decision"]["status"] == "BASARISIZ"

    # Session summary exposes time_series block
    sess_sum = client.get(f"/api/sessions/{sid}/summary").json()
    assert sess_sum["time_series"]["record_count"] == 3

    # Clear deletes all records
    cleared = client.delete(f"/api/sessions/{sid}/time-series")
    assert cleared.status_code == 200
    assert cleared.json()["deleted"] == 3
    assert cleared.json()["summary"]["record_count"] == 0


def test_sync_form_018_and_021_bidirectional_and_reports(client):
    proj = client.post("/api/projects", json={"name": "TS Sync Project", "code": "PRJ-TS"}).json()
    session = create_session(client, name="K-01", project_id=proj["id"], inputs=full_inputs())
    sid = session["id"]

    # Populate 25 hourly monitoring rows in Form 018 (midnight rollover 08:00 -> 08:00 next day)
    # Include 1 incomplete row to verify skipped_rows count
    rows_018 = []
    for hour in range(25):
        hh = (8 + hour) % 24
        rows_018.append(
            {
                "time_str": f"{hh:02d}:00",
                "pressure_bar": 82.0,
                "ambient_temp_c": 17.5,
                "soil_1_c": 16.0,
                "pipe_1_c": 16.0 + (0.2 if hour >= 21 else 0.0),
                "avg_pipe_c": 16.0 + (0.2 if hour >= 21 else 0.0),
            }
        )
    rows_018.append({"time_str": "bad", "pressure_bar": None, "avg_pipe_c": None})

    upd_018 = client.put(
        f"/api/sessions/{sid}/forms/leak_stabilization",
        json={"form_date": "2026-11-14", "extracted_data": {"rows": rows_018}},
    )
    assert upd_018.status_code == 200, upd_018.text

    # Pull from Form 018 -> time_series
    pulled = client.post(
        f"/api/sessions/{sid}/time-series/sync-form",
        json={"form_code": "leak_stabilization", "direction": "from_form", "mode": "replace"},
    )
    assert pulled.status_code == 200, pulled.text
    pulled_body = pulled.json()
    assert pulled_body["direction"] == "from_form"
    assert pulled_body["synced_count"] == 25
    assert pulled_body["skipped_rows"] == 1
    assert pulled_body["summary"]["duration_hours"] == 24.0
    assert pulled_body["summary"]["balanced"] is True
    assert pulled_body["summary"]["recording_passed"] is True
    assert pulled_body["items"][0]["source"] == "form_018"

    # Push time_series -> Form 021 (pressure_test) & check operational checkpoints
    pushed = client.post(
        f"/api/sessions/{sid}/time-series/sync-form",
        json={"form_code": "pressure_test", "direction": "to_form"},
    )
    assert pushed.status_code == 200, pushed.text
    assert pushed.json()["synced_count"] == 25

    forms = client.get(f"/api/sessions/{sid}/forms").json()
    checks_map = {item["key"]: item for item in forms["checkpoints"]}
    assert checks_map["thermal_balance"]["status"] == "passed"
    assert checks_map["pressure_records"]["status"] == "passed"
    pt_form = next(f for f in forms["forms"] if f["form_code"] == "pressure_test")
    assert len(pt_form["extracted_data"]["rows"]) == 25
    assert pt_form["extracted_data"]["time_log"]["duration_hours"] == 24.0

    # Save official thermal_balance result + export TXT, PDF, XLSX
    saved_res = client.post(
        f"/api/sessions/{sid}/results",
        json={"test_type": "thermal_balance", "payload": {"records": _hourly_records(24)}},
    )
    assert saved_res.status_code == 201, saved_res.text
    assert saved_res.json()["decision"]["status"] == "BASARILI"

    txt_preview = client.get(f"/api/sessions/{sid}/export?format=txt&preview=true")
    assert txt_preview.status_code == 200
    txt_content = txt_preview.json()["content"]
    assert "Zaman Serisi Izleme (Bolum 12 & 15)" in txt_content
    assert "Termal denge karari (12):" in txt_content
    assert "24 saatlik kayit karari (15.1):" in txt_content

    pdf_res = client.get(f"/api/sessions/{sid}/export?format=pdf")
    assert pdf_res.status_code == 200
    assert pdf_res.content[:4] == b"%PDF"

    xlsx_res = client.get(f"/api/sessions/{sid}/export?format=xlsx")
    assert xlsx_res.status_code == 200
    assert xlsx_res.content[:2] == b"PK"


def test_bool_rejection_revision_bump_pt_vs_022_match_and_error_paths(client):
    proj = client.post("/api/projects", json={"name": "TS Audit Project", "code": "PRJ-AUD"}).json()
    session = create_session(client, name="K-AUD", project_id=proj["id"], inputs=full_inputs())
    sid = session["id"]
    rev_initial = session["revision"]

    # Reject JSON boolean values on single & batch creation
    bad_bool = client.post(
        f"/api/sessions/{sid}/time-series",
        json={"pressure_bar": True, "temperature_c": 15.0},
    )
    assert bad_bool.status_code == 422

    # Empty to_form returns 422
    empty_sync = client.post(
        f"/api/sessions/{sid}/time-series/sync-form",
        json={"form_code": "pressure_test", "direction": "to_form"},
    )
    assert empty_sync.status_code == 422

    # Over-16 char source in batch returns 422
    long_source = client.post(
        f"/api/sessions/{sid}/time-series/batch",
        json={"records": _hourly_records(2), "source": "x" * 20},
    )
    assert long_source.status_code == 422

    # Insert 25 hourly cooling records with Pa = Pilk - Pson = +0.24 bar (85.00 -> 84.76)
    res = client.post(
        f"/api/sessions/{sid}/time-series/batch",
        json={"records": _hourly_records(24, p0=85.0, t0=16.0), "mode": "replace"},
    )
    assert res.status_code == 201

    # Also save Form 022 matching Pa = +0.24 bar and push time_series -> Form 021
    client.put(
        f"/api/sessions/{sid}/forms/pressure_acceptance",
        json={
            "extracted_data": {
                "pressure_acceptance": {
                    "pa_bar": 0.24,
                    "delta_t_c": -0.25,
                    "pt_bar": 0.2,
                }
            }
        },
    )
    rev_before_sync = client.get(f"/api/sessions/{sid}").json()["revision"]
    pushed = client.post(
        f"/api/sessions/{sid}/time-series/sync-form",
        json={"form_code": "pressure_test", "direction": "to_form"},
    )
    assert pushed.status_code == 200, pushed.text
    pushed_body = pushed.json()
    assert pushed_body["skipped_rows"] == 0
    assert pushed_body["session"]["revision"] == rev_before_sync + 1
    assert pushed_body["session"]["revision"] > rev_initial

    # Form 021 pt_vs_022 cross-check must PASS (Pilk - Pson = +0.24 matches Form 022 PA = +0.24)
    forms = client.get(f"/api/sessions/{sid}/forms").json()
    pt_form = next(f for f in forms["forms"] if f["form_code"] == "pressure_test")
    pt_findings = pt_form.get("findings") or pt_form["extracted_data"]["findings"]
    pt_vs_022 = next(f for f in pt_findings if f["code"] == "pt_vs_022")
    assert pt_vs_022["status"] == "passed"

    # Editing time_str with timestamp=None (as MonitoringFormEditor does) recomputes without stale ISO override
    edited_rows = list(pt_form["extracted_data"]["rows"])
    edited_rows[-1] = {**edited_rows[-1], "time_str": "06:00", "timestamp": None}
    upd_after_edit = client.put(
        f"/api/sessions/{sid}/forms/pressure_test",
        json={"extracted_data": {**pt_form["extracted_data"], "rows": edited_rows}},
    )
    assert upd_after_edit.status_code == 200
    assert upd_after_edit.json()["form"]["extracted_data"]["time_log"]["last_time"] == "06:00"

    # Build context for PDF/XLSX includes live Section 12 decision + |dT_4h|
    from app import db as app_db
    from app.models import HydroSession
    from app.services import reports as report_service
    from app.services import sessions as session_service

    with app_db.session_scope() as db_sess:
        orm_sess = db_sess.get(HydroSession, sid)
        assert orm_sess is not None
        ts_rows = session_service.get_ordered_time_series(db_sess, orm_sess)
        ctx = report_service.build_context(orm_sess, [], time_series_rows=ts_rows)
        assert ctx["test_results"]["Termal Denge Karari (12)"] == "BASARILI"
        assert "Son 4s Sicaklik Farki |dT_4h| (°C)" in ctx["test_results"]

    # Over-300 rows -> to_form reports skipped_rows truncation cleanly
    many_records = [
        {
            "timestamp": f"2026-11-{14 + (i // 288):02d}T{(i * 5 // 60) % 24:02d}:{(i * 5) % 60:02d}:00Z",
            "pressure_bar": 80.0,
            "temperature_c": 15.0,
        }
        for i in range(305)
    ]
    b305 = client.post(
        f"/api/sessions/{sid}/time-series/batch",
        json={"records": many_records, "mode": "replace"},
    )
    assert b305.status_code == 201
    pushed305 = client.post(
        f"/api/sessions/{sid}/time-series/sync-form",
        json={"form_code": "leak_stabilization", "direction": "to_form"},
    )
    assert pushed305.status_code == 200
    assert pushed305.json()["synced_count"] == 300
    assert pushed305.json()["skipped_rows"] == 5
