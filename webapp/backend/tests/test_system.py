"""Tests for /api/health, /api/meta, request ids and error envelopes."""

from __future__ import annotations

import uuid

from hidrostatik_test import APP_VERSION


def test_health_ok(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ok", "degraded"}
    assert body["engine"] == "hidrostatik_test"
    assert body["db"]["ok"] is True
    assert body["db"]["dialect"] == "sqlite"
    assert body["data_dir"]["writable"] is True
    assert isinstance(body["instance_id"], str) and len(body["instance_id"]) >= 8
    assert "queue" in body["ocr"]
    assert response.headers["X-Request-ID"]


def test_health_strict_never_500(client):
    response = client.get("/api/health?strict=1")
    assert response.status_code in {200, 503}
    assert response.json()["status"] in {"ok", "degraded", "fail"}


def test_meta_contract_fields(client):
    body = client.get("/api/meta").json()
    assert body["app"]["version"] == APP_VERSION
    assert body["spec"]["code"].startswith("4-NGTL")
    assert body["engine"]["decision_statuses"] == [
        "BEKLIYOR",
        "KATSAYI GUNCELLENMELI",
        "DOGRULANAMADI",
        "BASARILI",
        "BASARISIZ",
    ]
    assert any(item["key"] == "table_v1" for item in body["water_backends"])
    default_sources = [item for item in body["b_sources"] if item["default"]]
    assert len(default_sources) == 1
    assert default_sources[0]["key"] == "institutional"
    assert body["steel_models"] == [
        "linear",
        "volumetric",
        "volumetric_temperature",
    ]
    assert body["limits"]["max_test_section_length_m"] == 20000.0
    assert body["limits"]["max_test_section_volume_m3"] == 12500.0
    assert body["limits"]["air_acceptance_factor"] == 1.06
    assert body["limits"]["pressure_variation_acceptance_bar"] == 0.3
    assert body["units"]["pressure"] == "bar"
    assert len(body["location_classes"]) == 4
    assert len(body["pig_modes"]) == 4


def test_meta_spec(client):
    body = client.get("/api/meta/spec").json()
    assert body["acceptance_rules"]["air"] == {"text": "Vpa < 1.06 x Vp", "factor": 1.06}
    assert body["acceptance_rules"]["pressure"]["tolerance_bar"] == 0.3
    assert body["sign_convention"]["pa"] == "Pa = Pilk - Pson"
    assert len(body["checks"]) == 11


def test_request_id_is_echoed(client):
    request_id = "client-request-123"
    response = client.get("/api/meta", headers={"X-Request-ID": request_id})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == request_id


def test_validation_error_envelope(client):
    response = client.post("/api/coefficients/a", json={"temperature_c": "abc"})
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert isinstance(body["details"]["errors"], list)
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert set(body) == {"code", "message", "details", "request_id"}


def test_domain_error_envelope(client):
    response = client.post(
        "/api/calculations/air-content",
        json={
            "geometry": {"sections": []},
            "a_micro_per_bar": 44.97,
            "actual_added_water_m3": 0.01,
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "domain_validation_error"
    assert body["request_id"] == response.headers["X-Request-ID"]


def test_not_found_envelope(client):
    response = client.get("/api/sessions/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "not_found"
    assert body["details"]["resource"] == "session"


def test_unknown_api_route_envelope(client):
    response = client.get("/api/unknown-route")
    assert response.status_code == 404
    assert response.json()["code"] in {"not_found", "http_error"}


def test_workspace_header_default_anonymous(client):
    response = client.get("/api/health")
    assert response.headers["X-Session-ID"] == "anonymous"


def test_workspace_header_echo(client):
    workspace = str(uuid.uuid4())
    response = client.get("/api/meta", headers={"X-Session-ID": workspace})
    assert response.headers["X-Session-ID"] == workspace


def test_api_only_root_without_frontend(client):
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "hydro-web"
    assert body["status"] == "api_only"


def test_backup_drill_smoke_and_retention_pruning(tmp_path):
    from scripts import backup_drill

    first = backup_drill.run_backup_drill(tmp_path, max_backups=1)
    assert first["status"] == "ok"
    assert first["pruned_count"] == 0

    second = backup_drill.run_backup_drill(tmp_path, max_backups=1)
    assert second["status"] == "ok"
    assert second["pruned_count"] >= 1


def test_health_reports_disk_space_telemetry(client):
    body = client.get("/api/health").json()
    assert isinstance(body["data_dir"]["free_mb"], float)
    assert body["data_dir"]["free_mb"] >= 0.0
    assert isinstance(body["data_dir"]["low_disk_space"], bool)


def test_timeutil_json_safe_parse_and_numbers():
    from dataclasses import dataclass
    from datetime import date, datetime, timezone
    from enum import Enum

    import pytest
    from app.core import timeutil
    from app.core.errors import AppError

    class _Color(Enum):
        RED = "red"

    @dataclass
    class _Item:
        x: float
        when: date

    naive = datetime(2026, 11, 26, 10, 0, 0)
    assert timeutil.iso_z(naive) == "2026-11-26T10:00:00Z"
    assert timeutil.iso_z(None) is None
    assert timeutil.parse_datetime("") is None
    parsed = timeutil.parse_datetime("2026-11-26T10:00:00Z")
    assert parsed is not None and parsed.tzinfo == timezone.utc
    with pytest.raises(AppError):
        timeutil.parse_datetime("not-a-date")

    payload = timeutil.json_safe(
        {
            "nan": float("nan"),
            "inf": float("inf"),
            "item": _Item(x=1.5, when=date(2026, 11, 26)),
            "color": _Color.RED,
            "tags": {"a"},
        }
    )
    assert payload["nan"] is None
    assert payload["inf"] is None
    assert payload["item"] == {"x": 1.5, "when": "2026-11-26"}
    assert payload["color"] == "red"
    assert payload["tags"] == ["a"]
    assert timeutil.as_float("1.234,5") == 1234.5
    assert timeutil.as_positive_float(True) is None
    assert timeutil.fmt_number(12.3400, 4) == "12.34"
