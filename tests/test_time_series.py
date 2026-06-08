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


class TimeSeriesRecordEdgeTests(unittest.TestCase):
    def test_from_dict_none_volume(self) -> None:
        data = {
            "timestamp": "2026-01-01T12:00:00",
            "pressure_bar": 10.0,
            "temperature_c": 20.0,
            "volume_m3": None,
            "notes": "",
        }
        record = TimeSeriesRecord.from_dict(data)
        self.assertIsNone(record.volume_m3)

    def test_from_dict_none_volume_str(self) -> None:
        data = {
            "timestamp": "2026-01-01T12:00:00",
            "pressure_bar": 10.0,
            "temperature_c": 20.0,
            "volume_m3": "None",
            "notes": "",
        }
        record = TimeSeriesRecord.from_dict(data)
        self.assertIsNone(record.volume_m3)

    def test_from_dict_empty_volume_str(self) -> None:
        data = {
            "timestamp": "2026-01-01T12:00:00",
            "pressure_bar": 10.0,
            "temperature_c": 20.0,
            "volume_m3": "",
            "notes": "",
        }
        record = TimeSeriesRecord.from_dict(data)
        self.assertIsNone(record.volume_m3)

    def test_from_dict_zero_volume(self) -> None:
        data = {
            "timestamp": "2026-01-01T12:00:00",
            "pressure_bar": 10.0,
            "temperature_c": 20.0,
            "volume_m3": 0.0,
            "notes": "",
        }
        record = TimeSeriesRecord.from_dict(data)
        self.assertEqual(record.volume_m3, 0.0)

    def test_from_dict_invalid_volume_str(self) -> None:
        data = {
            "timestamp": "2026-01-01T12:00:00",
            "pressure_bar": 10.0,
            "temperature_c": 20.0,
            "volume_m3": "abc",
            "notes": "",
        }
        record = TimeSeriesRecord.from_dict(data)
        self.assertIsNone(record.volume_m3)

    def test_from_dict_notes_none(self) -> None:
        data = {
            "timestamp": "2026-01-01T12:00:00",
            "pressure_bar": 10.0,
            "temperature_c": 20.0,
            "volume_m3": 5.0,
            "notes": None,
        }
        record = TimeSeriesRecord.from_dict(data)
        self.assertEqual(record.notes, "")

    def test_from_dict_non_string_timestamp(self) -> None:
        data = {
            "timestamp": 12345,
            "pressure_bar": 10.0,
            "temperature_c": 20.0,
            "volume_m3": None,
            "notes": "",
        }
        record = TimeSeriesRecord.from_dict(data)
        # Falls back to datetime.now()
        self.assertIsNotNone(record.timestamp)
        self.assertTrue(hasattr(record.timestamp, "isoformat"))


class TimeSeriesStoreEdgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = TimeSeriesStore()
        self.now = datetime.now()

    def test_duration_hours_no_records(self) -> None:
        self.assertEqual(self.store.get_duration_hours(), 0.0)

    def test_duration_hours_one_record(self) -> None:
        self.store.add_record(50.0, 15.0, timestamp=self.now)
        self.assertEqual(self.store.get_duration_hours(), 0.0)

    def test_duration_hours_two_records(self) -> None:
        self.store.add_record(50.0, 15.0, timestamp=self.now)
        self.store.add_record(51.0, 15.2, timestamp=self.now + timedelta(hours=2))
        self.assertAlmostEqual(self.store.get_duration_hours(), 2.0, places=4)

    def test_check_thermal_balance_no_records(self) -> None:
        is_balanced, diff = self.store.check_thermal_balance()
        self.assertFalse(is_balanced)
        self.assertEqual(diff, float("inf"))

    def test_check_thermal_balance_one_record(self) -> None:
        self.store.add_record(50.0, 15.0, timestamp=self.now)
        is_balanced, diff = self.store.check_thermal_balance()
        self.assertFalse(is_balanced)
        self.assertEqual(diff, float("inf"))

    def test_check_thermal_balance_under_24h(self) -> None:
        start = self.now - timedelta(hours=12)
        for i in range(13):
            self.store.add_record(50.0, 15.0, timestamp=start + timedelta(hours=i))
        is_balanced, diff = self.store.check_thermal_balance()
        self.assertFalse(is_balanced)
        self.assertEqual(diff, float("inf"))

    def test_check_thermal_balance_over_24h_unstable(self) -> None:
        start = self.now - timedelta(hours=48)
        # 49 hourly records: first 46 at 15.0C, last 3 at 25.0C
        for i in range(49):
            temp = 15.0 if i < 46 else 25.0
            self.store.add_record(50.0, temp, timestamp=start + timedelta(hours=i))
        is_balanced, diff = self.store.check_thermal_balance()
        self.assertFalse(is_balanced)
        self.assertGreater(diff, THERMAL_BALANCE_THRESHOLD_C)

    def test_average_temperature_empty(self) -> None:
        self.assertIsNone(self.store.get_average_temperature())

    def test_average_temperature_with_filter(self) -> None:
        start = self.now - timedelta(hours=6)
        for i in range(7):
            self.store.add_record(50.0, 20.0 + i, timestamp=start + timedelta(hours=i))
        avg = self.store.get_average_temperature(last_n_hours=2.0)
        self.assertIsNotNone(avg)
        # Should only include the last 2 hours' worth
        self.assertGreater(avg, 20.0)

    def test_from_dict_no_records_key(self) -> None:
        store = TimeSeriesStore.from_dict({})
        self.assertEqual(len(store.get_records()), 0)

    def test_from_dict_records_not_list(self) -> None:
        store = TimeSeriesStore.from_dict({"records": "not_a_list"})
        self.assertEqual(len(store.get_records()), 0)

    def test_from_dict_non_dict_items(self) -> None:
        store = TimeSeriesStore.from_dict({"records": [1, 2, 3]})
        self.assertEqual(len(store.get_records()), 0)

    def test_to_csv_empty_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_file = Path(tmp_dir) / "empty.csv"
            self.store.to_csv(csv_file)
            self.assertFalse(csv_file.exists())

    def test_from_csv_nonexistent_path(self) -> None:
        store = TimeSeriesStore.from_csv(Path("/nonexistent/file.csv"))
        self.assertEqual(len(store.get_records()), 0)

    def test_from_json_nonexistent_path(self) -> None:
        store = TimeSeriesStore.from_json(Path("/nonexistent/file.json"))
        self.assertEqual(len(store.get_records()), 0)

    def test_clear_resets_store(self) -> None:
        self.store.add_record(50.0, 15.0, timestamp=self.now)
        self.assertEqual(len(self.store.get_records()), 1)
        self.store.clear()
        self.assertEqual(len(self.store.get_records()), 0)

    def test_to_json_contains_metadata(self) -> None:
        self.store.add_record(50.0, 15.0, timestamp=self.now)
        with tempfile.TemporaryDirectory() as tmp_dir:
            json_file = Path(tmp_dir) / "meta.json"
            self.store.to_json(json_file)
            import json as json_mod
            data = json_mod.loads(json_file.read_text(encoding="utf-8"))
            self.assertIn("metadata", data)
            self.assertEqual(data["metadata"]["record_count"], 1)
            self.assertEqual(data["metadata"]["duration_hours"], 0.0)
            self.assertIsInstance(data["metadata"]["thermal_balanced"], bool)


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
