from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from crxzipple.modules.channels.application.payload_redaction import (
    redact_channel_payload,
)
from crxzipple.modules.operations.application.read_models.channels_formatting import (
    normalized_filter,
    seconds_since,
    status_label,
    text,
    title,
    tone_for_status,
)
from crxzipple.modules.operations.application.read_models.channels_models import (
    ChannelEventRecord,
)
from crxzipple.modules.operations.application.read_models.channels_payload_formatting import (
    display_payload,
    short_json,
)

STALE_RUNTIME_AFTER_SECONDS = 300.0
RECENT_CHANNEL_HEALTH_SECONDS = 86400.0


def group_by_runtime(items: tuple[Any, ...]) -> dict[str, tuple[Any, ...]]:
    grouped: dict[str, list[Any]] = defaultdict(list)
    for item in items:
        runtime_id = text(getattr(item, "runtime_id", None), "")
        if runtime_id:
            grouped[runtime_id].append(item)
    return {key: tuple(value) for key, value in grouped.items()}


def interaction_search_text(interaction: Any) -> str:
    values = (
        getattr(interaction, "interaction_id", None),
        getattr(interaction, "channel_type", None),
        getattr(interaction, "channel_account_id", None),
        getattr(interaction, "external_event_id", None),
        getattr(interaction, "external_message_id", None),
        getattr(interaction, "external_conversation_id", None),
        getattr(interaction, "external_user_id", None),
        getattr(interaction, "agent_id", None),
        getattr(interaction, "session_key", None),
        getattr(interaction, "run_id", None),
        getattr(interaction, "status", None),
        getattr(interaction, "last_error", None),
        short_json(getattr(interaction, "reply_address", {}) or {}, size=400),
        short_json(getattr(interaction, "metadata", {}) or {}, size=400),
    )
    return " ".join(text(value, "") for value in values).lower()


def interaction_tone(interaction: Any) -> str:
    status = text(getattr(interaction, "status", None), "")
    error = text(getattr(interaction, "last_error", None), "")
    if error:
        return "danger"
    tone = tone_for_status(status)
    if tone != "neutral":
        return tone
    normalized = normalized_filter(status)
    if normalized in {"received", "submitted", "queued", "accepted", "running"}:
        return "info"
    if normalized in {"completed", "delivered"}:
        return "success"
    return "neutral"


def is_recent_interaction(interaction: Any, *, now: datetime) -> bool:
    updated_at = getattr(interaction, "updated_at", None)
    created_at = getattr(interaction, "created_at", None)
    for value in (updated_at, created_at):
        if isinstance(value, datetime):
            return seconds_since(value, now=now) <= RECENT_CHANNEL_HEALTH_SECONDS
    return False


def is_recent_channel_event(event: ChannelEventRecord, *, now: datetime) -> bool:
    return seconds_since(event.occurred_at, now=now) <= RECENT_CHANNEL_HEALTH_SECONDS


def runtime_status(runtime: Any, *, now: datetime) -> str:
    raw = text(getattr(runtime, "status", None), "online")
    heartbeat = getattr(runtime, "last_heartbeat_at", None)
    if seconds_since(heartbeat, now=now) > STALE_RUNTIME_AFTER_SECONDS:
        return "Stale"
    normalized = raw.strip().lower().replace("_", "-")
    if normalized in {"online", "ready", "healthy"}:
        return "Online"
    if normalized in {"offline", "stopped"}:
        return "Offline"
    if normalized in {"error", "failed"}:
        return "Error"
    return title(raw)


def runtime_status_sort(status: str) -> int:
    normalized = status.strip().lower()
    if normalized == "online":
        return 0
    if normalized in {"error", "failed", "offline"}:
        return 1
    if normalized == "stale":
        return 2
    return 3


def runtime_is_recent_stale(row: dict[str, Any]) -> bool:
    if row.get("status") != "Stale":
        return False
    seconds = row.get("_seconds_since_heartbeat")
    if not isinstance(seconds, (int, float)):
        return False
    return float(seconds) <= RECENT_CHANNEL_HEALTH_SECONDS


def account_profile(profile: Any | None, account_id: str) -> Any | None:
    if profile is None:
        return None
    for account in tuple(getattr(profile, "accounts", ()) or ()):
        if text(getattr(account, "account_id", None), "") == account_id:
            return account
    return None


def metadata_value(item: Any, key: str) -> Any:
    metadata = getattr(item, "metadata", None)
    if isinstance(metadata, dict):
        return metadata.get(key)
    return None


def payload_from_runtime(runtime: Any) -> dict[str, Any]:
    to_payload = getattr(runtime, "to_payload", None)
    if callable(to_payload):
        try:
            payload = to_payload()
            return (
                display_payload(redact_channel_payload(dict(payload)))
                if isinstance(payload, dict)
                else {}
            )
        except Exception:
            return {}
    return {
        "runtime_id": text(getattr(runtime, "runtime_id", None)),
        "channel_type": text(getattr(runtime, "channel_type", None)),
        "service_key": text(getattr(runtime, "service_key", None)),
        "status": text(getattr(runtime, "status", None)),
    }


def payload_from_interaction(interaction: Any) -> dict[str, Any]:
    to_payload = getattr(interaction, "to_payload", None)
    if callable(to_payload):
        try:
            payload = to_payload()
            return (
                display_payload(redact_channel_payload(dict(payload)))
                if isinstance(payload, dict)
                else {}
            )
        except Exception:
            return {}
    return {
        "interaction_id": text(getattr(interaction, "interaction_id", None)),
        "channel_type": text(getattr(interaction, "channel_type", None)),
        "channel_account_id": text(
            getattr(interaction, "channel_account_id", None),
        ),
        "run_id": text(getattr(interaction, "run_id", None)),
        "session_key": text(getattr(interaction, "session_key", None)),
        "status": status_label(text(getattr(interaction, "status", None))),
        "metadata": display_payload(
            redact_channel_payload(dict(getattr(interaction, "metadata", {}) or {})),
        ),
    }
