"""Project CRUD, section counting and session attachment tests."""

from __future__ import annotations

OTHER_WORKSPACE = {"X-Session-ID": "other-workspace"}


def _create_project(api, headers, **payload):
    response = api.post("/api/projects", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def _create_session(api, headers, **payload):
    response = api.post(
        "/api/sessions", json=payload or {"name": "Oturum Test"}, headers=headers
    )
    assert response.status_code in {200, 201}, response.text
    return response.json()


def test_project_create_and_list(client, headers):
    project = _create_project(
        client, headers, name="Kuzey Hatti", code="KH-01", client="ACME"
    )
    assert project["section_count"] == 0
    assert project["code"] == "KH-01"
    assert project["client"] == "ACME"
    assert project["created_at"] and project["updated_at"]

    listed = client.get("/api/projects", headers=headers)
    assert listed.status_code == 200
    assert listed.headers["X-Total-Count"] == "1"
    body = listed.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == project["id"]
    assert body["items"][0]["section_count"] == 0


def test_session_attach_and_project_detail(client, headers):
    project = _create_project(client, headers, name="Proje A")
    session = _create_session(client, headers, name="Bolum 1", project_id=project["id"])
    assert session["project_id"] == project["id"]

    detail = client.get(f"/api/projects/{project['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["section_count"] == 1

    listed = client.get(
        "/api/sessions", params={"project_id": project["id"]}, headers=headers
    )
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == session["id"]


def test_session_project_reassignment_and_detach(client, headers):
    first = _create_project(client, headers, name="P1")
    second = _create_project(client, headers, name="P2")
    session = _create_session(client, headers, name="S", project_id=first["id"])

    moved = client.put(
        f"/api/sessions/{session['id']}",
        json={"project_id": second["id"]},
        headers=headers,
    )
    assert moved.status_code == 200
    assert moved.json()["project_id"] == second["id"]
    assert (
        client.get(f"/api/projects/{first['id']}", headers=headers).json()[
            "section_count"
        ]
        == 0
    )
    assert (
        client.get(f"/api/projects/{second['id']}", headers=headers).json()[
            "section_count"
        ]
        == 1
    )

    detached = client.put(
        f"/api/sessions/{session['id']}", json={"project_id": None}, headers=headers
    )
    assert detached.status_code == 200
    fetched = client.get(f"/api/sessions/{session['id']}", headers=headers).json()
    assert fetched["project_id"] is None


def test_project_update_fields(client, headers):
    project = _create_project(
        client, headers, name="Eski", code="E-1", client="Eski Musteri"
    )
    updated = client.put(
        f"/api/projects/{project['id']}",
        json={"name": "Yeni", "code": "Y-2", "client": "Yeni Musteri"},
        headers=headers,
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["name"] == "Yeni"
    assert body["code"] == "Y-2"
    assert body["client"] == "Yeni Musteri"

    partial = client.put(
        f"/api/projects/{project['id']}",
        json={"description": "aciklama"},
        headers=headers,
    ).json()
    assert partial["description"] == "aciklama"
    assert partial["name"] == "Yeni"
    assert partial["code"] == "Y-2"
    assert partial["client"] == "Yeni Musteri"

    cleared = client.put(
        f"/api/projects/{project['id']}",
        json={"client": None, "code": None},
        headers=headers,
    ).json()
    assert cleared["client"] is None
    assert cleared["code"] == ""


def test_project_q_filter(client, headers):
    _create_project(client, headers, name="Alpha Hatti", code="AL-1", client="Kuzey Enerji")
    _create_project(client, headers, name="Beta Hatti", code="BE-2", client="Guney Enerji")

    assert (
        client.get("/api/projects", params={"q": "alpha"}, headers=headers).json()[
            "total"
        ]
        == 1
    )
    assert (
        client.get("/api/projects", params={"q": "be-2"}, headers=headers).json()[
            "total"
        ]
        == 1
    )
    assert (
        client.get(
            "/api/projects", params={"q": "guney enerji"}, headers=headers
        ).json()["total"]
        == 1
    )
    assert (
        client.get("/api/projects", params={"q": "yok"}, headers=headers).json()[
            "total"
        ]
        == 0
    )


def test_project_workspace_isolation(client, headers):
    project = _create_project(client, headers, name="Gizli")

    assert (
        client.get(f"/api/projects/{project['id']}", headers=OTHER_WORKSPACE).status_code
        == 404
    )
    assert (
        client.put(
            f"/api/projects/{project['id']}",
            json={"name": "Ele Gecir"},
            headers=OTHER_WORKSPACE,
        ).status_code
        == 404
    )
    assert (
        client.delete(
            f"/api/projects/{project['id']}", headers=OTHER_WORKSPACE
        ).status_code
        == 404
    )
    assert (
        client.get("/api/projects", headers=OTHER_WORKSPACE).json()["total"] == 0
    )

    foreign_session = client.post(
        "/api/sessions",
        json={"name": "Yabanci", "project_id": project["id"]},
        headers=OTHER_WORKSPACE,
    )
    assert foreign_session.status_code == 404


def test_project_delete_soft_and_detach(client, headers):
    project = _create_project(client, headers, name="Silinecek")
    session = _create_session(client, headers, name="S", project_id=project["id"])

    deleted = client.delete(f"/api/projects/{project['id']}", headers=headers)
    assert deleted.status_code == 204
    assert (
        client.get(f"/api/projects/{project['id']}", headers=headers).status_code
        == 404
    )
    assert client.get("/api/projects", headers=headers).json()["total"] == 0

    fetched = client.get(f"/api/sessions/{session['id']}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["project_id"] is None


def test_project_name_validation(client, headers):
    created = client.post("/api/projects", json={"name": "   "}, headers=headers)
    assert created.status_code == 422
    assert created.json()["code"] == "validation_error"

    project = _create_project(client, headers, name="Gecerli")
    updated = client.put(
        f"/api/projects/{project['id']}", json={"name": "  "}, headers=headers
    )
    assert updated.status_code == 422
    assert updated.json()["code"] == "validation_error"


def test_project_section_kp_meta_persisted_and_listed(client, headers):
    project = _create_project(client, headers, name="KP Test Projesi", code="PRJ-KP")
    first = client.post(
        "/api/sessions",
        json={
            "name": "K-01 · KP 0+000–12+000",
            "project_id": project["id"],
            "inputs": {
                "section_meta": {
                    "section_no": "K-01",
                    "description": "Birinci kesit",
                    "start_kp": "0+000",
                    "end_kp": "12+000",
                    "location": "KP 0+000 – 12+000",
                }
            },
        },
        headers=headers,
    )
    assert first.status_code == 201

    second = client.post(
        "/api/sessions",
        json={
            "name": "K-02 · KP 12+000–24+500",
            "project_id": project["id"],
            "inputs": {
                "section_meta": {
                    "section_no": "K-02",
                    "description": "Ikinci kesit",
                    "start_kp": "12+000",
                    "end_kp": "24+500",
                    "location": "KP 12+000 – 24+500",
                }
            },
        },
        headers=headers,
    )
    assert second.status_code == 201

    listed = client.get(
        f"/api/sessions?project_id={project['id']}", headers=headers
    ).json()["items"]
    by_no = {item["section_meta"]["section_no"]: item["section_meta"] for item in listed}
    assert by_no["K-01"]["start_kp"] == "0+000"
    assert by_no["K-01"]["end_kp"] == "12+000"
    assert by_no["K-02"]["start_kp"] == "12+000"
    assert by_no["K-02"]["end_kp"] == "24+500"
    assert by_no["K-01"]["end_kp"] == by_no["K-02"]["start_kp"]
