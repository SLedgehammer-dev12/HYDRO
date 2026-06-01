import json
import tempfile
import unittest
from pathlib import Path

from hidrostatik_test.services.database import DatabaseManager, SCHEMA_VERSION


class TestDatabaseManager(unittest.TestCase):
    def setUp(self):
        self.db_path = Path(tempfile.mktemp(suffix=".db"))
        self.db = DatabaseManager(db_path=self.db_path)

    def tearDown(self):
        self.db.close()
        self.db_path.unlink(missing_ok=True)

    def test_database_creates_tables(self):
        cursor = self.db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]
        expected = {
            "coefficients", "geometry_records", "schema_version",
            "sessions", "test_entries", "time_series_records",
        }
        for table in expected:
            self.assertIn(table, tables)

    def test_schema_version_recorded(self):
        cursor = self.db.conn.execute("SELECT MAX(version) FROM schema_version")
        self.assertEqual(cursor.fetchone()[0], SCHEMA_VERSION)

    def test_save_and_get_session(self):
        self.db.save_session("test-1", "Test Oturumu", "Notlar")
        session = self.db.get_session("test-1")
        self.assertEqual(session["name"], "Test Oturumu")
        self.assertEqual(session["notes"], "Notlar")

    def test_list_sessions_returns_sorted(self):
        self.db.save_session("s1", "Eski")
        self.db.save_session("s2", "Yeni")
        sessions = self.db.list_sessions()
        self.assertEqual(len(sessions), 2)

    def test_delete_session_cascades(self):
        self.db.save_session("sil", "Silinecek")
        self.db.add_test_entry(
            "sil", "air",
            {"temp": 10, "press": 50},
            {"ratio": 0.95, "passed": True},
            "BASARILI",
        )
        self.db.delete_session("sil")
        session = self.db.get_session("sil")
        self.assertIsNone(session)
        entries = self.db.get_session_entries("sil")
        self.assertEqual(entries, [])

    def test_add_test_entry_roundtrip(self):
        self.db.save_session("s1", "Test")
        entry_id = self.db.add_test_entry(
            "s1", "pressure",
            {"delta_t": 5.0, "pa": 0.2},
            {"margin": 0.15, "passed": True},
            "BASARILI",
        )
        self.assertGreater(entry_id, 0)
        entries = self.db.get_session_entries("s1")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["decision_status"], "BASARILI")
        self.assertEqual(entries[0]["inputs_json"]["delta_t"], 5.0)

    def test_time_series_crud(self):
        self.db.save_session("s1", "Test")
        id1 = self.db.add_time_series_record("s1", 50.0, 15.0)
        id2 = self.db.add_time_series_record("s1", 49.8, 15.2, notes="Test")
        self.assertGreater(id2, id1)
        records = self.db.get_time_series("s1")
        self.assertEqual(len(records), 2)

    def test_statistics(self):
        self.db.save_session("s1", "S1")
        self.db.add_test_entry("s1", "air", {}, {"ratio": 1.0}, "BASARILI")
        self.db.add_test_entry("s1", "pressure", {}, {"margin": 0.1}, "BASARILI")
        self.db.add_test_entry("s1", "field", {}, {"pig_speed": 1.5}, "BASARILI")
        stats = self.db.get_statistics()
        self.assertEqual(stats["total_tests"], 3)
        self.assertEqual(stats["total_sessions"], 1)
        self.assertEqual(stats["by_status"]["BASARILI"], 3)


if __name__ == "__main__":
    unittest.main()
