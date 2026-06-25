from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from crxzipple.modules.channels.domain import channel_dead_letter_topic
from crxzipple.modules.operations.application.read_models.models import (
    MetricCardModel,
    OperationsModuleOverview,
    RuntimeActionModel,
)
from crxzipple.modules.operations.application.read_models.modules_helpers import (
    health_metric,
    int_value,
    now,
    overview,
    s,
)
from crxzipple.shared.time import format_datetime_utc


def channels_operations_overview(query: Any) -> OperationsModuleOverview:
    current_time = now()
    runtimes = query.channel_runtime_manager.list_runtimes(channel_type=None)
    runtime_rows = [_channel_runtime_row(query, runtime) for runtime in runtimes]
    stale_count = sum(1 for row in runtime_rows if row["status"] == "Stale")
    online_count = sum(1 for row in runtime_rows if row["status"] == "online")
    dead_letters = _channel_dead_letter_rows(query, runtime_rows)
    health = "error" if dead_letters else "warning" if stale_count else "healthy"
    type_counts = Counter(row["channel_type"] for row in runtime_rows)

    return overview(
        module="channels",
        title="Channels",
        subtitle="聚合通道 runtime、连接绑定、账号绑定与死信。",
        health=health,
        updated_at=format_datetime_utc(current_time),
        metrics=(
            health_metric(health, "Loaded from channel runtime registry"),
            MetricCardModel(
                "runtimes",
                "Runtimes",
                str(len(runtime_rows)),
                f"{online_count} online",
                "info",
            ),
            MetricCardModel(
                "connections",
                "Connections",
                str(sum(int_value(row.get("connection_count")) for row in runtime_rows)),
                "active bindings",
                "info",
            ),
            MetricCardModel(
                "accounts",
                "Accounts",
                str(sum(int_value(row.get("account_count")) for row in runtime_rows)),
                "account bindings",
                "neutral",
            ),
            MetricCardModel(
                "stale",
                "Stale",
                str(stale_count),
                "heartbeat older than 5 minutes",
                "warning" if stale_count else "success",
            ),
            MetricCardModel(
                "dead_letters",
                "Dead Letters",
                str(len(dead_letters)),
                "across channel types",
                "danger" if dead_letters else "success",
            ),
        ),
        queue=tuple(runtime_rows),
        lane_locks=tuple(dead_letters),
        executor=tuple(
            {
                "channel_type": channel_type,
                "runtime_count": str(count),
                "status": "online" if count else "unknown",
            }
            for channel_type, count in sorted(type_counts.items())
        ),
        actions=(
            RuntimeActionModel(
                id="open_channel_runtime", label="Open Runtime", owner="channels"
            ),
            RuntimeActionModel(
                id="inspect_dead_letter",
                label="Inspect Dead Letter",
                owner="channels",
                risk="controlled",
            ),
        ),
    )


def _channel_runtime_row(
    query: Any,
    runtime: Any,
) -> dict[str, str]:
    accounts = query.channel_runtime_manager.list_account_bindings(
        runtime_id=runtime.runtime_id
    )
    connections = query.channel_runtime_manager.list_connection_bindings(
        runtime_id=runtime.runtime_id
    )
    heartbeat = getattr(runtime, "last_heartbeat_at", None)
    status = runtime.status
    if (
        isinstance(heartbeat, datetime)
        and (now() - heartbeat.astimezone(timezone.utc)).total_seconds() > 300
    ):
        status = "Stale"
    return {
        "runtime_id": runtime.runtime_id,
        "channel_type": runtime.channel_type,
        "service_key": s(runtime.service_key),
        "status": status,
        "registered_at": runtime.registered_at.isoformat(),
        "last_heartbeat_at": runtime.last_heartbeat_at.isoformat(),
        "account_count": str(len(accounts)),
        "connection_count": str(len(connections)),
    }


def _channel_dead_letter_rows(
    query: Any,
    runtime_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    if query.events_service is None:
        return []
    rows: list[dict[str, str]] = []
    for channel_type in sorted(
        {row["channel_type"] for row in runtime_rows} | {"web", "lark", "webhook"}
    ):
        topic = channel_dead_letter_topic(channel_type)
        for record in query.events_service.read_event_topic(topic, limit=20):
            rows.append(
                {
                    "cursor": record.cursor,
                    "topic": record.envelope.topic,
                    "event_id": record.envelope.id,
                    "channel_type": channel_type,
                    "reason": s(
                        record.envelope.payload.get("reason")
                        if isinstance(record.envelope.payload, dict)
                        else None
                    ),
                    "created_at": record.envelope.created_at.isoformat(),
                    "status": "Dead Letter",
                }
            )
    return rows
