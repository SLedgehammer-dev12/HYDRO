"""Coefficient routes (A/B resolution and reference tables)."""

from __future__ import annotations

from fastapi import APIRouter

from .. import schemas
from ..services import coefficients as coefficient_service

router = APIRouter(prefix="/coefficients", tags=["coefficients"])


@router.post("/a")
def coefficient_a(payload: schemas.CoefficientARequest) -> dict:
    return coefficient_service.coefficient_a(
        payload.temperature_c, payload.pressure_bar, payload.backend
    )


@router.post("/b")
def coefficient_b(payload: schemas.CoefficientBRequest) -> dict:
    return coefficient_service.coefficient_b(
        source=payload.source,
        temperature_c=payload.temperature_c,
        pressure_bar=payload.pressure_bar,
        steel_alpha_micro_per_c=payload.steel_alpha_micro_per_c,
        steel_model=payload.steel_model,
    )


@router.post("/compare")
def coefficient_compare(payload: schemas.CoefficientCompareRequest) -> dict:
    return coefficient_service.coefficient_compare(
        temperature_c=payload.temperature_c,
        pressure_bar=payload.pressure_bar,
        steel_alpha_micro_per_c=payload.steel_alpha_micro_per_c,
        steel_model=payload.steel_model,
    )


@router.post("/table")
def coefficient_table(payload: schemas.CoefficientTableRequest) -> dict:
    return coefficient_service.coefficient_table(
        table=payload.table,
        temperature_c=payload.temperature_c,
        pressure_bar=payload.pressure_bar,
        repair_anomalies=payload.repair_anomalies,
    )


@router.post("/reference-compare")
def reference_compare(payload: schemas.ReferenceCompareRequest) -> dict:
    return coefficient_service.reference_compare(
        temperature_c=payload.temperature_c,
        pressure_bar=payload.pressure_bar,
        repair_anomalies=payload.repair_anomalies,
    )


@router.post("/backend-comparison")
def backend_comparison(payload: schemas.BackendComparisonRequest) -> dict:
    return coefficient_service.backend_comparison(
        temperature_c=payload.temperature_c,
        pressure_bar=payload.pressure_bar,
        include_dev_backends=payload.include_dev_backends,
    )


__all__ = ["router"]
