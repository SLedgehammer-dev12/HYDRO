"""In-process bounded worker pool, cooperative cancellation, and crash recovery for OCR jobs."""

from __future__ import annotations

import math
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from ..core.timeutil import utcnow
from ..models import OcrAnalysis


class OcrQueueManager:
    """Thread-pool queue manager with cooperative cancellation and ETA estimation."""

    def __init__(self, max_concurrency: int = 1) -> None:
        self._lock = threading.Lock()
        self._max_concurrency = max(1, min(int(max_concurrency), 4))
        self._executor: ThreadPoolExecutor | None = None
        self._executor_workers = 0
        self._cancel_events: dict[str, threading.Event] = {}
        self._futures: dict[str, Future[None]] = {}
        self._avg_duration_s: float = 12.0

    @property
    def max_concurrency(self) -> int:
        with self._lock:
            return self._max_concurrency

    def configure(self, max_concurrency: int) -> None:
        target = max(1, min(int(max_concurrency), 4))
        with self._lock:
            self._max_concurrency = target
            if (
                self._executor is not None
                and self._executor_workers != target
                and not self._futures
            ):
                old = self._executor
                self._executor = None
                self._executor_workers = 0
                old.shutdown(wait=False, cancel_futures=True)

    def _ensure_executor_locked(self) -> ThreadPoolExecutor:
        if self._executor is None or self._executor_workers != self._max_concurrency:
            if self._executor is not None:
                self._executor.shutdown(wait=False, cancel_futures=False)
            self._executor = ThreadPoolExecutor(
                max_workers=self._max_concurrency,
                thread_name_prefix="hydro-ocr",
            )
            self._executor_workers = self._max_concurrency
        return self._executor

    def register_sync(self, analysis_id: str) -> threading.Event:
        """Register a cancellation event for a synchronous OCR execution."""
        with self._lock:
            event = self._cancel_events.get(analysis_id)
            if event is None:
                event = threading.Event()
                self._cancel_events[analysis_id] = event
            return event

    def unregister(self, analysis_id: str) -> None:
        with self._lock:
            self._cancel_events.pop(analysis_id, None)
            self._futures.pop(analysis_id, None)

    def submit(
        self,
        analysis_id: str,
        worker_fn: Callable[[threading.Event], None],
    ) -> threading.Event:
        """Schedule an OCR worker in the bounded pool and return its cancellation event."""
        with self._lock:
            event = self._cancel_events.get(analysis_id)
            if event is None:
                event = threading.Event()
                self._cancel_events[analysis_id] = event
            executor = self._ensure_executor_locked()

            def _run() -> None:
                try:
                    worker_fn(event)
                finally:
                    self.unregister(analysis_id)

            future = executor.submit(_run)
            self._futures[analysis_id] = future
            return event

    def cancel(self, analysis_id: str) -> bool:
        """Request cooperative cancellation and drop queued future if not yet started."""
        with self._lock:
            event = self._cancel_events.get(analysis_id)
            future = self._futures.get(analysis_id)
            found = event is not None or future is not None
            if event is not None:
                event.set()
            if future is not None:
                future.cancel()
            return found

    def record_duration(self, seconds: float) -> None:
        if not math.isfinite(seconds) or seconds < 0:
            return
        clamped = max(1.0, min(float(seconds), 120.0))
        with self._lock:
            self._avg_duration_s = (0.7 * self._avg_duration_s) + (0.3 * clamped)

    def estimate_wait_seconds(
        self,
        *,
        queued: int,
        running: int,
        size_bytes: int = 0,
    ) -> int:
        """Estimate remaining queue/run wait time in whole seconds (clamped 1..600)."""
        with self._lock:
            avg = self._avg_duration_s
            workers = max(1, self._max_concurrency)
        depth = max(0, int(queued)) + max(0, int(running)) + 1
        size_factor = max(0.0, float(size_bytes)) / float(2 * 1024 * 1024)
        estimate = ((depth / workers) * avg) + size_factor
        return max(1, min(int(round(estimate)), 600))

    def shutdown(self, *, wait: bool = True) -> None:
        with self._lock:
            for event in self._cancel_events.values():
                event.set()
            for future in self._futures.values():
                future.cancel()
            executor = self._executor
            self._executor = None
            self._executor_workers = 0
            self._cancel_events.clear()
            self._futures.clear()
        if executor is not None:
            executor.shutdown(wait=wait, cancel_futures=True)

    def recover_interrupted_jobs(self, session_factory: sessionmaker[OrmSession]) -> int:
        """Mark stale queued/running OCR rows left behind by a prior server shutdown/crash."""
        with session_factory() as db:
            stale = (
                db.execute(select(OcrAnalysis).where(OcrAnalysis.status.in_(("queued", "running"))))
                .scalars()
                .all()
            )
            if not stale:
                return 0
            now = utcnow()
            for row in stale:
                row.status = "failed"
                row.error_code = "worker_interrupted"
                row.error_message = (
                    "Sunucu yeniden baslatildigi icin yarida kalan OCR isi sonlandirildi."
                )
                row.finished_at = now
            db.commit()
            return len(stale)


OCR_QUEUE = OcrQueueManager()

__all__ = ["OCR_QUEUE", "OcrQueueManager"]
