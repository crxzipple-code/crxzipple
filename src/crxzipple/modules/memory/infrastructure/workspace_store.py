from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from crxzipple.modules.memory.domain.entities import MemoryEntry

_ENTRY_START_PREFIX = "<!-- crxzipple-memory-entry "
_ENTRY_END_MARKER = "<!-- /crxzipple-memory-entry -->"
_ENTRY_PATTERN = re.compile(
    r"<!-- crxzipple-memory-entry (?P<meta>\{.*?\}) -->\n?"
    r"(?P<content>.*?)"
    r"\n?<!-- /crxzipple-memory-entry -->",
    re.DOTALL,
)


@dataclass(frozen=True, slots=True)
class WorkspaceMemoryStore:
    def list_entries(
        self,
        *,
        workspace_dir: str,
        agent_id: str | None = None,
        query: str | None = None,
        limit: int | None = None,
    ) -> list[MemoryEntry]:
        root = _resolve_workspace_root(workspace_dir)
        if root is None:
            return []
        items: list[MemoryEntry] = []
        normalized_agent_id = agent_id.strip() if agent_id is not None else None
        for path in _iter_memory_files(root):
            items.extend(
                _load_entries_from_file(
                    root=root,
                    path=path,
                    agent_id_hint=normalized_agent_id,
                ),
            )
        if normalized_agent_id:
            items = [item for item in items if item.agent_id == normalized_agent_id]
        if query is not None and query.strip():
            normalized_query = query.strip().casefold()
            items = [
                item
                for item in items
                if normalized_query in item.title.casefold()
                or normalized_query in item.summary.casefold()
                or normalized_query in item.content.casefold()
                or any(normalized_query in tag.casefold() for tag in item.tags)
            ]
        items.sort(
            key=lambda item: (item.updated_at, item.created_at, item.id),
            reverse=True,
        )
        if limit is not None and limit > 0:
            return items[:limit]
        return items

    def get_entry(
        self,
        *,
        workspace_dir: str,
        entry_id: str,
    ) -> MemoryEntry | None:
        for entry in self.list_entries(workspace_dir=workspace_dir):
            if entry.id == entry_id:
                return entry
        return None

    def append_entry(
        self,
        *,
        workspace_dir: str,
        entry: MemoryEntry,
    ) -> MemoryEntry:
        root = _resolve_workspace_root(workspace_dir)
        if root is None:
            raise FileNotFoundError(f"Workspace '{workspace_dir}' was not found.")
        memory_dir = root / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        target_path = memory_dir / f"{entry.created_at.date().isoformat()}.md"
        relative_path = target_path.relative_to(root).as_posix()
        stored_entry = _entry_with_storage_metadata(entry, relative_path=relative_path)
        serialized = _serialize_entry_block(stored_entry)

        existing = target_path.read_text("utf-8") if target_path.exists() else ""
        with target_path.open("a", encoding="utf-8") as handle:
            if existing and not existing.endswith("\n\n"):
                handle.write("\n\n" if existing.endswith("\n") else "\n\n")
            handle.write(serialized)
            handle.write("\n")
        return stored_entry

    def remove_entry(
        self,
        *,
        workspace_dir: str,
        entry_id: str,
    ) -> bool:
        root = _resolve_workspace_root(workspace_dir)
        if root is None:
            return False
        removed = False
        for path in _iter_memory_files(root):
            text = path.read_text("utf-8")
            next_text, changed = _remove_entry_block(text, entry_id=entry_id)
            if not changed:
                continue
            path.write_text(next_text.strip() + ("\n" if next_text.strip() else ""), "utf-8")
            removed = True
        return removed


def _resolve_workspace_root(workspace_dir: str | None) -> Path | None:
    if workspace_dir is None or not workspace_dir.strip():
        return None
    try:
        root = Path(workspace_dir).expanduser().resolve(strict=True)
    except FileNotFoundError:
        return None
    if not root.is_dir():
        return None
    return root


def _iter_memory_files(root: Path) -> tuple[Path, ...]:
    files: list[Path] = []
    memory_path = root / "MEMORY.md"
    if memory_path.is_file():
        files.append(memory_path)
    elif (root / "memory.md").is_file():
        files.append(root / "memory.md")
    memory_dir = root / "memory"
    if memory_dir.is_dir():
        files.extend(
            candidate
            for candidate in sorted(memory_dir.glob("*.md"))
            if candidate.is_file()
        )
    return tuple(files)


def _load_entries_from_file(
    *,
    root: Path,
    path: Path,
    agent_id_hint: str | None = None,
) -> list[MemoryEntry]:
    text = path.read_text("utf-8")
    relative_path = path.relative_to(root).as_posix()
    stat = path.stat()
    matches = list(_ENTRY_PATTERN.finditer(text))
    if not matches:
        if not text.strip():
            return []
        return [
            _build_unstructured_entry(
                relative_path=relative_path,
                content=text.strip(),
                modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                agent_id_hint=agent_id_hint,
                line_start=1,
                line_end=max(1, len(text.splitlines()) or 1),
            ),
        ]
    return [
        _build_structured_entry(
            meta_payload=json.loads(match.group("meta")),
            content=match.group("content").strip(),
            relative_path=relative_path,
            line_start=_line_number_at_offset(text, match.start("content")),
            line_end=max(
                _line_number_at_offset(text, match.end("content")),
                _line_number_at_offset(text, match.start("content")),
            ),
        )
        for match in matches
    ]


def _build_unstructured_entry(
    *,
    relative_path: str,
    content: str,
    modified_at: datetime,
    agent_id_hint: str | None = None,
    line_start: int = 1,
    line_end: int = 1,
) -> MemoryEntry:
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    title = lines[0].lstrip("# ").strip() if lines else Path(relative_path).name
    summary = lines[1] if len(lines) > 1 else content[:160].strip()
    entry_id = f"file-{hashlib.sha256(relative_path.encode('utf-8')).hexdigest()[:24]}"
    return MemoryEntry(
        id=entry_id,
        agent_id=(agent_id_hint or "workspace").strip() or "workspace",
        title=title or Path(relative_path).name,
        content=content,
        summary=summary,
        metadata={
            "storage_kind": "workspace_file",
            "memory_file_path": relative_path,
            "memory_file_line_start": line_start,
            "memory_file_line_end": line_end,
            "synthetic": True,
        },
        created_at=modified_at,
        updated_at=modified_at,
    )


def _build_structured_entry(
    *,
    meta_payload: dict[str, object],
    content: str,
    relative_path: str,
    line_start: int,
    line_end: int,
) -> MemoryEntry:
    created_at = _parse_iso_datetime(meta_payload.get("created_at"))
    updated_at = _parse_iso_datetime(meta_payload.get("updated_at")) or created_at
    metadata = (
        dict(meta_payload.get("metadata", {}))
        if isinstance(meta_payload.get("metadata"), dict)
        else {}
    )
    metadata["storage_kind"] = "workspace_file"
    metadata["memory_file_path"] = relative_path
    metadata["memory_file_line_start"] = line_start
    metadata["memory_file_line_end"] = line_end
    return MemoryEntry(
        id=str(meta_payload["id"]),
        agent_id=str(meta_payload.get("agent_id", "workspace")).strip() or "workspace",
        title=str(meta_payload.get("title", Path(relative_path).name)),
        content=content,
        summary=str(meta_payload.get("summary", "")).strip(),
        session_key=_string_or_none(meta_payload.get("session_key")),
        run_id=_string_or_none(meta_payload.get("run_id")),
        source_candidate_id=_string_or_none(meta_payload.get("source_candidate_id")),
        tags=tuple(str(item) for item in (meta_payload.get("tags") or ()) if str(item).strip()),
        metadata=metadata,
        created_at=created_at,
        updated_at=updated_at,
    )


def _serialize_entry_block(entry: MemoryEntry) -> str:
    payload = {
        "id": entry.id,
        "agent_id": entry.agent_id,
        "title": entry.title,
        "summary": entry.summary,
        "session_key": entry.session_key,
        "run_id": entry.run_id,
        "source_candidate_id": entry.source_candidate_id,
        "tags": list(entry.tags),
        "created_at": entry.created_at.isoformat(),
        "updated_at": entry.updated_at.isoformat(),
        "metadata": dict(entry.metadata),
    }
    return (
        f"{_ENTRY_START_PREFIX}{json.dumps(payload, ensure_ascii=False)} -->\n"
        f"{entry.content.strip()}\n"
        f"{_ENTRY_END_MARKER}"
    )


def _remove_entry_block(text: str, *, entry_id: str) -> tuple[str, bool]:
    changed = False

    def _replace(match: re.Match[str]) -> str:
        nonlocal changed
        try:
            payload = json.loads(match.group("meta"))
        except json.JSONDecodeError:
            return match.group(0)
        if str(payload.get("id", "")).strip() != entry_id:
            return match.group(0)
        changed = True
        return ""

    updated = _ENTRY_PATTERN.sub(_replace, text)
    updated = re.sub(r"\n{3,}", "\n\n", updated).strip()
    return updated, changed


def _parse_iso_datetime(value: object) -> datetime:
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _line_number_at_offset(text: str, offset: int) -> int:
    bounded_offset = min(max(offset, 0), len(text))
    return text.count("\n", 0, bounded_offset) + 1


def _entry_with_storage_metadata(entry: MemoryEntry, *, relative_path: str) -> MemoryEntry:
    metadata = dict(entry.metadata)
    metadata["storage_kind"] = "workspace_file"
    metadata["memory_file_path"] = relative_path
    return MemoryEntry(
        id=entry.id,
        agent_id=entry.agent_id,
        title=entry.title,
        content=entry.content,
        summary=entry.summary,
        session_key=entry.session_key,
        run_id=entry.run_id,
        source_candidate_id=entry.source_candidate_id,
        tags=entry.tags,
        metadata=metadata,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )
