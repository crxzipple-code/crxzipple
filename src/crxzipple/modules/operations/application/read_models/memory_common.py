from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from crxzipple.modules.operations.application.read_models.memory_models import (
    MemoryContextRecord,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.memory_values import (
    status_label,
)
from crxzipple.shared.time import format_datetime_utc


def overview_rows(section: OperationsTableSectionModel) -> tuple[dict[str, str], ...]:
    return tuple(dict(row.cells) for row in section.rows[:80])


def record_status(record: MemoryContextRecord) -> str:
    if not record_resolved(record):
        return "No Context"
    if record.dirty:
        return "Dirty"
    if record.files and not record.index_db_exists:
        return "Missing Index"
    return "Ready"


def record_resolved(record: MemoryContextRecord) -> bool:
    return not record.error and bool(record.scope_ref and record.storage_root)


def record_tone(record: MemoryContextRecord) -> str:
    status = record_status(record)
    if status == "Ready":
        return "success"
    if status == "Missing Index":
        return "neutral"
    return "warning"


def index_status(record: MemoryContextRecord) -> str:
    return record_status(record)


def index_tone(status: str) -> str:
    if status == "Ready":
        return "success"
    if status == "No Context" or status == "Dirty":
        return "warning"
    return "neutral"


def context_payload(record: MemoryContextRecord | None) -> dict[str, str]:
    if record is None or not record_resolved(record):
        return {}
    return {
        "space_id": record.scope_ref,
        "storage_root": record.storage_root,
        "retrieval_backend": record.retrieval_backend,
    }


def watch_failures(metrics: Any | None) -> int:
    if metrics is None:
        return 0
    return int(getattr(metrics, "filesystem_sync_failures", 0) or 0) + int(getattr(metrics, "interval_sync_failures", 0) or 0)


def watcher_label(record: MemoryContextRecord, metrics: Any | None) -> str:
    if not record_resolved(record):
        return "-"
    if metrics is None:
        return "Not Configured"
    return f"{getattr(metrics, 'watched_contexts', 0)} contexts"


def progress(indexed: int, total: int) -> str:
    if total <= 0:
        return "0%"
    return f"{round((indexed / total) * 100)}%"


def index_updated_at(path: str) -> str:
    if not path or path == "-":
        return "-"
    try:
        target = Path(path)
        if not target.is_file():
            return "-"
        return format_datetime_utc(datetime.fromtimestamp(target.stat().st_mtime, timezone.utc))
    except Exception:
        return "-"


def kind_label(kind: str) -> str:
    mapping = {
        "long_term": "Long Term",
        "daily": "Daily",
        "archive": "Archive",
    }
    return mapping.get(kind, status_label(kind))


def backend_tone(backend: str) -> str:
    if backend == "vector":
        return "info"
    if backend == "hybrid":
        return "success"
    if backend == "keyword":
        return "neutral"
    return "warning"


def health_label(health: str) -> str:
    if health == "error":
        return "Error"
    if health == "warning":
        return "Warning"
    return "Healthy"


def health_delta(health: str) -> str:
    if health == "error":
        return "Memory service is not connected"
    if health == "warning":
        return "Memory context needs attention"
    return "Memory state is queryable"


def health_tone(health: str) -> str:
    if health == "error":
        return "danger"
    if health == "warning":
        return "warning"
    return "success"
