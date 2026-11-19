"""Sartname 14.1-14.3: basinclandirma hizi, basinc-hacim izleme ve 2 saatlik bekleme.

Kaynak: ``4-NGTL 0-GN-P-002-5007 R4`` bolum 14.

* 14.1: Izlenen basincin SMYS'nin %80'inden %95'ine cikarilmasi sirasinda
  basinc artis hizi dakikada en fazla 1 bar olmalidir.
* 14.2: %95 SMYS test basincina ulasildiktan sonra %100 SMYS'ye kadar
  basinc-hacim iliskisi 0,2 bar'lik artislarla izlenir; test basincina
  ulasmak icin doldurulan toplam su hacminin %0,2'sinden fazla su basilirsa
  basinclandirma DURDURULUR ve Idarenin talimati beklenir.
* 14.3: Test basincina erisildiginde 2 saatlik bekleme baslar, basinc ve sicaklik
  her 15 dakikada bir okunur. Bekleme sonunda basinc dususu varsa basinc
  yeniden izlenen basincin %100'une cikarilir.

Yorum notu (14.2): "basilan su" %95 SMYS'ye ulasildigi andaki kumulatif pompalanan
hacimden sonra eklenen su olarak yorumlanir ve doldurulan toplam su hacmine oranlanir.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Final

from .hydrotest_core import ValidationError
from .pressurization import (
    PRESSURIZATION_MIN_PRESSURE_TOLERANCE_BAR,
    PRESSURIZATION_RELATIVE_PRESSURE_TOLERANCE,
    PRESSURIZATION_VOLUME_DEVIATION_LIMIT_PERCENT,
)

RAMP_START_SMYS_FRACTION: Final[float] = 0.80
RAMP_END_SMYS_FRACTION: Final[float] = 0.95
FULL_SMYS_FRACTION: Final[float] = 1.00
MAX_RAMP_RATE_BAR_PER_MIN: Final[float] = 1.0
MONITORING_STEP_BAR: Final[float] = 0.2
HOLD_DURATION_MIN: Final[float] = 120.0
HOLD_READING_INTERVAL_MIN: Final[float] = 15.0

_PRESSURE_EPS_BAR: Final[float] = 1e-6
_TIME_EPS_MIN: Final[float] = 1e-6
_STEP_TOLERANCE_BAR: Final[float] = 1e-6
_INTERVAL_TOLERANCE_MIN: Final[float] = 0.5


def _finite(value: float, label: str) -> float:
    if not isfinite(value):
        raise ValidationError(f"{label} sonlu bir sayi olmalidir.")
    return value


@dataclass(frozen=True)
class PressurizationReading:
    """Basinclandirma sirasindaki tek okuma."""

    elapsed_min: float
    pressure_bar: float
    cumulative_added_volume_m3: float

    def __post_init__(self) -> None:
        _finite(self.elapsed_min, "Gecen sure")
        _finite(self.pressure_bar, "Basinc")
        _finite(self.cumulative_added_volume_m3, "Kumulatif ilave su hacmi")
        if self.elapsed_min < 0:
            raise ValidationError("Gecen sure negatif olamaz.")
        if self.pressure_bar < 0:
            raise ValidationError("Basinc negatif olamaz.")
        if self.cumulative_added_volume_m3 < 0:
            raise ValidationError("Kumulatif ilave su hacmi negatif olamaz.")


@dataclass(frozen=True)
class PressurizationRampInputs:
    readings: tuple[PressurizationReading, ...]
    test_pressure_100_smys_bar: float
    total_filled_volume_m3: float

    def __post_init__(self) -> None:
        _finite(self.test_pressure_100_smys_bar, "%100 SMYS test basinci")
        _finite(self.total_filled_volume_m3, "Doldurulan toplam su hacmi")
        if self.test_pressure_100_smys_bar <= 0:
            raise ValidationError("%100 SMYS test basinci sifirdan buyuk olmalidir.")
        if self.total_filled_volume_m3 <= 0:
            raise ValidationError("Doldurulan toplam su hacmi sifirdan buyuk olmalidir.")
        if len(self.readings) < 2:
            raise ValidationError("Basinclandirma izleme icin en az iki okuma gerekir.")
        previous = self.readings[0]
        for reading in self.readings[1:]:
            if reading.elapsed_min <= previous.elapsed_min + _TIME_EPS_MIN:
                raise ValidationError("Okumalar artan zaman sirasinda olmalidir.")
            if reading.cumulative_added_volume_m3 + _PRESSURE_EPS_BAR < (
                previous.cumulative_added_volume_m3
            ):
                raise ValidationError("Kumulatif ilave su hacmi azalamaz.")
            previous = reading


@dataclass(frozen=True)
class RampRateViolation:
    start_elapsed_min: float
    end_elapsed_min: float
    rate_bar_per_min: float


@dataclass(frozen=True)
class PressurizationRampResult:
    max_ramp_rate_bar_per_min: float
    ramp_rate_violations: tuple[RampRateViolation, ...]
    reached_95_smys: bool
    reached_100_smys: bool
    pumped_since_95_smys_m3: float
    excess_volume_limit_m3: float
    excess_volume_percent: float
    volume_limit_exceeded: bool
    stop_required: bool
    monitoring_gaps: tuple[float, ...]
    passed: bool | None
    ramp_rate_limit_bar_per_min: float = MAX_RAMP_RATE_BAR_PER_MIN
    volume_limit_percent: float = PRESSURIZATION_VOLUME_DEVIATION_LIMIT_PERCENT


def evaluate_pressurization_ramp(inputs: PressurizationRampInputs) -> PressurizationRampResult:
    """14.1 artis hizi ve 14.2 basinc-hacim izlemesini okuma serisi uzerinden degerlendirir.

    ``passed``: ``False`` ihlal/durdurma varsa, ``None`` %100 SMYS'ye henuz ulasilmadiysa,
    aksi halde ``True``.
    """

    p100 = inputs.test_pressure_100_smys_bar
    p80 = RAMP_START_SMYS_FRACTION * p100
    p95 = RAMP_END_SMYS_FRACTION * p100
    readings = inputs.readings

    # 14.1: %80-%95 SMYS bandi icindeki araliklarda artis hizi.
    violations: list[RampRateViolation] = []
    max_rate = 0.0
    for previous, current in zip(readings, readings[1:]):
        if previous.pressure_bar < p80 - _PRESSURE_EPS_BAR:
            continue
        if current.pressure_bar > p95 + _PRESSURE_EPS_BAR:
            continue
        delta_min = current.elapsed_min - previous.elapsed_min
        rate = (current.pressure_bar - previous.pressure_bar) / delta_min
        if rate > max_rate:
            max_rate = rate
        if rate > MAX_RAMP_RATE_BAR_PER_MIN + _PRESSURE_EPS_BAR:
            violations.append(
                RampRateViolation(
                    start_elapsed_min=previous.elapsed_min,
                    end_elapsed_min=current.elapsed_min,
                    rate_bar_per_min=rate,
                )
            )

    # 14.2: %95 SMYS'den sonraki pompalanan hacim ve 0,2 bar izleme adimlari.
    reference_index: int | None = None
    for index, reading in enumerate(readings):
        if reading.pressure_bar >= p95 - _PRESSURE_EPS_BAR:
            reference_index = index
            break

    reached_95 = reference_index is not None
    reached_100 = any(r.pressure_bar >= p100 - _PRESSURE_EPS_BAR for r in readings)
    excess_limit_m3 = (
        PRESSURIZATION_VOLUME_DEVIATION_LIMIT_PERCENT / 100.0 * inputs.total_filled_volume_m3
    )
    pumped_since_95 = 0.0
    gaps: list[float] = []
    if reference_index is not None:
        baseline = readings[reference_index].cumulative_added_volume_m3
        pumped_since_95 = readings[-1].cumulative_added_volume_m3 - baseline
        for previous, current in zip(readings[reference_index:], readings[reference_index + 1 :]):
            step = current.pressure_bar - previous.pressure_bar
            if step > MONITORING_STEP_BAR + _STEP_TOLERANCE_BAR:
                gaps.append(step)

    excess_percent = pumped_since_95 / inputs.total_filled_volume_m3 * 100.0
    volume_exceeded = pumped_since_95 > excess_limit_m3 + 1e-9
    stop_required = volume_exceeded and not reached_100

    passed: bool | None
    if violations or volume_exceeded:
        passed = False
    elif not reached_100:
        passed = None
    else:
        passed = True

    return PressurizationRampResult(
        max_ramp_rate_bar_per_min=max_rate,
        ramp_rate_violations=tuple(violations),
        reached_95_smys=reached_95,
        reached_100_smys=reached_100,
        pumped_since_95_smys_m3=pumped_since_95,
        excess_volume_limit_m3=excess_limit_m3,
        excess_volume_percent=excess_percent,
        volume_limit_exceeded=volume_exceeded,
        stop_required=stop_required,
        monitoring_gaps=tuple(gaps),
        passed=passed,
    )


@dataclass(frozen=True)
class HoldReading:
    """14.3 bekleme suresi okumasi (basinc + sicaklik)."""

    elapsed_min: float
    pressure_bar: float
    temperature_c: float

    def __post_init__(self) -> None:
        _finite(self.elapsed_min, "Gecen sure")
        _finite(self.pressure_bar, "Basinc")
        _finite(self.temperature_c, "Sicaklik")
        if self.elapsed_min < 0:
            raise ValidationError("Gecen sure negatif olamaz.")
        if self.pressure_bar < 0:
            raise ValidationError("Basinc negatif olamaz.")


@dataclass(frozen=True)
class PressureHoldInputs:
    readings: tuple[HoldReading, ...]
    target_pressure_bar: float

    def __post_init__(self) -> None:
        _finite(self.target_pressure_bar, "Hedef basinc")
        if self.target_pressure_bar <= 0:
            raise ValidationError("Hedef basinc sifirdan buyuk olmalidir.")
        if len(self.readings) < 2:
            raise ValidationError("Bekleme kaydi icin en az iki okuma gerekir.")
        previous = self.readings[0]
        for reading in self.readings[1:]:
            if reading.elapsed_min <= previous.elapsed_min + _TIME_EPS_MIN:
                raise ValidationError("Okumalar artan zaman sirasinda olmalidir.")
            previous = reading


@dataclass(frozen=True)
class PressureHoldResult:
    duration_min: float
    duration_ok: bool
    max_reading_gap_min: float
    interval_ok: bool
    pressure_drop_bar: float
    pressure_tolerance_bar: float
    repressurize_required: bool
    passed: bool
    required_duration_min: float = HOLD_DURATION_MIN
    required_interval_min: float = HOLD_READING_INTERVAL_MIN


def evaluate_pressure_hold(inputs: PressureHoldInputs) -> PressureHoldResult:
    """14.3: 2 saatlik bekleme, 15 dakikalik kayit araligi ve basinc dususu kontrolu.

    Basinc dususu bir basarisizlik degil, ``repressurize_required`` talimatidir:
    basinc yeniden izlenen basincin %100'une cikarilmalidir.
    """

    readings = inputs.readings
    duration = readings[-1].elapsed_min - readings[0].elapsed_min
    gaps = [b.elapsed_min - a.elapsed_min for a, b in zip(readings, readings[1:])]
    max_gap = max(gaps)

    duration_ok = duration >= HOLD_DURATION_MIN - _TIME_EPS_MIN
    interval_ok = max_gap <= HOLD_READING_INTERVAL_MIN + _INTERVAL_TOLERANCE_MIN

    tolerance = max(
        PRESSURIZATION_MIN_PRESSURE_TOLERANCE_BAR,
        PRESSURIZATION_RELATIVE_PRESSURE_TOLERANCE * inputs.target_pressure_bar,
    )
    drop = inputs.target_pressure_bar - readings[-1].pressure_bar
    repressurize = drop > tolerance

    return PressureHoldResult(
        duration_min=duration,
        duration_ok=duration_ok,
        max_reading_gap_min=max_gap,
        interval_ok=interval_ok,
        pressure_drop_bar=drop,
        pressure_tolerance_bar=tolerance,
        repressurize_required=repressurize,
        passed=duration_ok and interval_ok,
    )
