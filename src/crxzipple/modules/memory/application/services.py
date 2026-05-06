from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from time import perf_counter

from crxzipple.modules.memory.application.contracts import (
    MemoryIndexManagerPort,
    MemoryStorePort,
)
from crxzipple.modules.memory.application.events import (
    MEMORY_WRITE_FAILED_EVENT,
    MEMORY_WRITE_SUCCEEDED_EVENT,
    MemoryEventEmitter,
    emit_memory_event,
)
from crxzipple.modules.memory.application.indexing import (
    SearchMemoryIndexService,
    SyncMemoryIndexService,
)
from crxzipple.modules.memory.application.models import (
    MemoryExcerpt,
    MemoryFileSummary,
    MemorySearchHit,
    MemoryUseContext,
    MemoryWriteResult,
)

@dataclass(slots=True)
class FileBackedMemoryService:
    store: MemoryStorePort
    index_manager: MemoryIndexManagerPort
    sync_index: SyncMemoryIndexService | None = None
    search_index: SearchMemoryIndexService | None = None
    event_emitter: MemoryEventEmitter | None = None

    def __post_init__(self) -> None:
        if self.sync_index is None:
            self.sync_index = self.index_manager.sync_service
        if self.search_index is None:
            self.search_index = self.index_manager.search_service
        self._wire_event_emitter()

    def list_files(
        self,
        *,
        context: MemoryUseContext,
        kind: str | None = None,
        limit: int | None = None,
    ) -> list[MemoryFileSummary]:
        return self.store.list_files(
            context=context,
            kind=kind,  # type: ignore[arg-type]
            limit=limit,
        )

    def warm_context(self, *, context: MemoryUseContext) -> bool:
        assert self.sync_index is not None
        return self.sync_index.warm_context(context=context)

    def search(
        self,
        *,
        context: MemoryUseContext,
        query: str,
        limit: int = 6,
    ) -> list[MemorySearchHit]:
        assert self.search_index is not None
        return self.search_index.search(
            context=context,
            query=query,
            limit=limit,
        )

    def get(
        self,
        *,
        context: MemoryUseContext,
        path: str,
        start_line: int | None = None,
        line_count: int | None = None,
    ) -> MemoryExcerpt | None:
        return self.store.get(
            context=context,
            path=path,
            start_line=start_line,
            line_count=line_count,
        )

    def append_daily(
        self,
        *,
        context: MemoryUseContext,
        content: str,
        title: str | None = None,
        now: datetime | None = None,
    ) -> MemoryWriteResult:
        return self._write(
            context=context,
            operation="append_daily",
            writer=lambda: self.store.append_daily(
                context=context,
                content=content,
                title=title,
                now=now,
            ),
        )

    def write_long_term(
        self,
        *,
        context: MemoryUseContext,
        content: str,
    ) -> MemoryWriteResult:
        return self._write(
            context=context,
            operation="write_long_term",
            writer=lambda: self.store.write_long_term(
                context=context,
                content=content,
            ),
        )

    def write_archive(
        self,
        *,
        context: MemoryUseContext,
        content: str,
        slug: str | None = None,
        now: datetime | None = None,
    ) -> MemoryWriteResult:
        return self._write(
            context=context,
            operation="write_archive",
            writer=lambda: self.store.write_archive(
                context=context,
                content=content,
                slug=slug,
                now=now,
            ),
        )

    def _wire_event_emitter(self) -> None:
        if self.sync_index is not None:
            self.sync_index.event_emitter = self.event_emitter
        if self.search_index is not None:
            self.search_index.event_emitter = self.event_emitter

    def _write(
        self,
        *,
        context: MemoryUseContext,
        operation: str,
        writer: Callable[[], MemoryWriteResult],
    ) -> MemoryWriteResult:
        started_at = perf_counter()
        try:
            result = writer()
            assert self.sync_index is not None
            self.sync_index.mark_dirty(context=context, changed_paths=(result.path,))
        except Exception as exc:
            emit_memory_event(
                self.event_emitter,
                MEMORY_WRITE_FAILED_EVENT,
                context=context,
                status="failed",
                level="error",
                payload={
                    "operation": operation,
                    "duration_ms": _duration_ms(started_at),
                    "error_message": str(exc),
                },
            )
            raise
        emit_memory_event(
            self.event_emitter,
            MEMORY_WRITE_SUCCEEDED_EVENT,
            context=context,
            status="succeeded",
            payload={
                "operation": operation,
                "path": result.path,
                "kind": result.kind,
                "line_start": result.line_start,
                "line_end": result.line_end,
                "duration_ms": _duration_ms(started_at),
            },
        )
        return result


def _duration_ms(started_at: float) -> int:
    return max(0, round((perf_counter() - started_at) * 1000))
