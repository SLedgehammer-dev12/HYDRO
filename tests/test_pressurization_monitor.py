from __future__ import annotations

import unittest

from hidrostatik_test.domain import ValidationError
from hidrostatik_test.domain.post_test_operations import (
    DESTINATION_OTHER_SECTION,
    DESTINATION_WATERCOURSE,
    DepressurizationInputs,
    DischargeInputs,
    evaluate_depressurization,
    evaluate_discharge,
)
from hidrostatik_test.domain.pressurization_monitor import (
    HoldReading,
    PressureHoldInputs,
    PressurizationRampInputs,
    PressurizationReading,
    evaluate_pressure_hold,
    evaluate_pressurization_ramp,
)


def _reading(t: float, p: float, v: float) -> PressurizationReading:
    return PressurizationReading(elapsed_min=t, pressure_bar=p, cumulative_added_volume_m3=v)


class PressurizationRampTests(unittest.TestCase):
    P100 = 100.0

    def _inputs(self, readings: list[PressurizationReading]) -> PressurizationRampInputs:
        return PressurizationRampInputs(
            readings=tuple(readings),
            test_pressure_100_smys_bar=self.P100,
            total_filled_volume_m3=1000.0,
        )

    def test_ramp_rate_within_limit_and_completed_passes(self) -> None:
        result = evaluate_pressurization_ramp(
            self._inputs(
                [
                    _reading(0, 80.0, 0.0),
                    _reading(10, 90.0, 0.5),  # 1.0 bar/min (sinirda)
                    _reading(20, 95.0, 0.8),
                    _reading(30, 95.2, 0.9),
                    _reading(40, 100.0, 1.5),
                ]
            )
        )
        self.assertTrue(result.reached_95_smys)
        self.assertTrue(result.reached_100_smys)
        self.assertEqual(result.ramp_rate_violations, ())
        self.assertAlmostEqual(result.max_ramp_rate_bar_per_min, 1.0)
        self.assertIs(result.passed, True)

    def test_ramp_rate_over_one_bar_per_minute_fails(self) -> None:
        result = evaluate_pressurization_ramp(
            self._inputs(
                [
                    _reading(0, 80.0, 0.0),
                    _reading(5, 90.0, 0.5),  # 2 bar/min
                    _reading(15, 95.0, 0.8),
                ]
            )
        )
        self.assertEqual(len(result.ramp_rate_violations), 1)
        self.assertAlmostEqual(result.ramp_rate_violations[0].rate_bar_per_min, 2.0)
        self.assertIs(result.passed, False)

    def test_rate_below_80_percent_is_not_limited(self) -> None:
        result = evaluate_pressurization_ramp(
            self._inputs([_reading(0, 20.0, 0.0), _reading(1, 70.0, 5.0)])
        )
        self.assertEqual(result.ramp_rate_violations, ())

    def test_excess_water_after_95_percent_requires_stop(self) -> None:
        # Limit = %0.2 * 1000 m3 = 2.0 m3; 95% sonrasi 2.5 m3 basildi.
        result = evaluate_pressurization_ramp(
            self._inputs(
                [
                    _reading(0, 95.0, 10.0),
                    _reading(30, 97.0, 11.0),
                    _reading(60, 98.0, 12.5),
                ]
            )
        )
        self.assertAlmostEqual(result.excess_volume_limit_m3, 2.0)
        self.assertAlmostEqual(result.pumped_since_95_smys_m3, 2.5)
        self.assertTrue(result.volume_limit_exceeded)
        self.assertTrue(result.stop_required)
        self.assertIs(result.passed, False)

    def test_exact_limit_is_accepted_and_incomplete_is_none(self) -> None:
        result = evaluate_pressurization_ramp(
            self._inputs([_reading(0, 95.0, 10.0), _reading(30, 98.0, 12.0)])
        )
        self.assertFalse(result.volume_limit_exceeded)
        self.assertIs(result.passed, None)

    def test_monitoring_gap_over_0_2_bar_is_reported(self) -> None:
        result = evaluate_pressurization_ramp(
            self._inputs([_reading(0, 95.0, 0.0), _reading(10, 95.2, 0.1), _reading(20, 96.0, 0.2)])
        )
        self.assertEqual(len(result.monitoring_gaps), 1)
        self.assertAlmostEqual(result.monitoring_gaps[0], 0.8)

    def test_invalid_inputs_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            self._inputs([_reading(0, 80.0, 0.0)])
        with self.assertRaises(ValidationError):
            self._inputs([_reading(5, 80.0, 0.0), _reading(5, 81.0, 0.0)])
        with self.assertRaises(ValidationError):
            self._inputs([_reading(0, 80.0, 1.0), _reading(5, 81.0, 0.5)])
        with self.assertRaises(ValidationError):
            PressurizationRampInputs(
                readings=(_reading(0, 1.0, 0.0), _reading(1, 2.0, 0.0)),
                test_pressure_100_smys_bar=0.0,
                total_filled_volume_m3=10.0,
            )
        with self.assertRaises(ValidationError):
            _reading(0, float("nan"), 0.0)


class PressureHoldTests(unittest.TestCase):
    def _hold(self, readings: list[tuple[float, float]]) -> PressureHoldInputs:
        return PressureHoldInputs(
            readings=tuple(HoldReading(t, p, 12.0) for t, p in readings),
            target_pressure_bar=100.0,
        )

    def test_two_hour_hold_with_15_minute_readings_passes(self) -> None:
        readings = [(float(t), 100.0) for t in range(0, 121, 15)]
        result = evaluate_pressure_hold(self._hold(readings))
        self.assertTrue(result.duration_ok)
        self.assertTrue(result.interval_ok)
        self.assertTrue(result.passed)
        self.assertFalse(result.repressurize_required)

    def test_short_hold_fails_duration(self) -> None:
        result = evaluate_pressure_hold(self._hold([(0.0, 100.0), (15.0, 100.0), (90.0, 100.0)]))
        self.assertFalse(result.duration_ok)
        self.assertFalse(result.passed)

    def test_reading_gap_over_15_minutes_fails_interval(self) -> None:
        result = evaluate_pressure_hold(self._hold([(0.0, 100.0), (45.0, 100.0), (120.0, 100.0)]))
        self.assertFalse(result.interval_ok)
        self.assertFalse(result.passed)

    def test_pressure_drop_requires_repressurization_but_not_failure(self) -> None:
        readings = [(float(t), 100.0 - t * 0.01) for t in range(0, 121, 15)]
        result = evaluate_pressure_hold(self._hold(readings))
        self.assertGreater(result.pressure_drop_bar, result.pressure_tolerance_bar)
        self.assertTrue(result.repressurize_required)
        self.assertTrue(result.passed)

    def test_invalid_hold_inputs(self) -> None:
        with self.assertRaises(ValidationError):
            self._hold([(0.0, 100.0)])
        with self.assertRaises(ValidationError):
            self._hold([(10.0, 100.0), (5.0, 100.0)])


class DepressurizationTests(unittest.TestCase):
    def test_valid_depressurization_passes(self) -> None:
        result = evaluate_depressurization(DepressurizationInputs(True, 2.0, True, True))
        self.assertTrue(result.passed)
        self.assertEqual(result.violations, ())
        self.assertEqual(result.missing, ())

    def test_valve_larger_than_two_inch_is_violation(self) -> None:
        result = evaluate_depressurization(DepressurizationInputs(True, 3.0, True, True))
        self.assertFalse(result.passed)
        self.assertEqual(len(result.violations), 1)

    def test_failed_test_blocks_depressurization(self) -> None:
        result = evaluate_depressurization(DepressurizationInputs(False, 1.0, True, True))
        self.assertFalse(result.passed)
        self.assertTrue(any("basarili" in v for v in result.violations))

    def test_missing_information_is_not_passed(self) -> None:
        result = evaluate_depressurization(DepressurizationInputs(None, None))
        self.assertFalse(result.passed)
        self.assertEqual(result.violations, ())
        self.assertGreaterEqual(len(result.missing), 4)

    def test_invalid_valve_diameter_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            DepressurizationInputs(True, 0.0)
        with self.assertRaises(ValidationError):
            DepressurizationInputs(True, float("inf"))


def _discharge(**overrides: object) -> DischargeInputs:
    base: dict[str, object] = {
        "destination": DESTINATION_OTHER_SECTION,
        "used_discharge_pig": True,
        "hydraulic_load_measures_taken": True,
        "report_date": "2026-11-19",
        "report_time": "14:30",
        "pig_name": "PIG-07",
        "discharge_location": "KP 12+300",
        "duration_min": 95.0,
    }
    base.update(overrides)
    return DischargeInputs(**base)  # type: ignore[arg-type]


class DischargeTests(unittest.TestCase):
    def test_transfer_to_other_section_needs_no_approval(self) -> None:
        result = evaluate_discharge(_discharge())
        self.assertTrue(result.passed, result)

    def test_missing_pig_is_violation_when_false(self) -> None:
        result = evaluate_discharge(_discharge(used_discharge_pig=False))
        self.assertFalse(result.passed)
        self.assertTrue(any("(17)" in v for v in result.violations))

    def test_watercourse_requires_approval_and_erosion_control(self) -> None:
        result = evaluate_discharge(_discharge(destination=DESTINATION_WATERCOURSE))
        self.assertFalse(result.passed)
        self.assertEqual(result.violations, ())
        self.assertEqual(len(result.missing), 2)

        ok = evaluate_discharge(
            _discharge(
                destination=DESTINATION_WATERCOURSE,
                approvals_obtained=True,
                erosion_prevented=True,
            )
        )
        self.assertTrue(ok.passed, ok)

        bad = evaluate_discharge(
            _discharge(
                destination=DESTINATION_WATERCOURSE,
                approvals_obtained=False,
                erosion_prevented=False,
            )
        )
        self.assertEqual(len(bad.violations), 2)

    def test_treatment_and_analysis_only_when_requested(self) -> None:
        self.assertTrue(evaluate_discharge(_discharge(treatment_done=False)).passed)
        result = evaluate_discharge(_discharge(treatment_requested=True, treatment_done=False))
        self.assertFalse(result.passed)
        self.assertTrue(any("17.4" in v for v in result.violations))
        pending = evaluate_discharge(_discharge(sample_analysis_requested=True))
        self.assertFalse(pending.passed)
        self.assertEqual(pending.violations, ())

    def test_report_fields_17_6_are_required(self) -> None:
        result = evaluate_discharge(_discharge(report_time="", pig_name="  ", duration_min=None))
        self.assertFalse(result.passed)
        joined = " ".join(result.missing)
        for label in ("saat", "kullanilan pig", "islem suresi"):
            self.assertIn(label, joined)

    def test_invalid_inputs_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            _discharge(destination="ocean")
        with self.assertRaises(ValidationError):
            _discharge(duration_min=0.0)
        with self.assertRaises(ValidationError):
            _discharge(duration_min=float("nan"))


if __name__ == "__main__":
    unittest.main()
