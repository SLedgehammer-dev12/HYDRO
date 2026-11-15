"""Single adapter between API payloads and the ``hidrostatik_test`` domain.

The web layer never re-implements formulas: it constructs domain dataclasses,
calls domain functions and serialises the result.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Iterable

from .core.errors import AppError, error_from_domain
from .core.timeutil import json_safe


def _raise(exc: BaseException, **kwargs: Any) -> None:
    raise error_from_domain(exc, **kwargs) from exc


def build_pipe_section(data: Any) -> Any:
    from hidrostatik_test.domain import PipeSection

    try:
        return PipeSection(
            outside_diameter_mm=float(data.outside_diameter_mm),
            wall_thickness_mm=float(data.wall_thickness_mm),
            length_m=float(data.length_m),
        )
    except Exception as exc:  # domain ValidationError / conversion
        _raise(exc)


def build_pipe_sections(sections: Iterable[Any]) -> list[Any]:
    items = list(sections)
    if not items:
        try:
            from hidrostatik_test.domain import PipeGeometry

            PipeGeometry(sections=())
        except Exception as exc:
            _raise(exc)
    return [build_pipe_section(section) for section in items]


def build_pipe_model(sections: Iterable[Any]) -> Any:
    """Return ``PipeSection`` for one row, ``PipeGeometry`` for many.

    This mirrors the desktop rule: with a single pipe section the single
    section fields are used; with a segment list the chained geometry is used.
    """

    from hidrostatik_test.domain import PipeGeometry

    built = build_pipe_sections(sections)
    if len(built) == 1:
        return built[0]
    try:
        return PipeGeometry(sections=tuple(built))
    except Exception as exc:
        _raise(exc)


def build_geometry(data: Any) -> tuple[Any, list[Any]]:
    from hidrostatik_test.domain import PipeGeometry

    sections = build_pipe_sections(getattr(data, "sections", []) or [])
    try:
        geometry = PipeGeometry(sections=tuple(sections))
    except Exception as exc:
        _raise(exc)
    return geometry, sections


def geometry_summary(pipe: Any) -> dict[str, Any]:
    try:
        total_length = pipe.total_length_m if hasattr(pipe, "total_length_m") else pipe.length_m
        return {
            "total_length_m": total_length,
            "internal_volume_m3": pipe.internal_volume_m3,
            "internal_radius_mm": pipe.internal_radius_mm,
            "elasticity_term": pipe.elasticity_term,
        }
    except Exception as exc:
        _raise(exc)


def geometry_response(geometry: Any, sections: list[Any]) -> dict[str, Any]:
    from hidrostatik_test.domain import PipeGeometry

    summary = geometry_summary(geometry)
    rows = [
        {
            "index": index,
            "outside_diameter_mm": section.outside_diameter_mm,
            "wall_thickness_mm": section.wall_thickness_mm,
            "length_m": section.length_m,
            "internal_radius_mm": section.internal_radius_mm,
            "internal_volume_m3": section.internal_volume_m3,
            "elasticity_term": section.elasticity_term,
        }
        for index, section in enumerate(sections, start=1)
    ]
    # ``geometry`` is a PipeGeometry (even when one section was supplied);
    # the summary is volume weighted, identical for one section.
    assert isinstance(geometry, PipeGeometry)
    return {
        "section_count": len(sections),
        **summary,
        "sections": rows,
    }


def dataclass_dict(value: Any) -> dict[str, Any]:
    return json_safe(asdict(value))


def b_source_payload(result: Any) -> dict[str, Any]:
    return json_safe(
        {
            "b_micro_per_c": result.b_micro_per_c,
            "source": result.source,
            "label": result.label,
            "note": result.note,
            "repaired_table": result.repaired_table,
            "water_beta_micro_per_c": result.water_beta_micro_per_c,
            "steel_alpha_micro_per_c": result.steel_alpha_micro_per_c,
            "steel_model": result.steel_model,
        }
    )


def backend_info_payload(info: Any) -> dict[str, Any]:
    return {
        "key": info.key,
        "label": info.label,
        "distribution_ready": info.distribution_ready,
        "note": info.note,
    }


def raise_app(error: AppError) -> None:
    raise error


__all__ = [
    "backend_info_payload",
    "b_source_payload",
    "build_geometry",
    "build_pipe_model",
    "build_pipe_section",
    "build_pipe_sections",
    "dataclass_dict",
    "geometry_response",
    "geometry_summary",
    "raise_app",
]
