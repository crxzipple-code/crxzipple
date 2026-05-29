from __future__ import annotations

from collections.abc import Callable
from typing import Any

from crxzipple.shared.domain.events import Event

SKILL_RESOLUTION_COMPLETED_EVENT = "skills.resolution.completed"
SKILL_READ_SUCCEEDED_EVENT = "skills.read.succeeded"
SKILL_READ_FAILED_EVENT = "skills.read.failed"
SKILL_READINESS_CHANGED_EVENT = "skills.readiness.changed"
SKILL_VALIDATE_SUCCEEDED_EVENT = "skills.package.validate_succeeded"
SKILL_VALIDATE_FAILED_EVENT = "skills.package.validate_failed"
SKILL_INSTALL_SUCCEEDED_EVENT = "skills.package.install_succeeded"
SKILL_INSTALL_FAILED_EVENT = "skills.package.install_failed"
SKILL_CREATE_SUCCEEDED_EVENT = "skills.package.created"
SKILL_UPDATE_SUCCEEDED_EVENT = "skills.package.updated"
SKILL_DELETE_SUCCEEDED_EVENT = "skills.package.deleted"
SKILL_ENABLE_SUCCEEDED_EVENT = "skills.package.enabled"
SKILL_DISABLE_SUCCEEDED_EVENT = "skills.package.disabled"
SKILL_SOURCE_CREATED_EVENT = "skills.source.created"
SKILL_SOURCE_UPDATED_EVENT = "skills.source.updated"
SKILL_SOURCE_DELETED_EVENT = "skills.source.deleted"
SKILL_SOURCE_SYNCED_EVENT = "skills.source.synced"
SKILL_DRAFT_CREATED_EVENT = "skills.authoring.draft.created"
SKILL_DRAFT_UPDATED_EVENT = "skills.authoring.draft.updated"
SKILL_DRAFT_VALIDATED_EVENT = "skills.authoring.draft.validated"
SKILL_DRAFT_DIFF_BUILT_EVENT = "skills.authoring.draft.diff_built"
SKILL_DRAFT_APPLY_FAILED_EVENT = "skills.authoring.draft.apply_failed"
SKILL_DRAFT_APPLIED_EVENT = "skills.authoring.draft.applied"
SKILL_DRAFT_REJECTED_EVENT = "skills.authoring.draft.rejected"
SKILL_DRAFT_DELETED_EVENT = "skills.authoring.draft.deleted"

SKILL_OPERATION_EVENT_NAMES: tuple[str, ...] = (
    SKILL_RESOLUTION_COMPLETED_EVENT,
    SKILL_READINESS_CHANGED_EVENT,
    SKILL_READ_SUCCEEDED_EVENT,
    SKILL_READ_FAILED_EVENT,
    SKILL_VALIDATE_SUCCEEDED_EVENT,
    SKILL_VALIDATE_FAILED_EVENT,
    SKILL_INSTALL_SUCCEEDED_EVENT,
    SKILL_INSTALL_FAILED_EVENT,
    SKILL_CREATE_SUCCEEDED_EVENT,
    SKILL_UPDATE_SUCCEEDED_EVENT,
    SKILL_DELETE_SUCCEEDED_EVENT,
    SKILL_ENABLE_SUCCEEDED_EVENT,
    SKILL_DISABLE_SUCCEEDED_EVENT,
    SKILL_SOURCE_CREATED_EVENT,
    SKILL_SOURCE_UPDATED_EVENT,
    SKILL_SOURCE_DELETED_EVENT,
    SKILL_SOURCE_SYNCED_EVENT,
    SKILL_DRAFT_CREATED_EVENT,
    SKILL_DRAFT_UPDATED_EVENT,
    SKILL_DRAFT_VALIDATED_EVENT,
    SKILL_DRAFT_DIFF_BUILT_EVENT,
    SKILL_DRAFT_APPLY_FAILED_EVENT,
    SKILL_DRAFT_APPLIED_EVENT,
    SKILL_DRAFT_REJECTED_EVENT,
    SKILL_DRAFT_DELETED_EVENT,
)

SkillEventEmitter = Callable[[str, dict[str, Any]], None]


def emit_skill_event(
    emitter: SkillEventEmitter | None,
    event_name: str,
    *,
    payload: dict[str, Any] | None = None,
    status: str = "observed",
    level: str = "info",
) -> None:
    if emitter is None:
        return
    body = {
        "event_name": event_name,
        "status": status,
        "level": level,
        **(payload or {}),
    }
    try:
        emitter(event_name, body)
    except Exception:
        return


def skill_event_from_payload(event_name: str, payload: dict[str, Any]) -> Event:
    trace: dict[str, Any] = {}
    for key in ("trace_id", "correlation_id", "source_event_id"):
        value = _text(payload.get(key))
        if value:
            trace[key] = value
    return Event(
        name=event_name,
        kind="observe",
        payload={
            "event_name": event_name,
            **payload,
        },
        ordering_key=(
            _text(payload.get("run_id"))
            or _text(payload.get("skill"))
            or _text(payload.get("skill_name"))
            or _text(payload.get("surface"))
            or _text(payload.get("workspace_dir"))
        ),
        trace=trace,
    )


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None
