from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from crxzipple.modules.operations.application.read_models.channels_common import (
    group_by_runtime,
    runtime_status,
    runtime_status_sort,
)
from crxzipple.modules.operations.application.read_models.channels_formatting import (
    age_label,
    format_datetime,
    seconds_since,
    text,
    tone_for_status,
)
from crxzipple.modules.operations.application.read_models.channels_models import (
    ChannelEventRecord,
)


def runtime_records(
    *,
    runtimes: tuple[Any, ...],
    account_bindings: tuple[Any, ...],
    connection_bindings: tuple[Any, ...],
    events: tuple[ChannelEventRecord, ...],
    now: datetime,
) -> tuple[dict[str, Any], ...]:
    accounts_by_runtime = group_by_runtime(account_bindings)
    connections_by_runtime = group_by_runtime(connection_bindings)
    event_counts = Counter(
        event.runtime_id
        for event in events
        if event.runtime_id is not None and event.runtime_id
    )
    rows: list[dict[str, Any]] = []
    for runtime in runtimes:
        runtime_id = text(getattr(runtime, "runtime_id", None), "")
        seconds_since_heartbeat = seconds_since(
            getattr(runtime, "last_heartbeat_at", None),
            now=now,
        )
        status = runtime_status(runtime, now=now)
        rows.append(
            {
                "id": runtime_id,
                "runtime_id": runtime_id,
                "channel_type": text(getattr(runtime, "channel_type", None)),
                "service_key": text(getattr(runtime, "service_key", None)),
                "status": status,
                "registered_at": format_datetime(getattr(runtime, "registered_at", None)),
                "last_heartbeat": format_datetime(
                    getattr(runtime, "last_heartbeat_at", None),
                ),
                "heartbeat_age": age_label(seconds_since_heartbeat),
                "account_count": len(accounts_by_runtime.get(runtime_id, ())),
                "connection_count": len(connections_by_runtime.get(runtime_id, ())),
                "event_count": event_counts[runtime_id],
                "action": "Open",
                "route": f"/operations/channels?runtime_id={runtime_id}",
                "tone": tone_for_status(status),
                "_seconds_since_heartbeat": round(seconds_since_heartbeat, 3),
            }
        )
    rows.sort(
        key=lambda item: (
            runtime_status_sort(item["status"]),
            item["channel_type"],
            item["runtime_id"],
        )
    )
    return tuple(rows)
