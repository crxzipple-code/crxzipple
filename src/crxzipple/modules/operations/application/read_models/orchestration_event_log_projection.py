from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.presenters import (
    display_value,
    truncate_text,
)
from crxzipple.modules.operations.application.read_models.orchestration_event_log_labels import (
    event_display_label,
)
from crxzipple.modules.operations.application.read_models.routes import (
    workbench_trace_route,
)


def event_payload(event: Any) -> dict[str, object]:
    payload = getattr(event, "payload", None)
    return dict(payload) if isinstance(payload, dict) else {}


def event_name(event: Any, payload: dict[str, object]) -> str:
    event_name = getattr(event, "event_name", None)
    if isinstance(event_name, str) and event_name.strip():
        return event_name.strip()
    raw_name = getattr(event, "name", None)
    if isinstance(raw_name, str) and raw_name.strip():
        return raw_name.strip()
    payload_name = payload.get("event_name")
    if isinstance(payload_name, str) and payload_name.strip():
        return payload_name.strip()
    topic = getattr(event, "topic", None)
    return topic if isinstance(topic, str) and topic.strip() else "event"


def event_entity_id(
    payload: dict[str, object],
    *,
    fallback: str,
) -> str:
    for key in (
        "run_id",
        "request_id",
        "worker_id",
        "tool_run_id",
        "source_event_id",
    ):
        value = optional_str(payload.get(key))
        if value:
            return value
    return fallback


def event_trace_id(
    event: Any,
    payload: dict[str, object],
    *,
    fallback: str | None,
) -> str | None:
    for key in ("trace_id", "correlation_id", "source_event_id"):
        value = optional_str(payload.get(key))
        if value:
            return value
    trace = getattr(event, "trace", None)
    if isinstance(trace, dict):
        for key in ("trace_id", "correlation_id"):
            value = optional_str(trace.get(key))
            if value:
                return value
    return fallback


def event_source(event_name: str, payload: dict[str, object]) -> str:
    source_event_name = optional_str(payload.get("source_event_name"))
    if source_event_name:
        return event_source(source_event_name, {})
    if ".ingress." in event_name:
        return "Ingress"
    if ".scheduler." in event_name:
        return "Scheduler"
    if ".executor." in event_name:
        return "Executor"
    if ".runtime." in event_name or "runtime_observation" in event_name:
        return "Runtime"
    if ".run." in event_name:
        return "Run"
    return "Orchestration"


def event_summary(event_name: str, payload: dict[str, object]) -> str:
    summary = optional_str(payload.get("display_summary")) or optional_str(
        payload.get("summary"),
    )
    if summary:
        return truncate(summary)
    status = event_status_from_name(event_name, payload)
    entity = event_entity_id(payload, fallback="")
    source = event_source(event_name, payload)
    parts = [event_display_label(event_name, payload)]
    if status:
        parts.append(f"status {status}")
    if entity:
        parts.append(f"entity {entity}")
    if source and source != "Orchestration":
        parts.append(f"via {source}")
    return truncate(" / ".join(parts))


def event_details(payload: dict[str, object]) -> str:
    parts = []
    for key in (
        "code",
        "message",
        "reason",
        "status",
        "worker_id",
        "lane_key",
        "request_id",
        "tool_run_id",
        "source_event_name",
        "event_name",
    ):
        value = optional_str(payload.get(key))
        if value:
            parts.append(f"{key}={value}")
    return truncate("; ".join(parts) if parts else "-")


def event_level_from_name(event_name: str, payload: dict[str, object]) -> str:
    status = event_status_from_name(event_name, payload)
    if status in {"failed", "error"}:
        return "error"
    if status in {"waiting", "cancelled", "offline"}:
        return "warning"
    return "info"


def event_status_from_name(event_name: str, payload: dict[str, object]) -> str:
    status = optional_str(payload.get("status"))
    if status:
        return status
    tail = event_name.rsplit(".", 1)[-1]
    return tail.replace("_", "-")


def event_tone_from_name(event_name: str, payload: dict[str, object]) -> str:
    display_tone = optional_str(payload.get("display_tone")) or optional_str(
        payload.get("tone"),
    )
    if display_tone in {"success", "warning", "danger", "info", "neutral"}:
        return display_tone
    level = event_level_from_name(event_name, payload)
    if level == "error":
        return "danger"
    if level == "warning":
        return "warning"
    status = event_status_from_name(event_name, payload)
    if status in {"completed", "heartbeated", "registered"}:
        return "success"
    return "info"


def trace_route_from_id(trace_id: str | None) -> str:
    return workbench_trace_route(trace_id)


def optional_str(value: object | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def display(value: object | None) -> str:
    return display_value(value)


def truncate(value: str, *, limit: int = 96) -> str:
    return truncate_text(value, limit)
