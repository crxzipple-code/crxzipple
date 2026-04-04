from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
import threading
from typing import TYPE_CHECKING, Any

from crxzipple.core.logger import get_logger
from crxzipple.modules.memory.application.models import MemoryUseContext
from crxzipple.modules.memory.infrastructure.storage import ensure_storage_root, is_memory_relative_path

if TYPE_CHECKING:
    from crxzipple.modules.memory.application.services import FileBackedMemoryService

try:  # pragma: no cover - exercised through monkeypatch in tests when missing.
    from watchfiles import watch as _watchfiles_watch
except ModuleNotFoundError:  # pragma: no cover - local test env may not install optional dep.
    _watchfiles_watch = None


logger = get_logger(__name__)


@dataclass(slots=True)
class _WatchHandle:
    root: Path
    stop_event: threading.Event
    thread: threading.Thread | None
    contexts: dict[str, MemoryUseContext] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MemoryWatchMetrics:
    watched_roots: int
    watched_contexts: int
    filesystem_events: int
    filesystem_sync_runs: int
    filesystem_sync_failures: int
    interval_ticks: int
    interval_sync_runs: int
    interval_sync_failures: int


class MemoryWatchRegistry:
    def __init__(
        self,
        *,
        memory_service: FileBackedMemoryService,
        debounce_ms: int = 1_500,
        interval_seconds: float = 300.0,
        enabled: bool = True,
    ) -> None:
        self._memory_service = memory_service
        self._debounce_ms = max(int(debounce_ms), 0)
        self._interval_seconds = max(float(interval_seconds), 0.0)
        self._enabled = enabled
        self._lock = threading.RLock()
        self._handles: dict[str, _WatchHandle] = {}
        self._closed = False
        self._interval_stop_event = threading.Event()
        self._interval_thread: threading.Thread | None = None
        self._filesystem_events = 0
        self._filesystem_sync_runs = 0
        self._filesystem_sync_failures = 0
        self._interval_ticks = 0
        self._interval_sync_runs = 0
        self._interval_sync_failures = 0
        if self._enabled and self._interval_seconds > 0:
            self._interval_thread = threading.Thread(
                target=self._interval_loop,
                name="memory-watch:interval",
                daemon=True,
            )
            self._interval_thread.start()
        logger.debug(
            "memory watch registry initialized",
            extra={
                "watch_available": _watchfiles_watch is not None,
                "interval_seconds": self._interval_seconds,
                "enabled": self._enabled,
            },
        )

    @property
    def available(self) -> bool:
        return self._enabled and (
            _watchfiles_watch is not None or self._interval_seconds > 0
        )

    def ensure_watching(self, context: MemoryUseContext) -> bool:
        if not self.available:
            return False
        root = ensure_storage_root(context.storage_root)
        root_key = str(root)
        context_key = f"{context.space_id}::{context.storage_root}"
        with self._lock:
            if self._closed:
                return False
            handle = self._handles.get(root_key)
            if handle is None:
                stop_event = threading.Event()
                thread: threading.Thread | None = None
                if _watchfiles_watch is not None:
                    thread = threading.Thread(
                        target=self._watch_loop,
                        args=(root, stop_event),
                        name=f"memory-watch:{root.name}",
                        daemon=True,
                    )
                handle = _WatchHandle(root=root, stop_event=stop_event, thread=thread)
                self._handles[root_key] = handle
                if thread is not None:
                    thread.start()
                logger.debug(
                    "memory watcher root registered",
                    extra={
                        "storage_root": root_key,
                        "watch_backend": "watchfiles" if thread is not None else "interval-only",
                    },
                )
            handle.contexts[context_key] = context
            watched_roots = len(self._handles)
            watched_contexts = sum(len(item.contexts) for item in self._handles.values())
        logger.debug(
            "memory watcher context registered",
            extra={
                "space_id": context.space_id,
                "storage_root": root_key,
                "watched_roots": watched_roots,
                "watched_contexts": watched_contexts,
            },
        )
        return True

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            handles = tuple(self._handles.values())
            self._handles.clear()
        for handle in handles:
            handle.stop_event.set()
        for handle in handles:
            if handle.thread is not None:
                handle.thread.join(timeout=2)
        self._interval_stop_event.set()
        if self._interval_thread is not None:
            self._interval_thread.join(timeout=2)
        metrics = self.snapshot_metrics()
        logger.debug(
            "memory watch registry closed",
            extra={
                "watched_roots": metrics.watched_roots,
                "watched_contexts": metrics.watched_contexts,
                "filesystem_events": metrics.filesystem_events,
                "filesystem_sync_runs": metrics.filesystem_sync_runs,
                "filesystem_sync_failures": metrics.filesystem_sync_failures,
                "interval_ticks": metrics.interval_ticks,
                "interval_sync_runs": metrics.interval_sync_runs,
                "interval_sync_failures": metrics.interval_sync_failures,
            },
        )

    def snapshot_metrics(self) -> MemoryWatchMetrics:
        with self._lock:
            return MemoryWatchMetrics(
                watched_roots=len(self._handles),
                watched_contexts=sum(len(handle.contexts) for handle in self._handles.values()),
                filesystem_events=self._filesystem_events,
                filesystem_sync_runs=self._filesystem_sync_runs,
                filesystem_sync_failures=self._filesystem_sync_failures,
                interval_ticks=self._interval_ticks,
                interval_sync_runs=self._interval_sync_runs,
                interval_sync_failures=self._interval_sync_failures,
            )

    def _watch_loop(self, root: Path, stop_event: threading.Event) -> None:
        if _watchfiles_watch is None:
            return
        try:
            for changes in _watchfiles_watch(
                str(root),
                stop_event=stop_event,
                debounce=self._debounce_ms,
                recursive=True,
            ):
                if stop_event.is_set():
                    break
                changed_paths = self._memory_changed_paths(root, changes)
                if not changed_paths:
                    continue
                contexts = self._snapshot_contexts(root)
                with self._lock:
                    self._filesystem_events += 1
                logger.debug(
                    "memory watcher detected file changes",
                    extra={
                        "storage_root": str(root),
                        "changed_paths": changed_paths,
                        "contexts": len(contexts),
                    },
                )
                for context in contexts:
                    self._memory_service.index_manager.mark_dirty(
                        context=context,
                        changed_paths=changed_paths,
                    )
                for context in contexts:
                    try:
                        self._memory_service.warm_context(context=context)
                        with self._lock:
                            self._filesystem_sync_runs += 1
                    except Exception:
                        with self._lock:
                            self._filesystem_sync_failures += 1
                        logger.exception(
                            "memory watcher warm failed",
                            extra={
                                "storage_root": str(root),
                                "space_id": context.space_id,
                                "changed_paths": changed_paths,
                            },
                        )
                        continue
        except Exception:
            logger.exception(
                "memory watcher loop failed",
                extra={"storage_root": str(root)},
            )
            return

    def _interval_loop(self) -> None:
        while not self._interval_stop_event.wait(self._interval_seconds):
            if self._closed:
                return
            with self._lock:
                self._interval_ticks += 1
            for context in self._snapshot_all_contexts():
                try:
                    self._memory_service.warm_context(context=context)
                    with self._lock:
                        self._interval_sync_runs += 1
                except Exception:
                    with self._lock:
                        self._interval_sync_failures += 1
                    logger.exception(
                        "memory watcher interval warm failed",
                        extra={
                            "space_id": context.space_id,
                            "storage_root": context.storage_root,
                        },
                    )
                    continue

    def _snapshot_contexts(self, root: Path) -> tuple[MemoryUseContext, ...]:
        with self._lock:
            handle = self._handles.get(str(root))
            if handle is None:
                return ()
            return tuple(handle.contexts.values())

    def _snapshot_all_contexts(self) -> tuple[MemoryUseContext, ...]:
        with self._lock:
            contexts: dict[str, MemoryUseContext] = {}
            for handle in self._handles.values():
                contexts.update(handle.contexts)
            return tuple(contexts.values())

    @staticmethod
    def _memory_changed_paths(
        root: Path,
        changes: Iterable[Sequence[Any]],
    ) -> tuple[str, ...]:
        changed_paths: list[str] = []
        seen: set[str] = set()
        for change in changes:
            for changed_path in MemoryWatchRegistry._extract_paths(change):
                try:
                    resolved = Path(changed_path).resolve(strict=False)
                    relative = resolved.relative_to(root).as_posix()
                except Exception:
                    continue
                if not is_memory_relative_path(relative):
                    continue
                if relative in seen:
                    continue
                seen.add(relative)
                changed_paths.append(relative)
        return tuple(changed_paths)

    @staticmethod
    def _extract_paths(change: Sequence[Any]) -> tuple[str, ...]:
        if len(change) < 2:
            return ()
        paths: list[str] = []
        for item in change[1:]:
            if isinstance(item, str) and item.strip():
                paths.append(item)
        return tuple(paths)

__all__ = ["MemoryWatchMetrics", "MemoryWatchRegistry"]
