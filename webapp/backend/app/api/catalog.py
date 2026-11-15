"""Pipe/grade/reference-table catalog routes."""

from __future__ import annotations

from fastapi import APIRouter, Query

from ..services import catalog as catalog_service

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/pipes")
def pipes(
    q: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    return catalog_service.list_pipes(q=q, limit=limit, offset=offset)


@router.get("/pipes/{nps}/schedules")
def pipe_schedules(nps: str) -> dict:
    return catalog_service.pipe_schedules(nps)


@router.get("/grades")
def grades() -> dict:
    return catalog_service.list_grades()


@router.get("/reference-tables")
def reference_tables() -> dict:
    return catalog_service.reference_tables()


__all__ = ["router"]
