"""Request-scoped context (request id, workspace)."""

from __future__ import annotations

from contextvars import ContextVar

_request_id: ContextVar[str] = ContextVar("hydro_request_id", default="")
_workspace_hash: ContextVar[str] = ContextVar("hydro_workspace_hash", default="")
_actor: ContextVar[str] = ContextVar("hydro_actor", default="anonymous")


def set_request_context(request_id: str, workspace_hash: str, actor: str) -> None:
    _request_id.set(request_id)
    _workspace_hash.set(workspace_hash)
    _actor.set(actor)


def get_request_id() -> str:
    return _request_id.get()


def get_workspace_hash() -> str:
    return _workspace_hash.get()


def get_actor() -> str:
    return _actor.get()


__all__ = [
    "get_actor",
    "get_request_id",
    "get_workspace_hash",
    "set_request_context",
]
