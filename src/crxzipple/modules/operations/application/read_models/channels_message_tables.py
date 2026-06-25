from __future__ import annotations

from crxzipple.modules.operations.application.read_models.channels_models import (
    ChannelEventRecord,
)
from crxzipple.modules.operations.application.read_models.channels_sections import (
    table,
)
from crxzipple.modules.operations.application.read_models.channels_table_rows import (
    channel_event_row,
    dead_letter_row,
    message_row,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableSectionModel,
)


def dead_letter_table(
    events: tuple[ChannelEventRecord, ...],
) -> OperationsTableSectionModel:
    rows = tuple(dead_letter_row(event) for event in events)
    return table(
        "dead_letter_queue",
        "Dead Letter Queue",
        (
            ("time", "Time"),
            ("channel_type", "Channel Type"),
            ("runtime_id", "Runtime ID"),
            ("outbound_id", "Outbound ID"),
            ("reason", "Reason"),
            ("attempt_count", "Attempt"),
            ("topic", "Topic"),
            ("action", "Action"),
        ),
        rows,
        total=len(events),
        empty_state="No channel dead letters observed.",
    )


def recent_messages_table(
    events: tuple[ChannelEventRecord, ...],
    *,
    total: int,
) -> OperationsTableSectionModel:
    rows = tuple(message_row(event) for event in events)
    return table(
        "recent_messages",
        "Recent Messages",
        (
            ("time", "Time"),
            ("channel_type", "Channel Type"),
            ("direction", "Direction"),
            ("event", "Event"),
            ("runtime_id", "Runtime ID"),
            ("conversation_id", "Conversation ID"),
            ("status", "Status"),
            ("trace", "Trace"),
        ),
        rows,
        total=total,
        empty_state="No channel messages or channel events observed.",
    )


def channel_events_table(
    events: tuple[ChannelEventRecord, ...],
    *,
    total: int,
) -> OperationsTableSectionModel:
    rows = tuple(channel_event_row(event) for event in events)
    return table(
        "channel_events",
        "Channel Events",
        (
            ("time", "Time"),
            ("topic", "Topic"),
            ("event", "Event"),
            ("kind", "Kind"),
            ("status", "Status"),
            ("cursor", "Cursor"),
            ("trace", "Trace"),
        ),
        rows,
        total=total,
        empty_state="No channel event records observed.",
    )
