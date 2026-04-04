from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re

from crxzipple.modules.memory.application.models import (
    MemoryExcerpt,
    MemoryFileSummary,
    MemoryUseContext,
    MemoryWriteResult,
)
from crxzipple.modules.memory.domain import (
    MemoryFileKind,
    infer_memory_file_kind,
    is_memory_relative_path as _is_memory_relative_path,
)


@dataclass(frozen=True, slots=True)
class FileMemoryStore:
    def list_files(
        self,
        *,
        context: MemoryUseContext,
        kind: MemoryFileKind | None = None,
        limit: int | None = None,
    ) -> list[MemoryFileSummary]:
        root = ensure_storage_root(context.storage_root)
        items: list[MemoryFileSummary] = []
        for path in iter_memory_files(root):
            relative_path = path.relative_to(root).as_posix()
            file_kind = infer_memory_file_kind(relative_path)
            if kind is not None and file_kind != kind:
                continue
            text = path.read_text(encoding="utf-8")
            stat = path.stat()
            items.append(
                MemoryFileSummary(
                    path=relative_path,
                    kind=file_kind,
                    title=_summary_title(relative_path, text),
                    preview=_summary_preview(text),
                    updated_at=datetime.fromtimestamp(
                        stat.st_mtime,
                        tz=timezone.utc,
                    ).isoformat(),
                ),
            )
        items.sort(key=lambda item: (item.updated_at, item.path), reverse=True)
        if limit is not None and limit > 0:
            return items[:limit]
        return items

    def get(
        self,
        *,
        context: MemoryUseContext,
        path: str,
        start_line: int | None = None,
        line_count: int | None = None,
    ) -> MemoryExcerpt | None:
        root = ensure_storage_root(context.storage_root)
        target = resolve_memory_file(root, path)
        if target is None or not target.is_file():
            return None
        relative_path = target.relative_to(root).as_posix()
        text = target.read_text(encoding="utf-8")
        lines = text.splitlines()
        if not lines:
            return MemoryExcerpt(
                path=relative_path,
                text="",
                start_line=1,
                end_line=1,
                kind=infer_memory_file_kind(relative_path),
            )

        requested_start = max(start_line or 1, 1)
        if requested_start > len(lines):
            return None
        if line_count is None:
            requested_end = len(lines)
        else:
            requested_end = min(len(lines), requested_start + max(line_count, 1) - 1)
        excerpt_text = "\n".join(lines[requested_start - 1 : requested_end])
        return MemoryExcerpt(
            path=relative_path,
            text=excerpt_text,
            start_line=requested_start,
            end_line=max(requested_start, requested_end),
            kind=infer_memory_file_kind(relative_path),
        )

    def append_daily(
        self,
        *,
        context: MemoryUseContext,
        content: str,
        title: str | None = None,
        now: datetime | None = None,
    ) -> MemoryWriteResult:
        timestamp = now.astimezone(timezone.utc) if now is not None else datetime.now(timezone.utc)
        root = ensure_storage_root(context.storage_root)
        memory_dir = root / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        target = memory_dir / f"{timestamp.date().isoformat()}.md"
        if title is not None and title.strip():
            body = f"## {title.strip()}\n\n{content.strip()}\n"
        else:
            body = content.strip() + "\n"
        line_start, line_end = append_markdown_block(target, body)
        return MemoryWriteResult(
            path=target.relative_to(root).as_posix(),
            line_start=line_start,
            line_end=line_end,
            kind="daily",
        )

    def write_long_term(
        self,
        *,
        context: MemoryUseContext,
        content: str,
    ) -> MemoryWriteResult:
        root = ensure_storage_root(context.storage_root)
        target = root / "MEMORY.md"
        body = content.strip() + "\n"
        line_start, line_end = append_markdown_block(target, body)
        return MemoryWriteResult(
            path=target.relative_to(root).as_posix(),
            line_start=line_start,
            line_end=line_end,
            kind="long_term",
        )

    def archive_session(
        self,
        *,
        context: MemoryUseContext,
        content: str,
        slug: str | None = None,
        now: datetime | None = None,
    ) -> MemoryWriteResult:
        timestamp = now.astimezone(timezone.utc) if now is not None else datetime.now(timezone.utc)
        normalized_slug = slugify(slug or "session")
        root = ensure_storage_root(context.storage_root)
        memory_dir = root / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        target = memory_dir / f"{timestamp.date().isoformat()}-{normalized_slug}.md"
        body = content.strip() + "\n"
        target.write_text(body, encoding="utf-8")
        line_count = max(1, len(body.splitlines()) or 1)
        return MemoryWriteResult(
            path=target.relative_to(root).as_posix(),
            line_start=1,
            line_end=line_count,
            kind="archive",
        )


def ensure_storage_root(storage_root: str | Path) -> Path:
    root = Path(storage_root).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def iter_memory_files(root: Path) -> tuple[Path, ...]:
    files: list[Path] = []
    memory_file = root / "MEMORY.md"
    fallback_file = root / "memory.md"
    if memory_file.is_file():
        files.append(memory_file)
    elif fallback_file.is_file():
        files.append(fallback_file)
    memory_dir = root / "memory"
    if memory_dir.is_dir():
        files.extend(
            candidate
            for candidate in sorted(memory_dir.rglob("*.md"))
            if candidate.is_file()
        )
    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in files:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append(resolved)
    return tuple(deduped)


def memory_file_fingerprint(root: Path) -> tuple[tuple[str, int, int], ...]:
    return tuple(
        (
            path.relative_to(root).as_posix(),
            int(path.stat().st_mtime_ns),
            int(path.stat().st_size),
        )
        for path in iter_memory_files(root)
    )


def resolve_memory_file(root: Path, relative_path: str) -> Path | None:
    normalized = relative_path.strip().lstrip("/")
    if not normalized:
        return None
    target = (root / normalized).resolve()
    try:
        rel = target.relative_to(root)
    except ValueError:
        return None
    if not _is_memory_relative_path(rel.as_posix()):
        return None
    return target


def is_memory_relative_path(relative_path: str) -> bool:
    return _is_memory_relative_path(relative_path)


def memory_file_kind(relative_path: str) -> MemoryFileKind:
    return infer_memory_file_kind(relative_path)


def append_markdown_block(path: Path, body: str) -> tuple[int, int]:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    prefix = ""
    if existing:
        prefix = "\n\n" if not existing.endswith("\n\n") else ""
        if existing.endswith("\n") and not existing.endswith("\n\n"):
            prefix = "\n"
    line_start = existing.count("\n") + prefix.count("\n") + 1
    line_end = line_start + max(1, len(body.splitlines()) or 1) - 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(existing + prefix + body, encoding="utf-8")
    return line_start, line_end


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    slug = slug.strip("-")
    return slug or "session"


def _summary_title(relative_path: str, text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            heading = stripped.lstrip("#").strip()
            if heading:
                return heading
        return stripped[:80]
    return Path(relative_path).name


def _summary_preview(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    if lines[0].startswith("#"):
        lines = lines[1:]
    preview = " ".join(lines).strip()
    if len(preview) <= 180:
        return preview
    return preview[:177].rstrip() + "..."
