from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from crxzipple.modules.memory.domain import MemoryFileKind, MemoryItem


MemoryRetrievalBackend = Literal["keyword", "hybrid", "vector"]


@dataclass(frozen=True, slots=True)
class MemoryUseContext:
    space_id: str
    storage_root: str
    retrieval_backend: MemoryRetrievalBackend = "hybrid"

    def __post_init__(self) -> None:
        normalized_space_id = self.space_id.strip()
        normalized_storage_root = self.storage_root.strip()
        if not normalized_space_id:
            raise ValueError("MemoryUseContext.space_id cannot be empty.")
        if not normalized_storage_root:
            raise ValueError("MemoryUseContext.storage_root cannot be empty.")
        object.__setattr__(self, "space_id", normalized_space_id)
        object.__setattr__(self, "storage_root", normalized_storage_root)


@dataclass(frozen=True, slots=True)
class MemorySearchHit:
    item: MemoryItem
    path: str
    snippet: str
    start_line: int
    end_line: int
    score: float
    kind: MemoryFileKind

    @classmethod
    def from_item(
        cls,
        item: MemoryItem,
        *,
        score: float,
        snippet: str,
    ) -> "MemorySearchHit":
        return cls(
            item=item,
            path=item.path,
            snippet=snippet,
            start_line=item.start_line,
            end_line=item.end_line,
            score=score,
            kind=item.kind,
        )


@dataclass(frozen=True, slots=True)
class MemoryExcerpt:
    path: str
    text: str
    start_line: int
    end_line: int
    kind: MemoryFileKind


@dataclass(frozen=True, slots=True)
class MemoryWriteResult:
    path: str
    line_start: int
    line_end: int
    kind: MemoryFileKind


@dataclass(frozen=True, slots=True)
class MemoryFileSummary:
    path: str
    kind: MemoryFileKind
    title: str
    preview: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class MemorySearchRecord:
    id: str
    path: str
    start_line: int
    end_line: int
    text: str
    content_hash: str
    source_file_hash: str
    updated_at: int
    score: float
