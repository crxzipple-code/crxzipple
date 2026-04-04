from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from crxzipple.modules.memory.application.contracts import (
    MemoryEmbeddingProvider,
    MemoryIndexStore,
    MemorySearchGateway,
    MemorySourceScanner,
)
from crxzipple.modules.memory.application.models import (
    MemorySearchHit,
    MemorySearchRecord,
    MemoryUseContext,
)
from crxzipple.modules.memory.domain import (
    ChunkRange,
    MemoryChunkingPolicy,
    MemoryIndexPlanner,
    MemoryItem,
    infer_memory_file_kind,
    preview_text,
    search_snippet,
)


@dataclass(slots=True)
class SyncMemoryIndexService:
    source_scanner: MemorySourceScanner
    index_store: MemoryIndexStore
    planner: MemoryIndexPlanner = field(default_factory=MemoryIndexPlanner)
    chunking_policy: MemoryChunkingPolicy = field(default_factory=MemoryChunkingPolicy)
    embedding_provider: MemoryEmbeddingProvider | None = None
    _dirty_context_keys: set[str] = field(default_factory=set, init=False, repr=False)
    _known_fingerprints: dict[str, tuple[tuple[str, int, int], ...]] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )
    _known_metadata: dict[str, tuple[tuple[str, str], ...]] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )
    _dirty_paths_by_context: dict[str, set[str]] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )

    def ensure_synced(
        self,
        *,
        context: MemoryUseContext,
        force: bool = False,
    ) -> bool:
        context_key = _context_key(context)
        fingerprint = self.source_scanner.fingerprint(storage_root=context.storage_root)
        expected_metadata = self._expected_metadata(context)
        metadata_signature = tuple(sorted(expected_metadata.items()))
        dirty_paths = tuple(
            sorted(self._dirty_paths_by_context.get(context_key, ())),
        )
        if (
            not force
            and context_key not in self._dirty_context_keys
            and self._known_fingerprints.get(context_key) == fingerprint
            and self._known_metadata.get(context_key) == metadata_signature
        ):
            return False
        metadata_changed = self.index_store.sync_metadata(
            storage_root=context.storage_root,
            space_id=context.space_id,
            expected=expected_metadata,
        )
        existing_hashes = self.index_store.indexed_file_hashes(
            storage_root=context.storage_root,
            space_id=context.space_id,
        )
        use_incremental = (
            not force
            and not metadata_changed
            and bool(dirty_paths)
            and context_key in self._known_fingerprints
        )
        if use_incremental:
            current_files = self.source_scanner.scan_paths(
                storage_root=context.storage_root,
                relative_paths=dirty_paths,
            )
            active_paths = {item.path for item in current_files}
            stale_paths = tuple(path for path in dirty_paths if path not in active_paths)
            files_to_reindex = tuple(
                item
                for item in current_files
                if existing_hashes.get(item.path) != item.source_file_hash
            )
            needs_full_reindex = False
        else:
            current_files = self.source_scanner.scan(storage_root=context.storage_root)
            sync_plan = self.planner.build_sync_plan(
                current_files=current_files,
                existing_hashes=existing_hashes,
                metadata_changed=metadata_changed,
            )
            stale_paths = sync_plan.stale_paths
            files_to_reindex = sync_plan.files_to_reindex
            needs_full_reindex = sync_plan.needs_full_reindex
        if needs_full_reindex:
            self.index_store.clear(
                storage_root=context.storage_root,
                space_id=context.space_id,
            )
        for stale_path in stale_paths:
            self.index_store.delete_path(
                storage_root=context.storage_root,
                space_id=context.space_id,
                path=stale_path,
            )
        for indexed_file in files_to_reindex:
            chunks = self.chunking_policy.chunk_text(indexed_file.text)
            embeddings = self._embeddings_for_chunks(
                context=context,
                chunks=chunks,
            )
            self.index_store.replace_file_chunks(
                storage_root=context.storage_root,
                space_id=context.space_id,
                indexed_file=indexed_file,
                chunks=chunks,
                embeddings=embeddings,
                embedding_provider_name=(
                    self.embedding_provider.provider_name
                    if embeddings is not None and self.embedding_provider is not None
                    else None
                ),
                embedding_model_name=(
                    self.embedding_provider.model_name
                    if embeddings is not None and self.embedding_provider is not None
                    else None
                ),
                embedding_provider_key=(
                    self.embedding_provider.provider_key
                    if embeddings is not None and self.embedding_provider is not None
                    else None
                ),
                retrieval_backend=context.retrieval_backend,
            )
        self._dirty_context_keys.discard(context_key)
        self._dirty_paths_by_context.pop(context_key, None)
        if use_incremental:
            self._known_fingerprints[context_key] = _merge_fingerprint(
                self._known_fingerprints.get(context_key, ()),
                dirty_paths=dirty_paths,
                changed_paths=self.source_scanner.fingerprint_paths(
                    storage_root=context.storage_root,
                    relative_paths=dirty_paths,
                ),
            )
        else:
            self._known_fingerprints[context_key] = fingerprint
        self._known_metadata[context_key] = metadata_signature
        return True

    def mark_dirty(
        self,
        *,
        context: MemoryUseContext,
        changed_paths: Iterable[str] | None = None,
    ) -> None:
        context_key = _context_key(context)
        self._dirty_context_keys.add(context_key)
        normalized = _normalize_dirty_paths(changed_paths)
        if not normalized:
            return
        bucket = self._dirty_paths_by_context.setdefault(context_key, set())
        bucket.update(normalized)

    def warm_context(self, *, context: MemoryUseContext) -> bool:
        return self.ensure_synced(context=context, force=False)

    def _expected_metadata(self, context: MemoryUseContext) -> dict[str, str]:
        expected = dict(self.chunking_policy.expected_metadata())
        index_mode = self._index_mode(context)
        expected["index_mode"] = index_mode
        if index_mode == "vector" and self.embedding_provider is not None:
            expected["vector_provider"] = self.embedding_provider.provider_name
            expected["vector_model"] = self.embedding_provider.model_name
            expected["vector_provider_key"] = self.embedding_provider.provider_key
        else:
            expected["vector_provider"] = ""
            expected["vector_model"] = ""
            expected["vector_provider_key"] = ""
        return expected

    def _embeddings_for_chunks(
        self,
        *,
        context: MemoryUseContext,
        chunks: tuple["IndexedChunk", ...],
    ) -> tuple[tuple[float, ...], ...] | None:
        if self._index_mode(context) != "vector" or self.embedding_provider is None:
            return None
        if not chunks:
            return ()
        chunk_texts = [getattr(chunk, "text") for chunk in chunks]
        content_hashes = tuple(_content_hash(text) for text in chunk_texts)
        cached = self.index_store.load_embedding_cache(
            storage_root=context.storage_root,
            space_id=context.space_id,
            provider_name=self.embedding_provider.provider_name,
            model_name=self.embedding_provider.model_name,
            provider_key=self.embedding_provider.provider_key,
            content_hashes=content_hashes,
        )
        missing_indexes = [
            index
            for index, content_hash in enumerate(content_hashes)
            if content_hash not in cached
        ]
        if missing_indexes:
            generated = self.embedding_provider.embed_texts(
                [chunk_texts[index] for index in missing_indexes],
            )
            generated_by_hash = {
                content_hashes[index]: generated[offset]
                for offset, index in enumerate(missing_indexes)
            }
            if generated_by_hash:
                self.index_store.store_embedding_cache(
                    storage_root=context.storage_root,
                    space_id=context.space_id,
                    provider_name=self.embedding_provider.provider_name,
                    model_name=self.embedding_provider.model_name,
                    provider_key=self.embedding_provider.provider_key,
                    embeddings_by_hash=generated_by_hash,
                )
                cached = {**cached, **generated_by_hash}
        return tuple(cached[content_hash] for content_hash in content_hashes)

    @staticmethod
    def _index_mode(context: MemoryUseContext) -> str:
        if context.retrieval_backend in {"hybrid", "vector"}:
            return "vector"
        return "keyword"


@dataclass(slots=True)
class SearchMemoryIndexService:
    sync_service: SyncMemoryIndexService
    search_gateway: MemorySearchGateway
    embedding_provider: MemoryEmbeddingProvider | None = None

    def search(
        self,
        *,
        context: MemoryUseContext,
        query: str,
        limit: int = 6,
    ) -> list[MemorySearchHit]:
        normalized_query = query.strip()
        if not normalized_query:
            return []
        self.sync_service.ensure_synced(context=context, force=False)
        query_embedding: tuple[float, ...] | None = None
        if (
            context.retrieval_backend in {"hybrid", "vector"}
            and self.embedding_provider is not None
        ):
            query_embedding = self.embedding_provider.embed_texts((normalized_query,))[0]
        records = self.search_gateway.search_records(
            storage_root=context.storage_root,
            space_id=context.space_id,
            query=normalized_query,
            limit=max(limit, 1),
            retrieval_backend=context.retrieval_backend,
            query_embedding=query_embedding,
        )
        return [
            MemorySearchHit.from_item(
                self._memory_item_from_record(context=context, record=record),
                score=record.score,
                snippet=search_snippet(record.text, normalized_query),
            )
            for record in records
        ]

    def _memory_item_from_record(
        self,
        *,
        context: MemoryUseContext,
        record: MemorySearchRecord,
    ) -> MemoryItem:
        return MemoryItem(
            id=record.id,
            space_id=context.space_id,
            path=record.path,
            kind=infer_memory_file_kind(record.path),
            chunk_range=ChunkRange(
                start_line=record.start_line,
                end_line=record.end_line,
            ),
            preview=preview_text(record.text),
            content_hash=record.content_hash,
            source_file_hash=record.source_file_hash,
            updated_at=record.updated_at,
        )


def _content_hash(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _context_key(context: MemoryUseContext) -> str:
    return f"{context.space_id}::{context.storage_root}"


def _merge_fingerprint(
    existing: tuple[tuple[str, int, int], ...],
    *,
    dirty_paths: tuple[str, ...],
    changed_paths: tuple[tuple[str, int, int], ...],
) -> tuple[tuple[str, int, int], ...]:
    merged = {
        path: (path, mtime_ns, size_bytes)
        for path, mtime_ns, size_bytes in existing
    }
    for path in dirty_paths:
        merged.pop(path, None)
    for path, mtime_ns, size_bytes in changed_paths:
        merged[path] = (path, mtime_ns, size_bytes)
    return tuple(sorted(merged.values(), key=lambda item: item[0]))


def _normalize_dirty_paths(paths: Iterable[str] | None) -> tuple[str, ...]:
    if paths is None:
        return ()
    normalized: list[str] = []
    seen: set[str] = set()
    for path in paths:
        value = str(path).strip().lstrip("/")
        if not value:
            continue
        expanded = (
            ("MEMORY.md", "memory.md")
            if value in {"MEMORY.md", "memory.md"}
            else (value,)
        )
        for item in expanded:
            if item in seen:
                continue
            seen.add(item)
            normalized.append(item)
    return tuple(normalized)
