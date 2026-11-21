"""Parity fixtures: API responses must match direct domain calls.

Golden values are produced by calling the immutable ``hidrostatik_test``
package inside the test; they are never hand-written. Comparison tolerance is
``rel=1e-9`` for pure arithmetic.
"""

from __future__ import annotations

import math

from conftest import air_payload, pressure_payload, profile_payload

from hidrostatik_test.domain import (
    AirContentInputs,
    PipeGeometry,
    PipeSection,
    PressureVariationInputs,
    SectionPressureProfileInputs,
    evaluate_air_content_test,
    evaluate_pig_speed,
    evaluate_pressure_variation_test,
    evaluate_pressurization,
    evaluate_section_pressure_profile,
    get_location_class_rule,
    get_pig_speed_limit,
    get_pig_speed_limit_options,
    resolve_b_value,
)
from hidrostatik_test.domain.pressurization import PressurizationInputs
from hidrostatik_test.domain.water_properties import (
    calculate_water_compressibility_a,
    calculate_water_density,
)


def _close(actual: float, expected: float, rel: float = 1e-9) -> None:
    assert math.isclose(actual, expected, rel_tol=rel, abs_tol=1e-12), (actual, expected)


def test_parity_coefficient_a(client):
    expected = calculate_water_compressibility_a(20.0, 80.0, backend="table_v1")
    actual = client.post(
        "/api/coefficients/a",
        json={"temperature_c": 20.0, "pressure_bar": 80.0, "backend": "table_v1"},
    ).json()["a_micro_per_bar"]
    _close(actual, expected)


def test_parity_coefficient_b_sources(client):
    for source in ("institutional", "gail", "auto"):
        expected = resolve_b_value(
            source,
            temp_c=20.0,
            pressure_bar=80.0,
            steel_alpha_micro_per_c=12.0,
            steel_model="volumetric",
        )
        actual = client.post(
            "/api/coefficients/b",
            json={
                "source": source,
                "temperature_c": 20.0,
                "pressure_bar": 80.0,
                "steel_alpha_micro_per_c": 12.0,
                "steel_model": "volumetric",
            },
        ).json()
        _close(actual["b_micro_per_c"], expected.b_micro_per_c)
        assert actual["source"] == expected.source.value
        assert actual["repaired_table"] == expected.repaired_table


def test_parity_air_content(client):
    payload = air_payload()
    section = PipeSection(406.4, 8.74, 1000.0)
    expected = evaluate_air_content_test(
        AirContentInputs(
            pipe=section,
            a_micro_per_bar=44.971994,
            pressure_rise_bar=1.0,
            k_factor=1.02,
            actual_added_water_m3=0.00775,
        )
    )
    actual = client.post("/api/calculations/air-content", json=payload).json()
    _close(actual["theoretical_added_water_m3"], expected.theoretical_added_water_m3)
    _close(actual["acceptance_limit_m3"], expected.acceptance_limit_m3)
    _close(actual["ratio"], expected.ratio)
    assert actual["passed"] is expected.passed
    _close(
        actual["geometry"]["internal_volume_m3"],
        section.internal_volume_m3,
    )
    _close(actual["geometry"]["internal_radius_mm"], section.internal_radius_mm)
    _close(actual["geometry"]["elasticity_term"], section.elasticity_term)


def test_parity_air_exact_limit_fails(client):
    section = PipeSection(406.4, 8.74, 1000.0)
    expected = evaluate_air_content_test(AirContentInputs(section, 44.971994, 1.0, 1.02, 0.0))
    exact = expected.acceptance_limit_m3
    actual = client.post(
        "/api/calculations/air-content",
        json=air_payload(actual_added_water_m3=exact),
    ).json()
    assert actual["passed"] is False
    assert expected.passed is True


def test_parity_pressure_variation_negative_b(client):
    b_value = resolve_b_value("auto", temp_c=3.0, pressure_bar=80.0).b_micro_per_c
    payload = pressure_payload(
        b_micro_per_c=b_value,
        delta_t_c=2.0,
        actual_pressure_change_bar=-0.05,
    )
    expected = evaluate_pressure_variation_test(
        PressureVariationInputs(
            pipe=PipeSection(406.4, 8.74, 1000.0),
            a_micro_per_bar=44.971994,
            b_micro_per_c=b_value,
            delta_t_c=2.0,
            actual_pressure_change_bar=-0.05,
        )
    )
    actual = client.post("/api/calculations/pressure-variation", json=payload).json()
    _close(
        actual["theoretical_pressure_change_bar"],
        expected.theoretical_pressure_change_bar,
    )
    _close(
        actual["allowable_upper_pressure_change_bar"],
        expected.allowable_upper_pressure_change_bar,
    )
    _close(actual["margin_bar"], expected.margin_bar)
    assert actual["passed"] is expected.passed
    assert actual["negative_b"] is True


def test_parity_pressure_profile(client):
    request = profile_payload()
    expected = evaluate_section_pressure_profile(
        SectionPressureProfileInputs(
            pipe=PipeSection(406.4, 8.74, 12000.0),
            design_pressure_bar=80.0,
            smys_mpa=450.0,
            location_class=get_location_class_rule("Class 1 - min 1.25 x dizayn basinci"),
            highest_elevation_m=320.0,
            lowest_elevation_m=180.0,
            start_elevation_m=200.0,
            end_elevation_m=310.0,
            selected_pump_location="Baslangic noktasi",
            monitored_pressure_bar=112.0,
        )
    )
    actual = client.post("/api/calculations/pressure-profile", json=request).json()
    _close(
        actual["required_minimum_pressure_at_high_point_bar"],
        expected.required_minimum_pressure_at_high_point_bar,
    )
    _close(
        actual["maximum_allowable_pressure_at_low_point_bar"],
        expected.maximum_allowable_pressure_at_low_point_bar,
    )
    _close(actual["hydraulic_span_bar"], expected.hydraulic_span_bar)
    _close(
        actual["required_pressure_with_span_bar"],
        expected.required_pressure_with_span_bar,
    )
    for key in ("start_window", "end_window", "selected_window"):
        actual_window = actual[key]
        expected_window = getattr(expected, key)
        _close(
            actual_window["minimum_required_pressure_bar"],
            expected_window.minimum_required_pressure_bar,
        )
        _close(
            actual_window["maximum_allowable_pressure_bar"],
            expected_window.maximum_allowable_pressure_bar,
        )
        _close(
            actual_window["hydraulic_head_to_high_point_bar"],
            expected_window.hydraulic_head_to_high_point_bar,
        )
        _close(
            actual_window["hydraulic_head_to_low_point_bar"],
            expected_window.hydraulic_head_to_low_point_bar,
        )
    _close(
        actual["limiting_pressure_at_100_smys_bar"],
        expected.limiting_pressure_at_100_smys_bar,
    )
    _close(actual["total_length_m"], expected.total_length_m)
    _close(actual["total_internal_volume_m3"], expected.total_internal_volume_m3)
    assert actual["feasible"] is expected.feasible


def test_parity_pressure_profile_per_segment_smys(client):
    seg1 = PipeSection(
        outside_diameter_mm=406.4,
        wall_thickness_mm=8.74,
        length_m=600.0,
        smys_mpa=450.0,
        material_grade="API 5L X65",
    )
    seg2 = PipeSection(
        outside_diameter_mm=406.4,
        wall_thickness_mm=8.74,
        length_m=400.0,
        smys_mpa=290.0,
        material_grade="API 5L X42",
    )
    domain_inputs = SectionPressureProfileInputs(
        pipe=PipeGeometry(sections=(seg1, seg2)),
        design_pressure_bar=100.0,
        smys_mpa=450.0,
        location_class=get_location_class_rule("Class 1 - min 1.25 x dizayn basinci"),
        highest_elevation_m=200.0,
        lowest_elevation_m=100.0,
        start_elevation_m=100.0,
        end_elevation_m=180.0,
        selected_pump_location="Baslangic noktasi",
        monitored_pressure_bar=135.0,
    )
    expected = evaluate_section_pressure_profile(domain_inputs)
    actual = client.post(
        "/api/calculations/pressure-profile",
        json=profile_payload(
            geometry={
                "sections": [
                    {
                        "outside_diameter_mm": 406.4,
                        "wall_thickness_mm": 8.74,
                        "length_m": 600.0,
                        "smys_mpa": 450.0,
                        "material_grade": "API 5L X65",
                    },
                    {
                        "outside_diameter_mm": 406.4,
                        "wall_thickness_mm": 8.74,
                        "length_m": 400.0,
                        "smys_mpa": 290.0,
                        "material_grade": "API 5L X42",
                    },
                ]
            },
            design_pressure_bar=100.0,
            smys_mpa=450.0,
            monitored_pressure_bar=135.0,
        ),
    ).json()
    _close(
        actual["limiting_pressure_at_100_smys_bar"],
        expected.limiting_pressure_at_100_smys_bar,
    )
    assert actual["limiting_segment_index"] == expected.limiting_segment_index == 2
    assert actual["limiting_smys_mpa"] == expected.limiting_smys_mpa == 290.0
    assert actual["limiting_pipe_description"] == expected.limiting_pipe_description
    assert actual["feasible"] is expected.feasible


def test_parity_pig_and_pressurization(client):
    limit = get_pig_speed_limit(get_pig_speed_limit_options()[0])
    expected_pig = evaluate_pig_speed(5000.0, 45.0, limit)
    actual_pig = client.post(
        "/api/calculations/pig-speed",
        json={"mode": limit.label, "distance_m": 5000.0, "travel_time_min": 45.0},
    ).json()
    _close(actual_pig["speed_m_per_s"], expected_pig.speed_m_per_s)
    _close(actual_pig["speed_km_per_h"], expected_pig.speed_km_per_h)
    assert actual_pig["passed"] is expected_pig.passed

    expected_pressure = evaluate_pressurization(PressurizationInputs(10.0, 0.5, 10.48, 80.05, 80.0))
    actual_pressure = client.post(
        "/api/calculations/pressurization",
        json={
            "initial_volume_m3": 10.0,
            "added_volume_m3": 0.5,
            "theoretical_volume_m3": 10.48,
            "pressure_bar": 80.05,
            "expected_pressure_bar": 80.0,
        },
    ).json()
    _close(
        actual_pressure["volume_deviation_percent"],
        expected_pressure.volume_deviation_percent,
    )
    _close(actual_pressure["pressure_deviation_bar"], expected_pressure.pressure_deviation_bar)
    _close(actual_pressure["pressure_tolerance_bar"], expected_pressure.pressure_tolerance_bar)
    assert actual_pressure["passed"] is expected_pressure.passed


def test_parity_water_density(client):
    expected = calculate_water_density(15.0, 1.0)
    actual = client.post(
        "/api/calculations/water-density",
        json={"temperature_c": 15.0, "pressure_bar": 1.0},
    ).json()["density_kg_per_m3"]
    _close(actual, expected)


def test_parity_decision_margin_matches_domain(client):
    section = PipeSection(406.4, 8.74, 1000.0)
    expected = evaluate_air_content_test(AirContentInputs(section, 44.971994, 1.0, 1.02, 0.00775))
    actual = client.post("/api/calculations/air-content", json=air_payload()).json()
    _close(
        actual["decision"]["margin"],
        expected.acceptance_limit_m3 - expected.actual_added_water_m3,
    )
    assert actual["decision"]["rule"] == "Vpa < 1.06 x Vp"
