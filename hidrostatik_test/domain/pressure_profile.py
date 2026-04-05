from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from .hydrotest_core import PipeGeometry, PipeModel, PipeSection, ValidationError

WATER_DENSITY_AT_15C_KG_PER_M3: Final[float] = 999.1
GRAVITY_M_PER_S2: Final[float] = 9.80665
PRESSURE_CONVERSION_PASCAL_TO_BAR: Final[float] = 100000.0
CLASS_1_2_MIN_FACTOR: Final[float] = 1.25
CLASS_3_4_MIN_FACTOR: Final[float] = 1.50
MAX_TEST_SECTION_LENGTH_M: Final[float] = 20000.0
MAX_TEST_SECTION_VOLUME_M3: Final[float] = 12500.0
START_PUMP_LOCATION: Final[str] = "Baslangic noktasi"
END_PUMP_LOCATION: Final[str] = "Bitis noktasi"


@dataclass(frozen=True)
class LocationClassRule:
    label: str
    class_number: int
    minimum_test_factor: float
    spec_reference: str


@dataclass(frozen=True)
class PressureWindow:
    location_label: str
    location_elevation_m: float
    hydraulic_head_to_high_point_bar: float
    hydraulic_head_to_low_point_bar: float
    minimum_required_pressure_bar: float
    maximum_allowable_pressure_bar: float


@dataclass(frozen=True)
class SectionPressureProfileInputs:
    pipe: PipeModel
    design_pressure_bar: float
    smys_mpa: float
    location_class: LocationClassRule
    highest_elevation_m: float
    lowest_elevation_m: float
    start_elevation_m: float
    end_elevation_m: float
    selected_pump_location: str
    monitored_pressure_bar: float | None = None

    def __post_init__(self) -> None:
        if self.design_pressure_bar <= 0:
            raise ValidationError("Dizayn basinci sifirdan buyuk olmalidir.")
        if self.smys_mpa <= 0:
            raise ValidationError("SMYS sifirdan buyuk olmalidir.")
        if self.highest_elevation_m < self.lowest_elevation_m:
            raise ValidationError("En yuksek nokta kotu, en dusuk nokta kotundan kucuk olamaz.")
        for label, elevation in (
            ("Baslangic noktasi", self.start_elevation_m),
            ("Bitis noktasi", self.end_elevation_m),
        ):
            if elevation < self.lowest_elevation_m or elevation > self.highest_elevation_m:
                raise ValidationError(f"{label} kotu, min/max kot araligi icinde olmalidir.")
        if self.selected_pump_location not in {START_PUMP_LOCATION, END_PUMP_LOCATION}:
            raise ValidationError("Pompa konumu kullanici tarafindan baslangic veya bitis noktasi olarak secilmelidir.")
        if self.monitored_pressure_bar is not None and self.monitored_pressure_bar < 0:
            raise ValidationError("Izlenen basinc negatif olamaz.")


@dataclass(frozen=True)
class SectionPressureProfileResult:
    location_class: LocationClassRule
    required_minimum_pressure_at_high_point_bar: float
    maximum_allowable_pressure_at_low_point_bar: float
    hydraulic_span_bar: float
    required_pressure_with_span_bar: float
    start_window: PressureWindow
    end_window: PressureWindow
    selected_window: PressureWindow
    limiting_pressure_at_100_smys_bar: float
    limiting_pipe_description: str
    total_length_m: float
    total_internal_volume_m3: float
    within_length_limit: bool
    within_volume_limit: bool
    within_100_smys_span_limit: bool
    feasible: bool
    monitored_pressure_bar: float | None
    monitored_meets_minimum: bool | None
    monitored_under_maximum: bool | None


LOCATION_CLASS_RULES: tuple[LocationClassRule, ...] = (
    LocationClassRule(
        label="Class 1 - min 1.25 x dizayn basinci",
        class_number=1,
        minimum_test_factor=CLASS_1_2_MIN_FACTOR,
        spec_reference="NGTL 5007 / 4.2, ASME B31.8 Class 1",
    ),
    LocationClassRule(
        label="Class 2 - min 1.25 x dizayn basinci",
        class_number=2,
        minimum_test_factor=CLASS_1_2_MIN_FACTOR,
        spec_reference="NGTL 5007 / 4.2, ASME B31.8 Class 2",
    ),
    LocationClassRule(
        label="Class 3 - min 1.50 x dizayn basinci",
        class_number=3,
        minimum_test_factor=CLASS_3_4_MIN_FACTOR,
        spec_reference="NGTL 5007 / 4.2, ASME B31.8 Class 3",
    ),
    LocationClassRule(
        label="Class 4 - min 1.50 x dizayn basinci",
        class_number=4,
        minimum_test_factor=CLASS_3_4_MIN_FACTOR,
        spec_reference="NGTL 5007 / 4.2, ASME B31.8 Class 4",
    ),
)


def get_location_class_options() -> tuple[str, ...]:
    return tuple(rule.label for rule in LOCATION_CLASS_RULES)


def get_pump_location_options() -> tuple[str, ...]:
    return (START_PUMP_LOCATION, END_PUMP_LOCATION)


def get_location_class_rule(label: str) -> LocationClassRule:
    normalized = label.strip()
    for rule in LOCATION_CLASS_RULES:
        if rule.label == normalized:
            return rule
    raise ValidationError(f"Bilinmeyen Location Class secimi: {label}")


def evaluate_section_pressure_profile(inputs: SectionPressureProfileInputs) -> SectionPressureProfileResult:
    required_minimum_pressure_at_high_point_bar = (
        inputs.design_pressure_bar * inputs.location_class.minimum_test_factor
    )
    hydraulic_span_bar = _hydraulic_head_bar(inputs.highest_elevation_m - inputs.lowest_elevation_m)
    required_pressure_with_span_bar = required_minimum_pressure_at_high_point_bar + hydraulic_span_bar
    limiting_pressure_at_100_smys_bar, limiting_pipe_description = _pressure_at_100_smys_bar(
        pipe=inputs.pipe,
        smys_mpa=inputs.smys_mpa,
    )
    total_length_m = _pipe_model_total_length_m(inputs.pipe)
    total_internal_volume_m3 = inputs.pipe.internal_volume_m3
    within_length_limit = total_length_m <= MAX_TEST_SECTION_LENGTH_M
    within_volume_limit = total_internal_volume_m3 <= MAX_TEST_SECTION_VOLUME_M3
    within_100_smys_span_limit = required_pressure_with_span_bar <= limiting_pressure_at_100_smys_bar
    start_window = _build_pressure_window(
        location_label=START_PUMP_LOCATION,
        location_elevation_m=inputs.start_elevation_m,
        required_minimum_pressure_at_high_point_bar=required_minimum_pressure_at_high_point_bar,
        maximum_allowable_pressure_at_low_point_bar=limiting_pressure_at_100_smys_bar,
        highest_elevation_m=inputs.highest_elevation_m,
        lowest_elevation_m=inputs.lowest_elevation_m,
    )
    end_window = _build_pressure_window(
        location_label=END_PUMP_LOCATION,
        location_elevation_m=inputs.end_elevation_m,
        required_minimum_pressure_at_high_point_bar=required_minimum_pressure_at_high_point_bar,
        maximum_allowable_pressure_at_low_point_bar=limiting_pressure_at_100_smys_bar,
        highest_elevation_m=inputs.highest_elevation_m,
        lowest_elevation_m=inputs.lowest_elevation_m,
    )
    selected_window = start_window if inputs.selected_pump_location == START_PUMP_LOCATION else end_window
    feasible = within_100_smys_span_limit and within_length_limit and within_volume_limit

    monitored_meets_minimum: bool | None = None
    monitored_under_maximum: bool | None = None
    if inputs.monitored_pressure_bar is not None:
        monitored_meets_minimum = inputs.monitored_pressure_bar >= selected_window.minimum_required_pressure_bar
        monitored_under_maximum = inputs.monitored_pressure_bar <= selected_window.maximum_allowable_pressure_bar

    return SectionPressureProfileResult(
        location_class=inputs.location_class,
        required_minimum_pressure_at_high_point_bar=required_minimum_pressure_at_high_point_bar,
        maximum_allowable_pressure_at_low_point_bar=limiting_pressure_at_100_smys_bar,
        hydraulic_span_bar=hydraulic_span_bar,
        required_pressure_with_span_bar=required_pressure_with_span_bar,
        start_window=start_window,
        end_window=end_window,
        selected_window=selected_window,
        limiting_pressure_at_100_smys_bar=limiting_pressure_at_100_smys_bar,
        limiting_pipe_description=limiting_pipe_description,
        total_length_m=total_length_m,
        total_internal_volume_m3=total_internal_volume_m3,
        within_length_limit=within_length_limit,
        within_volume_limit=within_volume_limit,
        within_100_smys_span_limit=within_100_smys_span_limit,
        feasible=feasible,
        monitored_pressure_bar=inputs.monitored_pressure_bar,
        monitored_meets_minimum=monitored_meets_minimum,
        monitored_under_maximum=monitored_under_maximum,
    )


def _build_pressure_window(
    *,
    location_label: str,
    location_elevation_m: float,
    required_minimum_pressure_at_high_point_bar: float,
    maximum_allowable_pressure_at_low_point_bar: float,
    highest_elevation_m: float,
    lowest_elevation_m: float,
) -> PressureWindow:
    hydraulic_head_to_high_point_bar = _hydraulic_head_bar(highest_elevation_m - location_elevation_m)
    hydraulic_head_to_low_point_bar = _hydraulic_head_bar(location_elevation_m - lowest_elevation_m)
    return PressureWindow(
        location_label=location_label,
        location_elevation_m=location_elevation_m,
        hydraulic_head_to_high_point_bar=hydraulic_head_to_high_point_bar,
        hydraulic_head_to_low_point_bar=hydraulic_head_to_low_point_bar,
        minimum_required_pressure_bar=required_minimum_pressure_at_high_point_bar + hydraulic_head_to_high_point_bar,
        maximum_allowable_pressure_bar=maximum_allowable_pressure_at_low_point_bar - hydraulic_head_to_low_point_bar,
    )


def _hydraulic_head_bar(delta_h_m: float) -> float:
    return WATER_DENSITY_AT_15C_KG_PER_M3 * delta_h_m * GRAVITY_M_PER_S2 / PRESSURE_CONVERSION_PASCAL_TO_BAR


def _pressure_at_100_smys_bar(pipe: PipeModel, smys_mpa: float) -> tuple[float, str]:
    if isinstance(pipe, PipeSection):
        pressure_bar = _pipe_section_pressure_at_100_smys_bar(pipe, smys_mpa)
        description = (
            f"Tek kesit | OD={pipe.outside_diameter_mm:.2f} mm | Et={pipe.wall_thickness_mm:.2f} mm"
        )
        return pressure_bar, description

    limiting_index = -1
    limiting_pressure = float("inf")
    for index, section in enumerate(pipe.sections, start=1):
        candidate = _pipe_section_pressure_at_100_smys_bar(section, smys_mpa)
        if candidate < limiting_pressure:
            limiting_pressure = candidate
            limiting_index = index
    if limiting_index < 0:
        raise ValidationError("Segmentli geometri icin 100% SMYS limiti hesaplanamadi.")
    limiting_section = pipe.sections[limiting_index - 1]
    description = (
        f"Limit segment {limiting_index} | OD={limiting_section.outside_diameter_mm:.2f} mm | "
        f"Et={limiting_section.wall_thickness_mm:.2f} mm"
    )
    return limiting_pressure, description


def _pipe_model_total_length_m(pipe: PipeModel) -> float:
    if isinstance(pipe, PipeSection):
        return pipe.length_m
    return pipe.total_length_m


def _pipe_section_pressure_at_100_smys_bar(section: PipeSection, smys_mpa: float) -> float:
    return 20.0 * smys_mpa * section.wall_thickness_mm / section.outside_diameter_mm


__all__ = [
    "CLASS_1_2_MIN_FACTOR",
    "CLASS_3_4_MIN_FACTOR",
    "END_PUMP_LOCATION",
    "GRAVITY_M_PER_S2",
    "LOCATION_CLASS_RULES",
    "LocationClassRule",
    "MAX_TEST_SECTION_LENGTH_M",
    "MAX_TEST_SECTION_VOLUME_M3",
    "PRESSURE_CONVERSION_PASCAL_TO_BAR",
    "PressureWindow",
    "START_PUMP_LOCATION",
    "SectionPressureProfileInputs",
    "SectionPressureProfileResult",
    "WATER_DENSITY_AT_15C_KG_PER_M3",
    "evaluate_section_pressure_profile",
    "get_location_class_options",
    "get_location_class_rule",
    "get_pump_location_options",
]
