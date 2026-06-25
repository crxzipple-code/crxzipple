from __future__ import annotations

from crxzipple.modules.operations.application.read_models.channels_event_helpers import (
    dedupe_events,
)
from crxzipple.modules.operations.application.read_models.channels_formatting import (
    display_text,
    status_label,
    text,
    tone_for_status,
)
from crxzipple.modules.operations.application.read_models.channels_models import (
    ChannelEventRecord,
    ChannelRecordDetailModel,
)
from crxzipple.modules.operations.application.read_models.channels_payload_formatting import (
    display_payload,
)
from crxzipple.modules.operations.application.read_models.channels_sections import (
    table,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsKeyValueItemModel,
)


def record_details(
    events: tuple[ChannelEventRecord, ...],
) -> tuple[ChannelRecordDetailModel, ...]:
    unique = dedupe_events(events)
    return tuple(
        ChannelRecordDetailModel(
            record_id=event.id,
            title=display_text(event.event_name),
            status=status_label(event.status),
            tone=tone_for_status(event.status),
            summary=(
                OperationsKeyValueItemModel("Event ID", event.id, "neutral"),
                OperationsKeyValueItemModel("Topic", display_text(event.topic), "info"),
                OperationsKeyValueItemModel("Cursor", event.cursor, "neutral"),
                OperationsKeyValueItemModel(
                    "Channel Type",
                    text(event.channel_type),
                    "info",
                ),
                OperationsKeyValueItemModel(
                    "Runtime ID",
                    text(event.runtime_id),
                    "neutral",
                ),
                OperationsKeyValueItemModel(
                    "Status",
                    status_label(event.status),
                    tone_for_status(event.status),
                ),
            ),
            payload=display_payload(event.payload),
            trace=display_payload(event.trace),
            related=table(
                "record_related",
                "Related Routing",
                (
                    ("field", "Field"),
                    ("value", "Value"),
                ),
                tuple(
                    {"id": key, "field": label, "value": value}
                    for key, label, value in (
                        ("run_id", "Run ID", text(event.run_id)),
                        ("trace_id", "Trace", text(event.trace_id)),
                        ("connection_id", "Connection ID", text(event.connection_id)),
                        ("conversation_id", "Conversation ID", text(event.conversation_id)),
                    )
                    if value != "-"
                ),
                total=4,
                empty_state="No related routing identifiers.",
            ),
        )
        for event in unique[:80]
    )
