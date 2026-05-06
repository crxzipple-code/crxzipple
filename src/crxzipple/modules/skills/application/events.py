from __future__ import annotations

from collections.abc import Callable
from typing import Any

from crxzipple.shared.domain.events import Event

SKILL_RESOLUTION_COMPLETED_EVENT = "skills.resolution.completed"
SKILL_READ_SUCCEEDED_EVENT = "skills.read.succeeded"
SKILL_READ_FAILED_EVENT = "skills.read.failed"
SKILL_VALIDATE_SUCCEEDED_EVENT = "skills.package.validate_succeeded"
SKILL_VALIDATE_FAILED_EVENT = "skills.package.validate_failed"
SKILL_INSTALL_SUCCEEDED_EVENT = "skills.package.install_succeeded"
SKILL_INSTALL_FAILED_EVENT = "skills.package.install_failed"

SKILL_OPERATION_EVENT_NAMES: tuple[str, ...] = (
    SKILL_RESOLUTION_COMPLETED_EVENT,
    SKILL_READ_SUCCEEDED_EVENT,
    SKILL_READ_FAILED_EVENT,
    SKILL_VALIDATE_SUCCEEDED_EVENT,
    SKILL_VALIDATE_FAILED_EVENT,
    SKILL_INSTALL_SUCCEEDED_EVENT,
    SKILL_INSTALL_FAILED_EVENT,
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
