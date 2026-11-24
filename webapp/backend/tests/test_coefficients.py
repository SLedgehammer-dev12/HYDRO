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


def test_backend_comparison_sanitizes_unexpected_errors(client, monkeypatch):
    from hidrostatik_test.domain import water_properties as wp

    class BrokenBackend:
        def calculate_water_compressibility_a(self, _t: float, _p: float) -> float:
            raise RuntimeError("secret /internal/path failure")

        def calculate_water_thermal_expansion_beta(self, _t: float, _p: float) -> float:
            return 0.0

        def calculate_water_density(self, _t: float, _p: float) -> float:
            return 1000.0

    orig_get = wp.get_water_property_backend

    def fake_get(backend=None):
        if backend == "table_v1":
            return BrokenBackend()
        return orig_get(backend)

    monkeypatch.setattr(wp, "get_water_property_backend", fake_get)
    res = client.post(
        "/api/coefficients/backend-comparison",
        json={"temperature_c": 20.0, "pressure_bar": 80.0},
    )
    assert res.status_code == 200
    table = next(item for item in res.json()["items"] if item["backend"]["key"] == "table_v1")
    assert table["a_micro_per_bar"] is None
    assert table["error"] is not None
    assert "secret" not in table["error"]
    assert "/internal/path" not in table["error"]
    assert "beklenmeyen" in table["error"]


def test_web_backend_labels_and_reference_table_backends(client):
    meta = client.get("/api/meta").json()
    by_key = {item["key"]: item for item in meta["water_backends"]}
    assert by_key["table_v1"]["label"] == "IAPWS-IF97 Region 1"
    assert by_key["coolprop"]["label"] == "IAPWS-95"
    assert by_key["institutional"]["label"] == "Kurum içi A/B kontrol tablosu (BOTAŞ)"
    assert by_key["gail"]["label"] == "GAIL referans tablosu"

    res_inst_a = client.post(
        "/api/coefficients/a",
        json={"temperature_c": 20.0, "pressure_bar": 80.0, "backend": "institutional"},
    )
    assert res_inst_a.status_code == 200
    body_inst_a = res_inst_a.json()
    assert body_inst_a["backend"]["key"] == "institutional"
    assert body_inst_a["state"] == "reference"

    res_gail_a = client.post(
        "/api/coefficients/a",
        json={"temperature_c": 20.0, "pressure_bar": 80.0, "backend": "gail"},
    )
    assert res_gail_a.status_code == 200
    assert res_gail_a.json()["backend"]["key"] == "gail"

    res_inst_b = client.post(
        "/api/coefficients/b",
        json={
            "source": "auto",
            "temperature_c": 20.0,
            "pressure_bar": 80.0,
            "steel_alpha_micro_per_c": 12.0,
            "steel_model": "volumetric",
            "backend": "institutional",
        },
    )
    assert res_inst_b.status_code == 200
    body_inst_b = res_inst_b.json()
    assert body_inst_b["source"] == "institutional"
    assert body_inst_b["b_micro_per_c"] == 188.661

    res_gail_b = client.post(
        "/api/coefficients/b",
        json={
            "source": "auto",
            "temperature_c": 20.0,
            "pressure_bar": 80.0,
            "steel_alpha_micro_per_c": 12.0,
            "steel_model": "volumetric",
            "backend": "gail",
        },
    )
    assert res_gail_b.status_code == 200
    body_gail_b = res_gail_b.json()
    assert body_gail_b["source"] == "gail"
    assert body_gail_b["b_micro_per_c"] == 184.03
