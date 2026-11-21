"""Calculation endpoint tests."""

from __future__ import annotations

import math

from conftest import air_payload, pressure_payload, profile_payload


def test_geometry_single_and_multi(client):
    single = client.post(
        "/api/calculations/geometry",
        json={
            "sections": [
                {
                    "outside_diameter_mm": 406.4,
                    "wall_thickness_mm": 8.74,
                    "length_m": 1000.0,
                }
            ]
        },
    )
    assert single.status_code == 200
    body = single.json()
    assert body["section_count"] == 1
    assert math.isclose(body["internal_radius_mm"], 194.46, abs_tol=1e-9)
    assert math.isclose(body["elasticity_term"], 0.884 * 194.46 / 8.74, rel_tol=1e-12)

    multi = client.post(
        "/api/calculations/geometry",
        json={
            "sections": [
                {
                    "outside_diameter_mm": 406.4,
                    "wall_thickness_mm": 8.74,
                    "length_m": 1000.0,
                },
                {
                    "outside_diameter_mm": 323.9,
                    "wall_thickness_mm": 6.35,
                    "length_m": 500.0,
                },
            ]
        },
    ).json()
    assert multi["section_count"] == 2
    assert multi["total_length_m"] == 1500.0
    assert math.isclose(
        multi["internal_volume_m3"],
        body["internal_volume_m3"] + math.pi * ((323.9 / 2 - 6.35) / 1000) ** 2 * 500.0,
        rel_tol=1e-12,
    )


def test_air_content_pass(client):
    body = client.post("/api/calculations/air-content", json=air_payload()).json()
    assert body["passed"] is True
    assert body["decision"]["status"] == "BASARILI"
    assert body["decision"]["rule"] == "Vpa < 1.06 x Vp"
    assert body["acceptance_limit_m3"] > body["actual_added_water_m3"]
    assert math.isclose(
        body["decision"]["margin"],
        body["acceptance_limit_m3"] - body["actual_added_water_m3"],
        rel_tol=1e-12,
    )


def test_air_content_exact_boundary_fails(client):
    baseline = client.post("/api/calculations/air-content", json=air_payload()).json()
    exact = client.post(
        "/api/calculations/air-content",
        json=air_payload(actual_added_water_m3=baseline["acceptance_limit_m3"]),
    ).json()
    assert exact["passed"] is False
    assert exact["decision"]["status"] == "BASARISIZ"


def test_air_content_rejects_non_one_bar_rise(client):
    response = client.post("/api/calculations/air-content", json=air_payload(pressure_rise_bar=1.1))
    assert response.status_code == 400
    assert response.json()["code"] == "domain_validation_error"


def test_pressure_variation_pass(client):
    body = client.post("/api/calculations/pressure-variation", json=pressure_payload()).json()
    assert body["passed"] is True
    assert body["decision"]["status"] == "BASARILI"
    assert body["negative_b"] is False
    assert math.isclose(
        body["allowable_upper_pressure_change_bar"],
        body["theoretical_pressure_change_bar"] + 0.3,
        rel_tol=1e-12,
    )
    assert math.isclose(
        body["margin_bar"],
        body["actual_pressure_change_bar"] - body["theoretical_pressure_change_bar"],
        rel_tol=1e-12,
    )


def test_pressure_variation_negative_b_is_valid(client):
    body = client.post(
        "/api/calculations/pressure-variation",
        json=pressure_payload(b_micro_per_c=-60.0, actual_pressure_change_bar=-1.9),
    ).json()
    assert body["negative_b"] is True
    assert body["theoretical_pressure_change_bar"] < 0
    assert body["passed"] is True
    assert "B negatif" in body["decision"]["summary"]


def test_pressure_profile_window(client):
    body = client.post("/api/calculations/pressure-profile", json=profile_payload()).json()
    assert body["feasible"] is True
    assert body["within_length_limit"] is True
    assert body["within_volume_limit"] is True
    assert math.isclose(body["required_minimum_pressure_at_high_point_bar"], 100.0)
    assert math.isclose(
        body["required_pressure_with_span_bar"],
        body["required_minimum_pressure_at_high_point_bar"] + body["hydraulic_span_bar"],
        rel_tol=1e-12,
    )
    assert body["selected_window"]["minimum_required_pressure_bar"] < 112.0
    assert body["selected_window"]["maximum_allowable_pressure_bar"] > 112.0
    assert body["monitored_meets_minimum"] is True
    assert body["monitored_under_maximum"] is True
    assert body["decision"]["status"] == "BASARILI"


def test_pressure_profile_length_limit(client):
    body = client.post(
        "/api/calculations/pressure-profile",
        json=profile_payload(
            geometry={
                "sections": [
                    {
                        "outside_diameter_mm": 406.4,
                        "wall_thickness_mm": 8.74,
                        "length_m": 21000.0,
                    }
                ]
            }
        ),
    ).json()
    assert body["within_length_limit"] is False
    assert body["feasible"] is False
    assert body["decision"]["status"] == "BASARISIZ"


def test_pressure_profile_volume_limit(client):
    body = client.post(
        "/api/calculations/pressure-profile",
        json=profile_payload(
            geometry={
                "sections": [
                    {
                        "outside_diameter_mm": 2000.0,
                        "wall_thickness_mm": 10.0,
                        "length_m": 5000.0,
                    }
                ]
            },
            smys_mpa=450.0,
        ),
    ).json()
    assert body["within_volume_limit"] is False
    assert body["feasible"] is False


def test_pressure_profile_unknown_location_class(client):
    response = client.post(
        "/api/calculations/pressure-profile",
        json=profile_payload(location_class="Class 9"),
    )
    assert response.status_code == 400
    assert response.json()["code"] == "domain_validation_error"


def test_pig_speed_modes(client):
    cases = [
        ("Temizlik pigi", 5000.0, 45.0, "UYGUN", True),
        ("Temizlik pigi", 5000.0, 20.0, "LIMIT ASILDI", False),
        ("Serbest kontrol", 5000.0, 45.0, "BILGI", None),
    ]
    for mode, distance, travel, status, passed in cases:
        response = client.post(
            "/api/calculations/pig-speed",
            json={"mode": mode, "distance_m": distance, "travel_time_min": travel},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == status
        assert body["passed"] is passed
        assert body["speed_m_per_s"] > 0
        assert math.isclose(body["speed_km_per_h"], body["speed_m_per_s"] * 3.6, rel_tol=1e-12)


def test_pig_speed_invalid_mode(client):
    response = client.post(
        "/api/calculations/pig-speed",
        json={"mode": "Uzay pigi", "distance_m": 100, "travel_time_min": 10},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "domain_validation_error"


def test_pressurization_pass(client):
    body = client.post(
        "/api/calculations/pressurization",
        json={
            "initial_volume_m3": 10.0,
            "added_volume_m3": 0.5,
            "theoretical_volume_m3": 10.48,
            "pressure_bar": 80.05,
            "expected_pressure_bar": 80.0,
        },
    ).json()
    assert body["passed"] is True
    assert body["within_volume_limit"] is True
    assert body["within_pressure_limit"] is True
    assert body["underfilled"] is False
    assert math.isclose(body["volume_limit_percent"], 0.2)


def test_pressurization_underfill(client):
    body = client.post(
        "/api/calculations/pressurization",
        json={
            "initial_volume_m3": 10.0,
            "added_volume_m3": 0.0,
            "theoretical_volume_m3": 10.5,
            "pressure_bar": 80.0,
            "expected_pressure_bar": 80.0,
        },
    ).json()
    assert body["underfilled"] is True
    assert body["volume_shortfall_percent"] > 4.0


def test_thermal_balance_insufficient(client):
    body = client.post(
        "/api/calculations/thermal-balance",
        json={
            "records": [
                {
                    "timestamp": "2026-11-14T08:00:00Z",
                    "pressure_bar": 80.0,
                    "temperature_c": 18.2,
                },
                {
                    "timestamp": "2026-11-15T08:00:00Z",
                    "pressure_bar": 80.0,
                    "temperature_c": 18.1,
                },
                {
                    "timestamp": "2026-11-15T12:00:00Z",
                    "pressure_bar": 80.0,
                    "temperature_c": 18.15,
                },
            ]
        },
    ).json()
    assert body["duration_hours"] == 28.0
    assert body["balanced"] is False
    assert body["temp_diff_c"] is None
    assert body["decision"]["status"] == "DOGRULANAMADI"


def test_thermal_balance_stable(client):
    records = []
    for hour in range(0, 27, 2):
        day = 14 if hour < 24 else 15
        records.append(
            {
                "timestamp": f"2026-11-{day:02d}T{(hour % 24):02d}:00:00Z",
                "pressure_bar": 80.0,
                "temperature_c": 18.10,
            }
        )
    body = client.post("/api/calculations/thermal-balance", json={"records": records}).json()
    assert body["duration_hours"] == 26.0
    assert body["balanced"] is True
    assert body["temp_diff_c"] == 0.0
    assert body["decision"]["status"] == "BASARILI"


def test_water_density(client):
    body = client.post(
        "/api/calculations/water-density",
        json={"temperature_c": 15.0, "pressure_bar": 1.0},
    ).json()
    assert 990.0 < body["density_kg_per_m3"] < 1010.0


def test_water_density_error(client):
    response = client.post(
        "/api/calculations/water-density",
        json={"temperature_c": -300.0, "pressure_bar": 1.0},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "water_property_error"


def test_geometry_semantic_errors(client):
    for section in (
        {"outside_diameter_mm": -1, "wall_thickness_mm": 8.74, "length_m": 10},
        {"outside_diameter_mm": 16, "wall_thickness_mm": 8.0, "length_m": 10},
        {"outside_diameter_mm": 406.4, "wall_thickness_mm": 8.74, "length_m": 0},
    ):
        response = client.post("/api/calculations/geometry", json={"sections": [section]})
        assert response.status_code == 400
        assert response.json()["code"] == "domain_validation_error"


def _ramp_payload(readings, p100=100.0, total=1000.0):
    return {
        "readings": [
            {"elapsed_min": t, "pressure_bar": p, "cumulative_added_volume_m3": v}
            for t, p, v in readings
        ],
        "test_pressure_100_smys_bar": p100,
        "total_filled_volume_m3": total,
    }


def test_pressurization_ramp_stop_on_excess_volume(client):
    body = client.post(
        "/api/calculations/pressurization-ramp",
        json=_ramp_payload([(0, 95.0, 10.0), (30, 97.0, 11.0), (60, 98.0, 12.5)]),
    ).json()
    assert body["stop_required"] is True
    assert body["passed"] is False
    assert body["decision"]["status"] == "BASARISIZ"
    assert "DURDURUN" in body["decision"]["summary"]


def test_pressurization_ramp_pass_and_pending(client):
    done = client.post(
        "/api/calculations/pressurization-ramp",
        json=_ramp_payload([(0, 80.0, 0.0), (10, 90.0, 0.5), (20, 95.0, 0.8), (40, 100.0, 1.5)]),
    ).json()
    assert done["passed"] is True
    assert done["decision"]["status"] == "BASARILI"

    pending = client.post(
        "/api/calculations/pressurization-ramp",
        json=_ramp_payload([(0, 95.0, 0.0), (10, 96.0, 0.1)]),
    ).json()
    assert pending["passed"] is None
    assert pending["decision"]["status"] == "BEKLIYOR"


def test_pressurization_ramp_domain_validation_error(client):
    response = client.post(
        "/api/calculations/pressurization-ramp",
        json=_ramp_payload([(0, 80.0, 0.0)]),
    )
    assert response.status_code == 400
    assert response.json()["code"] == "domain_validation_error"


def test_pressure_hold_endpoint(client):
    ok = client.post(
        "/api/calculations/pressure-hold",
        json={
            "readings": [
                {"elapsed_min": t, "pressure_bar": 100.0, "temperature_c": 12.0}
                for t in range(0, 121, 15)
            ],
            "target_pressure_bar": 100.0,
        },
    ).json()
    assert ok["passed"] is True
    assert ok["repressurize_required"] is False
    assert ok["decision"]["status"] == "BASARILI"

    short = client.post(
        "/api/calculations/pressure-hold",
        json={
            "readings": [
                {"elapsed_min": 0, "pressure_bar": 100.0, "temperature_c": 12.0},
                {"elapsed_min": 60, "pressure_bar": 99.0, "temperature_c": 12.0},
            ],
            "target_pressure_bar": 100.0,
        },
    ).json()
    assert short["passed"] is False
    assert short["repressurize_required"] is True


def test_depressurization_endpoint(client):
    ok = client.post(
        "/api/calculations/depressurization",
        json={
            "test_passed": True,
            "release_valve_diameter_in": 2,
            "pipe_equipment_checked": True,
            "environmental_impact_checked": True,
        },
    ).json()
    assert ok["decision"]["status"] == "BASARILI"

    big_valve = client.post(
        "/api/calculations/depressurization",
        json={
            "test_passed": True,
            "release_valve_diameter_in": 4,
            "pipe_equipment_checked": True,
            "environmental_impact_checked": True,
        },
    ).json()
    assert big_valve["decision"]["status"] == "BASARISIZ"
    assert big_valve["violations"]

    empty = client.post("/api/calculations/depressurization", json={}).json()
    assert empty["decision"]["status"] == "BEKLIYOR"


def test_discharge_endpoint(client):
    base = {
        "destination": "other_section",
        "used_discharge_pig": True,
        "hydraulic_load_measures_taken": True,
        "report_date": "2026-11-19",
        "report_time": "14:30",
        "pig_name": "PIG-07",
        "discharge_location": "KP 12+300",
        "duration_min": 95,
    }
    ok = client.post("/api/calculations/discharge", json=base).json()
    assert ok["decision"]["status"] == "BASARILI"

    river = client.post(
        "/api/calculations/discharge",
        json={**base, "destination": "watercourse", "approvals_obtained": False},
    ).json()
    assert river["decision"]["status"] == "BASARISIZ"

    bad = client.post("/api/calculations/discharge", json={**base, "destination": "ocean"})
    assert bad.status_code == 400
    assert bad.json()["code"] == "domain_validation_error"


def test_pressure_variation_negative_b_flag_follows_b_sign(client):
    pos_b_neg_dt = client.post(
        "/api/calculations/pressure-variation",
        json=pressure_payload(
            b_micro_per_c=188.661,
            delta_t_c=-2.0,
            actual_pressure_change_bar=-5.9,
        ),
    ).json()
    assert pos_b_neg_dt["theoretical_pressure_change_bar"] < 0
    assert pos_b_neg_dt["negative_b"] is False
    assert "B negatif" not in pos_b_neg_dt["decision"]["summary"]

    neg_b_neg_dt = client.post(
        "/api/calculations/pressure-variation",
        json=pressure_payload(
            b_micro_per_c=-60.0,
            delta_t_c=-2.0,
            actual_pressure_change_bar=1.9,
        ),
    ).json()
    assert neg_b_neg_dt["theoretical_pressure_change_bar"] > 0
    assert neg_b_neg_dt["negative_b"] is True
    assert "B negatif" in neg_b_neg_dt["decision"]["summary"]

    neg_b_zero_dt = client.post(
        "/api/calculations/pressure-variation",
        json=pressure_payload(
            b_micro_per_c=-60.0,
            delta_t_c=0.0,
            actual_pressure_change_bar=0.0,
        ),
    ).json()
    assert neg_b_zero_dt["theoretical_pressure_change_bar"] == 0.0
    assert neg_b_zero_dt["negative_b"] is True


def test_coefficients_b_and_compare_accept_backend_and_cold_range(client):
    auto_cold = client.post(
        "/api/coefficients/b",
        json={
            "source": "auto",
            "temperature_c": 1.0,
            "pressure_bar": 30.0,
            "steel_alpha_micro_per_c": 12.0,
            "steel_model": "volumetric",
            "backend": "table_v1",
        },
    )
    assert auto_cold.status_code == 200, auto_cold.text
    cold_body = auto_cold.json()
    assert cold_body["water_beta_micro_per_c"] < 0
    assert cold_body["b_micro_per_c"] < 0
    assert "table_v1" in cold_body["note"]

    table_zero = client.post(
        "/api/coefficients/b",
        json={
            "source": "institutional",
            "temperature_c": 0.0,
            "pressure_bar": 50.0,
            "steel_alpha_micro_per_c": 12.0,
            "steel_model": "volumetric",
        },
    )
    assert table_zero.status_code == 400

    cmp_res = client.post(
        "/api/coefficients/compare",
        json={
            "temperature_c": 10.0,
            "pressure_bar": 50.0,
            "steel_alpha_micro_per_c": 12.0,
            "steel_model": "volumetric",
            "backend": "table_v1",
        },
    )
    assert cmp_res.status_code == 200, cmp_res.text
    assert "table_v1" in cmp_res.json()["auto"]["note"]


def test_evaluate_test_coefficient_b_propagates_backend(client):
    sess = client.post(
        "/api/sessions",
        json={"name": "Eval B Backend", "inputs": {"water_backend": "table_v1"}},
    ).json()
    saved = client.post(
        f"/api/sessions/{sess['id']}/results",
        json={
            "test_type": "coefficient_b",
            "payload": {
                "source": "auto",
                "temperature_c": 10.0,
                "pressure_bar": 50.0,
                "steel_alpha_micro_per_c": 12.0,
                "steel_model": "volumetric",
                "backend": "table_v1",
            },
        },
        headers={"If-Match": f'"{sess["revision"]}"'},
    )
    assert saved.status_code == 201, saved.text
    assert "table_v1" in saved.json()["result"]["note"]


def test_geometry_and_pressure_profile_per_segment_smys_and_validation(client):
    geom = client.post(
        "/api/calculations/geometry",
        json={
            "sections": [
                {
                    "outside_diameter_mm": 406.4,
                    "wall_thickness_mm": 8.74,
                    "length_m": 600.0,
                    "smys_mpa": 450.0,
                    "material_grade": "API 5L X65",
                },
                {
                    "outside_diameter_mm": 406.4,
                    "wall_thickness_mm": 8.74,
                    "length_m": 400.0,
                    "smys_mpa": 290.0,
                    "material_grade": "API 5L X42",
                },
            ]
        },
    )
    assert geom.status_code == 200, geom.text
    gbody = geom.json()
    assert gbody["sections"][0]["smys_mpa"] == 450.0
    assert gbody["sections"][0]["material_grade"] == "API 5L X65"
    assert gbody["sections"][1]["smys_mpa"] == 290.0
    assert math.isclose(
        gbody["sections"][1]["pressure_at_100_smys_bar"],
        20.0 * 290.0 * 8.74 / 406.4,
        rel_tol=1e-9,
    )

    prof = client.post(
        "/api/calculations/pressure-profile",
        json=profile_payload(
            geometry={
                "sections": [
                    {
                        "outside_diameter_mm": 406.4,
                        "wall_thickness_mm": 8.74,
                        "length_m": 600.0,
                        "smys_mpa": 450.0,
                        "material_grade": "API 5L X65",
                    },
                    {
                        "outside_diameter_mm": 406.4,
                        "wall_thickness_mm": 8.74,
                        "length_m": 400.0,
                        "smys_mpa": 290.0,
                        "material_grade": "API 5L X42",
                    },
                ]
            },
            smys_mpa=450.0,
            design_pressure_bar=100.0,
        ),
    )
    assert prof.status_code == 200, prof.text
    pbody = prof.json()
    assert pbody["limiting_segment_index"] == 2
    assert pbody["limiting_smys_mpa"] == 290.0
    assert math.isclose(
        pbody["limiting_pressure_at_100_smys_bar"],
        20.0 * 290.0 * 8.74 / 406.4,
        rel_tol=1e-9,
    )
    assert "Limit segment 2" in pbody["limiting_pipe_description"]
    assert "API 5L X42" in pbody["limiting_pipe_description"]

    bad_neg = client.post(
        "/api/calculations/geometry",
        json={
            "sections": [
                {
                    "outside_diameter_mm": 406.4,
                    "wall_thickness_mm": 8.74,
                    "length_m": 500.0,
                    "smys_mpa": -290.0,
                }
            ]
        },
    )
    assert bad_neg.status_code == 400
    assert bad_neg.json()["code"] == "domain_validation_error"

    bad_bool = client.post(
        "/api/calculations/geometry",
        json={
            "sections": [
                {
                    "outside_diameter_mm": 406.4,
                    "wall_thickness_mm": 8.74,
                    "length_m": 500.0,
                    "smys_mpa": True,
                }
            ]
        },
    )
    assert bad_bool.status_code == 422
