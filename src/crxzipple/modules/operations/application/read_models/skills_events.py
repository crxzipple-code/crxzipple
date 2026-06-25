from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.skills_common import (
    int_value,
    items,
    normalized_filter,
    short,
    status_label,
    text,
)
from crxzipple.modules.skills.application.events import (
    SKILL_DRAFT_APPLIED_EVENT,
    SKILL_DRAFT_APPLY_FAILED_EVENT,
    SKILL_DRAFT_DELETED_EVENT,
    SKILL_DRAFT_REJECTED_EVENT,
    SKILL_READ_FAILED_EVENT,
)

_AUTHORING_EVENT_PREFIX = "skills.authoring.draft."
_AUTHORING_TERMINAL_EVENTS = {
    SKILL_DRAFT_APPLIED_EVENT,
    SKILL_DRAFT_REJECTED_EVENT,
    SKILL_DRAFT_DELETED_EVENT,
}
_AUTHORING_TERMINAL_STATUSES = {"applied", "rejected", "expired"}


def is_authoring_event(event: OperationsObservedEvent) -> bool:
    return event.event_name.startswith(_AUTHORING_EVENT_PREFIX)


def authoring_draft_id(event: OperationsObservedEvent) -> str:
    return text(event.payload.get("draft_id") or event.entity_id or event.cursor or event.id)


def authoring_skill_name(event: OperationsObservedEvent) -> str:
    return text(
        event.payload.get("skill")
        or event.payload.get("skill_name")
        or event.entity_id,
        "-",
    )


def authoring_status_label(event: OperationsObservedEvent) -> str:
    return status_label(event.payload.get("draft_status") or event.status)


def authoring_readiness_label(event: OperationsObservedEvent) -> str:
    value = event.payload.get("readiness_status")
    if value is None:
        return "-"
    return status_label(value)


def is_authoring_terminal_event(event: OperationsObservedEvent) -> bool:
    if event.event_name in _AUTHORING_TERMINAL_EVENTS:
        return True
    status = normalized_filter(event.payload.get("draft_status") or event.status)
    return status in _AUTHORING_TERMINAL_STATUSES


def is_authoring_failure_event(event: OperationsObservedEvent) -> bool:
    if event.event_name == SKILL_DRAFT_APPLY_FAILED_EVENT:
        return True
    if event.level == "error" or event.status in {"failed", "error"}:
        return True
    return int_value(event.payload.get("validation_error_count")) > 0


def authoring_tone(event: OperationsObservedEvent) -> str:
    if is_authoring_failure_event(event):
        return "danger"
    status = normalized_filter(event.payload.get("draft_status") or event.status)
    if status in {"invalid", "failed", "error"}:
        return "danger"
    readiness = normalized_filter(event.payload.get("readiness_status"))
    if readiness not in {"all", "ready", "valid", "ok", "success", "succeeded"}:
        return "warning"
    if status in {"validated", "applied"}:
        return "success"
    return "neutral"


def authoring_next_step(event: OperationsObservedEvent) -> str:
    if event.event_name == SKILL_DRAFT_APPLY_FAILED_EVENT:
        return "Review failure and revise draft"
    if int_value(event.payload.get("validation_error_count")) > 0:
        return "Fix validation errors"
    status = normalized_filter(event.payload.get("draft_status") or event.status)
    if status == "draft":
        return "Validate draft"
    if status == "invalid":
        return "Revise draft"
    if event.event_name.endswith(".diff_built"):
        return "Apply owner write after approval"
    if status == "validated":
        return "Build diff or apply owner write"
    return "Inspect draft"


def authoring_validation_summary(event: OperationsObservedEvent) -> str:
    errors = int_value(event.payload.get("validation_error_count"))
    warnings = int_value(event.payload.get("validation_warning_count"))
    if errors or warnings:
        return f"{errors} errors / {warnings} warnings"
    readiness = authoring_readiness_label(event)
    return readiness if readiness != "-" else "-"


def authoring_error_details(event: OperationsObservedEvent) -> str:
    validation_errors = items(event.payload.get("validation_errors"))
    if validation_errors:
        return short("; ".join(validation_errors), 140)
    for key in ("error_message", "reason", "message"):
        value = event.payload.get(key)
        if value is not None and text(value, ""):
            return short(value, 140)
    return event_details(event.payload)


def event_details(payload: dict[str, Any]) -> str:
    missing = (
        items(payload.get("missing_tools"))
        + items(payload.get("missing_access"))
        + items(payload.get("missing_effects"))
        + items(payload.get("unsupported_platforms"))
    )
    if missing:
        return short(", ".join(missing), 120)
    for key in ("reason", "message", "summary", "error_message", "skill", "skill_name", "status"):
        value = payload.get(key)
        if value is not None and text(value, ""):
            return short(value, 120)
    return "-"


def read_event_details(event: OperationsObservedEvent) -> str:
    payload = event.payload
    if event.event_name == SKILL_READ_FAILED_EVENT:
        return short(
            payload.get("error_message") or payload.get("reason") or payload.get("message") or "-",
            120,
        )
    return short(payload.get("source") or payload.get("resolved_path") or "read completed", 120)


def short_event_name(event_name: str) -> str:
    return event_name.removeprefix("skills.").removeprefix("skill.")


def event_tone(event: OperationsObservedEvent) -> str:
    if event.level == "error" or event.status in {"failed", "error"}:
        return "danger"
    if event.level == "warning":
        return "warning"
    return "success" if event.status in {"ready", "success", "observed"} else "neutral"
