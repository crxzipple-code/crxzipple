from __future__ import annotations

from typing import Protocol

from crxzipple.modules.memory.application import (
    MemoryExcerpt,
    MemorySearchHit,
    MemoryUseContext,
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
