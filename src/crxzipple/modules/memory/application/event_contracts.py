from __future__ import annotations

from crxzipple.modules.memory.application.events import MEMORY_OPERATION_EVENT_NAMES
from crxzipple.shared import EventDefinition, EventDefinitionField, EventSurface


def memory_event_definitions() -> tuple[EventDefinition, ...]:
    common_fields = (
        EventDefinitionField("event_name", "Published memory operation event name.", "string", True),
        EventDefinitionField("status", "Operation status such as started, succeeded, failed, or resolved.", "string", True),
        EventDefinitionField("level", "Operational severity level.", "string"),
        EventDefinitionField("space_id", "Resolved memory space identifier.", "string"),
        EventDefinitionField("storage_root", "Memory storage root used by the operation.", "string"),
        EventDefinitionField("retrieval_backend", "Retrieval backend selected for this context.", "string"),
        EventDefinitionField("engine_id", "Memory engine identifier.", "string"),
        EventDefinitionField("vector_provider", "Embedding/vector provider used by the engine.", "string"),
        EventDefinitionField("vector_model", "Embedding/vector model used by the engine.", "string"),
        EventDefinitionField("credential_binding_id", "Access credential binding id required by the engine.", "string"),
        EventDefinitionField("readiness_status", "Engine readiness status.", "string"),
        EventDefinitionField("agent_id", "Agent or space reference requested by the caller.", "string"),
        EventDefinitionField("path", "Memory file path related to the operation.", "string"),
        EventDefinitionField("query", "Retrieval query when the event describes search.", "string"),
        EventDefinitionField("duration_ms", "Wall-clock operation duration in milliseconds.", "number"),
        EventDefinitionField("error_message", "Failure message for failed memory operations.", "string"),
    )
    return tuple(
        EventDefinition(
            definition_id=event_name,
            owner="memory",
            event_name=event_name,
            description="Memory runtime operation fact observed for operations observation.",
            producers=("FileBackedMemoryService", "AgentMemoryScopeResolver", "SyncMemoryIndexService", "SearchMemoryIndexService"),
            consumers=("OperationsEventObserver",),
            fields=common_fields,
            durability="persistent",
            publication_mode="direct",
        )
        for event_name in MEMORY_OPERATION_EVENT_NAMES
    )


def memory_event_surfaces() -> tuple[EventSurface, ...]:
    return (
        EventSurface(
            surface_id="memory.operations",
            owner="memory",
            description="Memory runtime facts consumed by the operations observer.",
            definition_ids=MEMORY_OPERATION_EVENT_NAMES,
            topics=tuple(f"events.named.{event_name}" for event_name in MEMORY_OPERATION_EVENT_NAMES),
            consumers=("operations.observer",),
        ),
    )
