from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from .hydrotest_core import FLOAT_TOLERANCE, ValidationError


@dataclass(frozen=True)
class PigSpeedLimit:
    label: str
    spec_reference: str
    max_speed_m_per_s: float | None

    @property
    def max_speed_km_per_h(self) -> float | None:
        if self.max_speed_m_per_s is None:
            return None
        return self.max_speed_m_per_s * 3.6

    @property
    def option_label(self) -> str:
        if self.max_speed_m_per_s is None:
            return f"{self.label} | limit yok | {self.spec_reference}"
        return f"{self.label} | max {self.max_speed_m_per_s:.3f} m/sn | {self.spec_reference}"


PIG_SPEED_LIMITS: Final[tuple[PigSpeedLimit, ...]] = (
    PigSpeedLimit("Temizlik pigi", "Madde 9", 2.5),
    PigSpeedLimit("On kurutma pigi", "Madde 18.3", 8.0 / 3.6),
    PigSpeedLimit("Nihai kurutma sunger pigi", "Madde 20.5", 1.2),
    PigSpeedLimit("Serbest kontrol", "Bilgi", None),
)


@dataclass(frozen=True)
class PigSpeedResult:
    distance_m: float
    travel_time_min: float
    speed_m_per_s: float
    speed_km_per_h: float
    limit: PigSpeedLimit
    passed: bool | None


def get_pig_speed_limit_options() -> tuple[str, ...]:
    return tuple(limit.option_label for limit in PIG_SPEED_LIMITS)


def get_pig_speed_limit(option_label: str) -> PigSpeedLimit:
    normalized = option_label.strip()
    for limit in PIG_SPEED_LIMITS:
        if limit.option_label == normalized:
            return limit
    raise ValidationError("Gecerli bir pig modu secin.")


def evaluate_pig_speed(distance_m: float, travel_time_min: float, limit: PigSpeedLimit) -> PigSpeedResult:
    if distance_m <= 0:
        raise ValidationError("Pig mesafesi sifirdan buyuk olmalidir.")
    if travel_time_min <= 0:
        raise ValidationError("Pig gelis suresi sifirdan buyuk olmalidir.")

    travel_time_seconds = travel_time_min * 60.0
    speed_m_per_s = distance_m / travel_time_seconds
    speed_km_per_h = speed_m_per_s * 3.6

    passed: bool | None = None
    if limit.max_speed_m_per_s is not None:
        passed = speed_m_per_s <= limit.max_speed_m_per_s + FLOAT_TOLERANCE

    return PigSpeedResult(
        distance_m=distance_m,
        travel_time_min=travel_time_min,
        speed_m_per_s=speed_m_per_s,
        speed_km_per_h=speed_km_per_h,
        limit=limit,
        passed=passed,
    )
