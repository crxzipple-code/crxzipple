from __future__ import annotations

from typing import Any

from crxzipple.modules.channels.domain import ChannelInteraction
from crxzipple.modules.events import EventCursor


def interaction_observe_settled(interaction: ChannelInteraction) -> bool:
    normalized_status = str(interaction.status or "").strip().lower()
    if normalized_status in {"failed", "cancelled"}:
        return True
    if normalized_status != "completed":
        return False
    metadata = dict(interaction.metadata)
    last_message_id = str(metadata.get("last_message_id") or "").strip()
    last_delivered_message_id = str(
        metadata.get("last_delivered_message_id") or "",
    ).strip()
    delivery_status = str(metadata.get("last_delivery_status") or "").strip().lower()
    if last_message_id:
        return (
            last_delivered_message_id == last_message_id
            and delivery_status == "ok"
        )
    return False


def interaction_observe_cursor(interaction: ChannelInteraction) -> EventCursor | None:
    raw_cursor = interaction.metadata.get("observe_cursor")
    if isinstance(raw_cursor, str) and raw_cursor.strip():
        return raw_cursor.strip()
    return None


def interaction_status_from_observe_fact(
    *,
    current_status: str,
    event_name: str,
    payload: dict[str, Any],
) -> str:
    raw_status = str(payload.get("status") or "").strip().lower()
    if raw_status:
        return raw_status
    normalized_event_name = event_name.strip().lower()
    if normalized_event_name.endswith(".completed"):
        return "completed"
    if normalized_event_name.endswith(".failed"):
        return "failed"
    if normalized_event_name.endswith(".cancelled"):
        return "cancelled"
    if ".waiting" in normalized_event_name:
        return "waiting"
    if normalized_event_name.endswith(".queued"):
        return "queued"
    return current_status
