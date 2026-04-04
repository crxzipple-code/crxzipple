from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

from crxzipple.modules.memory.application.models import MemorySearchRecord
from crxzipple.modules.memory.domain import IndexedChunk, IndexedMemoryFile


class MemorySourceScanner(Protocol):
    def scan(
        self,
        *,
        storage_root: str | Path,
    ) -> tuple[IndexedMemoryFile, ...]:
        ...

    def fingerprint(
        self,
        *,
        storage_root: str | Path,
    ) -> tuple[tuple[str, int, int], ...]:
        ...

    def scan_paths(
        self,
        *,
        storage_root: str | Path,
        relative_paths: Sequence[str],
    ) -> tuple[IndexedMemoryFile, ...]:
        ...

    def fingerprint_paths(
        self,
        *,
        storage_root: str | Path,
        relative_paths: Sequence[str],
    ) -> tuple[tuple[str, int, int], ...]:
        ...


class MemoryIndexStore(Protocol):
    def index_db_path(
        self,
        *,
        storage_root: str | Path,
        space_id: str,
    ) -> Path:
        ...

    def sync_metadata(
        self,
        *,
        storage_root: str | Path,
        space_id: str,
        expected: Mapping[str, str],
    ) -> bool:
        ...

    def indexed_file_hashes(
        self,
        *,
        storage_root: str | Path,
        space_id: str,
    ) -> dict[str, str]:
        ...

    def clear(
        self,
        *,
        storage_root: str | Path,
        space_id: str,
    ) -> None:
        ...

    def delete_path(
        self,
        *,
        storage_root: str | Path,
        space_id: str,
        path: str,
    ) -> None:
        ...

    def replace_file_chunks(
        self,
        *,
        storage_root: str | Path,
        space_id: str,
        indexed_file: IndexedMemoryFile,
        chunks: Sequence[IndexedChunk],
        embeddings: Sequence[tuple[float, ...]] | None,
        embedding_provider_name: str | None,
        embedding_model_name: str | None,
        embedding_provider_key: str | None,
        retrieval_backend: str,
    ) -> None:
        ...

    def load_embedding_cache(
        self,
        *,
        storage_root: str | Path,
        space_id: str,
        provider_name: str,
        model_name: str,
        provider_key: str,
        content_hashes: Sequence[str],
    ) -> dict[str, tuple[float, ...]]:
        ...

    def store_embedding_cache(
        self,
        *,
        storage_root: str | Path,
        space_id: str,
        provider_name: str,
        model_name: str,
        provider_key: str,
        embeddings_by_hash: Mapping[str, Sequence[float]],
    ) -> None:
        ...


class MemorySearchGateway(Protocol):
    def search_records(
        self,
        *,
        storage_root: str | Path,
        space_id: str,
        query: str,
        limit: int,
        retrieval_backend: str,
        query_embedding: Sequence[float] | None = None,
    ) -> list[MemorySearchRecord]:
        ...


class MemoryEmbeddingProvider(Protocol):
    @property
    def provider_name(self) -> str:
        ...

    @property
    def model_name(self) -> str:
        ...

    @property
    def provider_key(self) -> str:
        ...

    def embed_texts(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        ...
