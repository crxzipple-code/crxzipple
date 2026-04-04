from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.memory.domain.value_objects import ChunkRange, MemoryFileKind


@dataclass(frozen=True, slots=True)
class IndexedMemoryFile:
    path: str
    kind: MemoryFileKind
    source_file_hash: str
    mtime_ns: int
    size_bytes: int
    text: str


@dataclass(frozen=True, slots=True)
class MemoryItem:
    id: str
    space_id: str
    path: str
    kind: MemoryFileKind
    chunk_range: ChunkRange
    preview: str
    content_hash: str
    source_file_hash: str
    updated_at: int

    @property
    def start_line(self) -> int:
        return self.chunk_range.start_line

    @property
    def end_line(self) -> int:
        return self.chunk_range.end_line
