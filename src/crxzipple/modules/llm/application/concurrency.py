from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from threading import BoundedSemaphore, Lock
import time
from weakref import WeakKeyDictionary

from crxzipple.modules.llm.domain.entities import LlmProfile
from crxzipple.shared.runtime_metrics import (
    RuntimeMetricsRegistry,
    get_runtime_metrics_registry,
)


@dataclass(frozen=True, slots=True)
class _LimiterTarget:
    concurrency_key: str
    max_concurrency: int
    labels: dict[str, object]


@dataclass(slots=True)
class _SyncLimiterEntry:
    max_concurrency: int
    semaphore: BoundedSemaphore


@dataclass(slots=True)
class _AsyncLimiterEntry:
    max_concurrency: int
    semaphore: asyncio.Semaphore


class LlmConcurrencyLimiter:
    """Profile-scoped LLM limiter for protecting shared model backends."""

    def __init__(
        self,
        *,
        metrics: RuntimeMetricsRegistry | None = None,
    ) -> None:
        self.metrics = metrics or get_runtime_metrics_registry()
        self._lock = Lock()
        self._sync_entries: dict[str, _SyncLimiterEntry] = {}
        self._async_entries: WeakKeyDictionary[
            asyncio.AbstractEventLoop,
            dict[str, _AsyncLimiterEntry],
        ] = WeakKeyDictionary()

    @contextmanager
    def limit(self, profile: LlmProfile) -> Iterator[None]:
        target = self._target_for_profile(profile)
        if target is None:
            yield
            return

        entry = self._sync_entry(target)
        wait_started_at = time.perf_counter()
        with self.metrics.active(
            "llm.profile_limiter.waiters",
            labels=target.labels,
        ):
            entry.semaphore.acquire()
        self.metrics.record_timing(
            "llm.profile_limiter.wait_seconds",
            time.perf_counter() - wait_started_at,
            labels=target.labels,
        )
        try:
            with self.metrics.active(
                "llm.profile_limiter.active",
                labels=target.labels,
            ):
                yield
        finally:
            entry.semaphore.release()

    @asynccontextmanager
    async def limit_async(self, profile: LlmProfile) -> AsyncIterator[None]:
        target = self._target_for_profile(profile)
        if target is None:
            yield
            return

        entry = self._async_entry(target)
        wait_started_at = time.perf_counter()
        with self.metrics.active(
            "llm.profile_limiter.waiters",
            labels=target.labels,
        ):
            await entry.semaphore.acquire()
        self.metrics.record_timing(
            "llm.profile_limiter.wait_seconds",
            time.perf_counter() - wait_started_at,
            labels=target.labels,
        )
        try:
            with self.metrics.active(
                "llm.profile_limiter.active",
                labels=target.labels,
            ):
                yield
        finally:
            entry.semaphore.release()

    def _sync_entry(self, target: _LimiterTarget) -> _SyncLimiterEntry:
        with self._lock:
            existing = self._sync_entries.get(target.concurrency_key)
            if existing is not None and (
                existing.max_concurrency == target.max_concurrency
            ):
                return existing
            entry = _SyncLimiterEntry(
                max_concurrency=target.max_concurrency,
                semaphore=BoundedSemaphore(target.max_concurrency),
            )
            self._sync_entries[target.concurrency_key] = entry
            return entry

    def _async_entry(self, target: _LimiterTarget) -> _AsyncLimiterEntry:
        loop = asyncio.get_running_loop()
        with self._lock:
            entries = self._async_entries.setdefault(loop, {})
            existing = entries.get(target.concurrency_key)
            if existing is not None and (
                existing.max_concurrency == target.max_concurrency
            ):
                return existing
            entry = _AsyncLimiterEntry(
                max_concurrency=target.max_concurrency,
                semaphore=asyncio.Semaphore(target.max_concurrency),
            )
            entries[target.concurrency_key] = entry
            return entry

    @staticmethod
    def _target_for_profile(profile: LlmProfile) -> _LimiterTarget | None:
        max_concurrency = profile.max_concurrency
        if max_concurrency is None:
            return None
        concurrency_key = profile.concurrency_key or f"profile:{profile.id}"
        return _LimiterTarget(
            concurrency_key=concurrency_key,
            max_concurrency=max_concurrency,
            labels={
                "llm_id": profile.id,
                "provider": profile.provider.value,
                "concurrency_key": concurrency_key,
            },
        )
