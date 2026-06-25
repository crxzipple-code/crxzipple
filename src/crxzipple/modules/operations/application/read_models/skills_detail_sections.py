from __future__ import annotations

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
    format_bytes,
    items,
    skill_id,
    skill_name,
    source,
    status_label,
    text,
)
from crxzipple.modules.operations.application.read_models.skills_events import (
    event_details,
    event_tone,
    short_event_name,
)
from crxzipple.modules.operations.application.read_models.skills_models import (
    SkillRecord,
)
from crxzipple.shared.time import coerce_utc_datetime, format_datetime_utc


def detail_requirements_table(record: SkillRecord) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    requirements = getattr(record.package, "requirements", None)
    for field, label in (
        ("required_tools", "Required Tool"),
        ("suggested_tools", "Suggested Tool"),
        ("optional_tools", "Optional Tool"),
        ("required_effects", "Required Effect"),
        ("required_access", "Access"),
        ("supported_platforms", "Supported Platform"),
        ("setup_hints", "Setup Hint"),
    ):
        for value in items(getattr(requirements, field, ())):
            missing_values = (
                *record.missing_tools,
                *record.missing_access,
                *record.missing_effects,
                *record.unsupported_surfaces,
                *record.unsupported_platforms,
            )
            if field == "supported_platforms" and record.unsupported_platforms:
                status = "Unsupported"
            elif value in missing_values:
                status = "Setup Needed"
            else:
                status = "Declared"
            rows.append(
                OperationsTableRowModel(
                    id=f"detail-requirement:{field}:{value}",
                    cells={
                        "type": label,
                        "value": value,
                        "status": status,
                    },
                    status=status,
                    tone="warning" if status != "Declared" else "neutral",
                )
            )
    return OperationsTableSectionModel(
        id="skill_requirements",
        title="Skill Requirements",
        columns=(
            OperationsTableColumnModel("type", "Type"),
            OperationsTableColumnModel("value", "Value"),
            OperationsTableColumnModel("status", "Status"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No requirements declared.",
    )


def resources_table(package: Any) -> OperationsTableSectionModel:
    rows = [
        OperationsTableRowModel(
            id=f"resource:{skill_id(package)}:{text(getattr(resource, 'path', ''))}",
            cells={
                "path": text(getattr(resource, "path", "")),
                "kind": text(getattr(resource, "kind", "")),
                "size": format_bytes(int(getattr(resource, "size_bytes", 0) or 0)),
            },
            status="Available",
            tone="success",
        )
        for resource in tuple(getattr(package, "resources", ()) or ())
    ]
    return OperationsTableSectionModel(
        id="skill_resources",
        title="Skill Resources",
        columns=(
            OperationsTableColumnModel("path", "Path"),
            OperationsTableColumnModel("kind", "Kind"),
            OperationsTableColumnModel("size", "Size"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No resources bundled with this skill.",
    )


def events_for_skill_table(
    events: tuple[OperationsObservedEvent, ...],
    skill_name_value: str,
) -> OperationsTableSectionModel:
    filtered = tuple(
        event
        for event in events
        if event.entity_id == skill_name_value
        or text(event.payload.get("skill"), "") == skill_name_value
        or text(event.payload.get("skill_name"), "") == skill_name_value
    )
    rows = [
        OperationsTableRowModel(
            id=text(event.cursor or event.id, ""),
            cells={
                "time": format_datetime_utc(coerce_utc_datetime(event.occurred_at)),
                "event": short_event_name(event.event_name),
                "status": status_label(event.status),
                "details": event_details(event.payload),
            },
            status=event.status,
            tone=event_tone(event),
        )
        for event in filtered[:30]
    ]
    return OperationsTableSectionModel(
        id="skill_events",
        title="Skill Events",
        columns=(
            OperationsTableColumnModel("time", "Time"),
            OperationsTableColumnModel("event", "Event"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("details", "Details"),
        ),
        rows=tuple(rows),
        total=len(filtered),
        empty_state="No related skill events.",
    )


def skill_payload(package: Any) -> dict[str, Any]:
    requirements = getattr(package, "requirements", None)
    manifest = getattr(package, "manifest", None)
    return {
        "name": skill_name(package),
        "description": text(getattr(package, "description", "")),
        "version": text(getattr(package, "version", None), "1"),
        "source": source(package),
        "root_path": text(getattr(package, "root_path", "")),
        "manifest_path": text(getattr(package, "manifest_path", "")),
        "instructions_path": text(getattr(package, "instructions_path", "")),
        "tags": list(items(getattr(package, "tags", ()))),
        "requirements": {
            "required_tools": list(items(getattr(requirements, "required_tools", ()))),
            "optional_tools": list(items(getattr(requirements, "optional_tools", ()))),
            "suggested_tools": list(items(getattr(requirements, "suggested_tools", ()))),
            "required_effects": list(items(getattr(requirements, "required_effects", ()))),
            "surfaces": list(items(getattr(requirements, "surfaces", ()))),
            "required_access": list(items(getattr(requirements, "required_access", ()))),
            "supported_platforms": list(
                items(getattr(requirements, "supported_platforms", ()))
            ),
            "setup_hints": list(items(getattr(requirements, "setup_hints", ()))),
        },
        "manifest": {
            "api_version": text(getattr(manifest, "api_version", "")),
            "kind": text(getattr(manifest, "kind", "")),
            "when_to_use": text(getattr(manifest, "when_to_use", "")),
            "anti_patterns": list(items(getattr(manifest, "anti_patterns", ()))),
            "surfaces": list(items(getattr(manifest, "surfaces", ()))),
            "supported_platforms": list(items(getattr(manifest, "supported_platforms", ()))),
        },
    }
