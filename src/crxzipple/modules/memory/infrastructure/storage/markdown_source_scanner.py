from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from crxzipple.modules.memory.application.contracts import MemorySourceScanner
from crxzipple.modules.memory.domain import IndexedMemoryFile, infer_memory_file_kind
from crxzipple.modules.memory.infrastructure.storage.markdown_store import (
    ensure_storage_root,
    iter_memory_files,
    memory_file_fingerprint,
)


@dataclass(frozen=True, slots=True)
class MarkdownMemorySourceScanner(MemorySourceScanner):
    def scan(
        self,
        *,
        storage_root: str | Path,
    ) -> tuple[IndexedMemoryFile, ...]:
        root = ensure_storage_root(storage_root)
        return tuple(
            self._build_indexed_memory_file(path, root)
            for path in iter_memory_files(root)
        )

    def fingerprint(
        self,
        *,
        storage_root: str | Path,
    ) -> tuple[tuple[str, int, int], ...]:
        root = ensure_storage_root(storage_root)
        return memory_file_fingerprint(root)

    def scan_paths(
        self,
        *,
        storage_root: str | Path,
        relative_paths: tuple[str, ...] | list[str],
    ) -> tuple[IndexedMemoryFile, ...]:
        root = ensure_storage_root(storage_root)
        canonical = self._canonical_paths(root)
        files: list[IndexedMemoryFile] = []
        seen: set[str] = set()
        for relative_path in relative_paths:
            normalized = relative_path.strip().lstrip("/")
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            target = canonical.get(normalized)
            if target is None or not target.is_file():
                continue
            files.append(self._build_indexed_memory_file(target, root))
        return tuple(files)

    def fingerprint_paths(
        self,
        *,
        storage_root: str | Path,
        relative_paths: tuple[str, ...] | list[str],
    ) -> tuple[tuple[str, int, int], ...]:
        root = ensure_storage_root(storage_root)
        canonical = self._canonical_paths(root)
        fingerprints: list[tuple[str, int, int]] = []
        seen: set[str] = set()
        for relative_path in relative_paths:
            normalized = relative_path.strip().lstrip("/")
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            target = canonical.get(normalized)
            if target is None or not target.is_file():
                continue
            stat = target.stat()
            fingerprints.append(
                (
                    normalized,
                    int(stat.st_mtime_ns),
                    int(stat.st_size),
                ),
            )
        return tuple(fingerprints)

    @staticmethod
    def _build_indexed_memory_file(path: Path, root: Path) -> IndexedMemoryFile:
        stat = path.stat()
        text = path.read_text(encoding="utf-8")
        relative_path = path.relative_to(root).as_posix()
        return IndexedMemoryFile(
            path=relative_path,
            kind=infer_memory_file_kind(relative_path),
            source_file_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            mtime_ns=int(stat.st_mtime_ns),
            size_bytes=int(stat.st_size),
            text=text,
        )

    @staticmethod
    def _canonical_paths(root: Path) -> dict[str, Path]:
        return {
            path.relative_to(root).as_posix(): path
            for path in iter_memory_files(root)
        }
