import json
import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
