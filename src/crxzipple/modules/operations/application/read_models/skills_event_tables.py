from __future__ import annotations

from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.skills_common import (
    duration_label,
    short,
    status_label,
    text,
)
from crxzipple.modules.operations.application.read_models.skills_events import (
    event_details,
    event_tone,
    read_event_details,
    short_event_name,
)
from crxzipple.modules.skills.application.events import (
    SKILL_READ_FAILED_EVENT,
    SKILL_READ_SUCCEEDED_EVENT,
)
from crxzipple.shared.time import coerce_utc_datetime, format_datetime_utc


def resolution_logs_table(
    events: tuple[OperationsObservedEvent, ...],
) -> OperationsTableSectionModel:
    rows = [
        OperationsTableRowModel(
            id=text(event.cursor or event.id, ""),
            cells={
                "time": format_datetime_utc(coerce_utc_datetime(event.occurred_at)),
                "event": short_event_name(event.event_name),
                "skill": text(event.payload.get("skill") or event.payload.get("skill_name") or event.entity_id),
                "surface": text(event.payload.get("surface"), "-"),
                "result": status_label(event.status),
                "reason": event_details(event.payload),
                "trace": text(event.trace_id),
            },
            status=event.status,
            tone=event_tone(event),
        )
        for event in events[:120]
    ]
    return OperationsTableSectionModel(
        id="resolution_logs",
        title="Resolution Logs",
        columns=(
            OperationsTableColumnModel("time", "Time"),
            OperationsTableColumnModel("event", "Event"),
            OperationsTableColumnModel("skill", "Skill"),
            OperationsTableColumnModel("surface", "Surface"),
            OperationsTableColumnModel("result", "Result"),
            OperationsTableColumnModel("reason", "Reason"),
            OperationsTableColumnModel("trace", "Trace"),
        ),
        rows=tuple(rows),
        total=len(events),
        empty_state="No skill resolution events.",
    )


def skill_reads_table(
    events: tuple[OperationsObservedEvent, ...],
) -> OperationsTableSectionModel:
    read_events = tuple(
        event
        for event in events
        if event.event_name in {SKILL_READ_SUCCEEDED_EVENT, SKILL_READ_FAILED_EVENT}
    )
    rows = [
        OperationsTableRowModel(
            id=text(event.cursor or event.id, ""),
            cells={
                "time": format_datetime_utc(coerce_utc_datetime(event.occurred_at)),
                "skill": text(
                    event.payload.get("skill")
                    or event.payload.get("skill_name")
                    or event.entity_id,
                ),
                "path": short(
                    event.payload.get("resolved_path")
                    or event.payload.get("path")
                    or "SKILL.md",
                    72,
                ),
                "surface": text(event.payload.get("surface"), "-"),
                "result": status_label(event.status),
                "duration": duration_label(event.payload.get("duration_ms")),
                "reason": read_event_details(event),
            },
            status=event.status,
            tone=event_tone(event),
        )
        for event in read_events[:80]
    ]
    return OperationsTableSectionModel(
        id="skill_reads",
        title="Skill Reads",
        columns=(
            OperationsTableColumnModel("time", "Time"),
            OperationsTableColumnModel("skill", "Skill"),
            OperationsTableColumnModel("path", "Path"),
            OperationsTableColumnModel("surface", "Surface"),
            OperationsTableColumnModel("result", "Result"),
            OperationsTableColumnModel("duration", "Duration"),
            OperationsTableColumnModel("reason", "Reason"),
        ),
        rows=tuple(rows),
        total=len(read_events),
        empty_state="No skill read events.",
    )
