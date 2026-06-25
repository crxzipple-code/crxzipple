from __future__ import annotations

from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.skills_common import (
    short,
    status_label,
    text,
)
from crxzipple.modules.operations.application.read_models.skills_events import (
    authoring_draft_id,
    authoring_error_details,
    authoring_next_step,
    authoring_readiness_label,
    authoring_skill_name,
    authoring_status_label,
    authoring_tone,
    authoring_validation_summary,
    is_authoring_event,
    is_authoring_failure_event,
    is_authoring_terminal_event,
    short_event_name,
)
from crxzipple.shared.time import coerce_utc_datetime, format_datetime_utc


def authoring_backlog_table(
    events: tuple[OperationsObservedEvent, ...],
) -> OperationsTableSectionModel:
    latest_by_draft: dict[str, OperationsObservedEvent] = {}
    for event in sorted(
        (event for event in events if is_authoring_event(event)),
        key=lambda item: coerce_utc_datetime(item.occurred_at),
        reverse=True,
    ):
        draft_id = authoring_draft_id(event)
        if not draft_id or draft_id in latest_by_draft:
            continue
        latest_by_draft[draft_id] = event

    active_events = tuple(
        event
        for event in latest_by_draft.values()
        if not is_authoring_terminal_event(event)
    )
    rows = [
        OperationsTableRowModel(
            id=f"authoring:{authoring_draft_id(event)}",
            cells={
                "updated": format_datetime_utc(coerce_utc_datetime(event.occurred_at)),
                "draft": short(authoring_draft_id(event), 44),
                "skill": authoring_skill_name(event),
                "intent": status_label(event.payload.get("intent")),
                "status": authoring_status_label(event),
                "readiness": authoring_readiness_label(event),
                "actor": text(event.payload.get("actor"), "-"),
                "next_step": authoring_next_step(event),
            },
            status=authoring_status_label(event),
            tone=authoring_tone(event),
        )
        for event in sorted(
            active_events,
            key=lambda item: coerce_utc_datetime(item.occurred_at),
            reverse=True,
        )[:80]
    ]
    return OperationsTableSectionModel(
        id="authoring_backlog",
        title="Authoring Backlog",
        columns=(
            OperationsTableColumnModel("updated", "Updated"),
            OperationsTableColumnModel("draft", "Draft"),
            OperationsTableColumnModel("skill", "Skill"),
            OperationsTableColumnModel("intent", "Intent"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("readiness", "Readiness"),
            OperationsTableColumnModel("actor", "Actor"),
            OperationsTableColumnModel("next_step", "Next Step"),
        ),
        rows=tuple(rows),
        total=len(active_events),
        empty_state="No active skill authoring drafts.",
    )


def authoring_failures_table(
    events: tuple[OperationsObservedEvent, ...],
) -> OperationsTableSectionModel:
    failure_events = tuple(
        event
        for event in events
        if is_authoring_event(event) and is_authoring_failure_event(event)
    )
    rows = [
        OperationsTableRowModel(
            id=f"authoring-failure:{authoring_draft_id(event)}:{event.cursor or event.id}",
            cells={
                "time": format_datetime_utc(coerce_utc_datetime(event.occurred_at)),
                "draft": short(authoring_draft_id(event), 44),
                "skill": authoring_skill_name(event),
                "event": short_event_name(event.event_name),
                "status": authoring_status_label(event),
                "validation": authoring_validation_summary(event),
                "error": authoring_error_details(event),
                "actor": text(event.payload.get("actor"), "-"),
            },
            status=authoring_status_label(event),
            tone="danger",
        )
        for event in failure_events[:80]
    ]
    return OperationsTableSectionModel(
        id="authoring_failures",
        title="Authoring Failures",
        columns=(
            OperationsTableColumnModel("time", "Time"),
            OperationsTableColumnModel("draft", "Draft"),
            OperationsTableColumnModel("skill", "Skill"),
            OperationsTableColumnModel("event", "Event"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("validation", "Validation"),
            OperationsTableColumnModel("error", "Error"),
            OperationsTableColumnModel("actor", "Actor"),
        ),
        rows=tuple(rows),
        total=len(failure_events),
        empty_state="No skill authoring failures.",
    )
