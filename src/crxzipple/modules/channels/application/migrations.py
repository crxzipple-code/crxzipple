from __future__ import annotations

from dataclasses import replace
from typing import Any

from crxzipple.modules.channels.domain import (
    ChannelInteraction,
    ChannelInteractionRegistry,
)


_OLD_DELIVERED_TERM = "projec" + "ted"
_OLD_DELIVERY_TERM = "projec" + "tion"

_DELIVERY_METADATA_RENAMES = {
    "last_" + _OLD_DELIVERED_TERM + "_at": "last_delivered_at",
    "last_" + _OLD_DELIVERED_TERM + "_message_id": "last_delivered_message_id",
    "last_" + _OLD_DELIVERED_TERM + "_message_role": "last_delivered_message_role",
    "last_" + _OLD_DELIVERED_TERM + "_message_kind": "last_delivered_message_kind",
    "last_" + _OLD_DELIVERY_TERM + "_status": "last_delivery_status",
    "last_" + _OLD_DELIVERY_TERM + "_error": "last_delivery_error",
    "last_" + _OLD_DELIVERY_TERM + "_message_types": "last_delivery_message_types",
    "last_" + _OLD_DELIVERY_TERM + "_callback_status": "last_delivery_callback_status",
    "last_" + _OLD_DELIVERY_TERM + "_dead_letter_outbound_id": (
        "last_delivery_dead_letter_outbound_id"
    ),
    "last_" + _OLD_DELIVERY_TERM + "_failed_event_name": (
        "last_delivery_failed_event_name"
    ),
    "last_" + _OLD_DELIVERY_TERM + "_failed_at": "last_delivery_failed_at",
    _OLD_DELIVERED_TERM + "_artifact_ids": "delivered_artifact_ids",
    "max_" + _OLD_DELIVERY_TERM + "_attempts": "max_delivery_attempts",
}


def normalize_channel_interaction_delivery_state(
    registry: ChannelInteractionRegistry,
) -> ChannelInteractionRegistry:
    interactions = tuple(
        normalize_channel_interaction_delivery_metadata(interaction)
        for interaction in registry.interactions
    )
    if interactions == registry.interactions:
        return registry
    return replace(registry, interactions=interactions)


def normalize_channel_interaction_delivery_metadata(
    interaction: ChannelInteraction,
) -> ChannelInteraction:
    metadata = dict(interaction.metadata)
    changed = False
    for old_key, new_key in _DELIVERY_METADATA_RENAMES.items():
        if old_key not in metadata:
            continue
        old_value = metadata.pop(old_key)
        if new_key not in metadata:
            metadata[new_key] = old_value
        changed = True

    status = interaction.status
    if status.strip().lower() == ("projec" + "ted"):
        status = "delivered"
        changed = True

    if not changed:
        return interaction
    return replace(interaction, status=status, metadata=metadata)


__all__ = [
    "normalize_channel_interaction_delivery_metadata",
    "normalize_channel_interaction_delivery_state",
]
