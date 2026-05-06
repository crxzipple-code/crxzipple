from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from threading import Lock
import time
from typing import Iterator


MetricLabels = Mapping[str, object] | None


@dataclass(frozen=True, slots=True)
class RuntimeMetricKey:
    name: str
    labels: tuple[tuple[str, str], ...] = ()

    @classmethod
    def from_parts(
        cls,
        name: str,
        labels: MetricLabels = None,
    ) -> "RuntimeMetricKey":
        normalized_labels = tuple(
            sorted(
                (
                    str(key),
                    str(value),
                )
                for key, value in (labels or {}).items()
                if value is not None
            ),
        )
        return cls(name=name, labels=normalized_labels)

    def labels_payload(self) -> dict[str, str]:
        return dict(self.labels)


@dataclass(slots=True)
class RuntimeTimingAccumulator:
    count: int = 0
    total_seconds: float = 0.0
    max_seconds: float = 0.0

    def record(self, seconds: float) -> None:
        normalized_seconds = max(float(seconds), 0.0)
        self.count += 1
        self.total_seconds += normalized_seconds
        self.max_seconds = max(self.max_seconds, normalized_seconds)

    def to_payload(self) -> dict[str, object]:
        average = self.total_seconds / self.count if self.count else 0.0
        return {
            "count": self.count,
            "total_seconds": self.total_seconds,
            "max_seconds": self.max_seconds,
            "avg_seconds": average,
        }


class RuntimeMetricsRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: dict[RuntimeMetricKey, int] = {}
        self._gauges: dict[RuntimeMetricKey, float] = {}
        self._timings: dict[RuntimeMetricKey, RuntimeTimingAccumulator] = {}

    def increment_counter(
        self,
        name: str,
        amount: int = 1,
        *,
        labels: MetricLabels = None,
    ) -> None:
        key = RuntimeMetricKey.from_parts(name, labels)
        with self._lock:
            self._counters[key] = self._counters.get(key, 0) + int(amount)

    def set_gauge(
        self,
        name: str,
        value: float | int,
        *,
        labels: MetricLabels = None,
    ) -> None:
        key = RuntimeMetricKey.from_parts(name, labels)
        with self._lock:
            self._gauges[key] = float(value)

    def adjust_gauge(
        self,
        name: str,
        delta: float | int,
        *,
        labels: MetricLabels = None,
    ) -> None:
        key = RuntimeMetricKey.from_parts(name, labels)
        with self._lock:
            self._gauges[key] = self._gauges.get(key, 0.0) + float(delta)

    def record_timing(
        self,
        name: str,
        seconds: float,
        *,
        labels: MetricLabels = None,
    ) -> None:
        key = RuntimeMetricKey.from_parts(name, labels)
        with self._lock:
            accumulator = self._timings.setdefault(key, RuntimeTimingAccumulator())
            accumulator.record(seconds)

    @contextmanager
    def active(
        self,
        name: str,
        *,
        labels: MetricLabels = None,
    ) -> Iterator[None]:
        self.adjust_gauge(name, 1, labels=labels)
        try:
            yield
        finally:
            self.adjust_gauge(name, -1, labels=labels)

    @contextmanager
    def timed(
        self,
        name: str,
        *,
        labels: MetricLabels = None,
    ) -> Iterator[None]:
        started_at = time.perf_counter()
        try:
            yield
        finally:
            self.record_timing(
                name,
                time.perf_counter() - started_at,
                labels=labels,
            )

    def snapshot(
        self,
        *,
        prefixes: tuple[str, ...] = (),
    ) -> dict[str, object]:
        with self._lock:
            counters = dict(self._counters)
            gauges = dict(self._gauges)
            timings = {
                key: RuntimeTimingAccumulator(
                    count=value.count,
                    total_seconds=value.total_seconds,
                    max_seconds=value.max_seconds,
                )
                for key, value in self._timings.items()
            }

        return {
            "counters": [
                {
                    "name": key.name,
                    "labels": key.labels_payload(),
                    "value": value,
                }
                for key, value in sorted(
                    counters.items(),
                    key=lambda item: (item[0].name, item[0].labels),
                )
                if _matches_prefixes(key.name, prefixes)
            ],
            "gauges": [
                {
                    "name": key.name,
                    "labels": key.labels_payload(),
                    "value": value,
                }
                for key, value in sorted(
                    gauges.items(),
                    key=lambda item: (item[0].name, item[0].labels),
                )
                if _matches_prefixes(key.name, prefixes)
            ],
            "timings": [
                {
                    "name": key.name,
                    "labels": key.labels_payload(),
                    **value.to_payload(),
                }
                for key, value in sorted(
                    timings.items(),
                    key=lambda item: (item[0].name, item[0].labels),
                )
                if _matches_prefixes(key.name, prefixes)
            ],
        }

    def clear(self) -> None:
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._timings.clear()


_DEFAULT_RUNTIME_METRICS_REGISTRY = RuntimeMetricsRegistry()


def get_runtime_metrics_registry() -> RuntimeMetricsRegistry:
    return _DEFAULT_RUNTIME_METRICS_REGISTRY


def _matches_prefixes(name: str, prefixes: tuple[str, ...]) -> bool:
    if not prefixes:
        return True
    return any(name.startswith(prefix) for prefix in prefixes)
