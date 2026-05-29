from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from crxzipple.modules.memory.application.models import (
    MemoryExcerpt,
    MemoryFileSummary,
    MemorySearchHit,
    MemoryUseContext,
)


@dataclass(frozen=True, slots=True)
class MemoryScopeInventoryRecord:
    agent_id: str
    scope_ref: str
    storage_root: str
    retrieval_backend: str
    files: tuple[MemoryFileSummary, ...]
    indexed_file_count: int
    index_db_path: str
    index_db_exists: bool
    dirty: bool
    error: str = ""

    @property
    def resolved(self) -> bool:
        return not self.error and bool(self.scope_ref and self.storage_root)


@dataclass(slots=True)
class MemoryQueryService:
    file_memory_service: Any
    scope_resolver: Any

    def agent_scope_inventory(
        self,
        agent_id: str,
        *,
        file_limit: int = 240,
    ) -> MemoryScopeInventoryRecord:
        normalized = agent_id.strip()
        context = self._resolve_context(normalized)
        if context is None:
            return MemoryScopeInventoryRecord(
                agent_id=normalized,
                scope_ref="",
                storage_root="",
                retrieval_backend="",
                files=(),
                indexed_file_count=0,
                index_db_path="-",
                index_db_exists=False,
                dirty=False,
                error="memory context is not resolved",
            )
        files = tuple(self.list_files(context, limit=file_limit))
        index_db_path = self.index_db_path(context)
        return MemoryScopeInventoryRecord(
            agent_id=normalized,
            scope_ref=context.space_id,
            storage_root=context.storage_root,
            retrieval_backend=context.retrieval_backend,
            files=files,
            indexed_file_count=self.indexed_file_count(context),
            index_db_path=index_db_path,
            index_db_exists=Path(index_db_path).is_file() if index_db_path != "-" else False,
            dirty=self.context_key(context) in self.dirty_context_keys(),
        )

    def list_files(
        self,
        context: MemoryUseContext,
        *,
        limit: int | None = 240,
    ) -> tuple[MemoryFileSummary, ...]:
        return tuple(self.file_memory_service.list_files(context=context, limit=limit))

    def search_agent(
        self,
        agent_id: str,
        *,
        query: str,
        limit: int = 20,
    ) -> tuple[MemorySearchHit, ...]:
        context = self._resolve_context(agent_id)
        if context is None or not query:
            return ()
        return tuple(
            self.file_memory_service.search(
                context=context,
                query=query,
                limit=limit,
            ),
        )

    def get_agent_excerpt(
        self,
        agent_id: str,
        *,
        path: str,
        start_line: int | None = None,
        line_count: int | None = None,
    ) -> MemoryExcerpt | None:
        context = self._resolve_context(agent_id)
        if context is None:
            return None
        return self.file_memory_service.get(
            context=context,
            path=path,
            start_line=start_line,
            line_count=line_count,
        )

    def get_agent_long_term_excerpt(self, agent_id: str) -> MemoryExcerpt | None:
        return self.get_agent_excerpt(agent_id, path="MEMORY.md") or self.get_agent_excerpt(
            agent_id,
            path="memory.md",
        )

    def indexed_file_count(self, context: MemoryUseContext) -> int:
        index_store = self._index_store()
        indexed_file_hashes = getattr(index_store, "indexed_file_hashes", None)
        if not callable(indexed_file_hashes):
            return 0
        try:
            return len(
                indexed_file_hashes(
                    storage_root=context.storage_root,
                    space_id=context.space_id,
                )
            )
        except Exception:
            return 0

    def index_db_path(self, context: MemoryUseContext) -> str:
        manager = getattr(self.file_memory_service, "index_manager", None)
        index_db_path = getattr(manager, "index_db_path", None)
        if not callable(index_db_path):
            return "-"
        try:
            return str(index_db_path(context.storage_root, context.space_id))
        except Exception:
            return "-"

    def dirty_context_keys(self) -> set[str]:
        sync_index = getattr(self.file_memory_service, "sync_index", None)
        raw = getattr(sync_index, "_dirty_context_keys", set())
        return set(raw) if isinstance(raw, set) else set()

    @staticmethod
    def context_key(context: MemoryUseContext) -> str:
        return f"{context.space_id}::{context.storage_root}"

    def _resolve_context(self, agent_id: str) -> MemoryUseContext | None:
        resolve = getattr(self.scope_resolver, "resolve", None)
        if not callable(resolve):
            return None
        try:
            return resolve(agent_id)
        except Exception:
            return None

    def _index_store(self) -> Any | None:
        manager = getattr(self.file_memory_service, "index_manager", None)
        return getattr(manager, "index_store", None)
