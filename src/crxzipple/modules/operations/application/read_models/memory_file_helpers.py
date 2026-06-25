from __future__ import annotations

from pathlib import Path
from typing import Any

from crxzipple.modules.operations.application.read_models.memory_models import (
    MemoryContextRecord,
)
from crxzipple.modules.operations.application.read_models.memory_values import (
    format_bytes,
    text,
)


def file_is_indexed(record: MemoryContextRecord | None, item: Any) -> bool:
    if record is None:
        return False
    if record.indexed_file_count <= 0:
        return False
    # Index state is exposed as file count by the service contract; avoid leaking
    # persistence internals by treating the selected indexed set as a coverage signal.
    return record.indexed_file_count >= len(record.files)


def file_id(record: MemoryContextRecord | None, item: Any) -> str:
    space_id = record.scope_ref if record else "-"
    return f"{space_id}:{text(getattr(item, 'path', ''))}"


def file_size(record: MemoryContextRecord | None, item: Any) -> str:
    return format_bytes(file_size_bytes(record, item))


def file_size_bytes(record: MemoryContextRecord | None, item: Any) -> int:
    root = record.storage_root if record is not None else ""
    path = text(getattr(item, "path", ""), "")
    if not root or not path:
        return len(text(getattr(item, "preview", ""), ""))
    try:
        target = (Path(root).expanduser() / path).resolve()
        return int(target.stat().st_size) if target.is_file() else 0
    except Exception:
        return len(text(getattr(item, "preview", ""), ""))


def latest_file_update(files: tuple[Any, ...]) -> str:
    values = [text(getattr(item, "updated_at", ""), "") for item in files]
    values = [item for item in values if item]
    return max(values) if values else "-"


def file_search_blob(item: Any) -> str:
    return " ".join(
        (
            text(getattr(item, "path", "")),
            text(getattr(item, "title", "")),
            text(getattr(item, "kind", "")),
            text(getattr(item, "preview", "")),
        )
    ).lower()
