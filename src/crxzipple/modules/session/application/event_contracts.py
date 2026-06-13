from __future__ import annotations

from crxzipple.shared import EventDefinition, EventDefinitionField, EventSurface
from crxzipple.shared.domain.events import named_event_topic
from crxzipple.shared.orchestration_observation import SESSION_ITEM_APPENDED_SOURCE_EVENT


def session_event_definitions() -> tuple[EventDefinition, ...]:
    return (
        EventDefinition(
            definition_id=SESSION_ITEM_APPENDED_SOURCE_EVENT,
            owner="session",
            event_name=SESSION_ITEM_APPENDED_SOURCE_EVENT,
            description="Session-owned append fact emitted when a response item is persisted.",
            topics=(named_event_topic(SESSION_ITEM_APPENDED_SOURCE_EVENT),),
            producers=("SessionApplicationService.append_items",),
            consumers=(
                "operations observer",
                "workbench event relay",
                "context workspace provider mirror",
            ),
            fields=(
                EventDefinitionField("event_name", "Stable session event name.", "string", True),
                EventDefinitionField("session_key", "Owning session key.", "string", True),
                EventDefinitionField("session_id", "Session instance identifier.", "string", True),
                EventDefinitionField("item_id", "Persisted session item identifier.", "string", True),
                EventDefinitionField("sequence_no", "Session item sequence number.", "integer", True),
                EventDefinitionField("kind", "Session item kind.", "string", True),
                EventDefinitionField("role", "Conversation role when applicable.", "string"),
                EventDefinitionField("phase", "Assistant response phase when applicable.", "string"),
                EventDefinitionField("source_module", "Owner module that produced the item.", "string"),
                EventDefinitionField("source_kind", "Owner-local source kind.", "string"),
                EventDefinitionField("source_id", "Owner-local source identifier.", "string"),
                EventDefinitionField("provider_item_id", "Provider-native response item id.", "string"),
                EventDefinitionField("provider_item_type", "Provider-native response item type.", "string"),
                EventDefinitionField("call_id", "Tool call id for tool call/result items.", "string"),
                EventDefinitionField("tool_name", "Tool name for tool call/result items.", "string"),
                EventDefinitionField("visibility", "Model/user/chat/trace visibility flags.", "object", True),
                EventDefinitionField("item", "Full session item payload.", "object", True),
            ),
            durability="persistent",
            publication_mode="direct",
            notes=(
                "Session owns this fact; orchestration does not translate it into a run message event.",
                "Consumers that need run context should join via item source metadata or orchestration run read models.",
            ),
        ),
    )


def session_event_surfaces() -> tuple[EventSurface, ...]:
    return (
        EventSurface(
            surface_id="session.items",
            owner="session",
            description="Durable session item event surface for agent timeline and context replay.",
            definition_ids=(SESSION_ITEM_APPENDED_SOURCE_EVENT,),
            topics=(named_event_topic(SESSION_ITEM_APPENDED_SOURCE_EVENT),),
            consumers=("operations observer", "workbench event relay", "context workspace"),
            notes=("Session items are the durable response-item contract.",),
        ),
    )
