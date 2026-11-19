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


def _natural_section_sort_key(sec_no: str) -> tuple[int, str]:
    import re

    m = re.search(r"\d+", sec_no or "")
    return (int(m.group(0)) if m else 999999, (sec_no or "").upper())


def _thin_points(
    points: list[tuple[float, float]],
    max_points: int,
    *,
    required_xs: set[float] | None = None,
) -> list[tuple[float, float]]:
    if len(points) <= max_points or max_points < 4:
        return points
    min_idx = min(range(len(points)), key=lambda idx: points[idx][1])
    max_idx = max(range(len(points)), key=lambda idx: points[idx][1])
    keep: set[int] = {0, len(points) - 1, min_idx, max_idx}
    if required_xs:
        for idx, (x, _y) in enumerate(points):
            if any(abs(x - rx) <= 1.0 for rx in required_xs):
                keep.add(idx)
    slots = max(0, max_points - len(keep))
    if slots > 0:
        step = (len(points) - 1) / float(slots + 1)
        for slot in range(1, slots + 1):
            keep.add(min(len(points) - 1, round(slot * step)))
    return [points[idx] for idx in sorted(keep)][:max_points]


def build_project_scene(
    db: Any,
    project_id: str,
    workspace_hash: str,
) -> dict[str, Any]:
    """Projedeki tüm test bölümlerini (ve ayrı pafta profillerini) tek birleşik 3D sahnede toplar."""
    import re

    from sqlalchemy import select

    from ..models import HydroSession
    from . import projects as project_service
    from .plan_profile import format_kp, parse_kp_meters

    project = project_service.get_project(db, project_id, workspace_hash)
    rows = (
        db.execute(
            select(HydroSession).where(
                HydroSession.project_id == project.id,
                HydroSession.workspace_id_hash == workspace_hash,
                HydroSession.deleted_at.is_(None),
            )
        )
        .scalars()
        .all()
    )

    if not rows:
        return {
            "project_id": project.id,
            "project_name": project.name,
            "section_count": 0,
            "total_length_m": 0.0,
            "continuity_ok": True,
            "segments": [],
            "equipment": [],
            "profile_points": [],
            "landmarks": [],
            "start_kp_m": None,
            "is_survey_profile": False,
            "warnings": ["Projede henüz kayıtlı test bölümü bulunmuyor."],
            "sections": [],
        }

    records: list[dict[str, Any]] = []
    for idx, sess in enumerate(rows, start=1):
        inputs: dict[str, Any] = sess.inputs if isinstance(sess.inputs, dict) else {}
        raw_meta = inputs.get("section_meta")
        meta: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
        raw_geom = inputs.get("geometry")
        geom: dict[str, Any] = raw_geom if isinstance(raw_geom, dict) else {}
        raw_sp = inputs.get("section_profile")
        sp: dict[str, Any] = raw_sp if isinstance(raw_sp, dict) else {}
        raw_segs_val = inputs.get("segments")
        raw_segs: list[Any] = raw_segs_val if isinstance(raw_segs_val, list) else []

        sec_no = (
            str(meta.get("section_no") or "").strip()
            or str(sess.name or "").split("·")[0].strip()
            or f"K-{idx:02d}"
        )
        start_kp_m = parse_kp_meters(meta.get("start_kp"))
        end_kp_m = parse_kp_meters(meta.get("end_kp"))
        loc_str = str(meta.get("location") or "")
        if (start_kp_m is None or end_kp_m is None) and loc_str:
            kp_tokens = re.findall(r"\d+\s*\+\s*\d+(?:[.,]\d+)?", loc_str)
            if len(kp_tokens) >= 2:
                if start_kp_m is None:
                    start_kp_m = parse_kp_meters(kp_tokens[0])
                if end_kp_m is None:
                    end_kp_m = parse_kp_meters(kp_tokens[1])

        od_mm = as_float(geom.get("outside_diameter_mm"))
        wt_mm = as_float(geom.get("wall_thickness_mm"))
        seg_len_sum = 0.0
        for item in raw_segs:
            if not isinstance(item, dict):
                continue
            l_val = as_float(item.get("length_m"))
            if l_val and l_val > 0:
                seg_len_sum += l_val
            if od_mm is None:
                od_mm = as_float(item.get("outside_diameter_mm"))
            if wt_mm is None:
                wt_mm = as_float(item.get("wall_thickness_mm"))

        has_valid_kp = start_kp_m is not None and end_kp_m is not None and end_kp_m > start_kp_m
        geom_len = as_float(geom.get("length_m"))
        if has_valid_kp:
            assert start_kp_m is not None and end_kp_m is not None
            sec_len = round(end_kp_m - start_kp_m, 2)
        elif geom_len is not None and geom_len > 0:
            sec_len = round(geom_len, 2)
        elif seg_len_sum > 0:
            sec_len = round(seg_len_sum, 2)
        else:
            sec_len = 1000.0

        records.append(
            {
                "session": sess,
                "inputs": inputs,
                "meta": meta,
                "sp": sp,
                "sec_no": sec_no,
                "has_valid_kp": has_valid_kp,
                "start_kp_m": start_kp_m if has_valid_kp else None,
                "end_kp_m": end_kp_m if has_valid_kp else None,
                "start_kp": format_kp(start_kp_m)
                if has_valid_kp
                else str(meta.get("start_kp") or ""),
                "end_kp": format_kp(end_kp_m) if has_valid_kp else str(meta.get("end_kp") or ""),
                "sec_len": sec_len,
                "od_mm": od_mm if od_mm and od_mm > 0 else 406.4,
                "wt_mm": wt_mm if wt_mm and wt_mm > 0 else 8.74,
            }
        )

    def _order_key(rec: dict[str, Any]) -> tuple[Any, ...]:
        s_m = rec["start_kp_m"]
        e_m = rec["end_kp_m"]
        if rec["has_valid_kp"] and s_m is not None:
            return (0, float(s_m), float(e_m if e_m is not None else s_m), "")
        nat, norm = _natural_section_sort_key(rec["sec_no"])
        created = getattr(rec["session"], "created_at", None)
        return (1, float(nat), 0.0, f"{norm}-{created or ''}")

    records.sort(key=_order_key)

    origin_kp_m: float | None = records[0]["start_kp_m"]
    cursor_m = 0.0
    continuity_ok = True
    warnings: list[str] = []

    for idx, rec in enumerate(records):
        s_kp = rec["start_kp_m"]
        sec_no = rec["sec_no"]
        if (
            rec["has_valid_kp"]
            and origin_kp_m is not None
            and s_kp is not None
            and s_kp >= origin_kp_m - 0.5
        ):
            offset_m = round(max(0.0, s_kp - origin_kp_m), 2)
            if idx > 0:
                delta_m = round(offset_m - cursor_m, 1)
                prev_no = records[idx - 1]["sec_no"]
                if delta_m > 1.0:
                    continuity_ok = False
                    warnings.append(
                        f"{prev_no} ile {sec_no} arasında +{int(round(delta_m))} m KP boşluğu var."
                    )
                elif delta_m < -1.0:
                    continuity_ok = False
                    warnings.append(
                        f"{prev_no} ile {sec_no} arasında {int(round(abs(delta_m)))} m KP bindirmesi var."
                    )
        else:
            offset_m = round(cursor_m, 2)
            if idx > 0 or origin_kp_m is not None or not rec["has_valid_kp"]:
                continuity_ok = False
                if s_kp is None:
                    warnings.append(f"{sec_no} için tam KP aralığı eksik; sıraya eklendi.")
                else:
                    warnings.append(
                        f"{sec_no} başlangıç KP ({rec['start_kp']}) proje başlangıcından küçük olduğu için sıraya eklendi."
                    )
        end_offset_m = round(offset_m + rec["sec_len"], 2)
        rec["offset_m"] = offset_m
        rec["end_offset_m"] = end_offset_m
        cursor_m = max(cursor_m, end_offset_m)

    total_length_m = round(cursor_m, 2)
    density = _density()
    any_survey_profile = False
    global_profile_points: list[tuple[float, float]] = []
    boundary_xs: set[float] = set()
    segments: list[dict[str, Any]] = []
    equipment: list[dict[str, Any]] = []
    landmarks: list[dict[str, Any]] = []
    seen_landmarks: list[tuple[float, str, str]] = []
    sections_summary: list[dict[str, Any]] = []
    prev_end_el: float = 0.0

    for idx, rec in enumerate(records):
        sess = rec["session"]
        inputs = rec["inputs"]
        sp = rec["sp"]
        sec_len = rec["sec_len"]
        offset_m = rec["offset_m"]
        end_offset_m = rec["end_offset_m"]
        boundary_xs.add(offset_m)
        boundary_xs.add(end_offset_m)

        # Yerel kot profili
        raw_pts = inputs.get("profile_points")
        local_pts: list[tuple[float, float]] = []
        if isinstance(raw_pts, list) and raw_pts:
            parsed_pts: list[tuple[float, float]] = []
            for item in raw_pts:
                if not isinstance(item, dict):
                    continue
                sx = as_float(item.get("station_m"))
                sy = as_float(item.get("elevation_m"))
                if sx is None or sy is None:
                    continue
                clamped_x = round(max(0.0, min(sec_len, sx)), 2)
                parsed_pts.append((clamped_x, round(sy, 2)))
            parsed_pts.sort(key=lambda pt: pt[0])
            for px, py in parsed_pts:
                if not local_pts or abs(px - local_pts[-1][0]) > 0.5:
                    local_pts.append((px, py))
                else:
                    local_pts[-1] = (px, py)
        has_local_survey = len(local_pts) >= 2
        if has_local_survey:
            any_survey_profile = True
            if local_pts[0][0] > 0.0:
                local_pts.insert(0, (0.0, local_pts[0][1]))
            if local_pts[-1][0] < sec_len:
                local_pts.append((sec_len, local_pts[-1][1]))
        else:
            lowest_el = as_float(sp.get("lowest_elevation_m"))
            highest_el = as_float(sp.get("highest_elevation_m"))
            start_el = as_float(sp.get("start_elevation_m"))
            end_el = as_float(sp.get("end_elevation_m"))
            if start_el is None:
                start_el = lowest_el if lowest_el is not None else prev_end_el
            if end_el is None:
                end_el = highest_el if highest_el is not None else start_el
            if highest_el is None:
                highest_el = max(start_el, end_el)
            if lowest_el is None:
                lowest_el = min(start_el, end_el)
            raw_approx = [
                (0.0, round(start_el, 2)),
                (round(sec_len * 0.33, 2), round(highest_el, 2)),
                (round(sec_len * 0.68, 2), round(lowest_el, 2)),
                (sec_len, round(end_el, 2)),
            ]
            local_pts = []
            for px, py in sorted(raw_approx, key=lambda pt: pt[0]):
                if not local_pts or abs(px - local_pts[-1][0]) > 0.5:
                    local_pts.append((px, py))
                else:
                    local_pts[-1] = (px, py)
            if len(local_pts) < 2:
                local_pts = [(0.0, round(start_el, 2)), (sec_len, round(end_el, 2))]

        prev_end_el = local_pts[-1][1]
        for px, py in local_pts:
            gx = round(offset_m + px, 2)
            if not global_profile_points or abs(gx - global_profile_points[-1][0]) > 0.5:
                global_profile_points.append((gx, round(py, 2)))
            else:
                global_profile_points[-1] = (gx, round(py, 2))

        local_interp = _elevation_interpolator(local_pts)

        # Basınç, SMYS ve durum değerlendirmesi
        raw_field = inputs.get("field")
        field_in: dict[str, Any] = raw_field if isinstance(raw_field, dict) else {}
        raw_pres = inputs.get("pressure")
        pres_in: dict[str, Any] = raw_pres if isinstance(raw_pres, dict) else {}
        raw_air = inputs.get("air")
        air_in: dict[str, Any] = raw_air if isinstance(raw_air, dict) else {}
        base_p = as_float(field_in.get("monitored_pressure_bar"))
        if base_p is None:
            base_p = as_float(sp.get("monitored_pressure_bar"))
        if base_p is None:
            base_p = as_float(pres_in.get("pressure_bar"))
        if base_p is None:
            base_p = as_float(air_in.get("pressure_bar"))

        smys_mpa = as_float(sp.get("smys_mpa")) or 450.0
        limit_smys = (20.0 * smys_mpa * rec["wt_mm"]) / rec["od_mm"] if rec["od_mm"] > 0 else 0.0

        pump_loc = str(inputs.get("pump_location") or "")
        pump_at_end = "Bitis" in pump_loc or "Bitiş" in pump_loc
        pump_local_el = local_interp(sec_len if pump_at_end else 0.0)

        rs = sess.result_summary if isinstance(sess.result_summary, dict) else {}
        air_stat = str((rs.get("air") or {}).get("status") or "").upper()
        pres_stat = str((rs.get("pressure") or {}).get("status") or "").upper()
        if air_stat == "BASARISIZ" or pres_stat == "BASARISIZ":
            base_status = "fail"
        elif air_stat == "BASARILI" or pres_stat == "BASARILI":
            base_status = "pass"
        else:
            base_status = "pending"

        target_pts = max(3, min(24, round(64.0 * sec_len / max(total_length_m, 1.0))))
        sub_pts = _thin_points(local_pts, target_pts)
        bps = sorted({0.0, sec_len, *(pt[0] for pt in sub_pts)})
        clean_bps: list[float] = []
        for bp in bps:
            if not clean_bps or (bp - clean_bps[-1]) >= 0.5:
                clean_bps.append(bp)
        if clean_bps and clean_bps[-1] < sec_len:
            if (sec_len - clean_bps[-1]) >= 0.5:
                clean_bps.append(sec_len)
            else:
                clean_bps[-1] = sec_len

        sec_status_worst = base_status
        for sub_idx in range(len(clean_bps) - 1):
            a = clean_bps[sub_idx]
            b = clean_bps[sub_idx + 1]
            if b - a < 0.5:
                continue
            z0 = round(local_interp(a), 2)
            z1 = round(local_interp(b), 2)
            z_mid = 0.5 * (z0 + z1)

            seg_pressure: float | None = None
            utilization: float | None = None
            seg_status = base_status
            if base_p is not None and base_p > 0:
                head_bar = (
                    density
                    * GRAVITY_M_PER_S2
                    * (z_mid - pump_local_el)
                    / PRESSURE_CONVERSION_PASCAL_TO_BAR
                )
                seg_pressure = max(0.0, round(base_p - head_bar, 2))
                if limit_smys > 0:
                    utilization = round(seg_pressure / limit_smys, 4)
                    if utilization > 1.0:
                        seg_status = "fail"
                    elif base_status == "fail":
                        seg_status = "fail"
                    elif utilization > 0.9:
                        seg_status = "warning"
                    elif base_status == "pass":
                        seg_status = "pass"
                    else:
                        seg_status = "pass"

            if seg_status == "fail":
                sec_status_worst = "fail"
            elif seg_status == "warning" and sec_status_worst != "fail":
                sec_status_worst = "warning"
            elif seg_status == "pass" and sec_status_worst == "pending":
                sec_status_worst = "pass"

            if rec["has_valid_kp"] and rec["start_kp_m"] is not None:
                lbl = (
                    f"{rec['sec_no']} · KP {format_kp(rec['start_kp_m'] + a)}"
                    f"–{format_kp(rec['start_kp_m'] + b)}"
                )
            else:
                lbl = f"{rec['sec_no']} · #{sub_idx + 1}"

            seg_row: dict[str, Any] = {
                "id": f"proj-seg-{idx + 1}-{sub_idx + 1}",
                "session_id": sess.id,
                "section_no": rec["sec_no"],
                "label": lbl,
                "start_m": round(offset_m + a, 2),
                "end_m": round(offset_m + b, 2),
                "start_elevation_m": z0,
                "end_elevation_m": z1,
                "outside_diameter_mm": round(rec["od_mm"], 2),
                "wall_thickness_mm": round(rec["wt_mm"], 2),
                "status": seg_status,
            }
            if seg_pressure is not None:
                seg_row["pressure_bar"] = seg_pressure
            if utilization is not None:
                seg_row["utilization"] = utilization
            segments.append(seg_row)

        # Bölüm sınırı ekipman vanası
        if idx > 0:
            prev_no = records[idx - 1]["sec_no"]
            kp_note = f" (KP {rec['start_kp']})" if rec["has_valid_kp"] and rec["start_kp"] else ""
            equipment.append(
                {
                    "id": f"eq-boundary-{idx}",
                    "type": "valve",
                    "label": f"{prev_no} → {rec['sec_no']} Sınırı{kp_note}",
                    "distance_m": round(offset_m, 1),
                    "elevation_m": round(local_interp(0.0), 1),
                    "status": "pass",
                }
            )

        # Pafta saha geçiş noktaları (landmarks)
        raw_lms_val = inputs.get("landmarks")
        raw_lms: list[Any] = raw_lms_val if isinstance(raw_lms_val, list) else []
        for lm in raw_lms:
            if not isinstance(lm, dict):
                continue
            lm_st = as_float(lm.get("station_m"))
            lm_lbl = str(lm.get("label") or "").strip()
            if lm_st is None or not lm_lbl:
                continue
            clamped_st = max(0.0, min(sec_len, lm_st))
            global_d = round(offset_m + clamped_st, 1)
            lm_kind = str(lm.get("kind") or "crossing")
            if any(
                abs(global_d - kd) <= 50.0 and lm_kind == kk and lm_lbl.casefold() == kl.casefold()
                for kd, kk, kl in seen_landmarks
            ):
                continue
            seen_landmarks.append((global_d, lm_kind, lm_lbl))
            lm_el = as_float(lm.get("elevation_m"))
            if lm_el is None:
                lm_el = round(local_interp(clamped_st), 1)
            kp_val = str(lm.get("kp") or "").strip()
            if not kp_val and rec["has_valid_kp"] and rec["start_kp_m"] is not None:
                kp_val = format_kp(rec["start_kp_m"] + clamped_st)
            landmarks.append(
                {
                    "id": f"lm-{len(landmarks) + 1}",
                    "distance_m": global_d,
                    "elevation_m": round(lm_el, 1),
                    "kp": kp_val or None,
                    "kind": lm_kind,
                    "label": lm_lbl,
                }
            )

        sections_summary.append(
            {
                "session_id": sess.id,
                "section_no": rec["sec_no"],
                "name": sess.name,
                "start_kp": rec["start_kp"],
                "end_kp": rec["end_kp"],
                "start_m": round(offset_m, 2),
                "end_m": round(end_offset_m, 2),
                "length_m": round(rec["sec_len"], 2),
                "status": sec_status_worst,
            }
        )

    thinned_profile = _thin_points(global_profile_points, 300, required_xs=boundary_xs)
    global_interp = _elevation_interpolator(thinned_profile)

    # Başlangıç / bitiş ve ekstremum kot göstergeleri
    start_el_g = round(global_interp(0.0), 1) if thinned_profile else 0.0
    end_el_g = round(global_interp(total_length_m), 1) if thinned_profile else 0.0
    equipment.insert(
        0,
        {
            "id": "eq-pump-start",
            "type": "pump",
            "label": "Hat Başlangıcı / Pompa",
            "distance_m": 0.0,
            "elevation_m": start_el_g,
            "status": "pass",
        },
    )
    equipment.insert(
        0,
        {
            "id": "eq-launcher-start",
            "type": "pig-launcher",
            "label": "Pig Başlatıcı",
            "distance_m": 0.0,
            "elevation_m": start_el_g,
            "status": "pass",
        },
    )
    equipment.append(
        {
            "id": "eq-receiver-end",
            "type": "pig-receiver",
            "label": "Hat Sonu / Pig Alıcı",
            "distance_m": round(total_length_m, 1),
            "elevation_m": end_el_g,
            "status": "pass",
        }
    )

    if len(thinned_profile) >= 3:
        max_pt = max(thinned_profile, key=lambda pt: pt[1])
        min_pt = min(thinned_profile, key=lambda pt: pt[1])
        if 40.0 < max_pt[0] < total_length_m - 40.0:
            kp_txt = (
                f" (KP {format_kp(origin_kp_m + max_pt[0])})" if origin_kp_m is not None else ""
            )
            equipment.append(
                {
                    "id": "eq-global-summit",
                    "type": "gauge",
                    "label": f"Zirve · {max_pt[1]:.1f} m{kp_txt}",
                    "distance_m": round(max_pt[0], 1),
                    "elevation_m": round(max_pt[1], 1),
                    "status": "warning",
                }
            )
        if 40.0 < min_pt[0] < total_length_m - 40.0 and abs(min_pt[0] - max_pt[0]) > 40.0:
            kp_txt = (
                f" (KP {format_kp(origin_kp_m + min_pt[0])})" if origin_kp_m is not None else ""
            )
            equipment.append(
                {
                    "id": "eq-global-lowpoint",
                    "type": "gauge",
                    "label": f"Maks. Statik Yük · {min_pt[1]:.1f} m{kp_txt}",
                    "distance_m": round(min_pt[0], 1),
                    "elevation_m": round(min_pt[1], 1),
                    "status": "pass",
                }
            )

    pressures = [
        seg["pressure_bar"] for seg in segments if isinstance(seg.get("pressure_bar"), (int, float))
    ]
    payload: dict[str, Any] = {
        "project_id": project.id,
        "project_name": project.name,
        "section_count": len(sections_summary),
        "total_length_m": total_length_m,
        "continuity_ok": continuity_ok,
        "segments": segments,
        "equipment": equipment,
        "profile_points": [[pt[0], pt[1]] for pt in thinned_profile],
        "landmarks": landmarks,
        "start_kp_m": origin_kp_m,
        "is_survey_profile": any_survey_profile,
        "warnings": list(dict.fromkeys(warnings)),
        "sections": sections_summary,
    }
    if pressures:
        payload["pressure_min_bar"] = min(pressures)
        payload["pressure_max_bar"] = max(pressures)
    return payload


__all__ = [
    "APPROXIMATE_PROFILE_WARNING",
    "SCENE_SCHEMA_VERSION",
    "build_project_scene",
    "build_scene",
]
