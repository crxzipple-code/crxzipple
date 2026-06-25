from __future__ import annotations

import time


class OperationsObserverScanState:
    """Tracks wakeup topics and full-scan cadence for the observer pump."""

    def __init__(self, *, full_scan_interval_seconds: float) -> None:
        self._full_scan_interval_seconds = max(
            float(full_scan_interval_seconds),
            1.0,
        )
        self._full_scan_completed = False
        self._last_full_scan_at = 0.0
        self._wakeup_topics: set[str] = set()

    def mark_subscription_changed(self) -> None:
        self._full_scan_completed = False

    def mark_full_scan_completed(self) -> None:
        self._full_scan_completed = True
        self._last_full_scan_at = time.monotonic()

    def should_full_scan(self, *, from_beginning: bool) -> bool:
        if from_beginning or not self._full_scan_completed:
            return True
        return (
            time.monotonic() - self._last_full_scan_at
            >= self._full_scan_interval_seconds
        )

    def wakeup(self, topic: str) -> None:
        if topic:
            self._wakeup_topics.add(topic)

    def pop_wakeup_topics(self) -> set[str]:
        topics = set(self._wakeup_topics)
        self._wakeup_topics.clear()
        return topics
