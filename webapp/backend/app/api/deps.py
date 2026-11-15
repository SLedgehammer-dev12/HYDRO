"""FastAPI dependencies."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from ..core.config import Settings


@dataclass(frozen=True)
class Workspace:
    raw: str
    hash: str
    actor: str


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_workspace(request: Request) -> Workspace:
    return request.state.workspace


__all__ = ["Workspace", "get_settings", "get_workspace"]
