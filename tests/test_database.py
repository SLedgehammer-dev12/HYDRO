import os
import sqlite3
import stat
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path

from hidrostatik_test.services.database import (
    BUSY_TIMEOUT_MS,
    SCHEMA_VERSION,
    DatabaseManager,
    _utc_now_iso,
)


class TestDatabaseManager(unittest.TestCase):
    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp_dir.cleanup)
        self.db_path = Path(self._temp_dir.name) / "test.db"
        self.db = DatabaseManager(db_path=self.db_path)

    def tearDown(self):
        self.db.close()

    def test_database_creates_tables(self):
        cursor = self.db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]
        expected = {
            "coefficients",
            "geometry_records",
            "schema_version",
            "sessions",
            "test_entries",
            "time_series_records",
        }
        for table in expected:
            self.assertIn(table, tables)

    def test_schema_version_recorded(self):
        cursor = self.db.conn.execute("SELECT MAX(version) FROM schema_version")
        self.assertEqual(cursor.fetchone()[0], SCHEMA_VERSION)
        self.assertEqual(self.db.schema_version, SCHEMA_VERSION)
        self.assertEqual(self.db.conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)

    def test_connection_is_shared_between_threads(self):
        self.db.conn.execute("SELECT 1")
        errors: list[Exception] = []

        def worker() -> None:
            try:
                self.db.list_sessions()
            except Exception as exc:  # pragma: no cover - hata durumunda raporlanir
                errors.append(exc)

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()
        self.assertEqual(errors, [])

    def test_busy_timeout_and_synchronous_pragmas(self):
        self.assertEqual(self.db.conn.execute("PRAGMA busy_timeout").fetchone()[0], BUSY_TIMEOUT_MS)
        synchronous = self.db.conn.execute("PRAGMA synchronous").fetchone()[0]
        self.assertEqual(synchronous, 1)  # NORMAL

    @unittest.skipIf(os.name != "posix", "POSIX dosya izinleri gerekir")
    def test_posix_permissions_are_restricted(self):
        nested_path = Path(self._temp_dir.name) / "private" / "hydro.db"
        nested_db = DatabaseManager(db_path=nested_path)
        try:
            self.assertEqual(stat.S_IMODE(nested_path.parent.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(nested_path.stat().st_mode), 0o600)
        finally:
            nested_db.close()

    def test_save_and_get_session(self):
        self.db.save_session("test-1", "Test Oturumu", "Notlar")
        session = self.db.get_session("test-1")
        self.assertEqual(session["name"], "Test Oturumu")
        self.assertEqual(session["notes"], "Notlar")

    def test_timestamps_are_utc_iso8601(self):
        self.db.save_session("utc", "UTC")
        entry_id = self.db.add_test_entry("utc", "air", {}, {"passed": True})
        series_id = self.db.add_time_series_record("utc", 10.0, 15.0)
        self.assertGreater(entry_id, 0)
        self.assertGreater(series_id, 0)

        session = self.db.get_session("utc")
        for value in (session["created_at"], session["updated_at"]):
            parsed = datetime.fromisoformat(value)
            self.assertIsNotNone(parsed.tzinfo)
            self.assertEqual(parsed.utcoffset(), timezone.utc.utcoffset(None))

        entry = self.db.get_session_entries("utc")[0]
        parsed_entry = datetime.fromisoformat(entry["evaluated_at"])
        self.assertEqual(parsed_entry.utcoffset(), timezone.utc.utcoffset(None))

        record = self.db.get_time_series("utc")[0]
        parsed_record = datetime.fromisoformat(record["timestamp"])
        self.assertEqual(parsed_record.utcoffset(), timezone.utc.utcoffset(None))

    def test_utc_now_helper_has_explicit_offset(self):
        value = _utc_now_iso()
        self.assertTrue(value.endswith("+00:00"))

    def test_list_sessions_returns_sorted(self):
        self.db.save_session("s1", "Eski")
        self.db.save_session("s2", "Yeni")
        sessions = self.db.list_sessions()
        self.assertEqual(len(sessions), 2)

    def test_delete_session_cascades(self):
        self.db.save_session("sil", "Silinecek")
        self.db.add_test_entry(
            "sil",
            "air",
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
            "s1",
            "pressure",
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

    def test_concurrent_writes_are_serialized(self):
        self.db.save_session("parallel", "Paralel")
        n_threads = 4
        per_thread = 10
        errors: list[Exception] = []

        def worker(thread_index: int) -> None:
            try:
                for index in range(per_thread):
                    self.db.add_test_entry(
                        "parallel",
                        "field",
                        {"thread": thread_index, "index": index},
                        {"passed": True},
                    )
            except Exception as exc:  # pragma: no cover - hata durumunda raporlanir
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(index,)) for index in range(n_threads)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(self.db.get_session_entries("parallel")), n_threads * per_thread)
        self.assertEqual(self.db.get_statistics()["total_tests"], n_threads * per_thread)

    def test_legacy_database_is_migrated_to_user_version(self):
        legacy_path = Path(self._temp_dir.name) / "legacy.db"
        connection = sqlite3.connect(str(legacy_path))
        try:
            connection.executescript(
                """
                CREATE TABLE schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );
                CREATE TABLE sessions (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    notes TEXT DEFAULT '',
                    is_active INTEGER DEFAULT 1,
                    inputs_json TEXT DEFAULT '{}',
                    wizard_state_json TEXT DEFAULT '{}'
                );
                INSERT INTO schema_version (version, applied_at)
                    VALUES (1, '2025-01-01T00:00:00');
                INSERT INTO sessions (id, name, created_at, updated_at)
                    VALUES ('legacy', 'Eski Oturum', '2025-01-01T00:00:00', '2025-01-01T00:00:00');
                """
            )
            connection.commit()
        finally:
            connection.close()

        migrated = DatabaseManager(db_path=legacy_path)
        try:
            self.assertEqual(
                migrated.conn.execute("PRAGMA user_version").fetchone()[0],
                SCHEMA_VERSION,
            )
            self.assertEqual(migrated.get_session("legacy")["name"], "Eski Oturum")
            cursor = migrated.conn.execute("SELECT MAX(version) FROM schema_version")
            self.assertEqual(cursor.fetchone()[0], SCHEMA_VERSION)
        finally:
            migrated.close()

    def test_newer_database_schema_is_rejected(self):
        newer_path = Path(self._temp_dir.name) / "newer.db"
        connection = sqlite3.connect(str(newer_path))
        try:
            connection.execute(f"PRAGMA user_version={SCHEMA_VERSION + 5}")
            connection.commit()
        finally:
            connection.close()

        with self.assertRaisesRegex(RuntimeError, "Uygulamayi guncelleyin"):
            DatabaseManager(db_path=newer_path)


if __name__ == "__main__":
    unittest.main()
