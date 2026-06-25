from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.memory_common import (
    record_resolved,
    watch_failures,
)
from crxzipple.modules.operations.application.read_models.memory_models import (
    MemoryContextRecord,
)


def health(
    *,
    service_available: bool,
    selected_record: MemoryContextRecord | None,
    records: tuple[MemoryContextRecord, ...],
    watch_metrics: Any | None,
    events: tuple[OperationsObservedEvent, ...],
) -> str:
    if not service_available:
        return "error"
    if selected_record is None or not record_resolved(selected_record):
        return "warning"
    if any(item.error for item in records):
        return "warning"
    if watch_failures(watch_metrics) > 0:
        return "warning"
    if any(event.level == "error" or event.status in {"failed", "error"} for event in events):
        return "warning"
    return "healthy"
