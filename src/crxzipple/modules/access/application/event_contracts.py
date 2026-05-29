from __future__ import annotations

from crxzipple.modules.access.application.events import ACCESS_OPERATION_EVENT_NAMES
from crxzipple.shared import EventDefinition, EventDefinitionField, EventSurface
from crxzipple.shared.domain.events import named_event_topic


def access_event_definitions() -> tuple[EventDefinition, ...]:
    common_fields = (
        EventDefinitionField("event_name", "Published access operation event name.", "string", True),
        EventDefinitionField("status", "Operation status or credential resolution outcome.", "string", True),
        EventDefinitionField("level", "Operational severity level.", "string"),
        EventDefinitionField("action_id", "Access action id for operator-initiated changes.", "string"),
        EventDefinitionField("intent", "Access action intent such as register, setup, rotate, or verify.", "string"),
        EventDefinitionField("resource_kind", "Access resource kind affected by the event.", "string"),
        EventDefinitionField("resource_id", "Access resource identifier affected by the event.", "string"),
        EventDefinitionField("target_id", "Access target identifier affected by the event.", "string"),
        EventDefinitionField("binding_id", "Credential binding id associated with the event.", "string"),
        EventDefinitionField("credential_binding_id", "Credential binding id associated with the event.", "string"),
        EventDefinitionField("expected_kind", "Expected credential kind for runtime resolution.", "string"),
        EventDefinitionField("consumer_module", "Module consuming the credential.", "string"),
        EventDefinitionField("consumer_kind", "Consumer kind consuming the credential.", "string"),
        EventDefinitionField("consumer_id", "Consumer id consuming the credential.", "string"),
        EventDefinitionField("consumer_slot", "Consumer credential slot.", "string"),
        EventDefinitionField("allow_literal", "Whether literal credentials were allowed for this resolution.", "boolean"),
        EventDefinitionField("actor", "Actor that initiated an access action.", "string"),
        EventDefinitionField("operator", "Operator that initiated an access action.", "string"),
        EventDefinitionField("reason", "Human or system reason attached to the event.", "string"),
        EventDefinitionField("audit_ref", "Access action audit reference.", "string"),
        EventDefinitionField("error", "Redacted error payload for failed operations.", "object"),
        EventDefinitionField("result", "Redacted result payload for completed operations.", "object"),
    )
    return tuple(
        EventDefinition(
            definition_id=event_name,
            owner="access",
            event_name=event_name,
            description="Access credential, setup, and operator action fact consumed by Operations.",
            topics=(named_event_topic(event_name),),
            producers=("AccessApplicationService", "AccessActionService"),
            consumers=("OperationsEventObserver", "AccessOperationsReadModelProvider"),
            fields=common_fields,
            durability="persistent",
            publication_mode="direct",
        )
        for event_name in ACCESS_OPERATION_EVENT_NAMES
    )


def access_event_surfaces() -> tuple[EventSurface, ...]:
    return (
        EventSurface(
            surface_id="access.operations",
            owner="access",
            description="Access credential resolution, setup, and governance facts consumed by Operations.",
            definition_ids=ACCESS_OPERATION_EVENT_NAMES,
            topics=tuple(named_event_topic(event_name) for event_name in ACCESS_OPERATION_EVENT_NAMES),
            consumers=("operations.observer", "operations.access"),
        ),
    )
