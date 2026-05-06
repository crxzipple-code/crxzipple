from __future__ import annotations

from crxzipple.shared import EventDefinition, EventDefinitionField, EventSurface
from crxzipple.shared.domain.events import named_event_topic


OPERATIONS_PROJECTION_INVALIDATED_EVENT = "operations.projection.invalidated"


def operations_event_definitions() -> tuple[EventDefinition, ...]:
    return (
        EventDefinition(
            definition_id=OPERATIONS_PROJECTION_INVALIDATED_EVENT,
            owner="operations",
            event_name=OPERATIONS_PROJECTION_INVALIDATED_EVENT,
            description=(
                "Operations projection refresh contract emitted after a module "
                "projection is materialized."
            ),
            topics=(named_event_topic(OPERATIONS_PROJECTION_INVALIDATED_EVENT),),
            producers=("OperationsProjectionMaterializer",),
            consumers=("operations observer", "operations SSE", "web console"),
            fields=(
                EventDefinitionField("event_name", "Stable operations refresh event name.", "string", True),
                EventDefinitionField("module", "Operations module whose projection changed.", "string", True),
                EventDefinitionField("kinds", "Projection kinds invalidated for the module.", "array", True),
                EventDefinitionField("query_key", "Projection query key, usually default.", "string", True),
                EventDefinitionField("source", "Refresh source, usually operations-observer.", "string", True),
                EventDefinitionField("updated_at", "Projection materialization timestamp.", "string", True),
                EventDefinitionField("level", "Operational severity level for display.", "string"),
                EventDefinitionField("summary", "Display-safe refresh summary.", "string"),
                EventDefinitionField("display_label", "Short display label for refresh consumers.", "string"),
                EventDefinitionField("display_summary", "Human-readable refresh summary.", "string"),
                EventDefinitionField("display_tone", "Display tone such as info or success.", "string"),
                EventDefinitionField("entity_type", "Linked entity type for refresh routing.", "string"),
                EventDefinitionField("entity_id", "Linked operations module identifier.", "string"),
            ),
            durability="persistent",
            publication_mode="direct",
            notes=(
                "This event is the Operations-owned UI refresh signal; raw owner module events remain diagnostics input.",
            ),
        ),
    )


def operations_event_surfaces() -> tuple[EventSurface, ...]:
    return (
        EventSurface(
            surface_id="operations.projection_refresh",
            owner="operations",
            description="Operations projection invalidation surface for UI refresh consumers.",
            definition_ids=(OPERATIONS_PROJECTION_INVALIDATED_EVENT,),
            topics=(named_event_topic(OPERATIONS_PROJECTION_INVALIDATED_EVENT),),
            consumers=("operations SSE", "web console", "operations observer"),
            notes=(
                "Consumers should refresh Operations read models by module and projection kind.",
            ),
        ),
    )
