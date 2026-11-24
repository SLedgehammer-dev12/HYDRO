"""OIDC login/callback/logout and two-person approval routes."""

from __future__ import annotations

import base64
import json
import secrets
import time
import urllib.parse
import urllib.request
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from .. import schemas
from ..core.auth import (
    OIDC_STATE_COOKIE_NAME,
    ROLE_ADMIN,
    ROLE_OPERATOR,
    ROLE_SUPERVISOR,
    AuthPrincipal,
    build_oidc_authorize_url,
    clear_auth_cookies,
    generate_pkce_pair,
    issue_session_cookie,
    normalize_role,
    require_role,
    set_oidc_state_cookie,
    set_session_cookie,
    sign_payload,
    verify_payload,
)
from ..core.config import Settings
from ..core.errors import AppError
from ..core.timeutil import json_safe, utcnow
from ..db import get_db
from ..models import ApprovalRequest
from ..services import audit
from .deps import Workspace, get_settings, get_workspace

router = APIRouter(tags=["auth"])


def _principal_dict(principal: AuthPrincipal | None) -> dict[str, Any] | None:
    if principal is None:
        return None
    return {
        "sub": principal.sub,
        "email": principal.email,
        "name": principal.name,
        "role": principal.role,
        "workspace": principal.workspace,
    }


def _resolve_redirect_uri(request: Request, settings: Settings) -> str:
    if settings.oidc_redirect_uri.strip():
        return settings.oidc_redirect_uri.strip()
    return str(request.url_for("oidc_callback"))


def _decode_jwt_unverified_claims(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    padded = parts[1] + ("=" * (-len(parts[1]) % 4))
    try:
        data = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _exchange_oidc_code(
    settings: Settings,
    *,
    code: str,
    code_verifier: str,
    redirect_uri: str,
) -> dict[str, Any]:
    """Exchange authorization code + PKCE verifier at OIDC token & userinfo endpoints."""

    issuer = settings.oidc_issuer.rstrip("/")
    token_url = f"{issuer}/oauth/token"
    body = {
        "grant_type": "authorization_code",
        "client_id": settings.oidc_client_id,
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
    }
    if settings.oidc_client_secret.strip():
        body["client_secret"] = settings.oidc_client_secret.strip()
    req = urllib.request.Request(
        token_url,
        data=urllib.parse.urlencode(body).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
        token_data = json.loads(resp.read().decode("utf-8"))
    claims: dict[str, Any] = {}
    id_token = token_data.get("id_token")
    if isinstance(id_token, str) and id_token:
        claims.update(_decode_jwt_unverified_claims(id_token))
    access_token = token_data.get("access_token")
    if isinstance(access_token, str) and access_token and not claims.get("sub"):
        info_req = urllib.request.Request(
            f"{issuer}/userinfo",
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            method="GET",
        )
        with urllib.request.urlopen(info_req, timeout=10) as info_resp:  # noqa: S310
            userinfo = json.loads(info_resp.read().decode("utf-8"))
            if isinstance(userinfo, dict):
                claims.update(userinfo)
    return claims


@router.get("/auth/me")
def auth_me(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    principal = getattr(request.state, "principal", None)
    return {
        "auth_mode": settings.auth_mode,
        "enforced_auth": settings.has_enforced_auth,
        "authenticated": principal is not None,
        "user": _principal_dict(principal),
    }


@router.get("/auth/login")
def oidc_login(
    request: Request,
    next_path: str = Query(default="/", alias="next"),
    redirect: int = Query(default=1, ge=0, le=1),
    settings: Settings = Depends(get_settings),
):
    if not settings.has_enforced_auth:
        raise AppError(
            "auth_not_configured",
            "OIDC kimlik dogrulamasi bu sunucuda yapilandirilmamis.",
            status_code=400,
        )
    safe_next = next_path if next_path.startswith("/") and not next_path.startswith("//") else "/"
    state = secrets.token_urlsafe(24)
    verifier, challenge = generate_pkce_pair()
    redirect_uri = _resolve_redirect_uri(request, settings)
    authorize_url = build_oidc_authorize_url(
        settings,
        state=state,
        code_challenge=challenge,
        redirect_uri=redirect_uri,
    )
    state_cookie = sign_payload(
        {
            "state": state,
            "verifier": verifier,
            "next": safe_next,
            "exp": int(time.time()) + 600,
        },
        settings.auth_session_secret,
    )
    response: Response
    if redirect:
        response = RedirectResponse(url=authorize_url, status_code=302)
    else:
        response = JSONResponse(
            status_code=200,
            content={"authorize_url": authorize_url, "state": state},
        )
    set_oidc_state_cookie(response, state_cookie, settings)
    return response


@router.get("/auth/callback", name="oidc_callback")
def oidc_callback(
    request: Request,
    code: str = Query(min_length=1),
    state: str = Query(min_length=1),
    db: OrmSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    workspace: Workspace = Depends(get_workspace),
):
    if not settings.has_enforced_auth:
        raise AppError(
            "auth_not_configured",
            "OIDC kimlik dogrulamasi bu sunucuda yapilandirilmamis.",
            status_code=400,
        )
    state_data = verify_payload(
        request.cookies.get(OIDC_STATE_COOKIE_NAME),
        settings.auth_session_secret,
    )
    if (
        state_data is None
        or float(state_data.get("exp", 0)) <= time.time()
        or str(state_data.get("state") or "") != state
    ):
        raise AppError(
            "invalid_oidc_state",
            "OIDC durum dogrulamasi basarisiz veya suresi dolmus.",
            status_code=400,
        )

    redirect_uri = _resolve_redirect_uri(request, settings)
    try:
        claims = _exchange_oidc_code(
            settings,
            code=code,
            code_verifier=str(state_data.get("verifier") or ""),
            redirect_uri=redirect_uri,
        )
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            "oidc_exchange_failed",
            "OIDC yetkilendirme kodu dogrulanamadi.",
            status_code=502,
            details={"reason": str(exc)},
        ) from exc

    sub = str(claims.get("sub") or "").strip()
    if not sub:
        raise AppError("invalid_oidc_claims", "OIDC kimlik bilgisi 'sub' eksik.", status_code=401)
    role_raw = claims.get(settings.oidc_role_claim) or claims.get("roles") or claims.get("role")
    role = normalize_role(role_raw)
    ws_claim = claims.get("workspace")
    principal = AuthPrincipal(
        sub=sub,
        email=str(claims.get("email") or ""),
        name=str(claims.get("name") or claims.get("preferred_username") or sub),
        role=role,
        workspace=str(ws_claim).strip() if isinstance(ws_claim, str) and ws_claim.strip() else None,
    )
    session_token = issue_session_cookie(principal, settings)

    audit.record(
        db,
        action="auth.login",
        entity_type="auth_session",
        entity_id=sub[:64],
        workspace_hash=workspace.hash,
        actor=principal.actor,
        after={"role": principal.role, "email": principal.email},
    )
    db.commit()

    response = JSONResponse(
        status_code=200,
        content={"authenticated": True, "user": _principal_dict(principal)},
    )
    set_session_cookie(response, session_token, settings)
    response.delete_cookie(key=OIDC_STATE_COOKIE_NAME, path="/")
    return response


@router.post("/auth/logout")
def auth_logout(
    request: Request,
    db: OrmSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    workspace: Workspace = Depends(get_workspace),
) -> Response:
    principal = getattr(request.state, "principal", None)
    if principal is not None:
        audit.record(
            db,
            action="auth.logout",
            entity_type="auth_session",
            entity_id=principal.sub[:64],
            workspace_hash=workspace.hash,
            actor=principal.actor,
        )
        db.commit()
    response = JSONResponse(status_code=200, content={"ok": True})
    clear_auth_cookies(response, settings)
    return response


def _serialize_approval(row: ApprovalRequest) -> dict[str, Any]:
    return {
        "id": row.id,
        "action": row.action,
        "target_id": row.target_id,
        "status": row.status,
        "requested_by": row.requested_by,
        "requested_role": row.requested_role,
        "approved_by": row.approved_by,
        "approved_role": row.approved_role,
        "reason": row.reason,
        "decision_note": row.decision_note,
        "payload": row.payload or {},
        "created_at": row.created_at,
        "decided_at": row.decided_at,
        "consumed_at": row.consumed_at,
    }


def consume_two_person_approval(
    db: OrmSession,
    workspace_hash: str,
    *,
    action: str,
    target_id: str,
) -> ApprovalRequest:
    """Find and consume an approved two-person request or raise 403."""

    row = (
        db.execute(
            select(ApprovalRequest)
            .where(
                ApprovalRequest.workspace_id_hash == workspace_hash,
                ApprovalRequest.action == action,
                ApprovalRequest.target_id == target_id,
                ApprovalRequest.status == "approved",
            )
            .order_by(ApprovalRequest.decided_at.desc(), ApprovalRequest.created_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    if row is None or not row.approved_by or row.approved_by == row.requested_by:
        raise AppError(
            "approval_required",
            "Bu islem icin iki kisi onayi (baska bir yetkili tarafindan onaylanmis talep) gereklidir.",
            status_code=403,
            details={"action": action, "target_id": target_id},
        )
    row.status = "consumed"
    row.consumed_at = utcnow()
    db.flush()
    return row


@router.get("/approvals")
def list_approvals(
    status: str | None = Query(default=None),
    action: str | None = Query(default=None),
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict[str, Any]:
    stmt = select(ApprovalRequest).where(ApprovalRequest.workspace_id_hash == workspace.hash)
    if status:
        stmt = stmt.where(ApprovalRequest.status == status)
    if action:
        stmt = stmt.where(ApprovalRequest.action == action)
    rows = db.execute(stmt.order_by(ApprovalRequest.created_at.desc())).scalars().all()
    return json_safe({"items": [_serialize_approval(row) for row in rows]})


@router.post("/approvals", status_code=201)
def create_approval_request(
    request: Request,
    payload: schemas.ApprovalCreateRequest,
    db: OrmSession = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> dict[str, Any]:
    principal = getattr(request.state, "principal", None)
    requester = principal.actor if principal is not None else workspace.actor
    req_role = principal.role if principal is not None else ROLE_OPERATOR
    row = ApprovalRequest(
        workspace_id_hash=workspace.hash,
        action=payload.action,
        target_id=payload.target_id,
        status="pending",
        requested_by=requester,
        requested_role=req_role,
        reason=payload.reason,
        payload=payload.payload,
    )
    db.add(row)
    db.flush()
    audit.record(
        db,
        action="approval.requested",
        entity_type="approval_request",
        entity_id=row.id,
        workspace_hash=workspace.hash,
        actor=requester,
        after={
            "action": row.action,
            "target_id": row.target_id,
            "requested_by": row.requested_by,
        },
    )
    db.commit()
    db.refresh(row)
    return json_safe(_serialize_approval(row))


@router.post("/approvals/{approval_id}/decide")
def decide_approval_request(
    request: Request,
    approval_id: str,
    payload: schemas.ApprovalDecisionRequest,
    db: OrmSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    workspace: Workspace = Depends(get_workspace),
) -> dict[str, Any]:
    row = db.execute(
        select(ApprovalRequest).where(
            ApprovalRequest.id == approval_id,
            ApprovalRequest.workspace_id_hash == workspace.hash,
        )
    ).scalar_one_or_none()
    if row is None:
        raise AppError("not_found", "Onay talebi bulunamadi.", status_code=404)
    if row.status != "pending":
        raise AppError(
            "approval_already_decided",
            f"Onay talebi zaten '{row.status}' durumunda.",
            status_code=409,
        )

    min_role = ROLE_ADMIN if row.action == "db_restore" else ROLE_SUPERVISOR
    principal = (
        require_role(request, min_role)
        if settings.has_enforced_auth
        else getattr(request.state, "principal", None)
    )
    approver = principal.actor if principal is not None else workspace.actor
    if approver == row.requested_by:
        raise AppError(
            "self_approval_forbidden",
            "Istegi olusturan kullanici kendi istegini onaylayamaz (iki kisi onayi gereklidir).",
            status_code=403,
        )

    row.status = payload.decision
    row.approved_by = approver
    row.approved_role = principal.role if principal is not None else ROLE_SUPERVISOR
    row.decision_note = payload.note
    row.decided_at = utcnow()
    audit.record(
        db,
        action=f"approval.{payload.decision}",
        entity_type="approval_request",
        entity_id=row.id,
        workspace_hash=workspace.hash,
        actor=approver,
        after={
            "approval_id": row.id,
            "action": row.action,
            "target_id": row.target_id,
            "requested_by": row.requested_by,
            "approved_by": row.approved_by,
            "status": row.status,
        },
    )
    db.commit()
    db.refresh(row)
    return json_safe(_serialize_approval(row))


__all__ = ["consume_two_person_approval", "router"]
