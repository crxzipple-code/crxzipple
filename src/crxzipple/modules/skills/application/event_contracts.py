from __future__ import annotations

from crxzipple.modules.skills.application.events import SKILL_OPERATION_EVENT_NAMES
from crxzipple.shared import EventDefinition, EventDefinitionField, EventSurface


def skill_event_definitions() -> tuple[EventDefinition, ...]:
    common_fields = (
        EventDefinitionField("event_name", "Published skill operation event name.", "string", True),
        EventDefinitionField("status", "Operation status or resolver outcome.", "string", True),
        EventDefinitionField("level", "Operational severity level.", "string"),
        EventDefinitionField("skill", "Skill package name related to the event.", "string"),
        EventDefinitionField("skill_name", "Skill package name related to the event.", "string"),
        EventDefinitionField("surface", "Run or UI surface used for skill discovery.", "string"),
        EventDefinitionField("workspace_dir", "Workspace directory used for workspace skill discovery.", "string"),
        EventDefinitionField("source", "Skill package source such as system, global, workspace, or validation.", "string"),
        EventDefinitionField("path", "Skill file, package, or requested resource path.", "string"),
        EventDefinitionField("source_dir", "Skill package source directory for installs.", "string"),
        EventDefinitionField("scope", "Install scope for skill installation operations.", "string"),
        EventDefinitionField("ready_count", "Number of skills ready after resolution.", "number"),
        EventDefinitionField("setup_needed_count", "Number of skills needing setup after resolution.", "number"),
        EventDefinitionField("total_count", "Total number of considered skills.", "number"),
        EventDefinitionField("missing_tools", "Missing required tools observed during resolution.", "array"),
        EventDefinitionField("duration_ms", "Wall-clock operation duration in milliseconds.", "number"),
        EventDefinitionField("error_message", "Failure message for failed skill operations.", "string"),
    )
    return tuple(
        EventDefinition(
            definition_id=event_name,
            owner="skills",
            event_name=event_name,
            description="Skill runtime and catalog operation fact observed for operations observation.",
            producers=("SkillManager", "PromptAssembler"),
            consumers=("OperationsEventObserver", "SkillsOperationsReadModelProvider"),
            fields=common_fields,
            durability="persistent",
            publication_mode="direct",
        )
        for event_name in SKILL_OPERATION_EVENT_NAMES
    )


def skill_event_surfaces() -> tuple[EventSurface, ...]:
    return (
        EventSurface(
            surface_id="skills.operations",
            owner="skills",
            description="Skill catalog, resolver, validation, read, and install facts consumed by operations.",
            definition_ids=SKILL_OPERATION_EVENT_NAMES,
            topics=tuple(f"events.named.{event_name}" for event_name in SKILL_OPERATION_EVENT_NAMES),
            consumers=("operations.observer", "operations.skills"),
        ),
    )
