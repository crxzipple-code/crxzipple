from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.browser_values import (
    bytes_label,
    dict_value,
    join,
    short_generation,
    text,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableRowModel,
)
from crxzipple.shared.time import format_datetime_utc


NETWORK_EVENT_NAMES = frozenset(
    {
        "browser.network.capture.started",
        "browser.network.capture.stopped",
        "browser.network.request.observed",
        "browser.network.request.failed",
        "browser.network.fetch.executed",
        "browser.network.fetch.failed",
        "browser.network.replay.executed",
        "browser.network.replay.failed",
    },
)
DIAGNOSTIC_EVENT_NAMES = frozenset(
    {
        "browser.diagnostics.collected",
        "browser.trace.started",
        "browser.trace.exported",
        "browser.environment.changed",
    },
)


def recent_browser_events(
    operations_observation: Any | None,
    *,
    limit: int = 80,
) -> tuple[OperationsObservedEvent, ...]:
    get_module_observation = getattr(
        operations_observation,
        "get_module_observation",
        None,
    )
    if not callable(get_module_observation):
        return ()
    try:
        observation = get_module_observation("browser")
    except Exception:
        return ()
    if observation is None:
        return ()
    recent_events = getattr(observation, "recent_events", ())
    return tuple(
        event
        for event in tuple(recent_events)[: max(int(limit), 1)]
        if isinstance(event, OperationsObservedEvent)
    )


def network_activity_rows(
    events: tuple[OperationsObservedEvent, ...],
) -> tuple[OperationsTableRowModel, ...]:
    rows: list[OperationsTableRowModel] = []
    for event in events:
        if event.event_name not in NETWORK_EVENT_NAMES:
            continue
        payload = dict_value(event.payload)
        status = text(payload.get("status") or event.status, event.status)
        rows.append(
            OperationsTableRowModel(
                id=f"browser-network:{event.id}:{event.cursor}",
                status=status,
                tone=event_tone(event),
                cells={
                    "time": format_datetime_utc(event.occurred_at),
                    "event": browser_event_label(event.event_name),
                    "status": status,
                    "profile": text(payload.get("profile_name")),
                    "target_id": short_generation(payload.get("target_id")),
                    "capture": short_generation(payload.get("capture_id")),
                    "request": short_generation(payload.get("request_id")),
                    "method": text(payload.get("method")),
                    "http_status": text(payload.get("status_code")),
                    "resource": text(payload.get("resource_type")),
                    "url": text(payload.get("url") or payload.get("page_url")),
                    "summary": event_summary(event),
                },
            ),
        )
    return tuple(rows)


def diagnostic_rows(
    events: tuple[OperationsObservedEvent, ...],
) -> tuple[OperationsTableRowModel, ...]:
    rows: list[OperationsTableRowModel] = []
    for event in events:
        if event.event_name not in DIAGNOSTIC_EVENT_NAMES:
            continue
        payload = dict_value(event.payload)
        status = text(payload.get("status") or event.status, event.status)
        rows.append(
            OperationsTableRowModel(
                id=f"browser-diagnostic:{event.id}:{event.cursor}",
                status=status,
                tone=event_tone(event),
                cells={
                    "time": format_datetime_utc(event.occurred_at),
                    "event": browser_event_label(event.event_name),
                    "kind": text(
                        payload.get("diagnostic_kind")
                        or payload.get("environment_action"),
                    ),
                    "status": status,
                    "profile": text(payload.get("profile_name")),
                    "target_id": short_generation(payload.get("target_id")),
                    "issues": text(payload.get("issue_count")),
                    "console": text(payload.get("console_count")),
                    "errors": text(payload.get("error_count")),
                    "ready_state": text(payload.get("ready_state")),
                    "trace": short_generation(payload.get("trace_id")),
                    "trace_size": bytes_label(payload.get("trace_size_bytes")),
                    "changed": join(payload.get("changed_controls")),
                    "summary": event_summary(event),
                },
            ),
        )
    return tuple(rows)


def event_tone(event: OperationsObservedEvent) -> str:
    status = text(event.status, "").lower()
    level = text(event.level, "").lower()
    if level == "error" or status in {"failed", "error"} or event.event_name.endswith(".failed"):
        return "danger"
    if level == "warning" or status in {"warning", "degraded", "setup_needed"}:
        return "warning"
    if status in {"healthy", "ready", "started", "stopped", "exported", "observed", "executed"}:
        return "success"
    return "neutral"


def browser_event_label(event_name: str) -> str:
    value = event_name.removeprefix("browser.")
    return value.replace(".", " ")


def event_summary(event: OperationsObservedEvent) -> str:
    payload = dict_value(event.payload)
    for key in (
        "display_summary",
        "summary",
        "error_message",
        "failure_text",
        "release_reason",
    ):
        value = text(payload.get(key))
        if value != "-":
            return value
    return browser_event_label(event.event_name)
