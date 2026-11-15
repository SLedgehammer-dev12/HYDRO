"""Coefficient endpoint tests (A, B, tables, backends)."""

from __future__ import annotations

import math


def test_coefficient_a_table_backend(client):
    response = client.post(
        "/api/coefficients/a",
        json={"temperature_c": 20.0, "pressure_bar": 80.0, "backend": "table_v1"},
    )
    assert response.status_code == 200
    body = response.json()
    assert math.isclose(body["a_micro_per_bar"], 44.971994, rel_tol=1e-6)
    assert body["backend"]["key"] == "table_v1"
    assert body["state"] == "computed"


def test_coefficient_a_water_property_error(client):
    response = client.post(
        "/api/coefficients/a",
        json={"temperature_c": -300.0, "pressure_bar": 80.0, "backend": "table_v1"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "water_property_error"


def test_coefficient_a_unknown_backend(client):
    response = client.post(
        "/api/coefficients/a",
        json={"temperature_c": 20.0, "pressure_bar": 80.0, "backend": "nope"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "water_property_error"


def test_coefficient_b_defaults_to_institutional(client):
    response = client.post(
        "/api/coefficients/b",
        json={"temperature_c": 20.0, "pressure_bar": 80.0},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "institutional"
    assert body["b_micro_per_c"] == 188.661
    assert body["repaired_table"] is False
    assert body["water_beta_micro_per_c"] is None
    assert body["steel_model"] == ""


def test_coefficient_b_auto_volumetric(client):
    body = client.post(
        "/api/coefficients/b",
        json={
            "source": "auto",
            "temperature_c": 20.0,
            "pressure_bar": 80.0,
            "steel_alpha_micro_per_c": 12.0,
            "steel_model": "volumetric",
        },
    ).json()
    assert body["source"] == "auto"
    assert body["steel_model"] == "volumetric"
    assert body["water_beta_micro_per_c"] is not None
    assert body["steel_alpha_micro_per_c"] == 12.0
    assert math.isclose(
        body["b_micro_per_c"],
        body["water_beta_micro_per_c"] - 3 * 12.0,
        rel_tol=1e-12,
    )


def test_coefficient_b_table_range_error(client):
    response = client.post(
        "/api/coefficients/b",
        json={"source": "institutional", "temperature_c": 26.0, "pressure_bar": 80.0},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "reference_table_error"


def test_coefficient_b_gail_accepts_26c(client):
    response = client.post(
        "/api/coefficients/b",
        json={"source": "gail", "temperature_c": 26.0, "pressure_bar": 80.0},
    )
    assert response.status_code == 200
    assert response.json()["source"] == "gail"


def test_compare_deltas(client):
    body = client.post(
        "/api/coefficients/compare",
        json={
            "temperature_c": 20.0,
            "pressure_bar": 80.0,
            "steel_alpha_micro_per_c": 12.0,
            "steel_model": "volumetric",
        },
    ).json()
    assert body["institutional"]["b_micro_per_c"] == 188.661
    assert body["gail"]["b_micro_per_c"] == 184.03
    deltas = body["deltas"]
    assert math.isclose(
        deltas["institutional_vs_gail"],
        body["institutional"]["b_micro_per_c"] - body["gail"]["b_micro_per_c"],
        rel_tol=1e-12,
    )
    assert math.isclose(
        deltas["auto_vs_institutional"],
        body["auto"]["b_micro_per_c"] - body["institutional"]["b_micro_per_c"],
        rel_tol=1e-12,
    )
    assert math.isclose(
        deltas["auto_vs_gail"],
        body["auto"]["b_micro_per_c"] - body["gail"]["b_micro_per_c"],
        rel_tol=1e-12,
    )


def test_compare_range_error_at_26c(client):
    response = client.post(
        "/api/coefficients/compare",
        json={"temperature_c": 26.0, "pressure_bar": 80.0},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "reference_table_error"


def test_table_repaired_anomaly_at_7c_90bar(client):
    body = client.post(
        "/api/coefficients/table",
        json={
            "table": "institutional",
            "temperature_c": 7.0,
            "pressure_bar": 90.0,
            "repair_anomalies": True,
        },
    ).json()
    assert body["repaired"] is True
    assert "onarilmis" in body["repair_note"].lower()
    assert body["a_micro_per_bar"] != 45.515


def test_table_gail(client):
    body = client.post(
        "/api/coefficients/table",
        json={"table": "gail", "temperature_c": 20.0, "pressure_bar": 80.0},
    ).json()
    assert body["table"] == "gail"
    assert body["table_label"] == "GAIL referans tablosu"
    assert body["b_micro_per_c"] == 184.03


def test_reference_compare(client):
    body = client.post(
        "/api/coefficients/reference-compare",
        json={"temperature_c": 20.0, "pressure_bar": 80.0},
    ).json()
    assert math.isclose(
        body["a_delta"],
        body["control_point"]["a_micro_per_bar"] - body["gail_point"]["a_micro_per_bar"],
        rel_tol=1e-12,
    )
    assert math.isclose(
        body["b_delta"],
        body["control_point"]["b_micro_per_c"] - body["gail_point"]["b_micro_per_c"],
        rel_tol=1e-12,
    )


def test_backend_comparison_partial_success(client):
    body = client.post(
        "/api/coefficients/backend-comparison",
        json={"temperature_c": 20.0, "pressure_bar": 80.0},
    ).json()
    assert body["items"]
    table = next(item for item in body["items"] if item["backend"]["key"] == "table_v1")
    assert table["error"] is None
    assert math.isclose(table["a_micro_per_bar"], 44.971994, rel_tol=1e-6)
    assert table["density_kg_per_m3"] is not None
