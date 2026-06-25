from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.observation_models import (
    OperationsObservedEvent,
)
from crxzipple.modules.operations.application.read_models.llm_resolver_sections import (
    resolver_bucket,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)
from crxzipple.shared.time import format_datetime_utc


def fallback_problems_section(
    resolver_events: tuple[OperationsObservedEvent, ...],
) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    for event in resolver_events:
        bucket = resolver_bucket(event)
        if bucket not in {"fallback_used", "no_match"}:
            continue
        payload = event.payload
        rows.append(
            OperationsTableRowModel(
                id=event.id,
                cells={
                    "time": format_datetime_utc(event.occurred_at),
                    "run_id": event.run_id or _text(payload.get("run_id")) or "-",
                    "requested": _text(payload.get("requested_llm_id")) or "-",
                    "resolved": _text(payload.get("resolved_llm_id")) or "-",
                    "strategy": _text(payload.get("strategy")) or bucket,
                    "reason": _text(payload.get("reason"))
                    or _text(payload.get("error"))
                    or "-",
                    "trace": event.trace_id or "-",
                },
                status=bucket,
                tone="danger" if bucket == "no_match" else "warning",
            ),
        )
    return OperationsTableSectionModel(
        id="fallback_problems",
        title="Fallback / Resolver Problems",
        columns=_columns(
            ("time", "Time"),
            ("run_id", "Run ID"),
            ("requested", "Requested"),
            ("resolved", "Resolved"),
            ("strategy", "Strategy"),
            ("reason", "Reason"),
            ("trace", "Trace"),
        ),
        rows=tuple(rows[:50]),
        total=len(rows),
        empty_state="No resolver fallback problems observed.",
    )


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _columns(*pairs: tuple[str, str]) -> tuple[OperationsTableColumnModel, ...]:
    return tuple(OperationsTableColumnModel(key=key, label=label) for key, label in pairs)
