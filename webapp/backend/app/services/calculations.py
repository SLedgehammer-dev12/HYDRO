"""Stateless calculation endpoints.

Every function calls the immutable domain package; the only additions are
JSON shaping and decision text.
"""

from __future__ import annotations

from typing import Any

from ..core.errors import AppError, error_from_domain
from ..core.timeutil import iso_z, utcnow
from ..domain_adapter import (
    build_geometry,
    build_pipe_model,
    dataclass_dict,
    geometry_response,
    geometry_summary,
)
from . import decisions
from .coefficients import coefficient_a, coefficient_b


def _reraise(exc: BaseException, **kwargs: Any) -> None:
    raise error_from_domain(exc, **kwargs) from exc


def calculate_geometry(request: Any) -> dict[str, Any]:
    geometry, sections = build_geometry(request.geometry)
    return geometry_response(geometry, sections)


def calculate_geometry_payload(geometry_payload: Any) -> dict[str, Any]:
    geometry, sections = build_geometry(geometry_payload)
    return geometry_response(geometry, sections)


def calculate_air_content(request: Any) -> dict[str, Any]:
    from hidrostatik_test.domain import AirContentInputs, evaluate_air_content_test

    pipe = build_pipe_model(request.geometry.sections)
    try:
        inputs = AirContentInputs(
            pipe=pipe,
            a_micro_per_bar=request.a_micro_per_bar,
            pressure_rise_bar=request.pressure_rise_bar,
            k_factor=request.k_factor,
            actual_added_water_m3=request.actual_added_water_m3,
        )
        result = evaluate_air_content_test(inputs)
    except Exception as exc:
        _reraise(exc)
    return {
        "theoretical_added_water_m3": result.theoretical_added_water_m3,
        "acceptance_limit_m3": result.acceptance_limit_m3,
        "actual_added_water_m3": result.actual_added_water_m3,
        "ratio": result.ratio,
        "passed": result.passed,
        "geometry": geometry_summary(pipe),
        "decision": decisions.air_decision(result),
    }


def calculate_pressure_variation(request: Any) -> dict[str, Any]:
    from hidrostatik_test.domain import (
        PressureVariationInputs,
        evaluate_pressure_variation_test,
    )

    pipe = build_pipe_model(request.geometry.sections)
    try:
        inputs = PressureVariationInputs(
            pipe=pipe,
            a_micro_per_bar=request.a_micro_per_bar,
            b_micro_per_c=request.b_micro_per_c,
            delta_t_c=request.delta_t_c,
            actual_pressure_change_bar=request.actual_pressure_change_bar,
        )
        result = evaluate_pressure_variation_test(inputs)
    except Exception as exc:
        _reraise(exc)
    decision = decisions.pressure_decision(result)
    return {
        "theoretical_pressure_change_bar": result.theoretical_pressure_change_bar,
        "allowable_upper_pressure_change_bar": result.allowable_upper_pressure_change_bar,
        "actual_pressure_change_bar": result.actual_pressure_change_bar,
        "margin_bar": result.margin_bar,
        "passed": result.passed,
        "negative_b": result.theoretical_pressure_change_bar < 0,
        "geometry": geometry_summary(pipe),
        "decision": decision,
    }


def calculate_pressure_profile(request: Any) -> dict[str, Any]:
    from hidrostatik_test.domain import (
        SectionPressureProfileInputs,
        evaluate_section_pressure_profile,
        get_location_class_rule,
    )

    pipe = build_pipe_model(request.geometry.sections)
    try:
        rule = get_location_class_rule(request.location_class)
        inputs = SectionPressureProfileInputs(
            pipe=pipe,
            design_pressure_bar=request.design_pressure_bar,
            smys_mpa=request.smys_mpa,
            location_class=rule,
            highest_elevation_m=request.highest_elevation_m,
            lowest_elevation_m=request.lowest_elevation_m,
            start_elevation_m=request.start_elevation_m,
            end_elevation_m=request.end_elevation_m,
            selected_pump_location=request.pump_location,
            monitored_pressure_bar=request.monitored_pressure_bar,
        )
        result = evaluate_section_pressure_profile(inputs)
    except Exception as exc:
        _reraise(exc)
    return {
        "location_class": dataclass_dict(result.location_class),
        "required_minimum_pressure_at_high_point_bar": (
            result.required_minimum_pressure_at_high_point_bar
        ),
        "maximum_allowable_pressure_at_low_point_bar": (
            result.maximum_allowable_pressure_at_low_point_bar
        ),
        "hydraulic_span_bar": result.hydraulic_span_bar,
        "required_pressure_with_span_bar": result.required_pressure_with_span_bar,
        "start_window": dataclass_dict(result.start_window),
        "end_window": dataclass_dict(result.end_window),
        "selected_window": dataclass_dict(result.selected_window),
        "limiting_pressure_at_100_smys_bar": result.limiting_pressure_at_100_smys_bar,
        "limiting_pipe_description": result.limiting_pipe_description,
        "total_length_m": result.total_length_m,
        "total_internal_volume_m3": result.total_internal_volume_m3,
        "within_length_limit": result.within_length_limit,
        "within_volume_limit": result.within_volume_limit,
        "within_100_smys_span_limit": result.within_100_smys_span_limit,
        "feasible": result.feasible,
        "monitored_pressure_bar": result.monitored_pressure_bar,
        "monitored_meets_minimum": result.monitored_meets_minimum,
        "monitored_under_maximum": result.monitored_under_maximum,
        "decision": decisions.profile_decision(result),
    }


def resolve_pig_limit(mode: str) -> Any:
    """Accept the desktop option label or the short domain limit label."""

    from hidrostatik_test.domain import get_pig_speed_limit
    from hidrostatik_test.domain.operations import PIG_SPEED_LIMITS

    try:
        return get_pig_speed_limit(mode)
    except Exception:
        normalized = (mode or "").strip()
        for limit in PIG_SPEED_LIMITS:
            if limit.label == normalized:
                return limit
        raise


def calculate_pig_speed(request: Any) -> dict[str, Any]:
    from hidrostatik_test.domain import evaluate_pig_speed

    try:
        limit = resolve_pig_limit(request.mode)
        result = evaluate_pig_speed(
            distance_m=request.distance_m,
            travel_time_min=request.travel_time_min,
            limit=limit,
        )
    except Exception as exc:
        _reraise(exc)
    decision = decisions.pig_decision(result)
    return {
        "distance_m": result.distance_m,
        "travel_time_min": result.travel_time_min,
        "speed_m_per_s": result.speed_m_per_s,
        "speed_km_per_h": result.speed_km_per_h,
        "limit": {
            "label": result.limit.label,
            "spec_reference": result.limit.spec_reference,
            "max_speed_m_per_s": result.limit.max_speed_m_per_s,
            "max_speed_km_per_h": result.limit.max_speed_km_per_h,
        },
        "passed": result.passed,
        "status": decision["pig_status"],
        "summary": decision["summary"],
        "decision": {key: value for key, value in decision.items() if key not in {"pig_status"}},
    }


def calculate_pressurization(request: Any) -> dict[str, Any]:
    from hidrostatik_test.domain import PressurizationInputs, evaluate_pressurization

    try:
        inputs = PressurizationInputs(
            initial_volume_m3=request.initial_volume_m3,
            added_volume_m3=request.added_volume_m3,
            theoretical_volume_m3=request.theoretical_volume_m3,
            pressure_bar=request.pressure_bar,
            expected_pressure_bar=request.expected_pressure_bar,
        )
        result = evaluate_pressurization(inputs)
    except Exception as exc:
        _reraise(exc)
    return {
        "volume_deviation_percent": result.volume_deviation_percent,
        "pressure_deviation_bar": result.pressure_deviation_bar,
        "within_volume_limit": result.within_volume_limit,
        "within_pressure_limit": result.within_pressure_limit,
        "passed": result.passed,
        "volume_limit_percent": result.volume_limit_percent,
        "pressure_tolerance_bar": result.pressure_tolerance_bar,
        "underfilled": result.underfilled,
        "volume_shortfall_percent": result.volume_shortfall_percent,
        "decision": decisions.pressurization_decision(result),
    }


def _thermal_reason(duration_hours: float, temp_diff: float | None) -> str:
    from hidrostatik_test.domain.time_series import THERMAL_BALANCE_MIN_HOURS

    if duration_hours < THERMAL_BALANCE_MIN_HOURS:
        return "Termal denge icin en az 24 saat veri gerekir."
    if temp_diff is None:
        return "Son 4 saat ile onceki 4 saat karsilastirmasi icin yeterli kayit yok."
    return ""


def calculate_thermal_balance(records: list[Any]) -> dict[str, Any]:
    from hidrostatik_test.domain.time_series import TimeSeriesStore

    payload = []
    for record in records:
        timestamp = getattr(record, "timestamp", None) or utcnow()
        payload.append(
            {
                "timestamp": iso_z(timestamp),
                "pressure_bar": float(record.pressure_bar),
                "temperature_c": float(record.temperature_c),
                "volume_m3": record.volume_m3,
                "notes": getattr(record, "notes", "") or "",
            }
        )
    store = TimeSeriesStore.from_dict({"records": payload})
    duration = store.get_duration_hours()
    balanced, temp_diff_raw = store.check_thermal_balance()
    temp_diff = decisions.finite_or_none(temp_diff_raw)
    average_last_4h = store.get_average_temperature(4.0)
    reason = _thermal_reason(duration, temp_diff)
    decision = decisions.thermal_decision(
        duration_hours=duration,
        balanced=balanced,
        temp_diff_c=temp_diff,
        reason=reason,
    )
    return {
        "record_count": len(store.records),
        "duration_hours": duration,
        "balanced": balanced,
        "temp_diff_c": temp_diff,
        "reason": reason or None,
        "average_temperature_last_4h_c": average_last_4h,
        "decision": decision,
    }


def calculate_water_density(temperature_c: float, pressure_bar: float) -> dict[str, Any]:
    from hidrostatik_test.domain.water_properties import calculate_water_density

    try:
        density = calculate_water_density(temperature_c, pressure_bar)
    except Exception as exc:
        _reraise(exc)
    return {
        "density_kg_per_m3": density,
        "temperature_c": temperature_c,
        "pressure_bar": pressure_bar,
    }


# ---------------------------------------------------------------------------
# Session result dispatch (server-side recomputation)
# ---------------------------------------------------------------------------


def evaluate_test(test_type: str, payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Recompute one test from its payload and return ``(result, decision)``."""

    from .. import schemas

    if test_type == "air":
        result = calculate_air_content(schemas.AirContentRequest.model_validate(payload))
        return result, result["decision"]
    if test_type == "pressure":
        result = calculate_pressure_variation(
            schemas.PressureVariationRequest.model_validate(payload)
        )
        return result, result["decision"]
    if test_type == "coefficient_a":
        request = schemas.CoefficientARequest.model_validate(payload)
        result = coefficient_a(request.temperature_c, request.pressure_bar, request.backend)
        decision = {
            "status": decisions.STATUS_PASS,
            "title": "A Katsayisi",
            "summary": (
                f"A = {result['a_micro_per_bar']:.6f} 10^-6/bar "
                f"(T={request.temperature_c} °C, P={request.pressure_bar} bar)."
            ),
            "rule": "hesaplama tamamlandi",
            "margin": None,
        }
        result["decision"] = decision
        return result, decision
    if test_type == "coefficient_b":
        request = schemas.CoefficientBRequest.model_validate(payload)
        result = coefficient_b(
            source=request.source,
            temperature_c=request.temperature_c,
            pressure_bar=request.pressure_bar,
            steel_alpha_micro_per_c=request.steel_alpha_micro_per_c,
            steel_model=request.steel_model,
        )
        decision = {
            "status": decisions.STATUS_PASS,
            "title": "B Katsayisi",
            "summary": (f"B = {result['b_micro_per_c']:.6f} 10^-6/°C; kaynak = {result['label']}."),
            "rule": "hesaplama tamamlandi",
            "margin": None,
        }
        result["decision"] = decision
        return result, decision
    if test_type == "profile":
        result = calculate_pressure_profile(schemas.PressureProfileRequest.model_validate(payload))
        return result, result["decision"]
    if test_type == "pig":
        result = calculate_pig_speed(schemas.PigSpeedRequest.model_validate(payload))
        return result, result["decision"]
    if test_type == "pressurization":
        result = calculate_pressurization(schemas.PressurizationRequest.model_validate(payload))
        return result, result["decision"]
    if test_type == "thermal_balance":
        request = schemas.ThermalBalanceRequest.model_validate(payload)
        result = calculate_thermal_balance(request.records)
        return result, result["decision"]
    raise AppError(
        "validation_error",
        f"Bilinmeyen test tipi: {test_type}",
        status_code=422,
        details={"test_type": test_type},
    )


__all__ = [
    "calculate_air_content",
    "calculate_geometry",
    "calculate_geometry_payload",
    "calculate_pig_speed",
    "calculate_pressure_profile",
    "calculate_pressure_variation",
    "calculate_pressurization",
    "calculate_thermal_balance",
    "calculate_water_density",
    "evaluate_test",
    "resolve_pig_limit",
]
