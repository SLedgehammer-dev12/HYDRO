from __future__ import annotations

import math
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from hidrostatik_test.services.download_manager import DownloadManager, DownloadStatus
from hidrostatik_test.ui.download_dialog import (
    DownloadDialog,
    _format_eta,
    _format_size,
    _format_speed,
    _isfinite,
)


class FormatHelperTests(unittest.TestCase):
    def test_format_size_units(self) -> None:
        self.assertEqual(_format_size(0), "0 B")
        self.assertEqual(_format_size(512), "512 B")
        self.assertEqual(_format_size(1536), "1.5 KB")
        self.assertEqual(_format_size(1024 * 1024), "1.0 MB")
        self.assertEqual(_format_size(1024**3), "1.00 GB")

    def test_format_size_negative_is_clamped(self) -> None:
        self.assertEqual(_format_size(-10), "0 B")

    def test_format_size_non_finite_returns_placeholder(self) -> None:
        self.assertEqual(_format_size(float("nan")), "--")
        self.assertEqual(_format_size(float("inf")), "--")
        self.assertEqual(_format_size(float("-inf")), "--")

    def test_format_speed(self) -> None:
        self.assertEqual(_format_speed(1536), "1.5 KB/s")
        self.assertEqual(_format_speed(0), "0 B/s")
        self.assertEqual(_format_speed(float("nan")), "--")
        self.assertEqual(_format_speed(-1), "0 B/s")

    def test_format_eta(self) -> None:
        self.assertEqual(_format_eta(0), "--")
        self.assertEqual(_format_eta(-5), "--")
        self.assertEqual(_format_eta(float("nan")), "--")
        self.assertEqual(_format_eta(float("inf")), "--")
        self.assertEqual(_format_eta(30), "30 sn")
        self.assertEqual(_format_eta(90), "1 dk 30 sn")
        self.assertEqual(_format_eta(3660), "1 sa 1 dk")

    def test_isfinite_rejects_non_numeric_and_non_finite(self) -> None:
        self.assertTrue(_isfinite(1))
        self.assertTrue(_isfinite(1.5))
        self.assertFalse(_isfinite(math.inf))
        self.assertFalse(_isfinite(math.nan))
        self.assertFalse(_isfinite("12"))
        self.assertFalse(_isfinite(None))


class FakeDownloadManager:
    """DownloadManager sozlesmesini taklit eden test yoneticisi."""

    def __init__(self) -> None:
        self.enqueued: list[object] = []
        self.started: list[object] = []
        self.cancelled: list[Path] = []
        self.removed: list[Path] = []
        self.paused: list[Path] = []
        self.resumed: list[Path] = []
        self.status = DownloadStatus.PENDING
        self._callbacks: dict[str, object] = {}

    def enqueue(self, task: object) -> object:
        self.enqueued.append(task)
        return task

    def start(
        self,
        task: object,
        on_progress: object = None,
        on_complete: object = None,
        on_error: object = None,
    ) -> None:
        self.started.append(task)
        self._callbacks = {
            "on_progress": on_progress,
            "on_complete": on_complete,
            "on_error": on_error,
        }

    def cancel(self, destination: Path) -> bool:
        self.cancelled.append(destination)
        self.status = DownloadStatus.CANCELLED
        return True

    def remove(self, destination: Path) -> None:
        self.removed.append(destination)

    def pause(self, destination: Path) -> bool:
        self.paused.append(destination)
        return True

    def resume(
        self,
        destination: Path,
        on_progress: object = None,
        on_complete: object = None,
        on_error: object = None,
    ) -> bool:
        self.resumed.append(destination)
        return True

    def get_status(self, destination: Path) -> DownloadStatus:
        return self.status

    def emit_progress(
        self, downloaded: int, total: int, speed: float = 1024.0, eta: float = 30.0
    ) -> None:
        callback = self._callbacks["on_progress"]
        assert callable(callback)
        callback(Path("dest"), downloaded, total, speed, eta)

    def emit_complete(self) -> None:
        self.status = DownloadStatus.COMPLETED
        callback = self._callbacks["on_complete"]
        assert callable(callback)
        callback(Path("dest"))

    def emit_error(self, message: str = "ag hatasi") -> None:
        self.status = DownloadStatus.FAILED
        callback = self._callbacks["on_error"]
        assert callable(callback)
        callback(Path("dest"), message)


class DownloadManagerArgumentTests(unittest.TestCase):
    def test_class_argument_raises_clear_error(self) -> None:
        with self.assertRaises(TypeError) as context:
            DownloadDialog(
                parent=None,  # type: ignore[arg-type]
                download_manager=DownloadManager,  # type: ignore[arg-type]
                file_url="https://example.com/a.zip",
                file_name="a.zip",
                dest_path=Path("a.zip"),
            )
        self.assertIn("instance", str(context.exception))

    def test_object_without_manager_api_raises_clear_error(self) -> None:
        with self.assertRaises(TypeError) as context:
            DownloadDialog(
                parent=None,  # type: ignore[arg-type]
                download_manager=object(),  # type: ignore[arg-type]
                file_url="https://example.com/a.zip",
                file_name="a.zip",
                dest_path=Path("a.zip"),
            )
        self.assertIn("Eksik metotlar", str(context.exception))


class DownloadDialogTkTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk kullanilamiyor, diyalog testi atlandi: {exc}")
        self.root.withdraw()
        self.dest = Path(tempfile.mkdtemp()) / "guncelleme.zip"
        self.manager = FakeDownloadManager()
        self.dialog = DownloadDialog(
            parent=self.root,
            download_manager=self.manager,  # type: ignore[arg-type]
            file_url="https://example.com/guncelleme.zip",
            file_name="guncelleme.zip",
            dest_path=self.dest,
            total_bytes=2048,
        )

    def tearDown(self) -> None:
        self.dialog._close_dialog()
        self.root.destroy()

    def test_dialog_enqueues_and_starts_task(self) -> None:
        self.assertEqual(len(self.manager.enqueued), 1)
        self.assertEqual(len(self.manager.started), 1)
        task = self.manager.enqueued[0]
        self.assertEqual(getattr(task, "destination"), self.dest)
        self.assertIsNone(self.dialog._result)

    def test_worker_progress_only_enqueues_until_poll(self) -> None:
        self.manager.emit_progress(1024, 2048, speed=2048.0, eta=10.0)

        self.assertEqual(self.dialog._events.qsize(), 1)
        self.assertEqual(self.dialog._percent_label.cget("text"), "%0")

        self.dialog._drain_events()

        self.assertEqual(self.dialog._percent_label.cget("text"), "%50.0")
        self.assertEqual(self.dialog._speed_label.cget("text"), "Hiz: 2.0 KB/s")
        self.assertEqual(self.dialog._size_label.cget("text"), "1.0 KB / 2.0 KB")

    def test_complete_sets_result_and_close_does_not_ask(self) -> None:
        self.manager.emit_complete()
        self.dialog._drain_events()

        self.assertEqual(self.dialog._result, "completed")
        self.assertEqual(self.dialog._cancel_btn.cget("text"), "Kapat")

        with patch("hidrostatik_test.ui.download_dialog.messagebox.askyesno") as ask:
            self.dialog._on_close()

        ask.assert_not_called()
        self.assertTrue(self.dialog._destroyed)

    def test_error_result_and_close_does_not_ask(self) -> None:
        with patch(
            "hidrostatik_test.ui.download_dialog.messagebox.askretrycancel",
            return_value=False,
        ):
            self.manager.emit_error()
            self.dialog._drain_events()

        self.assertEqual(self.dialog._result, "error")

        with patch("hidrostatik_test.ui.download_dialog.messagebox.askyesno") as ask:
            self.dialog._on_close()

        ask.assert_not_called()
        self.assertTrue(self.dialog._destroyed)

    def test_cancel_while_running_asks_once(self) -> None:
        with patch(
            "hidrostatik_test.ui.download_dialog.messagebox.askyesno",
            return_value=True,
        ) as ask:
            self.dialog._on_cancel()

        self.assertEqual(ask.call_count, 1)
        self.assertEqual(self.manager.cancelled, [self.dest])
        self.assertEqual(self.dialog._result, "cancelled")
        self.assertEqual(self.dialog._cancel_btn.cget("text"), "Kapat")

        # Iptal sonrasi kapatma tekrar onay sormamali.
        with patch("hidrostatik_test.ui.download_dialog.messagebox.askyesno") as ask_again:
            self.dialog._on_close()

        ask_again.assert_not_called()
        self.assertTrue(self.dialog._destroyed)

    def test_cancel_declined_keeps_download_running(self) -> None:
        with patch(
            "hidrostatik_test.ui.download_dialog.messagebox.askyesno",
            return_value=False,
        ):
            self.dialog._on_cancel()

        self.assertEqual(self.manager.cancelled, [])
        self.assertIsNone(self.dialog._result)
        self.assertFalse(self.dialog._finished)

    def test_close_while_running_asks_and_cancels(self) -> None:
        with patch(
            "hidrostatik_test.ui.download_dialog.messagebox.askyesno",
            return_value=True,
        ) as ask:
            self.dialog._on_close()

        self.assertEqual(ask.call_count, 1)
        self.assertEqual(self.manager.cancelled, [self.dest])
        self.assertEqual(self.dialog._result, "cancelled")
        self.assertTrue(self.dialog._destroyed)

    def test_pause_toggle_calls_manager(self) -> None:
        self.dialog._toggle_pause()
        self.assertEqual(self.manager.paused, [self.dest])

        self.dialog._toggle_pause()
        self.assertEqual(self.manager.resumed, [self.dest])


if __name__ == "__main__":
    unittest.main()
