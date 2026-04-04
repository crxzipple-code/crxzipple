from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


MemoryFileKind = Literal["long_term", "daily", "archive"]


@dataclass(frozen=True, slots=True)
class ChunkRange:
    start_line: int
    end_line: int

    def __post_init__(self) -> None:
        if self.start_line <= 0:
            raise ValueError("ChunkRange.start_line must be positive.")
        if self.end_line < self.start_line:
            raise ValueError("ChunkRange.end_line cannot be before start_line.")


@dataclass(frozen=True, slots=True)
class IndexedChunk:
    chunk_range: ChunkRange
    text: str

    @property
    def start_line(self) -> int:
        return self.chunk_range.start_line

    @property
    def end_line(self) -> int:
        return self.chunk_range.end_line


@dataclass(frozen=True, slots=True)
class IndexSyncPlan:
    needs_full_reindex: bool
    stale_paths: tuple[str, ...]
    files_to_reindex: tuple["IndexedMemoryFile", ...]
