from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.channels_common import (
    interaction_tone,
    metadata_value,
    payload_from_interaction,
)
from crxzipple.modules.operations.application.read_models.channels_event_helpers import (
    events_for_interaction,
)
from crxzipple.modules.operations.application.read_models.channels_formatting import (
    format_datetime,
    short_optional,
    status_label,
    text,
)
from crxzipple.modules.operations.application.read_models.channels_models import (
    ChannelEventRecord,
    ChannelInteractionDetailModel,
)
from crxzipple.modules.operations.application.read_models.channels_sections import (
    key_value_section,
)
from crxzipple.modules.operations.application.read_models.channels_message_tables import (
    channel_events_table,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsKeyValueItemModel,
)


def interaction_details(
    interactions: tuple[Any, ...],
    *,
    events: tuple[ChannelEventRecord, ...],
) -> tuple[ChannelInteractionDetailModel, ...]:
    details: list[ChannelInteractionDetailModel] = []
    for interaction in interactions[:80]:
        interaction_id = text(getattr(interaction, "interaction_id", None), "")
        if not interaction_id:
            continue
        status = status_label(text(getattr(interaction, "status", None), "received"))
        related_events = events_for_interaction(interaction, events)
        tone = interaction_tone(interaction)
        details.append(
            ChannelInteractionDetailModel(
                interaction_id=interaction_id,
                title=interaction_id,
                status=status,
                tone=tone,
                summary=(
                    OperationsKeyValueItemModel(
                        "Interaction ID",
                        interaction_id,
                        "neutral",
                    ),
                    OperationsKeyValueItemModel(
                        "Channel Type",
                        text(getattr(interaction, "channel_type", None)),
                        "info",
                    ),
                    OperationsKeyValueItemModel(
                        "Account ID",
                        text(getattr(interaction, "channel_account_id", None)),
                        "neutral",
                    ),
                    OperationsKeyValueItemModel("Status", status, tone),
                    OperationsKeyValueItemModel(
                        "Run ID",
                        text(getattr(interaction, "run_id", None)),
                        "info",
                    ),
                    OperationsKeyValueItemModel(
                        "Session Key",
                        text(getattr(interaction, "session_key", None)),
                        "neutral",
                    ),
                    OperationsKeyValueItemModel(
                        "Updated At",
                        format_datetime(getattr(interaction, "updated_at", None)),
                        "neutral",
                    ),
                    OperationsKeyValueItemModel(
                        "Last Error",
                        short_optional(getattr(interaction, "last_error", None)),
                        tone,
                    ),
                ),
                routing=key_value_section(
                    "interaction_routing",
                    "Routing",
                    {
                        "external_event_id": getattr(interaction, "external_event_id", None),
                        "external_message_id": getattr(interaction, "external_message_id", None),
                        "external_conversation_id": getattr(
                            interaction,
                            "external_conversation_id",
                            None,
                        ),
                        "external_user_id": getattr(interaction, "external_user_id", None),
                        "agent_id": getattr(interaction, "agent_id", None),
                        "active_session_id": metadata_value(
                            interaction,
                            "active_session_id",
                        ),
                        "observe_cursor": metadata_value(interaction, "observe_cursor"),
                    },
                ),
                reply_address=key_value_section(
                    "reply_address",
                    "Reply Address",
                    getattr(interaction, "reply_address", {}) or {},
                ),
                metadata=key_value_section(
                    "interaction_metadata",
                    "Metadata",
                    getattr(interaction, "metadata", {}) or {},
                ),
                events=channel_events_table(
                    related_events[:40],
                    total=len(related_events),
                ),
                raw_payload=payload_from_interaction(interaction),
            )
        )
    return tuple(details)
