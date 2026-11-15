"""3D scene model derived server-side from session inputs.

The scene never calculates engineering decisions; it only derives geometry,
stations, elevations and a hydrostatic pressure *visualisation* from domain
constants (density at 15 °C, gravity, SMYS limit formula via domain output).
"""

from __future__ import annotations

from typing import Any, Callable

from hidrostatik_test.domain.pressure_profile import (
    GRAVITY_M_PER_S2,
    PRESSURE_CONVERSION_PASCAL_TO_BAR,
)
from hidrostatik_test.domain.water_properties import (
    WATER_DENSITY_DEFAULT_KG_PER_M3,
    calculate_water_density,
)

from ..core.errors import AppError
from ..core.timeutil import as_float, iso_z, utcnow
from ..domain_adapter import build_pipe_model, build_pipe_section

SCENE_SCHEMA_VERSION = 1
APPROXIMATE_PROFILE_WARNING = (
    "Kot profili start/highest/lowest/end noktalarindan yaklasik turetildi."
)
NO_ELEVATION_WARNING = "Kot bilgisi girilmedi; zemin 0 m kabul edildi."
NO_PRESSURE_WARNING = "Izlenen basinc girilmedi; basinc renkleri hesaplanmadi."
NEGATIVE_PRESSURE_WARNING = "Hidrostatik turetimde negatif basinc 0'a kirpildi."
PUMP_ASSUMPTION_WARNING = "Pompa konumu secilmedi; baslangic noktasi kabul edildi."


def _density() -> float:
    try:
        return calculate_water_density(15.0, 1.0)
    except Exception:
        return WATER_DENSITY_DEFAULT_KG_PER_M3


def _elevation_interpolator(points: list[tuple[float, float]]) -> Callable[[float], float]:
    ordered = sorted(points)
    if not ordered:
        return lambda _station: 0.0
    if len(ordered) == 1:
        only = ordered[0][1]
        return lambda _station: only

    def interpolate(station: float) -> float:
        if station <= ordered[0][0]:
            return ordered[0][1]
        if station >= ordered[-1][0]:
            return ordered[-1][1]
        for (s0, e0), (s1, e1) in zip(ordered, ordered[1:]):
            if s0 <= station <= s1:
                if s1 == s0:
                    return e1
                ratio = (station - s0) / (s1 - s0)
                return e0 + (e1 - e0) * ratio
        return ordered[-1][1]

    return interpolate


def _sections(inputs: dict[str, Any]) -> list[Any]:
    from .sessions import _sections_from_inputs

    return _sections_from_inputs(inputs)


def _profile_from_inputs(
    inputs: dict[str, Any], total_length: float
) -> tuple[list[dict[str, float]], Callable[[float], float], list[str], bool]:
    warnings: list[str] = []
    raw_points = inputs.get("profile_points")
    if isinstance(raw_points, list) and raw_points:
        points: list[tuple[float, float]] = []
        for item in raw_points:
            if not isinstance(item, dict):
                continue
            station = as_float(item.get("station_m"))
            elevation = as_float(item.get("elevation_m"))
            if station is None or elevation is None:
                continue
            points.append((station, elevation))
        if points:
            return (
                [{"station_m": s, "elevation_m": e} for s, e in sorted(points)],
                _elevation_interpolator(points),
                warnings,
                False,
            )

    profile = inputs.get("section_profile") or {}
    highest = as_float(profile.get("highest_elevation_m"))
    lowest = as_float(profile.get("lowest_elevation_m"))
    start = as_float(profile.get("start_elevation_m"))
    end = as_float(profile.get("end_elevation_m"))

    if start is None:
        start = lowest if lowest is not None else 0.0
    if end is None:
        end = lowest if lowest is not None else 0.0
    if highest is None:
        highest = max(start, end)
    if lowest is None:
        lowest = min(start, end)

    if not any(
        value is not None
        for value in (
            as_float(profile.get("highest_elevation_m")),
            as_float(profile.get("lowest_elevation_m")),
            as_float(profile.get("start_elevation_m")),
            as_float(profile.get("end_elevation_m")),
        )
    ):
        warnings.append(NO_ELEVATION_WARNING)

    peak = highest
    if peak <= max(start, end):
        if lowest < min(start, end):
            peak = lowest
        else:
            peak = (start + end) / 2.0
    mid_station = total_length / 2.0
    points = [(0.0, start), (mid_station, peak), (total_length, end)]
    warnings.append(APPROXIMATE_PROFILE_WARNING)
    return (
        [{"station_m": s, "elevation_m": e} for s, e in points],
        _elevation_interpolator(points),
        warnings,
        True,
    )


def _pig_payload(inputs: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    field = inputs.get("field") or {}
    modes = inputs.get("modes") or {}
    distance = as_float(field.get("pig_distance_m"))
    travel = as_float(field.get("pig_travel_time_min"))
    speed = as_float(field.get("pig_speed_m_per_s"))
    mode = str(modes.get("pig_mode") or "Temizlik pigi")
    limit_status = "unknown"
    label = mode

    if speed is None and distance is not None and travel is not None:
        try:
            from hidrostatik_test.domain import evaluate_pig_speed

            from .calculations import resolve_pig_limit

            limit = resolve_pig_limit(mode)
            result = evaluate_pig_speed(distance, travel, limit)
            speed = result.speed_m_per_s
            travel = result.travel_time_min
            label = limit.label
            limit_status = (
                "info" if result.passed is None else ("ok" if result.passed else "exceeded")
            )
        except Exception:
            warnings.append("Pig hizi hesaplanamadi; mod ve mesafe/sureyi kontrol edin.")
    elif speed is not None and distance is not None and travel is not None:
        try:
            from .calculations import resolve_pig_limit

            limit = resolve_pig_limit(mode)
            label = limit.label
            if limit.max_speed_m_per_s is None:
                limit_status = "info"
            else:
                limit_status = "ok" if speed <= limit.max_speed_m_per_s else "exceeded"
        except Exception:
            pass

    return (
        {
            "station_m": distance or 0.0,
            "speed_m_per_s": speed,
            "travel_time_min": travel,
            "label": label,
            "limit_status": limit_status,
        },
        warnings,
    )


def _scaled_utilization(pressure: float | None, limit: float | None) -> float | None:
    if pressure is None or limit is None or limit <= 0:
        return None
    return pressure / limit


def _status(utilization: float | None, pressure: float | None) -> str:
    if pressure is None or utilization is None:
        return "unknown"
    if utilization >= 1.0:
        return "critical"
    if utilization >= 0.9:
        return "warning"
    return "ok"


def build_scene(inputs: dict[str, Any]) -> dict[str, Any]:
    sections = _sections(inputs or {})
    if not sections:
        raise AppError(
            "incomplete_geometry",
            "Sahne icin geometri girilmelidir.",
            status_code=422,
            details={
                "missing": [
                    "geometry.outside_diameter_mm",
                    "geometry.wall_thickness_mm",
                    "geometry.length_m",
                ]
            },
        )

    try:
        pipe = build_pipe_model(sections)
    except AppError:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise AppError("domain_validation_error", str(exc), status_code=400) from exc

    warnings: list[str] = []
    stations: list[dict[str, Any]] = []
    station_cursor = 0.0
    for index, section in enumerate(sections, start=1):
        domain_section = build_pipe_section(section)
        length = float(domain_section.length_m)
        start_station = as_float(getattr(section, "start_station_m", None))
        if start_station is not None:
            station_cursor = start_station
        stations.append(
            {
                "index": index,
                "section": domain_section,
                "schema": section,
                "station_start_m": station_cursor,
                "station_end_m": station_cursor + length,
                "length_m": length,
            }
        )
        station_cursor += length

    total_length = station_cursor
    profile_points, elevation_at, profile_warnings, approximate = _profile_from_inputs(
        inputs or {}, total_length
    )
    warnings.extend(profile_warnings)
    warnings = list(dict.fromkeys(warnings))

    profile = inputs.get("section_profile") or {}
    smys = as_float(profile.get("smys_mpa"))
    air = inputs.get("air") or {}
    pressure_inputs = inputs.get("pressure") or {}
    field_inputs = inputs.get("field") or {}
    monitored = as_float(profile.get("monitored_pressure_bar"))
    if monitored is None:
        monitored = as_float(field_inputs.get("monitored_pressure_bar"))
    if monitored is None:
        monitored = as_float(pressure_inputs.get("pressure_bar"))
    if monitored is None:
        monitored = as_float(air.get("pressure_bar"))

    pump_location = str(inputs.get("pump_location") or "").strip()
    side = "start"
    if not pump_location:
        warnings.append(PUMP_ASSUMPTION_WARNING)
    elif "Bitis" in pump_location:
        side = "end"
    elif "Baslangic" not in pump_location:
        warnings.append(PUMP_ASSUMPTION_WARNING)

    pump_station = 0.0 if side == "start" else total_length
    pump_elevation = elevation_at(pump_station)
    density = _density()
    negative_clipped = False

    def pressure_at(station: float) -> float | None:
        nonlocal negative_clipped
        if monitored is None:
            return None
        head_bar = (
            density
            * GRAVITY_M_PER_S2
            * (elevation_at(station) - pump_elevation)
            / PRESSURE_CONVERSION_PASCAL_TO_BAR
        )
        pressure = monitored - head_bar
        if pressure < 0:
            negative_clipped = True
            return 0.0
        return pressure

    if monitored is None:
        warnings.append(NO_PRESSURE_WARNING)

    segment_rows: list[dict[str, Any]] = []
    catalog = inputs.get("geometry_catalog") or {}
    for station in stations:
        section = station["section"]
        schema_section = station.get("schema")
        od = float(section.outside_diameter_mm)
        wt = float(section.wall_thickness_mm)
        limit_smys = 20.0 * smys * wt / od if smys is not None and od > 0 else None
        pressure = pressure_at(station["station_start_m"])
        utilization = _scaled_utilization(pressure, limit_smys)
        nps_label = getattr(schema_section, "nps_label", None)
        schedule_label = getattr(schema_section, "schedule_label", None)
        if len(stations) == 1:
            nps_label = nps_label or (str(catalog.get("size_option") or "") or None)
            schedule_label = schedule_label or (str(catalog.get("schedule_option") or "") or None)
        segment_rows.append(
            {
                "id": f"seg-{station['index']}",
                "index": station["index"],
                "nps_label": nps_label,
                "schedule_label": schedule_label,
                "station_start_m": station["station_start_m"],
                "station_end_m": station["station_end_m"],
                "length_m": station["length_m"],
                "elevation_start_m": elevation_at(station["station_start_m"]),
                "elevation_end_m": elevation_at(station["station_end_m"]),
                "od_mm": od,
                "wt_mm": wt,
                "id_mm": od - 2.0 * wt,
                "grade": str(inputs.get("material_grade") or "") or None,
                "smys_mpa": smys,
                "pressure_at_100_smys_bar": limit_smys,
                "pressure_bar": pressure,
                "utilization": utilization,
                "status": _status(utilization, pressure),
                "internal_volume_m3": float(section.internal_volume_m3),
            }
        )

    # Equipment
    boundary_stations = sorted(
        {0.0, total_length}
        | {row["station_start_m"] for row in stations}
        | {row["station_end_m"] for row in stations}
    )
    valves: list[dict[str, Any]] = []
    pump = {
        "station_m": pump_station,
        "elevation_m": pump_elevation,
        "side": side,
        "monitored_pressure_bar": monitored,
    }
    test_head = {
        "station_m": min(total_length, pump_station + 1.0),
        "elevation_m": elevation_at(min(total_length, pump_station + 1.0)),
        "label": "Test basligi",
        "pressure_bar": monitored,
    }

    raw_equipment = inputs.get("equipment")
    if isinstance(raw_equipment, list) and raw_equipment:
        for index, item in enumerate(raw_equipment, start=1):
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind") or "mainline")
            station_value = as_float(item.get("station_m"))
            if station_value is None:
                continue
            station_value = max(0.0, min(total_length, station_value))
            elevation = as_float(item.get("elevation_m"))
            if elevation is None:
                elevation = elevation_at(station_value)
            if kind in {"valve", "mainline", "vent", "drain"}:
                valves.append(
                    {
                        "id": str(item.get("id") or f"v-{index}"),
                        "station_m": station_value,
                        "elevation_m": elevation,
                        "kind": kind,
                        "label": str(item.get("label") or kind),
                        "state": str(item.get("state") or "unknown"),
                    }
                )
            elif kind == "pump":
                pump.update(
                    {
                        "station_m": station_value,
                        "elevation_m": elevation,
                        "side": "start" if station_value <= total_length / 2 else "end",
                    }
                )
            elif kind == "test_head":
                test_head.update(
                    {
                        "station_m": station_value,
                        "elevation_m": elevation,
                        "label": str(item.get("label") or "Test basligi"),
                    }
                )

    if not valves:
        for index, station_value in enumerate(boundary_stations, start=1):
            if station_value == 0.0:
                label = "Baslangic vanasi"
            elif station_value == total_length:
                label = "Bitis vanasi"
            else:
                label = f"Segment siniri {station_value:.0f} m"
            valves.append(
                {
                    "id": f"v-{index}",
                    "station_m": station_value,
                    "elevation_m": elevation_at(station_value),
                    "kind": "mainline",
                    "label": label,
                    "state": "open",
                }
            )

    pig, pig_warnings = _pig_payload(inputs or {})
    warnings.extend(pig_warnings)
    if total_length > 0:
        pig["station_m"] = float(pig.get("station_m") or 0.0) % total_length

    sample_stations = sorted(set(boundary_stations) | {total_length})
    sampled_pressures = [
        value
        for value in (pressure_at(station) for station in sample_stations)
        if value is not None
    ]
    sampled_utilization = [
        row["utilization"] for row in segment_rows if row["utilization"] is not None
    ]
    if negative_clipped:
        warnings.append(NEGATIVE_PRESSURE_WARNING)

    elevations = [row["elevation_start_m"] for row in segment_rows] + [
        row["elevation_end_m"] for row in segment_rows
    ]
    if profile_points:
        elevations.extend(point["elevation_m"] for point in profile_points)

    warnings = list(dict.fromkeys(warnings))
    totals = {
        "total_length_m": float(
            pipe.total_length_m if hasattr(pipe, "total_length_m") else pipe.length_m
        ),
        "internal_volume_m3": float(pipe.internal_volume_m3),
        "internal_radius_mm": float(pipe.internal_radius_mm),
        "elasticity_term": float(pipe.elasticity_term),
    }

    return {
        "schema_version": SCENE_SCHEMA_VERSION,
        "units": {"length": "m", "elevation": "m", "pressure": "bar", "diameter": "mm"},
        "extent": {
            "station_start_m": 0.0,
            "station_end_m": total_length,
            "elevation_min_m": min(elevations) if elevations else 0.0,
            "elevation_max_m": max(elevations) if elevations else 0.0,
            "bounding_radius_m": max(total_length / 2.0, 1.0),
        },
        "profile": profile_points,
        "segments": segment_rows,
        "equipment": {
            "valves": valves,
            "pump": pump,
            "test_head": test_head,
            "pig": pig,
        },
        "ranges": {
            "pressure_bar": {
                "min": min(sampled_pressures) if sampled_pressures else 0.0,
                "max": max(sampled_pressures) if sampled_pressures else 0.0,
            },
            "utilization": {
                "min": min(sampled_utilization) if sampled_utilization else 0.0,
                "max": max(sampled_utilization) if sampled_utilization else 0.0,
            },
        },
        "layers": [
            "ground",
            "pipe",
            "valves",
            "pump",
            "test_head",
            "pig",
            "elevation_profile",
            "pressure_colors",
            "labels",
        ],
        "warnings": warnings,
        "approximate_profile": approximate,
        "profile_points": profile_points,
        "totals": totals,
        "generated_at": iso_z(utcnow()),
        "vertical_exaggeration": 3.0,
    }


__all__ = [
    "APPROXIMATE_PROFILE_WARNING",
    "SCENE_SCHEMA_VERSION",
    "build_scene",
]
