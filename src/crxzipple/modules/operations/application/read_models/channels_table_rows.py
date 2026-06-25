from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.channels_common import (
    account_profile,
    interaction_tone,
    metadata_value,
)
from crxzipple.modules.operations.application.read_models.channels_event_helpers import (
    event_direction,
    failure_reason,
    trace_route,
)
from crxzipple.modules.operations.application.read_models.channels_formatting import (
    display_text,
    format_datetime,
    join,
    short_optional,
    status_label,
    text,
    title,
    tone_for_status,
)
from crxzipple.modules.operations.application.read_models.channels_models import (
    ChannelEventRecord,
)
from crxzipple.modules.operations.application.read_models.channels_payload_formatting import (
    short_json,
)
from crxzipple.modules.operations.application.read_models.channels_sections import (
    capabilities_label,
)
from crxzipple.shared.time import format_datetime_utc


def dead_letter_row(event: ChannelEventRecord) -> dict[str, Any]:
    return {
        "id": event.id,
        "time": format_datetime_utc(event.occurred_at),
        "channel_type": text(event.channel_type),
        "runtime_id": text(event.runtime_id),
        "status": "Dead Letter",
        "outbound_id": text(event.payload.get("outbound_id")),
        "reason": failure_reason(event),
        "attempt_count": text(event.payload.get("attempt_count")),
        "topic": display_text(event.topic),
        "cursor": event.cursor,
        "action": "Inspect",
        "trace_route": trace_route(event),
        "route": trace_route(event),
        "tone": "danger",
    }


def message_row(event: ChannelEventRecord) -> dict[str, Any]:
    return {
        "id": event.id,
        "time": format_datetime_utc(event.occurred_at),
        "channel_type": text(event.channel_type),
        "direction": event_direction(event),
        "event": display_text(event.event_name),
        "runtime_id": text(event.runtime_id),
        "connection_id": text(event.connection_id),
        "conversation_id": text(event.conversation_id),
        "status": status_label(event.status),
        "topic": display_text(event.topic),
        "cursor": event.cursor,
        "trace": text(event.trace_id),
        "trace_route": trace_route(event),
        "route": trace_route(event),
        "tone": tone_for_status(event.status),
    }


def interaction_row(interaction: Any) -> dict[str, Any]:
    status = status_label(text(getattr(interaction, "status", None), "received"))
    return {
        "id": text(getattr(interaction, "interaction_id", None), ""),
        "interaction_id": text(getattr(interaction, "interaction_id", None)),
        "channel_type": text(getattr(interaction, "channel_type", None)),
        "status": status,
        "account_id": text(getattr(interaction, "channel_account_id", None)),
        "run_id": text(getattr(interaction, "run_id", None)),
        "session_key": text(getattr(interaction, "session_key", None)),
        "agent_id": text(getattr(interaction, "agent_id", None)),
        "updated_at": format_datetime(getattr(interaction, "updated_at", None)),
        "last_error": short_optional(getattr(interaction, "last_error", None)),
        "observe_cursor": text(metadata_value(interaction, "observe_cursor")),
        "active_session_id": text(metadata_value(interaction, "active_session_id")),
        "tone": interaction_tone(interaction),
    }


def account_binding_rows(
    bindings: tuple[Any, ...],
    *,
    profiles: tuple[Any, ...],
) -> tuple[dict[str, Any], ...]:
    profile_by_type = {
        text(getattr(profile, "channel_type", None), ""): profile for profile in profiles
    }
    rows: list[dict[str, Any]] = []
    for binding in bindings:
        channel_type = text(getattr(binding, "channel_type", None), "")
        account_id = text(getattr(binding, "channel_account_id", None), "")
        account_profile_record = account_profile(profile_by_type.get(channel_type), account_id)
        rows.append(
            {
                "id": f"{channel_type}:{account_id}",
                "channel_type": channel_type,
                "account_id": account_id,
                "runtime_id": text(getattr(binding, "runtime_id", None)),
                "transport_mode": text(
                    getattr(account_profile_record, "transport_mode", None)
                    if account_profile_record is not None
                    else metadata_value(binding, "transport_mode")
                ),
                "status": "Enabled"
                if account_profile_record is None or bool(getattr(account_profile_record, "enabled", True))
                else "Disabled",
                "updated_at": format_datetime(getattr(binding, "updated_at", None)),
                "metadata": short_json(getattr(binding, "metadata", {})),
                "tone": "success",
            }
        )
    return tuple(rows)


def connection_binding_row(binding: Any) -> dict[str, Any]:
    return {
        "id": text(getattr(binding, "connection_id", None), ""),
        "channel_type": text(getattr(binding, "channel_type", None)),
        "connection_id": text(getattr(binding, "connection_id", None)),
        "runtime_id": text(getattr(binding, "runtime_id", None)),
        "account_id": text(getattr(binding, "channel_account_id", None)),
        "conversation_id": text(getattr(binding, "conversation_id", None)),
        "supports_streaming": "Yes" if bool(getattr(binding, "supports_streaming", False)) else "No",
        "updated_at": format_datetime(getattr(binding, "updated_at", None)),
        "observe_cursor": text(metadata_value(binding, "observe_cursor")),
        "live_cursor": text(metadata_value(binding, "live_cursor")),
        "status": "Active",
        "tone": "success",
    }


def profile_row(profile: Any) -> dict[str, Any]:
    accounts = tuple(getattr(profile, "accounts", ()) or ())
    enabled = bool(getattr(profile, "enabled", True))
    return {
        "id": text(getattr(profile, "channel_type", None), ""),
        "channel_type": text(getattr(profile, "channel_type", None)),
        "status": "Enabled" if enabled else "Disabled",
        "account_count": len(accounts),
        "transport_modes": join(
            getattr(account, "transport_mode", None) for account in accounts
        ),
        "capabilities": capabilities_label(getattr(profile, "capabilities", None)),
        "metadata": short_json(getattr(profile, "metadata", {})),
        "tone": "success" if enabled else "warning",
    }


def channel_event_row(event: ChannelEventRecord) -> dict[str, Any]:
    return {
        **message_row(event),
        "kind": title(event.kind),
        "topic": event.topic,
        "cursor": event.cursor,
    }
