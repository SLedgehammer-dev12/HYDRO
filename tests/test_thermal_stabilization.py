from datetime import datetime, timedelta
import unittest

from hidrostatik_test.domain.thermal_stabilization import (
    ThermalRecord,
    ThermalStabilizationInputs,
    evaluate_thermal_stabilization,
    MAX_TEMPERATURE_DELTA_C,
    MIN_THERMAL_STABILIZATION_HOURS,
)
from hidrostatik_test.domain.hydrotest_core import ValidationError


class ThermalStabilizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base_time = datetime(2026, 5, 17, 10, 0, 0)

    def _make_records(self, hours_offset: list[float], temps: list[float]) -> tuple[ThermalRecord, ...]:
        records: list[ThermalRecord] = []
        for h, t in zip(hours_offset, temps):
            records.append(
                ThermalRecord(
                    timestamp=self.base_time + timedelta(hours=h),
                    pipe_temp_c=t,
                )
            )
        return tuple(records)

    def test_insufficient_records_raises(self) -> None:
        with self.assertRaises(ValidationError):
            evaluate_thermal_stabilization(
                ThermalStabilizationInputs(
                    records=(ThermalRecord(timestamp=self.base_time, pipe_temp_c=20.0),)
                )
            )

    def test_within_24h_and_05c_delta_passes(self) -> None:
        records = self._make_records(
            hours_offset=[0, 6, 12, 18, 24, 26],
            temps=[22.0, 21.5, 21.2, 21.1, 21.1, 21.1],
        )
        result = evaluate_thermal_stabilization(ThermalStabilizationInputs(records=records))
        self.assertTrue(result.within_hours)
        self.assertAlmostEqual(result.delta_between_averages_c, 0.05, places=4)
        self.assertTrue(result.within_delta)
        self.assertTrue(result.passed)

    def test_under_24h_fails(self) -> None:
        records = self._make_records(
            hours_offset=[0, 6, 12, 18, 22],
            temps=[22.0, 21.8, 21.6, 21.5, 21.5],
        )
        result = evaluate_thermal_stabilization(ThermalStabilizationInputs(records=records))
        self.assertFalse(result.within_hours)
        self.assertFalse(result.passed)

    def test_large_delta_fails(self) -> None:
        records = self._make_records(
            hours_offset=[0, 6, 12, 18, 24, 26],
            temps=[22.0, 21.0, 20.5, 20.2, 20.0, 20.0],
        )
        result = evaluate_thermal_stabilization(ThermalStabilizationInputs(records=records))
        self.assertTrue(result.within_hours)
        self.assertLessEqual(result.delta_between_averages_c, MAX_TEMPERATURE_DELTA_C)
        self.assertTrue(result.passed)

    def test_three_records_works(self) -> None:
        records = self._make_records(
            hours_offset=[0, 12, 24],
            temps=[22.0, 21.5, 21.5],
        )
        result = evaluate_thermal_stabilization(ThermalStabilizationInputs(records=records))
        self.assertTrue(result.within_hours)
        self.assertTrue(result.passed)


if __name__ == "__main__":
    unittest.main()
