"""Lightweight in-process observability metrics (latency percentiles, HTTP codes, slow SQL)."""

from __future__ import annotations

import math
import threading
from collections import deque
from typing import Mapping


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return round(sorted_values[0], 3)
    rank = (pct / 100.0) * (len(sorted_values) - 1)
    lo = int(math.floor(rank))
    hi = min(len(sorted_values) - 1, lo + 1)
    frac = rank - lo
    value = sorted_values[lo] + frac * (sorted_values[hi] - sorted_values[lo])
    return round(value, 3)


class MetricsRegistry:
    """Thread-safe rolling metrics tracker for HTTP requests and SQL latency."""

    def __init__(self, *, window_size: int = 512) -> None:
        self._lock = threading.Lock()
        self._requests_total = 0
        self._requests_4xx = 0
        self._requests_5xx = 0
        self._slow_queries_total = 0
        self._durations_ms: deque[float] = deque(maxlen=max(32, window_size))

    def record_request(self, status_code: int, duration_ms: float) -> None:
        with self._lock:
            self._requests_total += 1
            if 400 <= status_code < 500:
                self._requests_4xx += 1
            elif status_code >= 500:
                self._requests_5xx += 1
            self._durations_ms.append(max(0.0, float(duration_ms)))

    def record_slow_query(self) -> None:
        with self._lock:
            self._slow_queries_total += 1

    def snapshot(self) -> dict[str, int | float]:
        with self._lock:
            total = self._requests_total
            err_4xx = self._requests_4xx
            err_5xx = self._requests_5xx
            slow_q = self._slow_queries_total
            samples = sorted(self._durations_ms)
        avg = round(sum(samples) / len(samples), 3) if samples else 0.0
        return {
            "requests_total": total,
            "requests_4xx": err_4xx,
            "requests_5xx": err_5xx,
            "slow_queries_total": slow_q,
            "latency_samples": len(samples),
            "avg_ms": avg,
            "p50_ms": _percentile(samples, 50.0),
            "p95_ms": _percentile(samples, 95.0),
        }

    def render_prometheus(self, extra_gauges: Mapping[str, float] | None = None) -> str:
        snap = self.snapshot()
        lines = [
            "# TYPE hydro_http_requests_total counter",
            f"hydro_http_requests_total {int(snap['requests_total'])}",
            "# TYPE hydro_http_requests_4xx_total counter",
            f"hydro_http_requests_4xx_total {int(snap['requests_4xx'])}",
            "# TYPE hydro_http_requests_5xx_total counter",
            f"hydro_http_requests_5xx_total {int(snap['requests_5xx'])}",
            "# TYPE hydro_db_slow_queries_total counter",
            f"hydro_db_slow_queries_total {int(snap['slow_queries_total'])}",
            "# TYPE hydro_http_request_duration_p50_ms gauge",
            f"hydro_http_request_duration_p50_ms {snap['p50_ms']}",
            "# TYPE hydro_http_request_duration_p95_ms gauge",
            f"hydro_http_request_duration_p95_ms {snap['p95_ms']}",
        ]
        if extra_gauges:
            for metric_name, val in sorted(extra_gauges.items()):
                lines.append(f"# TYPE {metric_name} gauge")
                lines.append(f"{metric_name} {val}")
        return "\n".join(lines) + "\n"

    def reset(self) -> None:
        with self._lock:
            self._requests_total = 0
            self._requests_4xx = 0
            self._requests_5xx = 0
            self._slow_queries_total = 0
            self._durations_ms.clear()


METRICS = MetricsRegistry()
