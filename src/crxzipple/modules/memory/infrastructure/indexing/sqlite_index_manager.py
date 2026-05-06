from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from crxzipple.modules.memory.application.indexing import (
    SearchMemoryIndexService,
    SyncMemoryIndexService,
)
from crxzipple.modules.memory.application.contracts import MemoryEmbeddingProvider
from crxzipple.modules.memory.application.models import MemorySearchHit, MemoryUseContext
from crxzipple.modules.memory.domain import MemoryChunkingPolicy
from crxzipple.modules.memory.infrastructure.indexing.sqlite_index_store import (
    SqliteMemoryIndexStore,
)
from crxzipple.modules.memory.infrastructure.storage.markdown_source_scanner import (
    MarkdownMemorySourceScanner,
)


@dataclass(slots=True)
class FileMemoryIndexManager:
    chunk_chars: int = 1_600
    overlap_chars: int = 320
    index_store: SqliteMemoryIndexStore = field(default_factory=SqliteMemoryIndexStore)
    source_scanner: MarkdownMemorySourceScanner = field(default_factory=MarkdownMemorySourceScanner)
    embedding_provider: MemoryEmbeddingProvider | None = None
    sync_service: SyncMemoryIndexService = field(init=False)
    search_service: SearchMemoryIndexService = field(init=False)

    def __post_init__(self) -> None:
        if self.embedding_provider is None:
            from crxzipple.modules.memory.infrastructure.indexing.embeddings import (
                LocalHashedMemoryEmbeddingProvider,
            )

            self.embedding_provider = LocalHashedMemoryEmbeddingProvider()
        policy = MemoryChunkingPolicy(
            chunk_chars=self.chunk_chars,
            overlap_chars=self.overlap_chars,
        )
        self.sync_service = SyncMemoryIndexService(
            source_scanner=self.source_scanner,
            index_store=self.index_store,
            chunking_policy=policy,
            embedding_provider=self.embedding_provider,
        )
        self.search_service = SearchMemoryIndexService(
            sync_service=self.sync_service,
            search_gateway=self.index_store,
            embedding_provider=self.embedding_provider,
        )

    def search(
        self,
        *,
        context: MemoryUseContext,
        query: str,
        limit: int = 6,
    ) -> list[MemorySearchHit]:
        return self.search_service.search(
            context=context,
            query=query,
            limit=limit,
        )

    def ensure_synced(self, *, context: MemoryUseContext) -> None:
        self.sync_service.ensure_synced(context=context)

    def warm_context(self, *, context: MemoryUseContext) -> bool:
        return self.sync_service.warm_context(context=context)

    def mark_dirty(
        self,
        *,
        context: MemoryUseContext,
        changed_paths: tuple[str, ...] | list[str] | None = None,
    ) -> None:
        self.sync_service.mark_dirty(context=context, changed_paths=changed_paths)

    def index_db_path(self, root: Path | str, space_id: str) -> Path:
        return self.index_store.index_db_path(storage_root=root, space_id=space_id)
