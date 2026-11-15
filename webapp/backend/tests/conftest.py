"""Pytest fixtures for the HYDRO web backend."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

TESTS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = TESTS_DIR.parent
REPO_ROOT = BACKEND_DIR.parents[1]
for path in (str(TESTS_DIR), str(BACKEND_DIR), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from app import db  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url="sqlite:///:memory:",
        data_dir=tmp_path / "data",
        frontend_dist=tmp_path / "dist",
        max_upload_mb=1,
    )


@pytest.fixture()
def client(settings: Settings):
    db.dispose_database()
    application = create_app(settings)
    with TestClient(application) as test_client:
        yield test_client
    db.dispose_database()


@pytest.fixture()
def headers() -> dict[str, str]:
    return {"X-Session-ID": "test-workspace"}


def full_inputs(**overrides: Any) -> dict[str, Any]:
    inputs: dict[str, Any] = {
        "schema_version": 1,
        "active_tab": "pressure",
        "water_backend": "table_v1",
        "geometry": {
            "outside_diameter_mm": 406.4,
            "wall_thickness_mm": 8.74,
            "length_m": 12000.0,
        },
        "geometry_catalog": {
            "size_option": "NPS 16 (DN 400) - OD 406.40 mm",
            "schedule_option": "Sch 20 - 8.74 mm",
        },
        "section_profile": {
            "highest_elevation_m": 320.0,
            "lowest_elevation_m": 180.0,
            "start_elevation_m": 200.0,
            "end_elevation_m": 310.0,
            "design_pressure_bar": 80.0,
            "smys_mpa": 450.0,
        },
        "material_grade": "API 5L PSL2 X65 / L450 - SMYS 450 MPa",
        "location_class": "Class 1 - min 1.25 x dizayn basinci",
        "pump_location": "Baslangic noktasi",
        "air": {
            "temperature_c": 20.0,
            "pressure_bar": 112.0,
            "a_micro_per_bar": 44.971994,
            "pressure_rise_bar": 1.0,
            "k_factor": 1.02,
            "actual_added_water_m3": 0.00775,
        },
        "pressure": {
            "temperature_c": 20.0,
            "pressure_bar": 112.0,
            "a_micro_per_bar": 44.971994,
            "b_micro_per_c": 188.661,
            "delta_t_c": 2.0,
            "actual_pressure_change_bar": 5.95,
        },
        "field": {
            "ambient_temperature_c": 5.0,
            "pig_distance_m": 5000.0,
            "pig_travel_time_min": 45.0,
        },
        "modes": {
            "air_a_mode": "auto",
            "pressure_a_mode": "auto",
            "pressure_b_mode": "table",
            "pressure_b_source": "institutional",
            "steel_model": "volumetric",
            "pig_mode": "Temizlik pigi",
        },
        "checks": {"ambient_temp": True, "forms": True},
    }
    inputs.update(overrides)
    return inputs


def create_session(client: TestClient, **payload: Any) -> dict[str, Any]:
    response = client.post("/api/sessions", json=payload or {"name": "Oturum Test"})
    assert response.status_code in {200, 201}, response.text
    return response.json()


def air_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "geometry": {
            "sections": [
                {
                    "outside_diameter_mm": 406.4,
                    "wall_thickness_mm": 8.74,
                    "length_m": 1000.0,
                }
            ]
        },
        "a_micro_per_bar": 44.971994,
        "pressure_rise_bar": 1.0,
        "k_factor": 1.02,
        "actual_added_water_m3": 0.00775,
    }
    payload.update(overrides)
    return payload


def pressure_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "geometry": {
            "sections": [
                {
                    "outside_diameter_mm": 406.4,
                    "wall_thickness_mm": 8.74,
                    "length_m": 1000.0,
                }
            ]
        },
        "a_micro_per_bar": 44.971994,
        "b_micro_per_c": 188.661,
        "delta_t_c": 2.0,
        "actual_pressure_change_bar": 5.95,
    }
    payload.update(overrides)
    return payload


def profile_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "geometry": {
            "sections": [
                {
                    "outside_diameter_mm": 406.4,
                    "wall_thickness_mm": 8.74,
                    "length_m": 12000.0,
                }
            ]
        },
        "design_pressure_bar": 80.0,
        "smys_mpa": 450.0,
        "location_class": "Class 1 - min 1.25 x dizayn basinci",
        "highest_elevation_m": 320.0,
        "lowest_elevation_m": 180.0,
        "start_elevation_m": 200.0,
        "end_elevation_m": 310.0,
        "pump_location": "Baslangic noktasi",
        "monitored_pressure_bar": 112.0,
    }
    payload.update(overrides)
    return payload


def assert_close(actual: float, expected: float, *, rel: float = 1e-9) -> None:
    import math

    assert math.isclose(actual, expected, rel_tol=rel, abs_tol=1e-12), (
        actual,
        expected,
    )


__all__ = [
    "air_payload",
    "assert_close",
    "create_session",
    "full_inputs",
    "pressure_payload",
    "profile_payload",
]
