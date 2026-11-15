"""Catalog endpoint tests."""

from __future__ import annotations


def test_pipes_list_and_search(client):
    body = client.get("/api/catalog/pipes", params={"limit": 5}).json()
    assert body["limit"] == 5
    assert 0 < len(body["items"]) <= 5
    assert body["total"] >= 40
    first = body["items"][0]
    assert {"nps", "dn", "outside_diameter_mm", "option_label", "schedules"} <= set(first)

    search = client.get("/api/catalog/pipes", params={"q": "16"}).json()
    assert search["total"] >= 1
    assert any(item["nps"] == "16" for item in search["items"])


def test_pipe_schedules_by_nps_and_dn(client):
    by_nps = client.get("/api/catalog/pipes/16/schedules")
    assert by_nps.status_code == 200
    body = by_nps.json()
    assert body["nps"] == "16"
    assert body["dn"] == "400"
    assert body["outside_diameter_mm"] == 406.4
    assert any(item["wall_thickness_mm"] == 8.74 for item in body["items"])

    by_dn = client.get("/api/catalog/pipes/400/schedules")
    assert by_dn.status_code == 200
    assert by_dn.json()["nps"] == "16"


def test_pipe_schedules_not_found(client):
    response = client.get("/api/catalog/pipes/9999/schedules")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_grades(client):
    body = client.get("/api/catalog/grades").json()
    assert body["total"] == 9
    x65 = next(item for item in body["items"] if item["grade"] == "X65")
    assert x65["smys_mpa"] == 450.0
    assert x65["iso_label"] == "L450"
    assert x65["option_label"].startswith("API 5L PSL2 X65")


def test_reference_tables(client):
    body = client.get("/api/catalog/reference-tables").json()
    assert body["total"] == 2
    by_key = {item["key"]: item for item in body["items"]}
    assert by_key["institutional"]["temperature"]["min"] == 1.0
    assert by_key["institutional"]["temperature"]["max"] == 25.0
    assert by_key["institutional"]["pressure"]["min"] == 30.0
    assert by_key["institutional"]["pressure"]["max"] == 120.0
    assert by_key["institutional"]["a_repair"]["enabled"] is True
    assert by_key["gail"]["temperature"]["min"] == 2.0
    assert by_key["gail"]["temperature"]["max"] == 30.0
    assert by_key["gail"]["pressure"]["step"] == 10.0
