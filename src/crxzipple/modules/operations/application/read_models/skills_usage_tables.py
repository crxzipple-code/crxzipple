from __future__ import annotations

from collections import defaultdict
from typing import Any

from crxzipple.modules.operations.application.observation_models import (
    OperationsObservedEvent,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.skills_common import (
    dict_items,
    int_value,
    status_label,
    text,
)
from crxzipple.modules.skills.application.events import (
    SKILL_READ_FAILED_EVENT,
    SKILL_READ_SUCCEEDED_EVENT,
    SKILL_RESOLUTION_COMPLETED_EVENT,
)
from crxzipple.shared.time import coerce_utc_datetime, format_datetime_utc


def skill_usage_table(
    events: tuple[OperationsObservedEvent, ...],
) -> OperationsTableSectionModel:
    usage: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "resolved": 0,
            "reads": 0,
            "failures": 0,
            "last_seen": None,
            "last_status": "observed",
            "surfaces": set(),
        },
    )
    for event in sorted(events, key=lambda item: coerce_utc_datetime(item.occurred_at)):
        if event.event_name == SKILL_RESOLUTION_COMPLETED_EVENT:
            _record_resolution_usage(usage, event)
        if event.event_name in {SKILL_READ_SUCCEEDED_EVENT, SKILL_READ_FAILED_EVENT}:
            _record_read_usage(usage, event)

    ranked = sorted(
        usage.items(),
        key=lambda item: (
            int_value(item[1]["resolved"]) + int_value(item[1]["reads"]),
            coerce_utc_datetime(item[1]["last_seen"]),
        ),
        reverse=True,
    )
    rows = tuple(
        _skill_usage_row(skill, values) for skill, values in ranked[:12]
    )
    return OperationsTableSectionModel(
        id="top_used_skills",
        title="Runtime Skill Usage",
        columns=(
            OperationsTableColumnModel("skill", "Skill"),
            OperationsTableColumnModel("resolved", "Resolved"),
            OperationsTableColumnModel("reads", "Reads"),
            OperationsTableColumnModel("failures", "Failures"),
            OperationsTableColumnModel("surface", "Surface"),
            OperationsTableColumnModel("last_seen", "Last Seen"),
            OperationsTableColumnModel("status", "Status"),
        ),
        rows=rows,
        total=len(ranked),
        empty_state="No runtime skill usage events.",
    )


def _record_resolution_usage(
    usage: dict[str, dict[str, Any]],
    event: OperationsObservedEvent,
) -> None:
    for item in dict_items(event.payload.get("skills")):
        skill = text(
            item.get("skill") or item.get("skill_name"),
            "",
        )
        if not skill:
            continue
        entry = usage[skill]
        entry["resolved"] += 1
        entry["last_status"] = text(item.get("status") or event.status, "observed")
        _record_usage_surface(entry, event)
        entry["last_seen"] = event.occurred_at


def _record_read_usage(
    usage: dict[str, dict[str, Any]],
    event: OperationsObservedEvent,
) -> None:
    skill = text(
        event.payload.get("skill")
        or event.payload.get("skill_name")
        or event.entity_id,
        "",
    )
    if not skill:
        return
    entry = usage[skill]
    entry["reads"] += 1
    if event.event_name == SKILL_READ_FAILED_EVENT:
        entry["failures"] += 1
    entry["last_status"] = event.status
    _record_usage_surface(entry, event)
    entry["last_seen"] = event.occurred_at


def _record_usage_surface(
    entry: dict[str, Any],
    event: OperationsObservedEvent,
) -> None:
    surface_value = text(event.payload.get("surface"), "")
    if surface_value:
        entry["surfaces"].add(surface_value)


def _skill_usage_row(
    skill: str,
    values: dict[str, Any],
) -> OperationsTableRowModel:
    return OperationsTableRowModel(
        id=f"skill-usage:{skill}",
        cells={
            "skill": skill,
            "resolved": str(int_value(values["resolved"])),
            "reads": str(int_value(values["reads"])),
            "failures": str(int_value(values["failures"])),
            "surface": ", ".join(sorted(values["surfaces"])) or "-",
            "last_seen": (
                format_datetime_utc(values["last_seen"])
                if values["last_seen"] is not None
                else "-"
            ),
            "status": status_label(values["last_status"]),
        },
        status=status_label(values["last_status"]),
        tone="danger" if int_value(values["failures"]) else "success",
    )
