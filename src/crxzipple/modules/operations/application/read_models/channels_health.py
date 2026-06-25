from __future__ import annotations

from datetime import datetime
from typing import Any

from crxzipple.modules.operations.application.read_models.channels_common import (
    interaction_tone,
    is_recent_channel_event,
    is_recent_interaction,
    runtime_is_recent_stale,
)
from crxzipple.modules.operations.application.read_models.channels_models import (
    ChannelEventRecord,
)


def health(
    *,
    service_available: bool,
    runtimes: tuple[dict[str, Any], ...],
    profiles: tuple[Any, ...],
    dead_letters: tuple[ChannelEventRecord, ...],
    interactions: tuple[Any, ...],
    now: datetime,
) -> str:
    if not service_available:
        return "error"
    if any(is_recent_channel_event(event, now=now) for event in dead_letters):
        return "error"
    if any(row["status"] in {"Error", "Failed", "Offline"} for row in runtimes):
        return "error"
    if any(
        interaction_tone(item) == "danger"
        and is_recent_interaction(item, now=now)
        for item in interactions
    ):
        return "error"
    if any(runtime_is_recent_stale(row) for row in runtimes):
        return "warning"
    if not runtimes and not profiles:
        return "warning"
    return "healthy"
