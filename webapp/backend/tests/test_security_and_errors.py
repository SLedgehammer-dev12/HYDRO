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
