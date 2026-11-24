"""OIDC Authorization Code + PKCE, signed HttpOnly sessions, and RBAC helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any

from fastapi import Request, Response

from .config import Settings
from .errors import AppError

SESSION_COOKIE_NAME = "hydro_session"
OIDC_STATE_COOKIE_NAME = "hydro_oidc_state"

ROLE_OPERATOR = "operator"
ROLE_SUPERVISOR = "supervisor"
ROLE_ADMIN = "admin"
VALID_ROLES = frozenset({ROLE_OPERATOR, ROLE_SUPERVISOR, ROLE_ADMIN})
ROLE_RANK: dict[str, int] = {
    ROLE_OPERATOR: 1,
    ROLE_SUPERVISOR: 2,
    ROLE_ADMIN: 3,
}


@dataclass(frozen=True)
class AuthPrincipal:
    sub: str
    email: str = ""
    name: str = ""
    role: str = ROLE_OPERATOR
    workspace: str | None = None

    @property
    def actor(self) -> str:
        return f"{self.role}:{self.sub}"[:80]

    def has_role(self, min_role: str) -> bool:
        return ROLE_RANK.get(self.role, 0) >= ROLE_RANK.get(min_role, 99)


def normalize_role(raw: Any) -> str:
    """Normalize OIDC role or roles claim to the highest valid application role."""

    candidates: list[str] = []
    if isinstance(raw, str):
        candidates.extend(part.strip().lower() for part in raw.replace(",", " ").split())
    elif isinstance(raw, (list, tuple, set)):
        for item in raw:
            if isinstance(item, str) and item.strip():
                candidates.append(item.strip().lower())

    best = ROLE_OPERATOR
    best_rank = ROLE_RANK[ROLE_OPERATOR]
    for candidate in candidates:
        rank = ROLE_RANK.get(candidate, 0)
        if rank > best_rank:
            best = candidate
            best_rank = rank
    return best


def _b64u_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64u_decode(raw: str) -> bytes:
    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(raw + padding)


def sign_payload(payload: dict[str, Any], secret: str) -> str:
    """Sign a JSON dictionary with HMAC-SHA256."""

    if not secret:
        raise ValueError("auth_session_secret must not be empty")
    body = _b64u_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    sig = hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{_b64u_encode(sig)}"


def verify_payload(token: str | None, secret: str) -> dict[str, Any] | None:
    """Verify HMAC-SHA256 token and return decoded dict or None."""

    if not token or not secret or "." not in token:
        return None
    body, sig = token.split(".", 1)
    expected = hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    try:
        actual = _b64u_decode(sig)
    except Exception:
        return None
    if not hmac.compare_digest(actual, expected):
        return None
    try:
        decoded = json.loads(_b64u_decode(body).decode("utf-8"))
    except Exception:
        return None
    return decoded if isinstance(decoded, dict) else None


def issue_session_cookie(
    principal: AuthPrincipal,
    settings: Settings,
    *,
    now: float | None = None,
) -> str:
    ts = float(now if now is not None else time.time())
    ttl = max(300, int(settings.auth_session_ttl_s))
    payload = {
        "sub": principal.sub,
        "email": principal.email,
        "name": principal.name,
        "role": normalize_role(principal.role),
        "workspace": principal.workspace,
        "iat": int(ts),
        "last_seen": int(ts),
        "exp": int(ts + ttl),
        "sid": secrets.token_hex(12),
    }
    return sign_payload(payload, settings.auth_session_secret)


def parse_session_cookie(
    token: str | None,
    settings: Settings,
    *,
    now: float | None = None,
) -> tuple[AuthPrincipal, bool] | None:
    data = verify_payload(token, settings.auth_session_secret)
    if data is None:
        return None
    ts = float(now if now is not None else time.time())
    try:
        exp = float(data.get("exp", 0))
        last_seen = float(data.get("last_seen", data.get("iat", 0)))
    except (TypeError, ValueError):
        return None
    if exp <= ts:
        return None
    idle_limit = max(60, int(settings.auth_idle_timeout_s))
    if (ts - last_seen) > idle_limit:
        return None
    sub = str(data.get("sub") or "").strip()
    if not sub:
        return None
    ws = data.get("workspace")
    principal = AuthPrincipal(
        sub=sub,
        email=str(data.get("email") or ""),
        name=str(data.get("name") or ""),
        role=normalize_role(data.get("role")),
        workspace=str(ws).strip() if isinstance(ws, str) and ws.strip() else None,
    )
    needs_refresh = (ts - last_seen) > 60
    return principal, needs_refresh


def _cookie_secure(settings: Settings) -> bool:
    return bool(settings.auth_cookie_secure or not settings.is_loopback_host)


def set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=max(300, int(settings.auth_session_ttl_s)),
        httponly=True,
        samesite="lax",
        secure=_cookie_secure(settings),
        path="/",
    )


def set_oidc_state_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=OIDC_STATE_COOKIE_NAME,
        value=token,
        max_age=600,
        httponly=True,
        samesite="lax",
        secure=_cookie_secure(settings),
        path="/",
    )


def clear_auth_cookies(response: Response, settings: Settings) -> None:
    secure = _cookie_secure(settings)
    response.delete_cookie(
        key=SESSION_COOKIE_NAME, path="/", httponly=True, samesite="lax", secure=secure
    )
    response.delete_cookie(
        key=OIDC_STATE_COOKIE_NAME, path="/", httponly=True, samesite="lax", secure=secure
    )


def generate_pkce_pair() -> tuple[str, str]:
    """Generate RFC 7636 PKCE (code_verifier, S256 code_challenge)."""

    verifier = _b64u_encode(secrets.token_bytes(32))
    challenge = _b64u_encode(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def build_oidc_authorize_url(
    settings: Settings,
    *,
    state: str,
    code_challenge: str,
    redirect_uri: str,
) -> str:
    issuer = settings.oidc_issuer.rstrip("/")
    query = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": settings.oidc_client_id,
            "redirect_uri": redirect_uri,
            "scope": "openid profile email",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{issuer}/authorize?{query}"


def require_role(request: Request, min_role: str) -> AuthPrincipal | None:
    """Enforce RBAC when OIDC auth is active; return None in auth_mode='none'."""

    settings = request.app.state.settings
    if not settings.has_enforced_auth:
        return None
    principal = getattr(request.state, "principal", None)
    if principal is None:
        raise AppError(
            "authentication_required",
            "Bu islem icin oturum acmaniz gerekiyor.",
            status_code=401,
        )
    if not principal.has_role(min_role):
        raise AppError(
            "insufficient_role",
            f"Bu islem icin en az '{min_role}' rolu gereklidir.",
            status_code=403,
            details={"required_role": min_role, "actual_role": principal.role},
        )
    return principal


__all__ = [
    "AuthPrincipal",
    "OIDC_STATE_COOKIE_NAME",
    "ROLE_ADMIN",
    "ROLE_OPERATOR",
    "ROLE_RANK",
    "ROLE_SUPERVISOR",
    "SESSION_COOKIE_NAME",
    "VALID_ROLES",
    "build_oidc_authorize_url",
    "clear_auth_cookies",
    "generate_pkce_pair",
    "issue_session_cookie",
    "normalize_role",
    "parse_session_cookie",
    "require_role",
    "set_oidc_state_cookie",
    "set_session_cookie",
    "sign_payload",
    "verify_payload",
]
