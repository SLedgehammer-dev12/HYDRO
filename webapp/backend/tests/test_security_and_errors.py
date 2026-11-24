"""Security boundary, local-admin isolation, bind guard, and error-path tests."""

from __future__ import annotations

import ast
import inspect
import io
import sys
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
from app import db
from app.core.config import Settings
from app.core.errors import AppError, validation_error
from app.main import create_app
from fastapi.testclient import TestClient


def test_all_apperror_and_validation_error_calls_use_valid_signatures():
    """Static AST check: ensure no stale ``AppError(..., status=...)`` or invalid kwargs exist."""

    app_root = Path(__file__).resolve().parents[1] / "app"
    apperror_params = set(inspect.signature(AppError.__init__).parameters) - {"self"}
    val_params = set(inspect.signature(validation_error).parameters)

    violations: list[str] = []
    for py_file in sorted(app_root.rglob("*.py")):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn_name = node.func.id if isinstance(node.func, ast.Name) else None
            if fn_name not in {"AppError", "validation_error"}:
                continue
            allowed = apperror_params if fn_name == "AppError" else val_params
            for kw in node.keywords:
                if kw.arg is not None and kw.arg not in allowed:
                    violations.append(
                        f"{py_file.relative_to(app_root)}:{node.lineno} {fn_name} invalid kw '{kw.arg}'"
                    )
            if fn_name == "AppError" and (len(node.args) + len(node.keywords) < 2):
                violations.append(
                    f"{py_file.relative_to(app_root)}:{node.lineno} AppError missing code/message"
                )

    assert violations == []


@pytest.mark.parametrize(
    ("filename", "content", "mock_dwg_missing", "expected_status", "expected_code"),
    [
        ("rapor.exe", b"MZ\x00\x00", False, 415, "unsupported_format"),
        ("bos.pdf", b"", False, 422, "empty_file"),
        ("sahte.pdf", b"NOT-A-PDF-HEADER", False, 415, "invalid_file_signature"),
        ("buyuk.pdf", b"%PDF-1.4\n" + b"0" * (2 * 1024 * 1024), False, 413, "file_too_large"),
        ("cizim.dwg", b"AC1027" + b"\x00" * 64, True, 503, "dwg_converter_missing"),
    ],
    ids=["unsupported_format", "empty_file", "invalid_signature", "file_too_large", "dwg_missing"],
)
def test_plan_profile_scan_error_paths_return_clean_4xx_503_envelopes(
    client,
    headers,
    monkeypatch,
    filename: str,
    content: bytes,
    mock_dwg_missing: bool,
    expected_status: int,
    expected_code: str,
):
    monkeypatch.setenv("HYDRO_MAX_UPLOAD_MB", "1")
    with patch(
        "app.services.plan_profile._find_dwg2dxf",
        return_value=None if mock_dwg_missing else "/usr/bin/false",
    ):
        res = client.post(
            "/api/projects/plan-profile/scan",
            headers=headers,
            files={"file": (filename, io.BytesIO(content), "application/octet-stream")},
        )
    assert res.status_code == expected_status
    body = res.json()
    assert body["code"] == expected_code
    assert body["message"]


def test_archive_manifest_mismatch_returns_422_not_500(client, headers):
    sample = client.post(
        "/api/projects/generate-sample",
        headers=headers,
        json={"scenario": "passing", "section_count": 1, "name": "Manifest Hat"},
    ).json()
    pid = sample["project"]["id"]
    arc = client.get(f"/api/projects/{pid}/archive", headers=headers).content

    tampered = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(arc), "r") as z_in,
        zipfile.ZipFile(tampered, "w", compression=zipfile.ZIP_DEFLATED) as z_out,
    ):
        for info in z_in.infolist():
            z_out.writestr(info.filename, z_in.read(info.filename))
        z_out.writestr("unexpected_extra.json", b"{}")

    res = client.post(
        "/api/projects/import-archive",
        headers=headers,
        files={"file": ("mismatch.hydroproj.zip", tampered.getvalue(), "application/zip")},
    )
    assert res.status_code == 422
    assert res.json()["code"] == "validation_error"
    assert "unexpected" in res.json()["details"]


def test_local_admin_blocks_remote_host_and_proxy_forwarded_requests(headers, tmp_path: Path):
    # 1) Server bound to 0.0.0.0 without token blocks admin routes even if auth_mode='none'
    remote_dir = tmp_path / "remote"
    app = create_app(
        Settings(
            host="0.0.0.0",
            data_dir=remote_dir,
            database_url=f"sqlite:///{remote_dir}/hydro.db",
            auth_mode="none",
        )
    )
    try:
        rc = TestClient(app)
        health = rc.get("/api/health").json()
        assert health["security"]["loopback_only"] is False
        assert health["security"]["warnings"]

        for method, path, payload in (
            ("GET", "/api/system/workspaces", None),
            ("POST", "/api/system/db-backup", {}),
            ("GET", "/api/system/db-stats", None),
        ):
            r = rc.request(method, path, headers=headers, json=payload)
            assert r.status_code == 403
            assert r.json()["code"] == "local_admin_loopback_only"
    finally:
        db.dispose_database()

    # 2) Loopback host rejects X-Forwarded-For / Forwarded proxy requests
    local_dir = tmp_path / "local_proxy"
    local_app = create_app(
        Settings(
            host="127.0.0.1",
            data_dir=local_dir,
            database_url=f"sqlite:///{local_dir}/hydro.db",
            auth_mode="none",
        )
    )
    try:
        lc = TestClient(local_app)
        proxied = lc.get(
            "/api/system/workspaces",
            headers={**headers, "X-Forwarded-For": "203.0.113.50"},
        )
        assert proxied.status_code == 403
        assert proxied.json()["code"] == "local_admin_loopback_only"
    finally:
        db.dispose_database()


def test_workspace_claim_requires_proof_or_explicit_flag_and_admin_token(tmp_path: Path):
    ws_old = {"X-Session-ID": "owner-ws-secret"}
    ws_new = {"X-Session-ID": "requester-ws"}

    # Blind claim fails, wrong key fails, allow_workspace_claim=True works
    d1 = tmp_path / "ws_claim"
    app = create_app(
        Settings(
            data_dir=d1,
            database_url=f"sqlite:///{d1}/hydro.db",
            allow_workspace_claim=False,
        )
    )
    try:
        c = TestClient(app)
        c.post("/api/projects", headers=ws_old, json={"name": "Gizli Proje"})
        listed = c.get("/api/system/workspaces", headers=ws_new).json()
        old_hash = next(i["workspace_hash"] for i in listed["items"] if not i["is_current"])

        blind = c.post(
            "/api/system/workspaces/claim",
            headers=ws_new,
            json={"source_workspace_hash": old_hash},
        )
        assert blind.status_code == 403
        assert blind.json()["code"] == "workspace_claim_disabled"

        wrong_key = c.post(
            "/api/system/workspaces/claim",
            headers=ws_new,
            json={"source_workspace_hash": old_hash, "source_workspace_key": "wrong-key"},
        )
        assert wrong_key.status_code == 403
        assert wrong_key.json()["code"] == "workspace_claim_forbidden"
    finally:
        db.dispose_database()

    # Valid local_admin_token authorizes admin routes even under auth_mode='token'
    d2 = tmp_path / "tok"
    tok_app = create_app(
        Settings(
            host="0.0.0.0",
            data_dir=d2,
            database_url=f"sqlite:///{d2}/hydro.db",
            auth_mode="token",
            local_admin_token="super-secret-admin",
            allow_workspace_claim=True,
        )
    )
    try:
        tc = TestClient(tok_app)
        assert tc.get("/api/system/db-stats", headers=ws_new).status_code == 403
        ok = tc.get(
            "/api/system/db-stats",
            headers={**ws_new, "X-Hydro-Admin-Token": "super-secret-admin"},
        )
        assert ok.status_code == 200
    finally:
        db.dispose_database()


def test_run_web_rejects_unauthenticated_0000_without_allow_remote(tmp_path: Path, monkeypatch):
    repo_root = Path(__file__).resolve().parents[3]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from webapp import run_web

    monkeypatch.delenv("HYDRO_ALLOW_REMOTE", raising=False)
    monkeypatch.delenv("HYDRO_AUTH_MODE", raising=False)
    code = run_web.main(["--host", "0.0.0.0", "--data-dir", str(tmp_path)])
    assert code == 2


def test_auth_mode_placeholder_does_not_bypass_bind_guard_or_health_warnings(
    tmp_path: Path, monkeypatch
):
    repo_root = Path(__file__).resolve().parents[3]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from webapp import run_web

    monkeypatch.delenv("HYDRO_ALLOW_REMOTE", raising=False)
    monkeypatch.setenv("HYDRO_AUTH_MODE", "oidc")
    code = run_web.main(["--host", "0.0.0.0", "--data-dir", str(tmp_path / "run")])
    assert code == 2

    app = create_app(
        Settings(
            host="0.0.0.0",
            data_dir=tmp_path / "app",
            database_url=f"sqlite:///{tmp_path / 'app' / 'hydro.db'}",
            auth_mode="oidc",
        )
    )
    try:
        rc = TestClient(app)
        health = rc.get("/api/health").json()
        assert health["security"]["auth_mode"] == "oidc"
        assert health["security"]["enforced_auth"] is False
        assert len(health["security"]["warnings"]) >= 2
    finally:
        db.dispose_database()


def test_security_headers_csp_and_cache_control_policies(tmp_path: Path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        '<!doctype html><html><head><script src="/theme-init.js"></script></head>'
        '<body><div id="root"></div><script type="module" src="/assets/app-123.js"></script></body></html>',
        encoding="utf-8",
    )
    (dist / "theme-init.js").write_text("window.__hydroTheme=1;", encoding="utf-8")
    (dist / "assets" / "app-123.js").write_text("console.log('hydro');", encoding="utf-8")

    app = create_app(
        Settings(
            data_dir=tmp_path / "data",
            database_url="sqlite:///:memory:",
            frontend_dist=dist,
        )
    )
    try:
        c = TestClient(app)
        root = c.get("/")
        assert root.status_code == 200
        assert root.headers["X-Content-Type-Options"] == "nosniff"
        assert root.headers["X-Frame-Options"] == "DENY"
        assert root.headers["Referrer-Policy"] == "no-referrer"
        assert "Content-Security-Policy" in root.headers
        assert "script-src 'self'" in root.headers["Content-Security-Policy"]
        assert root.headers["Cache-Control"] == "no-cache"

        asset = c.get("/assets/app-123.js")
        assert asset.status_code == 200
        assert asset.headers["Cache-Control"] == "public, max-age=31536000, immutable"

        api_res = c.get("/api/health")
        assert api_res.status_code == 200
        assert api_res.headers["Cache-Control"] == "no-store"

        docs_res = c.get("/docs")
        assert docs_res.status_code == 200
        assert "Content-Security-Policy" not in docs_res.headers
    finally:
        db.dispose_database()


def test_dns_rebinding_host_header_rejected(client):
    res = client.get("/api/health", headers={"Host": "evil.example.com"})
    assert res.status_code == 400
    assert res.json()["code"] == "invalid_host"


def test_cross_site_origin_and_sec_fetch_site_blocked_on_admin_mutations(client, headers):
    bad_origin = client.post(
        "/api/system/db-backup",
        headers={**headers, "Origin": "https://evil.example"},
        json={},
    )
    assert bad_origin.status_code == 403
    assert bad_origin.json()["code"] == "cross_site_forbidden"

    cross_fetch = client.post(
        "/api/update/apply",
        headers={**headers, "Sec-Fetch-Site": "cross-site"},
    )
    assert cross_fetch.status_code == 403
    assert cross_fetch.json()["code"] == "cross_site_forbidden"


def test_proxy_headers_beyond_xff_blocked_on_admin_routes(client, headers):
    for header_name in ("X-Real-IP", "CF-Connecting-IP", "True-Client-IP"):
        res = client.get("/api/system/workspaces", headers={**headers, header_name: "203.0.113.10"})
        assert res.status_code == 403
        assert res.json()["code"] == "local_admin_loopback_only"


def test_update_routes_require_local_admin_and_redact_host_paths(client, tmp_path: Path):
    local_status = client.get("/api/update/status")
    assert local_status.status_code == 200
    runtime = local_status.json()["runtime"]
    assert "executable_path" not in runtime
    assert "install_dir" not in runtime
    assert "app_bundle" not in runtime

    remote_app = create_app(
        Settings(
            host="0.0.0.0",
            data_dir=tmp_path / "upd",
            database_url=f"sqlite:///{tmp_path / 'upd' / 'hydro.db'}",
            auth_mode="none",
        )
    )
    try:
        rc = TestClient(remote_app)
        assert rc.get("/api/update/status").status_code == 403
        assert rc.post("/api/update/check").status_code == 403
        assert rc.post("/api/update/apply").status_code == 403
    finally:
        db.dispose_database()


def test_bounded_uploads_reject_oversized_files_early_413(client, headers):
    oversized = b"PK\x03\x04" + (b"A" * (1024 * 1024 + 128))
    for route, filename, content_type in (
        ("/api/projects/import-archive", "huge.hydroproj.zip", "application/zip"),
        ("/api/import/desktop-db", "huge.db", "application/octet-stream"),
        ("/api/system/db-restore", "huge.db", "application/octet-stream"),
    ):
        res = client.post(
            route,
            headers=headers,
            files={"file": (filename, io.BytesIO(oversized), content_type)},
        )
        assert res.status_code == 413
        assert res.json()["code"] == "file_too_large"


def test_rate_limiter_enforces_429_and_retry_after(client, headers):
    last_res = None
    for _ in range(31):
        last_res = client.post(
            "/api/reports/export",
            headers=headers,
            json={"format": "txt", "title": "Rate Test", "metadata": {"k": "v"}},
        )
        if last_res.status_code == 429:
            break
    assert last_res is not None
    assert last_res.status_code == 429
    assert last_res.json()["code"] == "rate_limited"
    assert int(last_res.headers["Retry-After"]) >= 1


def test_request_id_sanitized_clamped_and_db_restore_malformed_json_returns_422(client, headers):
    long_id = "req-" + ("x" * 100) + "!!?"
    res = client.get("/api/meta", headers={"X-Request-ID": long_id})
    assert res.status_code == 200
    echoed = res.headers["X-Request-ID"]
    assert 1 <= len(echoed) <= 64
    assert "!" not in echoed and "?" not in echoed

    bad_json = client.post(
        "/api/system/db-restore",
        headers=headers,
        json={"backup_filename": {"invalid": True}},
    )
    assert bad_json.status_code == 422
    assert bad_json.json()["code"] == "validation_error"


def test_trash_restore_session_does_not_restore_other_workspace_parent_project(
    client, headers, settings
):
    from app.core import security as sec
    from app.models import HydroSession, Project
    from app.services import db_admin as db_admin_service
    from app.services.projects import utcnow

    ws_a = headers["X-Session-ID"]
    ws_b_hash = sec.workspace_hash("other-workspace")
    ws_a_hash = sec.workspace_hash(ws_a)
    now = utcnow()

    with db.session_scope() as session:
        other_project = Project(
            workspace_id_hash=ws_b_hash,
            name="Baska Alan Projesi",
            deleted_at=now,
        )
        session.add(other_project)
        session.flush()
        own_session = HydroSession(
            workspace_id_hash=ws_a_hash,
            project_id=other_project.id,
            name="Alan A Kesiti",
            deleted_at=now,
        )
        session.add(own_session)
        session.flush()
        sess_id = own_session.id
        proj_id = other_project.id

    with db.session_scope() as session:
        restored = db_admin_service.restore_trash_item(
            session, ws_a_hash, entity_type="session", entity_id=sess_id
        )
        assert restored["restored_sessions"] == 1

    with db.session_scope() as session:
        still_deleted = session.get(Project, proj_id)
        assert still_deleted is not None
        assert still_deleted.deleted_at is not None


def test_trusted_hosts_normalizes_ports_and_ipv6_brackets(tmp_path: Path):
    s = Settings(
        host="0.0.0.0",
        data_dir=tmp_path / "th",
        database_url=f"sqlite:///{tmp_path / 'th' / 'hydro.db'}",
        trusted_hosts=("App.Example.Com:8443", "[::1]:8080"),
    )
    assert s.trusted_hosts == ("app.example.com", "::1")

    app = create_app(s)
    try:
        c = TestClient(app)
        assert c.get("/api/health", headers={"Host": "app.example.com:8443"}).status_code == 200
        assert c.get("/api/health", headers={"Host": "[::1]"}).status_code == 200
        bad = c.get("/api/health", headers={"Host": "rogue.example"})
        assert bad.status_code == 400
        assert bad.json()["code"] == "invalid_host"
    finally:
        db.dispose_database()


def test_db_maintenance_clean_exports_removes_nested_directories(client, headers, settings):
    adhoc_dir = settings.exports_dir / "_adhoc"
    sess_dir = settings.exports_dir / "session-nested"
    adhoc_dir.mkdir(parents=True, exist_ok=True)
    sess_dir.mkdir(parents=True, exist_ok=True)
    f1 = adhoc_dir / "a.txt"
    f2 = sess_dir / "b.pdf"
    f1.write_text("report a", encoding="utf-8")
    f2.write_bytes(b"%PDF-1.4\ntest")

    res = client.post(
        "/api/system/db-maintenance",
        headers=headers,
        json={"clean_exports": True, "clean_orphan_uploads": False},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["removed_export_files"] == 2
    assert not f1.exists()
    assert not f2.exists()
    assert not adhoc_dir.exists()
    assert not sess_dir.exists()
    assert settings.exports_dir.exists()


def test_update_status_redacts_job_verified_path(client, monkeypatch):
    from app.api import system as system_api

    fake_status = system_api.WEB_UPDATE_MANAGER.get_status()
    fake_status["job"]["verified_path"] = "/Users/secret/path/HydroWeb.dmg"
    monkeypatch.setattr(system_api.WEB_UPDATE_MANAGER, "get_status", lambda: fake_status)

    res = client.get("/api/update/status")
    assert res.status_code == 200
    assert res.json()["job"]["verified_path"] == ""


def test_slice1_form_optimistic_concurrency_and_etag(client, headers):
    sess = client.post("/api/sessions", json={"name": "F1 Concurrency"}, headers=headers).json()
    sid = sess["id"]

    # Initial GET returns ETag "0"
    g0 = client.get(f"/api/sessions/{sid}/forms/cleaning", headers=headers)
    assert g0.status_code == 200
    assert g0.headers.get("etag") == '"0"'

    # Matching If-Match "0" succeeds -> revision becomes 1, ETag "1"
    u1 = client.put(
        f"/api/sessions/{sid}/forms/cleaning",
        headers={**headers, "If-Match": '"0"'},
        json={"form_date": "2026-11-23", "extracted_data": {"notes": "rev1"}},
    )
    assert u1.status_code == 200, u1.text
    assert u1.headers.get("etag") == '"1"'
    assert u1.json()["form"]["revision"] == 1

    # Stale If-Match "0" returns 409 revision_conflict with current form payload
    stale_hdr = client.put(
        f"/api/sessions/{sid}/forms/cleaning",
        headers={**headers, "If-Match": '"0"'},
        json={"form_date": "2026-11-23", "extracted_data": {"notes": "stale"}},
    )
    assert stale_hdr.status_code == 409
    err = stale_hdr.json()
    assert err["code"] == "revision_conflict"
    assert err["details"]["expected_revision"] == 0
    assert err["details"]["current_revision"] == 1
    assert err["details"]["current"]["revision"] == 1

    # Stale body revision (without If-Match header) also returns 409
    stale_body = client.put(
        f"/api/sessions/{sid}/forms/cleaning",
        headers=headers,
        json={"revision": 0, "extracted_data": {"notes": "stale-body"}},
    )
    assert stale_body.status_code == 409

    # Matching revision 1 succeeds -> revision becomes 2
    u2 = client.put(
        f"/api/sessions/{sid}/forms/cleaning",
        headers={**headers, "If-Match": '"1"'},
        json={"form_date": "2026-11-23", "extracted_data": {"notes": "rev2"}},
    )
    assert u2.status_code == 200
    assert u2.json()["form"]["revision"] == 2


def test_slice1_strict_write_models_and_list_bounds():
    import pydantic
    import pytest
    from app import schemas

    # F15: extra="forbid" on write/analysis schemas rejects typo fields
    with pytest.raises(pydantic.ValidationError):
        schemas.SectionFormUpdateRequest.model_validate({"unknown_typo": 123})
    with pytest.raises(pydantic.ValidationError):
        schemas.CoefficientARequest.model_validate(
            {"temperature_c": 15.0, "pressure_bar": 80.0, "extra_field": True}
        )

    # F6: realistic upper bounds on list inputs
    with pytest.raises(pydantic.ValidationError):
        schemas.GeometryIn.model_validate(
            {
                "sections": [
                    {"outside_diameter_mm": 323.9, "wall_thickness_mm": 6.4, "length_m": 10.0}
                ]
                * 2001
            }
        )
    with pytest.raises(pydantic.ValidationError):
        schemas.PressurizationRampRequest.model_validate(
            {
                "readings": [
                    {"elapsed_min": 1.0, "pressure_bar": 10.0, "cumulative_added_volume_m3": 0.1}
                ]
                * 5001,
                "test_pressure_100_smys_bar": 100.0,
                "total_filled_volume_m3": 500.0,
            }
        )
    with pytest.raises(pydantic.ValidationError):
        schemas.ThermalBalanceRequest.model_validate(
            {"records": [{"pressure_bar": 80.0, "temperature_c": 15.0}] * 10001}
        )


def test_slice1_heavy_endpoint_rate_limits_and_workspace_isolation(tmp_path: Path):
    from app.core.rate_limit import RATE_LIMITER

    s = Settings(
        host="127.0.0.1",
        data_dir=tmp_path / "rl",
        database_url=f"sqlite:///{tmp_path / 'rl' / 'hydro.db'}",
        rate_limit_enabled=True,
    )
    app = create_app(s)
    try:
        with TestClient(app) as tc:
            ws1 = {"X-Session-ID": "ws-alpha"}
            ws2 = {"X-Session-ID": "ws-beta"}
            sess1 = tc.post("/api/sessions", json={"name": "RL1"}, headers=ws1).json()
            proj1 = tc.post("/api/projects", json={"name": "RLProj"}, headers=ws1).json()
            bkp = tc.post("/api/system/db-backup", headers=ws1, json={"reason": "rl"}).json()

            RATE_LIMITER.reset()
            # Archive limit=15 -> 16th call for ws1 returns 429, while ws2 on same IP is NOT blocked
            for _ in range(15):
                assert (
                    tc.get(f"/api/projects/{proj1['id']}/archive", headers=ws1).status_code == 200
                )
            r429 = tc.get(f"/api/projects/{proj1['id']}/archive", headers=ws1)
            assert r429.status_code == 429
            assert r429.json()["code"] == "rate_limited"

            proj2 = tc.post("/api/projects", json={"name": "RLProj2"}, headers=ws2).json()
            assert tc.get(f"/api/projects/{proj2['id']}/archive", headers=ws2).status_code == 200

            # DB backup download limit=20 -> 21st call returns 429
            RATE_LIMITER.reset()
            for _ in range(20):
                assert (
                    tc.get(f"/api/system/db-backups/{bkp['filename']}", headers=ws1).status_code
                    == 200
                )
            assert (
                tc.get(f"/api/system/db-backups/{bkp['filename']}", headers=ws1).status_code == 429
            )

            # Session export limit=30 -> 31st call returns 429
            RATE_LIMITER.reset()
            for _ in range(30):
                assert (
                    tc.get(
                        f"/api/sessions/{sess1['id']}/export?format=txt", headers=ws1
                    ).status_code
                    == 200
                )
            assert (
                tc.get(f"/api/sessions/{sess1['id']}/export?format=txt", headers=ws1).status_code
                == 429
            )
    finally:
        db.dispose_database()


def test_slice1_auth_mode_fails_closed_even_with_allow_remote_or_loopback(
    tmp_path: Path, monkeypatch
):
    from app.core.config import validate_bind_security

    err_remote = validate_bind_security(
        Settings(host="0.0.0.0", data_dir=tmp_path, auth_mode="oidc", allow_remote=True)
    )
    assert err_remote is not None and "HYDRO_AUTH_MODE" in err_remote

    err_loop = validate_bind_security(
        Settings(host="127.0.0.1", data_dir=tmp_path, auth_mode="oidc", allow_remote=False)
    )
    assert err_loop is not None and "HYDRO_AUTH_MODE" in err_loop

    repo_root = Path(__file__).resolve().parents[3]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from webapp import run_web

    monkeypatch.setenv("HYDRO_AUTH_MODE", "oidc")
    monkeypatch.setenv("HYDRO_ALLOW_REMOTE", "1")
    code = run_web.main(["--host", "127.0.0.1", "--data-dir", str(tmp_path / "rw")])
    assert code == 2


def test_slice2_meta_exposes_ocr_timeout_and_admin_flags_without_token_leak(tmp_path: Path):
    s = Settings(
        host="0.0.0.0",
        data_dir=tmp_path / "m2",
        database_url=f"sqlite:///{tmp_path / 'm2' / 'hydro.db'}",
        ocr_timeout_s=900,
        local_admin_token="top-secret-token-99",
    )
    app = create_app(s)
    try:
        with TestClient(app) as tc:
            res = tc.get("/api/meta")
            assert res.status_code == 200
            body = res.json()
            assert body["limits"]["ocr_timeout_s"] == 900
            assert body["features"]["admin_token_configured"] is True
            assert body["features"]["is_loopback_host"] is False
            assert "top-secret-token-99" not in res.text
    finally:
        db.dispose_database()


def test_slice4_stream_upload_to_tempfile_and_json_body_size_cap(tmp_path: Path):
    import asyncio

    import pytest
    from app.core import security
    from app.core.errors import AppError

    class FakeUpload:
        def __init__(self, chunks: list[bytes]) -> None:
            self._chunks = list(chunks)

        async def read(self, _size: int = 65536) -> bytes:
            return self._chunks.pop(0) if self._chunks else b""

    ok_path = asyncio.run(
        security.stream_upload_to_tempfile(
            FakeUpload([b"hello ", b"world"]), max_bytes=64, suffix=".bin", temp_dir=tmp_path
        )
    )
    assert ok_path.is_file()
    assert ok_path.read_bytes() == b"hello world"
    ok_path.unlink(missing_ok=True)

    with pytest.raises(AppError) as exc_info:
        asyncio.run(
            security.stream_upload_to_tempfile(
                FakeUpload([b"a" * 40, b"b" * 40]),
                max_bytes=64,
                suffix=".oversize",
                temp_dir=tmp_path,
            )
        )
    assert exc_info.value.status_code == 413
    assert exc_info.value.code == "file_too_large"
    assert list(tmp_path.glob("*.oversize")) == []

    # JSON body size cap middleware rejects >32 MB Content-Length before reading into RAM
    s = Settings(
        host="127.0.0.1",
        data_dir=tmp_path / "jcap",
        database_url=f"sqlite:///{tmp_path / 'jcap' / 'hydro.db'}",
    )
    app = create_app(s)
    try:
        with TestClient(app) as tc:
            oversize = tc.post(
                "/api/sessions",
                content=b'{"name":"x"}',
                headers={
                    "Content-Type": "application/json",
                    "Content-Length": str(40 * 1024 * 1024),
                },
            )
            assert oversize.status_code == 413
            assert oversize.json()["code"] == "payload_too_large"
    finally:
        db.dispose_database()


def test_slice4_export_ttl_cleanup_and_tempfile_project_archive(tmp_path: Path):
    import io
    import os
    import time
    import zipfile

    from app.services import project_archive, reports

    s = Settings(
        host="127.0.0.1",
        data_dir=tmp_path / "exp",
        database_url=f"sqlite:///{tmp_path / 'exp' / 'hydro.db'}",
    )
    app = create_app(s)
    try:
        with TestClient(app) as tc:
            stale_dir = s.exports_dir / "stale-session"
            stale_dir.mkdir(parents=True, exist_ok=True)
            stale_file = stale_dir / "old-report.txt"
            stale_file.write_text("stale", encoding="utf-8")
            old_ts = time.time() - 90_000
            os.utime(stale_file, (old_ts, old_ts))

            fresh_dir = s.exports_dir / "fresh-session"
            fresh_dir.mkdir(parents=True, exist_ok=True)
            fresh_file = fresh_dir / "fresh-report.txt"
            fresh_file.write_text("fresh", encoding="utf-8")

            if hasattr(reports, "_reset_export_prune_throttle"):
                reports._reset_export_prune_throttle()

            sess = tc.post("/api/sessions", json={"name": "TTL Kesit"}).json()
            exp_res = tc.get(f"/api/sessions/{sess['id']}/export", params={"format": "txt"})
            assert exp_res.status_code == 200
            assert not stale_file.exists()
            assert fresh_file.exists()

            assert hasattr(project_archive, "export_project_archive_to_tempfile")
            proj = tc.post("/api/projects", json={"name": "Arsiv Projesi", "code": "ARS-01"}).json()
            arch_res = tc.get(f"/api/projects/{proj['id']}/archive")
            assert arch_res.status_code == 200
            with zipfile.ZipFile(io.BytesIO(arch_res.content), "r") as zf:
                assert "manifest.json" in zf.namelist()
                assert "project.json" in zf.namelist()
            # Temp archive file inside data_dir must be unlinked by background cleanup
            assert list(s.data_dir.glob("hydro_archive_*.zip")) == []
    finally:
        db.dispose_database()


def test_slice4_db_restore_maintenance_barrier_returns_503_retry_after(tmp_path: Path):
    s = Settings(
        host="127.0.0.1",
        data_dir=tmp_path / "maint",
        database_url=f"sqlite:///{tmp_path / 'maint' / 'hydro.db'}",
    )
    app = create_app(s)
    try:
        with TestClient(app) as tc:
            assert hasattr(db, "begin_restore_swap") and hasattr(db, "end_restore_swap")
            db.begin_restore_swap(timeout_s=0.5)
            try:
                blocked = tc.get("/api/sessions")
                assert blocked.status_code == 503
                assert blocked.headers.get("Retry-After") == "2"
                assert blocked.json()["code"] == "db_restoring"

                health = tc.get("/api/health")
                assert health.status_code == 200
            finally:
                db.end_restore_swap()

            recovered = tc.get("/api/sessions")
            assert recovered.status_code == 200
    finally:
        db.dispose_database()


def test_generate_sample_project_deduplicates_and_enforces_rate_limit(tmp_path: Path):
    from app.core.rate_limit import RATE_LIMITER

    RATE_LIMITER.reset()
    s = Settings(
        host="127.0.0.1",
        data_dir=tmp_path / "sample_rl",
        database_url=f"sqlite:///{tmp_path / 'sample_rl' / 'hydro.db'}",
        rate_limit_enabled=True,
    )
    app = create_app(s)
    ws_headers = {"X-Session-ID": "sample-rl-ws"}
    try:
        with TestClient(app) as tc:
            first = tc.post(
                "/api/projects/generate-sample",
                headers=ws_headers,
                json={"scenario": "mixed", "section_count": 2, "code": "DEMO-TUR"},
            )
            assert first.status_code == 201, first.text
            first_body = first.json()
            assert first_body["reused"] is False

            second = tc.post(
                "/api/projects/generate-sample",
                headers=ws_headers,
                json={"scenario": "mixed", "section_count": 2, "code": "DEMO-TUR"},
            )
            assert second.status_code == 201, second.text
            second_body = second.json()
            assert second_body["reused"] is True
            assert second_body["project"]["id"] == first_body["project"]["id"]

            # Consume remaining requests in 5/min bucket -> 6th fails with 429
            for _ in range(3):
                r = tc.post(
                    "/api/projects/generate-sample",
                    headers=ws_headers,
                    json={"scenario": "passing", "section_count": 1},
                )
                assert r.status_code == 201
            limited = tc.post(
                "/api/projects/generate-sample",
                headers=ws_headers,
                json={"scenario": "passing", "section_count": 1},
            )
            assert limited.status_code == 429
            assert limited.json()["code"] == "rate_limited"
    finally:
        RATE_LIMITER.reset()
        db.dispose_database()


def test_strict_write_models_reject_unknown_fields_via_http(client, headers):
    bad_sess = client.post(
        "/api/sessions",
        headers=headers,
        json={"name": "Typo Test", "smysMpa": 999},
    )
    assert bad_sess.status_code == 422
    assert bad_sess.json()["code"] == "validation_error"

    bad_sample = client.post(
        "/api/projects/generate-sample",
        headers=headers,
        json={"unexpected_field": True},
    )
    assert bad_sample.status_code == 422
    assert bad_sample.json()["code"] == "validation_error"
