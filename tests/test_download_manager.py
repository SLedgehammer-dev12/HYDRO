from __future__ import annotations

import hashlib
import http.server
import tempfile
import threading
import time
import unittest
from pathlib import Path

from hidrostatik_test.services.download_manager import (
    DownloadManager,
    DownloadStatus,
    DownloadTask,
)

PAYLOAD = bytes(range(256)) * 4096  # 1 MiB, sikistirilamaz/deterministik
PAYLOAD_SHA256 = hashlib.sha256(PAYLOAD).hexdigest()


class _RangeRequestHandler(http.server.BaseHTTPRequestHandler):
    """Yerel test sunucusu; Range destekleyip desteklememesi ayarlanabilir."""

    payload = PAYLOAD
    chunk_size = 32768
    delay_seconds = 0.04
    honor_range = True

    def log_message(self, *_args) -> None:  # test ciktisini kirletme
        return

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        start = 0
        range_header = self.headers.get("Range")
        if self.honor_range and range_header and range_header.startswith("bytes="):
            start = int(range_header[len("bytes=") :].split("-", 1)[0])
        body = self.payload[start:]
        self.send_response(206 if start else 200)
        if start:
            self.send_header(
                "Content-Range",
                f"bytes {start}-{len(self.payload) - 1}/{len(self.payload)}",
            )
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        for offset in range(0, len(body), self.chunk_size):
            try:
                self.wfile.write(body[offset : offset + self.chunk_size])
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return
            time.sleep(self.delay_seconds)


class DownloadManagerTestBase(unittest.TestCase):
    honor_range = True

    @classmethod
    def setUpClass(cls) -> None:
        handler = type(
            "TestRangeHandler",
            (_RangeRequestHandler,),
            {"honor_range": cls.honor_range},
        )
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.server_thread.join(timeout=5)

    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp_dir.cleanup)
        self.destination = Path(self._temp_dir.name) / "payload.bin"
        self.manager = DownloadManager()

    def _task(self) -> DownloadTask:
        return DownloadTask(
            url=f"{self.base_url}/payload.bin",
            destination=self.destination,
            expected_sha256=PAYLOAD_SHA256,
            total_bytes=len(PAYLOAD),
        )

    def _wait_for(self, predicate, timeout: float = 10.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.01)
        return False

    def _wait_for_stable_size(self, timeout: float = 5.0) -> int:
        deadline = time.monotonic() + timeout
        previous = -1
        while time.monotonic() < deadline:
            current = self.destination.stat().st_size if self.destination.exists() else 0
            if current == previous:
                return current
            previous = current
            time.sleep(0.15)
        return previous


class PausableDownloadTests(DownloadManagerTestBase):
    honor_range = True

    def test_pause_resume_keeps_single_worker_and_valid_checksum(self) -> None:
        first_chunk = threading.Event()
        completed = threading.Event()
        thread_names: set[str] = set()
        errors: list[str] = []

        def on_progress(
            _destination: Path,
            downloaded: int,
            _total: int,
            _speed: float,
            _eta: float,
        ) -> None:
            thread_names.add(threading.current_thread().name)
            if downloaded > 0:
                first_chunk.set()

        def on_complete(_destination: Path) -> None:
            thread_names.add(threading.current_thread().name)
            completed.set()

        def on_error(_destination: Path, message: str) -> None:
            errors.append(message)

        thread = self.manager.start(
            self._task(),
            on_progress=on_progress,
            on_complete=on_complete,
            on_error=on_error,
        )

        # Ayni hedef icin ikinci bir start cagrisi yeni worker acmamali.
        duplicate = self.manager.start(self._task())
        self.assertIs(duplicate, thread)
        self.assertEqual(self.manager.active_worker_count(self.destination), 1)

        self.assertTrue(first_chunk.wait(timeout=10), "Ilk parca alinamadi.")
        self.assertTrue(self.manager.pause(self.destination))
        self.assertEqual(self.manager.get_status(self.destination), DownloadStatus.PAUSED)

        paused_size = self._wait_for_stable_size()
        self.assertGreater(paused_size, 0)
        self.assertLess(paused_size, len(PAYLOAD))
        self.assertEqual(self.manager.active_worker_count(self.destination), 1)

        self.assertTrue(self.manager.resume(self.destination))
        self.assertIn(
            self.manager.get_status(self.destination),
            {DownloadStatus.PENDING, DownloadStatus.DOWNLOADING},
        )

        self.assertTrue(completed.wait(timeout=20), f"Indirme tamamlanmadi: {errors}")
        thread.join(timeout=10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])

        self.assertEqual(self.destination.read_bytes(), PAYLOAD)
        self.assertEqual(hashlib.sha256(self.destination.read_bytes()).hexdigest(), PAYLOAD_SHA256)
        self.assertEqual(self.manager.get_status(self.destination), DownloadStatus.COMPLETED)
        self.assertEqual(self.manager.active_worker_count(self.destination), 0)
        self.assertEqual(
            thread_names, {thread.name}, "Indirme birden fazla worker tarafindan yazildi."
        )

    def test_cancel_deletes_partial_file_when_requested(self) -> None:
        started = threading.Event()

        def on_progress(_destination: Path, downloaded: int, *_args: object) -> None:
            if downloaded > 0:
                started.set()

        thread = self.manager.start(self._task(), on_progress=on_progress)
        self.assertTrue(started.wait(timeout=10), "Indirme baslamadi.")
        self.assertTrue(self.manager.cancel(self.destination, delete_partial=True))
        thread.join(timeout=10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(self.manager.get_status(self.destination), DownloadStatus.CANCELLED)
        self.assertFalse(self.destination.exists())

    def test_cancel_keeps_partial_file_by_default(self) -> None:
        started = threading.Event()

        def on_progress(_destination: Path, downloaded: int, *_args: object) -> None:
            if downloaded > 0:
                started.set()

        thread = self.manager.start(self._task(), on_progress=on_progress)
        self.assertTrue(started.wait(timeout=10), "Indirme baslamadi.")
        self.assertTrue(self.manager.cancel(self.destination))
        thread.join(timeout=10)
        self.assertFalse(thread.is_alive())
        self.assertTrue(self.destination.exists())
        self.assertLess(self.destination.stat().st_size, len(PAYLOAD))

    def test_cancel_does_not_delete_completed_download(self) -> None:
        completed = threading.Event()
        thread = self.manager.start(self._task(), on_complete=lambda _destination: completed.set())
        self.assertTrue(completed.wait(timeout=20), "Indirme tamamlanmadi.")
        thread.join(timeout=10)

        self.assertFalse(self.manager.cancel(self.destination, delete_partial=True))
        self.assertTrue(self.destination.exists())
        self.assertEqual(self.manager.get_status(self.destination), DownloadStatus.COMPLETED)

    def test_get_task_returns_detached_copy(self) -> None:
        task = self._task()
        self.manager.enqueue(task)
        snapshot = self.manager.get_task(self.destination)
        self.assertIsNotNone(snapshot)
        self.assertIsNot(task, snapshot)
        snapshot.status = DownloadStatus.COMPLETED
        snapshot.downloaded_bytes = 123
        self.assertEqual(self.manager.get_status(self.destination), DownloadStatus.PENDING)
        self.assertEqual(self.manager.get_task(self.destination).downloaded_bytes, 0)

    def test_remove_stops_tracking_and_cancels_worker(self) -> None:
        started = threading.Event()

        def on_progress(_destination: Path, downloaded: int, *_args: object) -> None:
            if downloaded > 0:
                started.set()

        thread = self.manager.start(self._task(), on_progress=on_progress)
        self.assertTrue(started.wait(timeout=10), "Indirme baslamadi.")
        self.manager.remove(self.destination)
        thread.join(timeout=10)
        self.assertFalse(thread.is_alive())
        self.assertIsNone(self.manager.get_status(self.destination))
        self.assertIsNone(self.manager.get_task(self.destination))


class RangeIgnoredDownloadTests(DownloadManagerTestBase):
    honor_range = False

    def test_partial_file_is_restarted_when_server_ignores_range(self) -> None:
        # Onceki oturumdan kalan yarim dosyayi taklit et.
        self.destination.parent.mkdir(parents=True, exist_ok=True)
        self.destination.write_bytes(PAYLOAD[:100_000])

        completed = threading.Event()
        errors: list[str] = []

        thread = self.manager.start(
            self._task(),
            on_complete=lambda _destination: completed.set(),
            on_error=lambda _destination, message: errors.append(message),
        )
        self.assertTrue(completed.wait(timeout=20), f"Indirme tamamlanmadi: {errors}")
        thread.join(timeout=10)

        self.assertEqual(errors, [])
        self.assertEqual(self.destination.read_bytes(), PAYLOAD)
        self.assertEqual(self.manager.get_status(self.destination), DownloadStatus.COMPLETED)


if __name__ == "__main__":
    unittest.main()
