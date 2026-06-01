from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from pathlib import Path
import tempfile

from hidrostatik_test.domain.time_series import (
    THERMAL_BALANCE_MIN_HOURS,
    THERMAL_BALANCE_THRESHOLD_C,
    TimeSeriesRecord,
    TimeSeriesStore,
)


class TimeSeriesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = TimeSeriesStore()
        self.now = datetime.now()

    def test_record_to_dict_and_back(self) -> None:
        record = TimeSeriesRecord(
            timestamp=self.now,
            pressure_bar=50.0,
            temperature_c=15.5,
            volume_m3=100.0,
            notes="Initial reading",
        )
        d = record.to_dict()
        self.assertEqual(d["timestamp"], self.now.isoformat())
        self.assertEqual(d["pressure_bar"], 50.0)
        self.assertEqual(d["temperature_c"], 15.5)
        self.assertEqual(d["volume_m3"], 100.0)
        self.assertEqual(d["notes"], "Initial reading")

        reconstructed = TimeSeriesRecord.from_dict(d)
        self.assertEqual(reconstructed.timestamp, self.now)
        self.assertEqual(reconstructed.pressure_bar, 50.0)
        self.assertEqual(reconstructed.temperature_c, 15.5)
        self.assertEqual(reconstructed.volume_m3, 100.0)
        self.assertEqual(reconstructed.notes, "Initial reading")

    def test_store_operations(self) -> None:
        self.assertEqual(len(self.store.get_records()), 0)
        
        self.store.add_record(50.0, 15.0, timestamp=self.now)
        self.store.add_record(51.0, 15.2, timestamp=self.now + timedelta(hours=1))

        records = self.store.get_records()
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].pressure_bar, 50.0)
        self.assertEqual(records[1].pressure_bar, 51.0)
        
        duration = self.store.get_duration_hours()
        self.assertAlmostEqual(duration, 1.0, places=4)

        avg_temp = self.store.get_average_temperature()
        self.assertAlmostEqual(avg_temp, 15.1, places=4)

    def test_thermal_balance_logic(self) -> None:
        # Not enough records or duration
        is_balanced, diff = self.store.check_thermal_balance()
        self.assertFalse(is_balanced)
        self.assertEqual(diff, float("inf"))

        # Add records spanning 24 hours
        start_time = self.now - timedelta(hours=24)
        for i in range(25):
            t = start_time + timedelta(hours=i)
            # stable temperature around 15.0 C
            self.store.add_record(50.0, 15.0, timestamp=t)

        is_balanced, diff = self.store.check_thermal_balance()
        self.assertTrue(is_balanced)
        self.assertLessEqual(diff, THERMAL_BALANCE_THRESHOLD_C)

    def test_json_and_csv_serialization(self) -> None:
        self.store.add_record(50.0, 15.0, timestamp=self.now)
        self.store.add_record(51.0, 15.2, timestamp=self.now + timedelta(hours=1))

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            json_file = tmp_path / "test.json"
            csv_file = tmp_path / "test.csv"

            # Test JSON
            self.store.to_json(json_file)
            loaded_json_store = TimeSeriesStore.from_json(json_file)
            self.assertEqual(len(loaded_json_store.get_records()), 2)
            self.assertEqual(loaded_json_store.get_records()[1].temperature_c, 15.2)

            # Test CSV
            self.store.to_csv(csv_file)
            loaded_csv_store = TimeSeriesStore.from_csv(csv_file)
            self.assertEqual(len(loaded_csv_store.get_records()), 2)
            self.assertEqual(loaded_csv_store.get_records()[0].pressure_bar, 50.0)


if __name__ == "__main__":
    unittest.main()
