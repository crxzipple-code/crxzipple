from __future__ import annotations

from typing import Protocol

from crxzipple.modules.memory.application import (
    MemoryExcerpt,
    MemorySearchHit,
    MemoryUseContext,
    MemoryWriteResult,
)


class MemoryPort(Protocol):
    def resolve_context(
        self,
        *,
        space_id: str | None,
    ) -> MemoryUseContext | None:
        ...

    def search(
        self,
        *,
        context: MemoryUseContext,
        query: str,
        limit: int = 6,
    ) -> list[MemorySearchHit]:
        ...

    def warm_context(
        self,
        *,
        context: MemoryUseContext,
    ) -> bool:
        ...

    def get(
        self,
        *,
        context: MemoryUseContext,
        path: str,
        start_line: int | None = None,
        line_count: int | None = None,
    ) -> MemoryExcerpt | None:
        ...

    def append_daily(
        self,
        *,
        context: MemoryUseContext,
        content: str,
        title: str | None = None,
    ) -> MemoryWriteResult:
        ...

    def write_long_term(
        self,
        *,
        context: MemoryUseContext,
        content: str,
    ) -> MemoryWriteResult:
        ...

    def archive_session(
        self,
        *,
        context: MemoryUseContext,
        content: str,
        slug: str | None = None,
    ) -> MemoryWriteResult:
        ...
