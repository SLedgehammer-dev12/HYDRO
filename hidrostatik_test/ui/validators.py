from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tkinter as tk


def safe_float(value: str) -> float | None:
    normalized = value.strip().replace(",", ".")
    if not normalized:
        return None
    try:
        return float(normalized)
    except ValueError:
        return None


def validate_geometry_inputs(
    outside_diameter_mm: float | None,
    wall_thickness_mm: float | None,
    length_m: float | None,
) -> tuple[str | None, str]:
    if outside_diameter_mm is None or wall_thickness_mm is None or length_m is None:
        return None, "incomplete"
    
    if outside_diameter_mm <= 0:
        return "Dis cap sifirdan buyuk olmalidir.", "error"
    
    if wall_thickness_mm <= 0:
        return "Et kalinligi sifirdan buyuk olmalidir.", "error"
    
    if length_m <= 0:
        return "Hat uzunlugu sifirdan buyuk olmalidir.", "error"
    
    if wall_thickness_mm * 2 >= outside_diameter_mm:
        return "Et kalinligi borunun ic capini sifira dusurecek kadar buyuk olamaz.", "error"
    
    return None, "valid"


def validate_elevation_inputs(
    highest_elevation_m: float | None,
    lowest_elevation_m: float | None,
    start_elevation_m: float | None,
    end_elevation_m: float | None,
) -> tuple[str | None, str]:
    if any(v is None for v in [highest_elevation_m, lowest_elevation_m, start_elevation_m, end_elevation_m]):
        return None, "incomplete"
    
    if highest_elevation_m < lowest_elevation_m:
        return "En yuksek nokta kotu, en dusuk noktadan kucuk olamaz.", "error"
    
    for label, elevation in [("Baslangic", start_elevation_m), ("Bitis", end_elevation_m)]:
        if elevation < lowest_elevation_m or elevation > highest_elevation_m:
            return f"{label} noktasi kotu, min/max kot araligi icinde olmalidir.", "error"
    
    return None, "valid"


__all__ = [
    "safe_float",
    "validate_elevation_inputs",
    "validate_geometry_inputs",
]
