"""Lightweight thread-safe in-process sliding-window rate limiter."""

from __future__ import annotations

import hashlib
import threading
import time
from collections import deque

from fastapi import Request

from .config import Settings
from .errors import AppError


class RateLimiter:
    """Bounded per-key sliding-window request limiter."""

    def __init__(self, *, max_keys: int = 4096) -> None:
        self._lock = threading.Lock()
        self._max_keys = max(64, max_keys)
        self._buckets: dict[tuple[str, str], deque[float]] = {}

    def check(self, bucket: str, client_key: str, *, limit: int, window_s: float = 60.0) -> None:
        if limit <= 0 or window_s <= 0:
            return
        now = time.monotonic()
        cutoff = now - window_s
        key = (bucket, client_key or "local")
        with self._lock:
            if key not in self._buckets and len(self._buckets) >= self._max_keys:
                self._prune_unlocked(cutoff)
                if len(self._buckets) >= self._max_keys:
                    oldest = next(iter(self._buckets))
                    self._buckets.pop(oldest, None)
            timestamps = self._buckets.setdefault(key, deque())
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
            if len(timestamps) >= limit:
                retry_after = max(1, int((timestamps[0] + window_s) - now + 0.999))
                raise AppError(
                    "rate_limited",
                    "Cok fazla istek gonderildi; lutfen kisa bir sure sonra tekrar deneyin.",
                    status_code=429,
                    details={"bucket": bucket, "retry_after_s": retry_after},
                )
            timestamps.append(now)

    def _prune_unlocked(self, older_than: float) -> None:
        stale = [k for k, dq in self._buckets.items() if not dq or dq[-1] <= older_than]
        for k in stale:
            self._buckets.pop(k, None)

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


RATE_LIMITER = RateLimiter()


def enforce_rate_limit(
    request: Request,
    settings: Settings,
    *,
    bucket: str,
    limit: int = 30,
    window_s: float = 60.0,
) -> None:
    if not settings.rate_limit_enabled:
        return
    client_host = (request.client.host if request.client else "").strip() or "unknown"
    raw_ws = (request.headers.get("X-Session-ID") or "").strip()
    if raw_ws:
        ws_tag = hashlib.sha256(raw_ws[:256].encode("utf-8", errors="ignore")).hexdigest()[:12]
        client_key = f"{client_host}:{ws_tag}"
    else:
        client_key = client_host
    RATE_LIMITER.check(bucket, client_key, limit=limit, window_s=window_s)


__all__ = ["RATE_LIMITER", "RateLimiter", "enforce_rate_limit"]
