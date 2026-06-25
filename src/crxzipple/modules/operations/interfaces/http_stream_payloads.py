from __future__ import annotations

import json
from typing import Any

from crxzipple.modules.events import EventTopicRecord
from crxzipple.modules.operations.application.read_models.projection_payloads import (
    PROJECTED_MODULES,
)
from crxzipple.shared.time import format_datetime_utc

_PROJECTED_MODULES = PROJECTED_MODULES


def operations_stream_record_payload(record: EventTopicRecord) -> dict[str, Any]:
    payload = dict(record.envelope.payload)
    modules = operations_stream_modules(payload)
    return {
        "event_type": "projection_updated",
        "event_id": record.envelope.id,
        "module": modules[0] if len(modules) == 1 else None,
        "modules": modules,
        "kinds": operations_stream_kinds(payload),
        "query_key": str(payload.get("query_key") or "default"),
        "updated_at": str(
            payload.get("updated_at")
            or format_datetime_utc(record.envelope.occurred_at),
        ),
    }


def operations_stream_modules(payload: dict[str, Any]) -> list[str]:
    candidates = [
        payload.get("module"),
        payload.get("module_id"),
        *(payload.get("modules") if isinstance(payload.get("modules"), list) else []),
    ]
    modules = []
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        module = candidate.strip().lower()
        if module in _PROJECTED_MODULES and module not in modules:
            modules.append(module)
    return modules


def operations_stream_kinds(payload: dict[str, Any]) -> list[str]:
    raw_kinds = payload.get("kinds")
    if not isinstance(raw_kinds, list):
        raw_kinds = [payload.get("kind")]
    return [
        kind
        for item in raw_kinds
        if isinstance(item, str) and (kind := item.strip().lower())
    ]


def format_operations_sse_event(event_name: str, payload: dict[str, Any]) -> str:
    return f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
