"""Property-based invariant tests for critical hydrotest domain physics and bounds."""

from __future__ import annotations

import math

import pytest
from app.services.coefficients import coefficient_a, coefficient_b
from hypothesis import given, settings
from hypothesis import strategies as st

from hidrostatik_test.domain import (
    AirContentInputs,
    PipeGeometry,
    PipeSection,
    PressureVariationInputs,
    evaluate_air_content_test,
    evaluate_pressure_variation_test,
)


@given(
    backend=st.sampled_from(["coolprop", "table_v1", "institutional", "gail"]),
    temperature_c=st.floats(min_value=2.0, max_value=25.0, allow_nan=False, allow_infinity=False),
    pressure_bar=st.floats(min_value=30.0, max_value=120.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=40, deadline=None)
def test_coefficient_a_positive_and_finite_across_backends(
    backend: str,
    temperature_c: float,
    pressure_bar: float,
) -> None:
    res = coefficient_a(temperature_c=temperature_c, pressure_bar=pressure_bar, backend=backend)
    a_val = float(res["a_micro_per_bar"])
    assert math.isfinite(a_val)
    assert 20.0 < a_val < 80.0


@given(
    backend=st.sampled_from(["coolprop", "table_v1"]),
    t1=st.floats(min_value=5.0, max_value=30.0, allow_nan=False, allow_infinity=False),
    delta_t=st.floats(min_value=0.5, max_value=15.0, allow_nan=False, allow_infinity=False),
    pressure_bar=st.floats(min_value=10.0, max_value=120.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=40, deadline=None)
def test_coefficient_b_monotonic_with_temperature_above_density_max(
    backend: str,
    t1: float,
    delta_t: float,
    pressure_bar: float,
) -> None:
    t2 = t1 + delta_t
    b1 = float(
        coefficient_b(
            source="auto",
            temperature_c=t1,
            pressure_bar=pressure_bar,
            steel_alpha_micro_per_c=12.0,
            steel_model="volumetric",
            backend=backend,
        )["b_micro_per_c"]
    )
    b2 = float(
        coefficient_b(
            source="auto",
            temperature_c=t2,
            pressure_bar=pressure_bar,
            steel_alpha_micro_per_c=12.0,
            steel_model="volumetric",
            backend=backend,
        )["b_micro_per_c"]
    )
    assert math.isfinite(b1) and math.isfinite(b2)
    assert b2 > b1


@given(
    outside_diameter_mm=st.floats(
        min_value=150.0, max_value=1400.0, allow_nan=False, allow_infinity=False
    ),
    wall_ratio=st.floats(min_value=0.01, max_value=0.06, allow_nan=False, allow_infinity=False),
    length_m=st.floats(min_value=100.0, max_value=20000.0, allow_nan=False, allow_infinity=False),
    a_micro_per_bar=st.floats(
        min_value=35.0, max_value=60.0, allow_nan=False, allow_infinity=False
    ),
    k_factor=st.floats(min_value=0.95, max_value=1.10, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=40, deadline=None)
def test_air_content_six_percent_boundary_invariant(
    outside_diameter_mm: float,
    wall_ratio: float,
    length_m: float,
    a_micro_per_bar: float,
    k_factor: float,
) -> None:
    pressure_rise_bar = 1.0
    wall_thickness_mm = round(outside_diameter_mm * wall_ratio, 3)
    pipe = PipeGeometry(
        (
            PipeSection(
                outside_diameter_mm=outside_diameter_mm,
                wall_thickness_mm=wall_thickness_mm,
                length_m=length_m,
            ),
        )
    )
    ref = evaluate_air_content_test(
        AirContentInputs(
            pipe=pipe,
            a_micro_per_bar=a_micro_per_bar,
            pressure_rise_bar=pressure_rise_bar,
            k_factor=k_factor,
            actual_added_water_m3=0.0,
        )
    )
    vp = ref.theoretical_added_water_m3
    passing = evaluate_air_content_test(
        AirContentInputs(
            pipe=pipe,
            a_micro_per_bar=a_micro_per_bar,
            pressure_rise_bar=pressure_rise_bar,
            k_factor=k_factor,
            actual_added_water_m3=vp * 1.059,
        )
    )
    exact_limit = evaluate_air_content_test(
        AirContentInputs(
            pipe=pipe,
            a_micro_per_bar=a_micro_per_bar,
            pressure_rise_bar=pressure_rise_bar,
            k_factor=k_factor,
            actual_added_water_m3=vp * 1.06,
        )
    )
    over_limit = evaluate_air_content_test(
        AirContentInputs(
            pipe=pipe,
            a_micro_per_bar=a_micro_per_bar,
            pressure_rise_bar=pressure_rise_bar,
            k_factor=k_factor,
            actual_added_water_m3=vp * 1.061,
        )
    )
    assert passing.passed is True
    assert exact_limit.passed is False
    assert over_limit.passed is False


@given(
    outside_diameter_mm=st.floats(
        min_value=150.0, max_value=1400.0, allow_nan=False, allow_infinity=False
    ),
    wall_ratio=st.floats(min_value=0.01, max_value=0.06, allow_nan=False, allow_infinity=False),
    length_m=st.floats(min_value=100.0, max_value=20000.0, allow_nan=False, allow_infinity=False),
    a_micro_per_bar=st.floats(
        min_value=35.0, max_value=60.0, allow_nan=False, allow_infinity=False
    ),
    b_micro_per_c=st.floats(
        min_value=-50.0, max_value=350.0, allow_nan=False, allow_infinity=False
    ),
    delta_t_c=st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=40, deadline=None)
def test_pressure_variation_point_three_bar_boundary_invariant(
    outside_diameter_mm: float,
    wall_ratio: float,
    length_m: float,
    a_micro_per_bar: float,
    b_micro_per_c: float,
    delta_t_c: float,
) -> None:
    wall_thickness_mm = round(outside_diameter_mm * wall_ratio, 3)
    pipe = PipeGeometry(
        (
            PipeSection(
                outside_diameter_mm=outside_diameter_mm,
                wall_thickness_mm=wall_thickness_mm,
                length_m=length_m,
            ),
        )
    )
    ref = evaluate_pressure_variation_test(
        PressureVariationInputs(
            pipe=pipe,
            a_micro_per_bar=a_micro_per_bar,
            b_micro_per_c=b_micro_per_c,
            delta_t_c=delta_t_c,
            actual_pressure_change_bar=0.0,
        )
    )
    pt = ref.theoretical_pressure_change_bar
    passing = evaluate_pressure_variation_test(
        PressureVariationInputs(
            pipe=pipe,
            a_micro_per_bar=a_micro_per_bar,
            b_micro_per_c=b_micro_per_c,
            delta_t_c=delta_t_c,
            actual_pressure_change_bar=pt + 0.3 - 1e-4,
        )
    )
    failing = evaluate_pressure_variation_test(
        PressureVariationInputs(
            pipe=pipe,
            a_micro_per_bar=a_micro_per_bar,
            b_micro_per_c=b_micro_per_c,
            delta_t_c=delta_t_c,
            actual_pressure_change_bar=pt + 0.3 + 1e-4,
        )
    )
    assert passing.passed is True
    assert failing.passed is False
    assert passing.allowable_upper_pressure_change_bar == pytest.approx(pt + 0.3)
