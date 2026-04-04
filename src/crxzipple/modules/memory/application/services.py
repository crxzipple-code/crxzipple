from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

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
from crxzipple.modules.memory.infrastructure.indexing import FileMemoryIndexManager
from crxzipple.modules.memory.infrastructure.storage import FileMemoryStore


@dataclass(slots=True)
class FileBackedMemoryService:
    store: FileMemoryStore = field(default_factory=FileMemoryStore)
    index_manager: FileMemoryIndexManager = field(default_factory=FileMemoryIndexManager)
    sync_index: SyncMemoryIndexService | None = None
    search_index: SearchMemoryIndexService | None = None

    def __post_init__(self) -> None:
        if self.sync_index is None:
            self.sync_index = self.index_manager.sync_service
        if self.search_index is None:
            self.search_index = self.index_manager.search_service

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
        result = self.store.append_daily(
            context=context,
            content=content,
            title=title,
            now=now,
        )
        assert self.sync_index is not None
        self.sync_index.mark_dirty(context=context, changed_paths=(result.path,))
        return result

    def write_long_term(
        self,
        *,
        context: MemoryUseContext,
        content: str,
    ) -> MemoryWriteResult:
        result = self.store.write_long_term(
            context=context,
            content=content,
        )
        assert self.sync_index is not None
        self.sync_index.mark_dirty(context=context, changed_paths=(result.path,))
        return result

    def archive_session(
        self,
        *,
        context: MemoryUseContext,
        content: str,
        slug: str | None = None,
        now: datetime | None = None,
    ) -> MemoryWriteResult:
        result = self.store.archive_session(
            context=context,
            content=content,
            slug=slug,
            now=now,
        )
        assert self.sync_index is not None
        self.sync_index.mark_dirty(context=context, changed_paths=(result.path,))
        return result
