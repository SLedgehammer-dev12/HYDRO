"""Free report export route."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from .. import schemas
from ..core.config import Settings
from ..core.errors import validation_error
from ..services import reports as report_service
from .deps import get_settings

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("/export")
def export_report(
    payload: schemas.ReportExportRequest,
    settings: Settings = Depends(get_settings),
):
    if payload.format not in report_service.FORMAT_ALIASES:
        raise validation_error(f"Desteklenmeyen rapor formati: {payload.format}", field="format")
    target = report_service.free_export(
        settings,
        fmt=payload.format,
        title=payload.title,
        metadata=payload.metadata,
        geometry_data=payload.geometry_data,
        test_results=payload.test_results,
        checklist=payload.checklist,
    )
    return FileResponse(
        path=target,
        media_type=report_service.CONTENT_TYPES[payload.format],
        filename=report_service.export_filename(payload.format),
    )


__all__ = ["router"]
