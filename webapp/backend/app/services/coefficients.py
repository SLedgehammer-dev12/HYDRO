"""Coefficient endpoints' domain orchestration (A, B, tables, backends)."""

from __future__ import annotations

import logging
from typing import Any

from ..core.errors import error_from_domain
from ..domain_adapter import b_source_payload, backend_info_payload

logger = logging.getLogger("hydro.web.coefficients")


def _reraise(exc: BaseException, **kwargs: Any) -> None:
    raise error_from_domain(exc, **kwargs) from exc


def coefficient_a(temperature_c: float, pressure_bar: float, backend: str | None) -> dict[str, Any]:
    from hidrostatik_test.domain.water_properties import (
        get_default_water_property_backend,
        get_water_property_backend,
    )

    try:
        backend_obj = (
            get_water_property_backend(backend) if backend else get_default_water_property_backend()
        )
        value = backend_obj.calculate_water_compressibility_a(temperature_c, pressure_bar)
    except Exception as exc:
        _reraise(exc)
    info = getattr(backend_obj, "info", None)
    return {
        "a_micro_per_bar": value,
        "temperature_c": temperature_c,
        "pressure_bar": pressure_bar,
        "backend": backend_info_payload(info) if info is not None else None,
        "state": "computed",
    }


def coefficient_b(
    *,
    source: str,
    temperature_c: float,
    pressure_bar: float,
    steel_alpha_micro_per_c: float,
    steel_model: str,
    backend: str | None = None,
) -> dict[str, Any]:
    from hidrostatik_test.domain import resolve_b_value

    try:
        result = resolve_b_value(
            source,
            temp_c=temperature_c,
            pressure_bar=pressure_bar,
            steel_alpha_micro_per_c=steel_alpha_micro_per_c,
            steel_model=steel_model,
            backend=backend,
        )
    except Exception as exc:
        _reraise(exc, reference_table_hint=source in {"institutional", "gail"})
    return b_source_payload(result)


def coefficient_compare(
    *,
    temperature_c: float,
    pressure_bar: float,
    steel_alpha_micro_per_c: float,
    steel_model: str,
    backend: str | None = None,
) -> dict[str, Any]:
    from hidrostatik_test.domain import compare_b_sources

    try:
        comparison = compare_b_sources(
            temp_c=temperature_c,
            pressure_bar=pressure_bar,
            steel_alpha_micro_per_c=steel_alpha_micro_per_c,
            steel_model=steel_model,
            backend=backend,
        )
    except Exception as exc:
        _reraise(exc, reference_table_hint=True)

    return {
        "temperature_c": temperature_c,
        "pressure_bar": pressure_bar,
        "institutional": b_source_payload(comparison.institutional),
        "gail": b_source_payload(comparison.gail),
        "auto": b_source_payload(comparison.auto),
        "deltas": {
            "institutional_vs_gail": comparison.institutional_vs_gail,
            "auto_vs_institutional": comparison.auto_vs_institutional,
            "auto_vs_gail": comparison.auto_vs_gail,
        },
    }


def coefficient_table(
    *,
    table: str,
    temperature_c: float,
    pressure_bar: float,
    repair_anomalies: bool,
) -> dict[str, Any]:
    from hidrostatik_test.data import (
        lookup_botas_reference_point,
        lookup_gail_reference_point,
    )

    try:
        if table == "gail":
            point = lookup_gail_reference_point(temp_c=temperature_c, pressure_bar=pressure_bar)
            table_label = "GAIL referans tablosu"
        else:
            point = lookup_botas_reference_point(
                temp_c=temperature_c,
                pressure_bar=pressure_bar,
                repair_anomalies=repair_anomalies,
            )
            table_label = "Kurum ici A/B kontrol tablosu"
    except Exception as exc:
        _reraise(exc)

    return {
        "table": table,
        "table_label": table_label,
        "requested": {"temperature_c": temperature_c, "pressure_bar": pressure_bar},
        "a_micro_per_bar": point.a_micro_per_bar,
        "b_micro_per_c": point.b_micro_per_c,
        "source_note": point.source_note,
        "repaired": point.repaired,
        "repair_note": point.repair_note,
    }


def _point_payload(point: Any) -> dict[str, Any]:
    return {
        "a_micro_per_bar": point.a_micro_per_bar,
        "b_micro_per_c": point.b_micro_per_c,
        "source_note": point.source_note,
        "repaired": point.repaired,
        "repair_note": point.repair_note,
    }


def reference_compare(
    *,
    temperature_c: float,
    pressure_bar: float,
    repair_anomalies: bool,
) -> dict[str, Any]:
    from hidrostatik_test.data import compare_reference_b_sources

    try:
        comparison = compare_reference_b_sources(
            temp_c=temperature_c,
            pressure_bar=pressure_bar,
            repair_anomalies=repair_anomalies,
        )
    except Exception as exc:
        _reraise(exc)

    return {
        "temperature_c": temperature_c,
        "pressure_bar": pressure_bar,
        "control_point": _point_payload(comparison.control_point),
        "gail_point": _point_payload(comparison.gail_point),
        "a_delta": comparison.a_delta,
        "b_delta": comparison.b_delta,
    }


def backend_comparison(
    *,
    temperature_c: float,
    pressure_bar: float,
    include_dev_backends: bool,
) -> dict[str, Any]:
    from hidrostatik_test.domain import ValidationError
    from hidrostatik_test.domain.water_properties import (
        WaterPropertyError,
        get_available_water_property_backends,
        get_water_property_backend,
    )

    items: list[dict[str, Any]] = []
    for info in get_available_water_property_backends(include_dev_backends=include_dev_backends):
        entry: dict[str, Any] = {
            "backend": backend_info_payload(info),
            "a_micro_per_bar": None,
            "beta_micro_per_c": None,
            "density_kg_per_m3": None,
            "error": None,
        }
        try:
            backend = get_water_property_backend(info.key)
            entry["a_micro_per_bar"] = backend.calculate_water_compressibility_a(
                temperature_c, pressure_bar
            )
            entry["beta_micro_per_c"] = backend.calculate_water_thermal_expansion_beta(
                temperature_c, pressure_bar
            )
            entry["density_kg_per_m3"] = backend.calculate_water_density(
                temperature_c, pressure_bar
            )
        except (WaterPropertyError, ValidationError) as exc:
            entry["error"] = str(exc)
        except Exception:  # partial success is contract behaviour; keep details sanitized
            logger.exception("Water property backend %s failed during comparison", info.key)
            entry["error"] = "Backend hesaplama sirasinda beklenmeyen bir hata olustu."
        items.append(entry)

    return {
        "temperature_c": temperature_c,
        "pressure_bar": pressure_bar,
        "items": items,
    }


__all__ = [
    "backend_comparison",
    "coefficient_a",
    "coefficient_b",
    "coefficient_compare",
    "coefficient_table",
    "reference_compare",
]
