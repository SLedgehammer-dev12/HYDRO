"""Stateless calculation routes."""

from __future__ import annotations

from fastapi import APIRouter

from .. import schemas
from ..services import calculations as calculation_service

router = APIRouter(prefix="/calculations", tags=["calculations"])


@router.post("/geometry")
def geometry(payload: schemas.GeometryIn) -> dict:
    return calculation_service.calculate_geometry_payload(payload)


@router.post("/air-content")
def air_content(payload: schemas.AirContentRequest) -> dict:
    return calculation_service.calculate_air_content(payload)


@router.post("/pressure-variation")
def pressure_variation(payload: schemas.PressureVariationRequest) -> dict:
    return calculation_service.calculate_pressure_variation(payload)


@router.post("/pressure-profile")
def pressure_profile(payload: schemas.PressureProfileRequest) -> dict:
    return calculation_service.calculate_pressure_profile(payload)


@router.post("/pig-speed")
def pig_speed(payload: schemas.PigSpeedRequest) -> dict:
    return calculation_service.calculate_pig_speed(payload)


@router.post("/pressurization")
def pressurization(payload: schemas.PressurizationRequest) -> dict:
    return calculation_service.calculate_pressurization(payload)


@router.post("/thermal-balance")
def thermal_balance(payload: schemas.ThermalBalanceRequest) -> dict:
    return calculation_service.calculate_thermal_balance(payload.records)


@router.post("/water-density")
def water_density(payload: schemas.WaterDensityRequest) -> dict:
    return calculation_service.calculate_water_density(payload.temperature_c, payload.pressure_bar)


__all__ = ["router"]
