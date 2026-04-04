from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import re

from crxzipple.modules.memory.domain.entities import IndexedMemoryFile
from crxzipple.modules.memory.domain.value_objects import ChunkRange, IndexedChunk, IndexSyncPlan, MemoryFileKind


def infer_memory_file_kind(relative_path: str) -> MemoryFileKind:
    normalized = relative_path.strip().lstrip("/")
    if normalized in {"MEMORY.md", "memory.md"}:
        return "long_term"
    if re.fullmatch(r"memory/\d{4}-\d{2}-\d{2}\.md", normalized):
        return "daily"
    return "archive"


def is_memory_relative_path(relative_path: str) -> bool:
    normalized = relative_path.strip().lstrip("/")
    if normalized in {"MEMORY.md", "memory.md"}:
        return True
    return normalized.startswith("memory/") and normalized.endswith(".md")


@dataclass(frozen=True, slots=True)
class MemoryIndexPlanner:
    def build_sync_plan(
        self,
        *,
        current_files: tuple[IndexedMemoryFile, ...],
        existing_hashes: dict[str, str],
        metadata_changed: bool,
    ) -> IndexSyncPlan:
        active_paths = {item.path for item in current_files}
        stale_paths = tuple(sorted(set(existing_hashes) - active_paths))
        files_to_reindex = tuple(
            item
            for item in current_files
            if metadata_changed or existing_hashes.get(item.path) != item.source_file_hash
        )
        return IndexSyncPlan(
            needs_full_reindex=metadata_changed,
            stale_paths=stale_paths,
            files_to_reindex=files_to_reindex,
        )


@dataclass(frozen=True, slots=True)
class MemoryChunkingPolicy:
    chunk_chars: int = 1_600
    overlap_chars: int = 320

    def expected_metadata(self) -> dict[str, str]:
        return {
            "schema_version": "openclaw-like-v1",
            "chunk_chars": str(self.chunk_chars),
            "overlap_chars": str(self.overlap_chars),
        }

    def chunk_text(self, text: str) -> tuple[IndexedChunk, ...]:
        if not text.strip():
            return ()
        line_segments: list[tuple[int, str]] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line:
                line_segments.append((line_number, ""))
                continue
            remaining = line
            while len(remaining) > self.chunk_chars:
                line_segments.append((line_number, remaining[: self.chunk_chars]))
                remaining = remaining[self.chunk_chars :]
            line_segments.append((line_number, remaining))

        chunks: list[IndexedChunk] = []
        current: list[tuple[int, str]] = []
        current_chars = 0
        for line_number, segment in line_segments:
            segment_chars = len(segment) + 1
            if current and current_chars + segment_chars > self.chunk_chars:
                chunks.append(_build_chunk(current))
                current = _tail_overlap(current, self.overlap_chars)
                current_chars = sum(len(item[1]) + 1 for item in current)
            current.append((line_number, segment))
            current_chars += segment_chars
        if current:
            chunks.append(_build_chunk(current))
        return tuple(chunks)


def preview_text(text: str, *, max_chars: int = 180) -> str:
    condensed = re.sub(r"\s+", " ", text).strip()
    if len(condensed) <= max_chars:
        return condensed
    return condensed[: max_chars - 3].rstrip() + "..."


def search_snippet(text: str, query: str, *, max_chars: int = 220) -> str:
    condensed = re.sub(r"\s+", " ", text).strip()
    if len(condensed) <= max_chars:
        return condensed
    lowered = condensed.casefold()
    anchor = _best_query_anchor(lowered, query)
    if anchor is None:
        start = 0
    else:
        offset, anchor_length = anchor
        center = offset + (anchor_length // 2)
        start = max(0, center - (max_chars // 2))
    end = min(len(condensed), start + max_chars)
    if end - start < max_chars:
        start = max(0, end - max_chars)
    snippet = condensed[start:end].strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(condensed):
        snippet = snippet + "..."
    return snippet


def score_from_rank(rank: float) -> float:
    return 1.0 / (1.0 + abs(rank))


def _build_chunk(items: list[tuple[int, str]]) -> IndexedChunk:
    return IndexedChunk(
        chunk_range=ChunkRange(
            start_line=items[0][0],
            end_line=items[-1][0],
        ),
        text="\n".join(segment for _, segment in items).strip(),
    )


def _tail_overlap(items: list[tuple[int, str]], overlap_chars: int) -> list[tuple[int, str]]:
    if overlap_chars <= 0 or not items:
        return []
    overlap: list[tuple[int, str]] = []
    total = 0
    for item in reversed(items):
        overlap.insert(0, item)
        total += len(item[1]) + 1
        if total >= overlap_chars:
            break
    return overlap


def _tokenize(value: str) -> tuple[str, ...]:
    return tuple(
        token
        for token in re.findall(r"[0-9A-Za-z_]+", value.casefold())
        if token
    )


def _best_query_anchor(text: str, query: str) -> tuple[int, int] | None:
    token_counts = Counter(token for token in _tokenize(query) if len(token) >= 2)
    matches: list[tuple[str, int, int]] = []
    for token, count in token_counts.items():
        index = text.find(token)
        if index >= 0:
            matches.append((token, count, index))
    if not matches:
        return None
    token, _, index = max(
        matches,
        key=lambda item: (item[1] * len(item[0]), item[1], len(item[0]), -item[2]),
    )
    return index, len(token)
