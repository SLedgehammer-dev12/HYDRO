import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from hidrostatik_test.domain.session_manager import SessionManager, TestSession


class TestTestSession(unittest.TestCase):
    def test_session_auto_generates_id(self):
        s = TestSession()
        self.assertTrue(len(s.id) > 0)

    def test_session_to_dict_roundtrip(self):
        s1 = TestSession(name="Test", notes="Aciklama")
        s1.inputs = {"od": "219.1", "wt": "8.18"}
        d = s1.to_dict()
        s2 = TestSession.from_dict(d)
        self.assertEqual(s1.name, s2.name)
        self.assertEqual(s1.id, s2.id)
        self.assertEqual(s1.inputs, s2.inputs)


class TestSessionManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        # We explicitly set use_db=False to verify index/JSON functionality isolatedly
        self.manager = SessionManager(sessions_dir=self.temp_dir, use_db=False)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_session(self):
        s = self.manager.create_session("Test 1")
        self.assertEqual(s.name, "Test 1")
        self.assertEqual(self.manager.get_active_session().id, s.id)

    def test_switch_session_preserves_data(self):
        s1 = self.manager.create_session("Oturum 1")
        s1.inputs = {"key": "value1"}
        s2 = self.manager.create_session("Oturum 2")
        s2.inputs = {"key": "value2"}

        restored = self.manager.switch_session(s1.id)
        self.assertEqual(restored.inputs["key"], "value1")

    def test_list_sessions_returns_all(self):
        self.manager.create_session("A")
        self.manager.create_session("B")
        self.assertEqual(len(self.manager.list_sessions()), 2)

    def test_delete_session_removes_from_disk(self):
        s = self.manager.create_session("Silinecek")
        path = self.temp_dir / f"{s.id}.json"
        self.assertTrue(path.exists())
        self.manager.delete_session(s.id)
        self.assertFalse(path.exists())

    def test_restore_last_session(self):
        self.manager.create_session("Ilk")
        import time
        time.sleep(0.01)
        self.manager.create_session("Son")
        restored = self.manager.restore_last_session()
        self.assertEqual(restored.name, "Son")


class SessionManagerDBTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.db_path = self.temp_dir / "test.db"
        # Mock DatabaseManager entirely
        self.mock_db = MagicMock()
        self.mock_db.list_sessions.return_value = []
        self.db_patcher = patch(
            "hidrostatik_test.services.database.DatabaseManager",
            return_value=self.mock_db,
        )
        self.db_patcher.start()

    def tearDown(self):
        self.db_patcher.stop()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_db_init_creates_manager_and_loads_sessions(self):
        manager = SessionManager(sessions_dir=self.temp_dir, use_db=True, db_path=self.db_path)
        self.assertTrue(manager.use_db)
        self.assertIsNotNone(manager._db)
        self.mock_db.list_sessions.assert_called_once()

    def test_db_create_session_saves_to_db(self):
        manager = SessionManager(sessions_dir=self.temp_dir, use_db=True, db_path=self.db_path)
        session = manager.create_session("DB Test")
        self.mock_db.save_session.assert_called()
        call_kwargs = self.mock_db.save_session.call_args[1]
        self.assertEqual(call_kwargs["session_id"], session.id)
        self.assertEqual(call_kwargs["name"], "DB Test")

    def test_db_switch_session_loads_from_db(self):
        self.mock_db.list_sessions.return_value = [
            {"id": "sess1", "name": "DB Oturum", "created_at": "2026-01-01", "updated_at": "2026-01-02"}
        ]
        self.mock_db.get_session.return_value = {
            "id": "sess1",
            "name": "DB Oturum",
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-02T00:00:00",
            "notes": "test",
            "inputs_json": '{"key": "value"}',
            "wizard_state_json": None,
        }
        self.mock_db.get_time_series.return_value = []
        self.mock_db.get_session_entries.return_value = []

        manager = SessionManager(sessions_dir=self.temp_dir, use_db=True, db_path=self.db_path)
        session = manager.switch_session("sess1")

        self.assertEqual(session.id, "sess1")
        self.assertEqual(session.name, "DB Oturum")
        self.assertEqual(session.inputs, {"key": "value"})
        self.mock_db.get_session.assert_called_with("sess1")

    def test_db_switch_session_handles_broken_json_gracefully(self):
        self.mock_db.list_sessions.return_value = [
            {"id": "broken", "name": "Bozuk", "created_at": "2026-01-01", "updated_at": "2026-01-02"}
        ]
        self.mock_db.get_session.return_value = {
            "id": "broken",
            "name": "Bozuk",
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-02T00:00:00",
            "notes": "",
            "inputs_json": "{invalid json}",
            "wizard_state_json": None,
        }
        self.mock_db.get_time_series.return_value = []
        self.mock_db.get_session_entries.return_value = []

        manager = SessionManager(sessions_dir=self.temp_dir, use_db=True, db_path=self.db_path)
        session = manager.switch_session("broken")

        self.assertEqual(session.id, "broken")
        self.assertEqual(session.inputs, {})

    def test_db_list_sessions_uses_db(self):
        self.mock_db.list_sessions.return_value = [
            {"id": "s1", "name": "A", "created_at": "2026-01-01", "updated_at": "2026-01-02"},
            {"id": "s2", "name": "B", "created_at": "2026-01-01", "updated_at": "2026-01-03"},
        ]
        manager = SessionManager(sessions_dir=self.temp_dir, use_db=True, db_path=self.db_path)
        sessions = manager.list_sessions()
        self.assertEqual(len(sessions), 2)
        self.assertEqual(sessions[0]["id"], "s2")  # newest first

    def test_db_delete_session_calls_db_delete(self):
        self.mock_db.list_sessions.return_value = []
        manager = SessionManager(sessions_dir=self.temp_dir, use_db=True, db_path=self.db_path)
        manager._sessions["to_delete"] = TestSession(id="to_delete")
        manager._active_session_id = "to_delete"
        manager.delete_session("to_delete")
        self.mock_db.delete_session.assert_called_with("to_delete")

    def test_db_update_inputs_saves_to_db(self):
        self.mock_db.list_sessions.return_value = []
        manager = SessionManager(sessions_dir=self.temp_dir, use_db=True, db_path=self.db_path)
        manager.create_session("Input Test")
        manager.update_inputs({"od": "219.1"})
        self.mock_db.save_session.assert_called()

    def test_restore_last_session_creates_default_when_empty(self):
        self.mock_db.list_sessions.return_value = []
        manager = SessionManager(sessions_dir=self.temp_dir, use_db=True, db_path=self.db_path)
        session = manager.restore_last_session()
        self.assertIsNotNone(session)
        self.assertEqual(session.name, "Varsayilan Oturum")

    def test_restore_last_session_returns_most_recent(self):
        self.mock_db.list_sessions.return_value = [
            {"id": "old", "name": "Eski", "created_at": "2026-01-01", "updated_at": "2026-01-01T00:00:00"},
            {"id": "new", "name": "Yeni", "created_at": "2026-01-02", "updated_at": "2026-01-02T00:00:00"},
        ]
        self.mock_db.get_session.return_value = {
            "id": "new",
            "name": "Yeni",
            "created_at": "2026-01-02T00:00:00",
            "updated_at": "2026-01-02T00:00:00",
            "notes": "",
            "inputs_json": "{}",
            "wizard_state_json": None,
        }
        self.mock_db.get_time_series.return_value = []
        self.mock_db.get_session_entries.return_value = []

        manager = SessionManager(sessions_dir=self.temp_dir, use_db=True, db_path=self.db_path)
        session = manager.restore_last_session()
        self.assertEqual(session.id, "new")
        self.assertEqual(session.name, "Yeni")


if __name__ == "__main__":
    unittest.main()
