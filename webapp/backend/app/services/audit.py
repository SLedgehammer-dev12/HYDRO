"""Audit trail helpers."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..core.context import get_actor, get_request_id, get_workspace_hash
from ..core.timeutil import iso_z
from ..models import AuditEvent


def record(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: str,
    session_id: str | None = None,
    workspace_hash: str | None = None,
    actor: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> AuditEvent:
    event = AuditEvent(
        workspace_id_hash=workspace_hash or get_workspace_hash(),
        session_id=session_id,
        actor=actor or get_actor(),
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        before=before,
        after=after,
        request_id=request_id or get_request_id(),
    )
    db.add(event)
    return event


def user_payload(event: AuditEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "session_id": event.session_id,
        "action": event.action,
        "actor": event.actor,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "before": event.before,
        "after": event.after,
        "request_id": event.request_id,
        "created_at": iso_z(event.created_at),
    }


__all__ = ["record", "user_payload"]
