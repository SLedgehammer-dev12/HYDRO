"""Tests for R4: OIDC PKCE login, HttpOnly sessions, RBAC, and two-person approval."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from app import db
from app.core import auth as auth_core
from app.core.auth import (
    OIDC_STATE_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    AuthPrincipal,
    issue_session_cookie,
)
from app.core.config import Settings
from app.main import create_app
from app.models import AuditEvent
from app.services import db_admin as db_admin_service
from fastapi.testclient import TestClient
from sqlalchemy import select


def _oidc_settings(tmp_path: Path, db_name: str = "r4_auth.db") -> Settings:
    return Settings(
        database_url=f"sqlite:///{(tmp_path / db_name).as_posix()}",
        data_dir=tmp_path / "data",
        frontend_dist=tmp_path / "dist",
        auth_mode="oidc",
        auth_session_secret="r4-test-session-secret-0123456789",
        oidc_issuer="https://idp.example.com",
        oidc_client_id="hydro-web-client",
        auth_session_ttl_s=3600,
        auth_idle_timeout_s=600,
    )


def test_oidc_pkce_login_callback_me_logout_and_fail_closed(tmp_path: Path):
    settings = _oidc_settings(tmp_path)
    app = create_app(settings)
    try:
        with TestClient(app) as client:
            # 1) Public health endpoint remains reachable; protected API endpoints fail closed (401)
            assert client.get("/api/health").status_code == 200
            denied = client.get("/api/projects")
            assert denied.status_code == 401
            assert denied.json()["code"] == "authentication_required"

            me_anon = client.get("/api/auth/me")
            assert me_anon.status_code == 200
            assert me_anon.json()["enforced_auth"] is True
            assert me_anon.json()["authenticated"] is False

            # 2) Start OIDC Authorization Code + PKCE login
            login_res = client.get("/api/auth/login?redirect=0")
            assert login_res.status_code == 200, login_res.text
            login_body = login_res.json()
            assert "code_challenge=" in login_body["authorize_url"]
            assert "code_challenge_method=S256" in login_body["authorize_url"]
            assert OIDC_STATE_COOKIE_NAME in login_res.cookies

            # 3) Exchange authorization code at callback -> sets HttpOnly SameSite=Lax session cookie
            with patch(
                "app.api.auth._exchange_oidc_code",
                return_value={
                    "sub": "u-op-1",
                    "email": "operator@botas.local",
                    "name": "Operator One",
                    "role": "operator",
                },
            ):
                cb_res = client.get(
                    "/api/auth/callback",
                    params={"code": "auth-code-123", "state": login_body["state"]},
                )
            assert cb_res.status_code == 200, cb_res.text
            assert cb_res.json()["authenticated"] is True
            assert cb_res.json()["user"]["role"] == "operator"
            set_cookie_hdr = cb_res.headers.get("set-cookie", "")
            assert "HttpOnly" in set_cookie_hdr
            assert "SameSite=lax" in set_cookie_hdr or "samesite=lax" in set_cookie_hdr.lower()

            # 4) Signed-in operator can access /api/auth/me and /api/projects
            me_res = client.get("/api/auth/me")
            assert me_res.status_code == 200
            assert me_res.json()["authenticated"] is True
            assert me_res.json()["user"]["sub"] == "u-op-1"
            assert client.get("/api/projects").status_code == 200

            # 5) Logout clears cookie and blocks subsequent API access
            logout_res = client.post("/api/auth/logout")
            assert logout_res.status_code == 200
            assert client.get("/api/projects").status_code == 401
    finally:
        db.dispose_database()


def test_rbac_role_matrix_and_idle_timeout(tmp_path: Path):
    settings = _oidc_settings(tmp_path, db_name="r4_rbac.db")
    app = create_app(settings)
    op_cookie = issue_session_cookie(
        AuthPrincipal(sub="op-1", name="Op", role="operator", workspace="team-a"),
        settings,
    )
    sup_cookie = issue_session_cookie(
        AuthPrincipal(sub="sup-1", name="Sup", role="supervisor", workspace="team-a"),
        settings,
    )
    adm_cookie = issue_session_cookie(
        AuthPrincipal(sub="adm-1", name="Adm", role="admin", workspace="team-a"),
        settings,
    )
    stale_cookie = issue_session_cookie(
        AuthPrincipal(sub="op-stale", role="operator", workspace="team-a"),
        settings,
        now=1000.0,
    )

    try:
        with TestClient(app) as client:
            # Operator can use app endpoints, but is forbidden (403) on admin DB endpoints
            client.cookies.set(SESSION_COOKIE_NAME, op_cookie)
            assert client.get("/api/projects").status_code == 200
            op_admin = client.get("/api/system/db-backups")
            assert op_admin.status_code == 403
            assert op_admin.json()["code"] == "insufficient_role"

            # Supervisor also cannot access admin-only DB endpoints
            client.cookies.set(SESSION_COOKIE_NAME, sup_cookie)
            assert client.get("/api/system/db-backups").status_code == 403

            # Admin can access admin DB endpoints
            client.cookies.set(SESSION_COOKIE_NAME, adm_cookie)
            assert client.get("/api/system/db-backups").status_code == 200

            # Stale cookie fails idle timeout check
            client.cookies.set(SESSION_COOKIE_NAME, stale_cookie)
            assert client.get("/api/projects").status_code == 401
            assert auth_core.parse_session_cookie(stale_cookie, settings) is None
    finally:
        db.dispose_database()


def test_two_person_approval_for_session_finalize_and_audit_trail(tmp_path: Path):
    settings = _oidc_settings(tmp_path, db_name="r4_finalize.db")
    app = create_app(settings)
    op_cookie = issue_session_cookie(
        AuthPrincipal(sub="op-1", name="Operator", role="operator", workspace="shared-ws"),
        settings,
    )
    sup_cookie = issue_session_cookie(
        AuthPrincipal(sub="sup-1", name="Supervisor", role="supervisor", workspace="shared-ws"),
        settings,
    )

    try:
        with TestClient(app) as client:
            client.cookies.set(SESSION_COOKIE_NAME, op_cookie)
            sess_res = client.post("/api/sessions", json={"name": "HAT-FINAL-01"})
            assert sess_res.status_code == 201
            session_id = sess_res.json()["id"]

            # Direct finalization without approval -> 403 approval_required
            unapproved = client.put(
                f"/api/sessions/{session_id}",
                json={"status": "final"},
            )
            assert unapproved.status_code == 403
            assert unapproved.json()["code"] == "approval_required"

            # Operator requests two-person approval
            req_res = client.post(
                "/api/approvals",
                json={
                    "action": "session_finalize",
                    "target_id": session_id,
                    "reason": "Tum saha kontrolleri tamamlandi",
                },
            )
            assert req_res.status_code == 201
            approval_id = req_res.json()["id"]
            assert req_res.json()["status"] == "pending"

            # Same actor (even with supervisor role on another request) cannot self-approve
            client.cookies.set(SESSION_COOKIE_NAME, sup_cookie)
            self_req = client.post(
                "/api/approvals",
                json={
                    "action": "session_finalize",
                    "target_id": session_id,
                    "reason": "Self request test",
                },
            )
            assert self_req.status_code == 201
            self_dec = client.post(
                f"/api/approvals/{self_req.json()['id']}/decide",
                json={"decision": "approved"},
            )
            assert self_dec.status_code == 403
            assert self_dec.json()["code"] == "self_approval_forbidden"

            # Second actor (supervisor) approves the operator's request
            client.cookies.set(SESSION_COOKIE_NAME, sup_cookie)
            dec_res = client.post(
                f"/api/approvals/{approval_id}/decide",
                json={"decision": "approved", "note": "Onaylandi"},
            )
            assert dec_res.status_code == 200, dec_res.text
            assert dec_res.json()["status"] == "approved"
            assert dec_res.json()["requested_by"] == "operator:op-1"
            assert dec_res.json()["approved_by"] == "supervisor:sup-1"

            # Finalize succeeds now (by operator) and consumes the approval
            client.cookies.set(SESSION_COOKIE_NAME, op_cookie)
            fin_res = client.put(
                f"/api/sessions/{session_id}",
                json={"status": "final"},
            )
            assert fin_res.status_code == 200, fin_res.text
            assert fin_res.json()["status"] == "final"

            listed = client.get("/api/approvals", params={"action": "session_finalize"}).json()[
                "items"
            ]
            consumed_row = next(item for item in listed if item["id"] == approval_id)
            assert consumed_row["status"] == "consumed"

            # Audit trail contains both requester and approver
            with db.session_scope() as s:
                evt = (
                    s.execute(
                        select(AuditEvent).where(
                            AuditEvent.action == "session.finalized",
                            AuditEvent.entity_id == session_id,
                        )
                    )
                    .scalars()
                    .first()
                )
                assert evt is not None
                assert evt.after is not None
                assert evt.after["requested_by"] == "operator:op-1"
                assert evt.after["approved_by"] == "supervisor:sup-1"
    finally:
        db.dispose_database()


def test_two_person_approval_for_db_restore(tmp_path: Path):
    settings = _oidc_settings(tmp_path, db_name="r4_restore.db")
    app = create_app(settings)
    adm1_cookie = issue_session_cookie(
        AuthPrincipal(sub="adm-1", name="Admin One", role="admin", workspace="ops-ws"),
        settings,
    )
    adm2_cookie = issue_session_cookie(
        AuthPrincipal(sub="adm-2", name="Admin Two", role="admin", workspace="ops-ws"),
        settings,
    )

    try:
        with TestClient(app) as client:
            client.cookies.set(SESSION_COOKIE_NAME, adm1_cookie)
            backup_info = db_admin_service.create_db_backup(settings, reason="r4_test")
            fname = backup_info["filename"]

            # Restore without approval -> 403 approval_required
            blocked = client.post("/api/system/db-restore", json={"backup_filename": fname})
            assert blocked.status_code == 403
            assert blocked.json()["code"] == "approval_required"

            # Admin-1 requests restore approval and tries self-approval -> 403 self_approval_forbidden
            req_res = client.post(
                "/api/approvals",
                json={"action": "db_restore", "target_id": fname, "reason": "Rollback drill"},
            )
            assert req_res.status_code == 201
            approval_id = req_res.json()["id"]

            self_res = client.post(
                f"/api/approvals/{approval_id}/decide",
                json={"decision": "approved"},
            )
            assert self_res.status_code == 403
            assert self_res.json()["code"] == "self_approval_forbidden"

            # Admin-2 approves -> Admin-1 executes restore
            client.cookies.set(SESSION_COOKIE_NAME, adm2_cookie)
            ok_dec = client.post(
                f"/api/approvals/{approval_id}/decide",
                json={"decision": "approved", "note": "Onayli geri yukleme"},
            )
            assert ok_dec.status_code == 200

            client.cookies.set(SESSION_COOKIE_NAME, adm1_cookie)
            restored = client.post("/api/system/db-restore", json={"backup_filename": fname})
            assert restored.status_code == 200, restored.text
            assert restored.json()["restored"] is True
            assert restored.json()["source"] == fname
    finally:
        db.dispose_database()
