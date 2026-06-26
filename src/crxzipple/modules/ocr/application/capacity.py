from __future__ import annotations

from contextlib import contextmanager
from threading import Lock
from typing import Iterator

from crxzipple.modules.ocr.domain import (
    OcrCapacityExceededError,
    OcrCapacitySnapshot,
)


class OcrCapacityLimiter:
    def __init__(self, max_concurrent_requests: int) -> None:
        self._max_concurrent_requests = max(int(max_concurrent_requests), 1)
        self._in_flight_requests = 0
        self._lock = Lock()

    @contextmanager
    def acquire(self) -> Iterator[None]:
        with self._lock:
            if self._in_flight_requests >= self._max_concurrent_requests:
                raise OcrCapacityExceededError(
                    "OCR capacity is exhausted "
                    f"({self._in_flight_requests}/"
                    f"{self._max_concurrent_requests} requests in flight).",
                )
            self._in_flight_requests += 1
        try:
            yield
        finally:
            with self._lock:
                self._in_flight_requests = max(self._in_flight_requests - 1, 0)

    def snapshot(self) -> OcrCapacitySnapshot:
        with self._lock:
            in_flight = self._in_flight_requests
        return OcrCapacitySnapshot(
            max_concurrent_requests=self._max_concurrent_requests,
            in_flight_requests=in_flight,
        )
