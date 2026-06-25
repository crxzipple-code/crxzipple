from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.daemon_common import (
    _short,
    _text,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsKeyValueItemModel,
    OperationsKeyValueSectionModel,
)


def metadata_section(raw_metadata: Any) -> OperationsKeyValueSectionModel:
    metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
    items = [
        OperationsKeyValueItemModel(_text(key, ""), _short(value, 120))
        for key, value in sorted(metadata.items())
        if not str(key).startswith("_")
    ]
    if not items:
        items = [OperationsKeyValueItemModel("Metadata", "-")]
    return OperationsKeyValueSectionModel(
        id="metadata",
        title="Metadata",
        items=tuple(items[:16]),
    )


def matching_events(
    events: tuple[OperationsObservedEvent, ...],
    *,
    service_key: str,
    entity_id: str,
) -> tuple[OperationsObservedEvent, ...]:
    matches: list[OperationsObservedEvent] = []
    for event in events:
        payload = dict(event.payload)
        candidates = {
            event.entity_id,
            _text(payload.get("process_id"), ""),
            _text(payload.get("service_key"), ""),
            _text(payload.get("daemon_service_key"), ""),
            _text(payload.get("instance_id"), ""),
            _text(payload.get("lease_id"), ""),
            _text(payload.get("worker_id"), ""),
            _text(payload.get("daemon_worker_id"), ""),
        }
        if service_key in candidates or entity_id in candidates:
            matches.append(event)
    return tuple(matches)
