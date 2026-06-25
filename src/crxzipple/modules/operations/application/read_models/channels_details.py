from __future__ import annotations

from datetime import datetime
from typing import Any

from crxzipple.modules.operations.application.read_models.channels_common import (
    group_by_runtime,
    payload_from_runtime,
    runtime_status,
)
from crxzipple.modules.operations.application.read_models.channels_connection_helpers import (
    event_matches_runtime,
)
from crxzipple.modules.operations.application.read_models.channels_formatting import (
    age_label,
    seconds_since,
    text,
    tone_for_status,
)
from crxzipple.modules.operations.application.read_models.channels_models import (
    ChannelEventRecord,
    ChannelRuntimeDetailModel,
)
from crxzipple.modules.operations.application.read_models.channels_binding_tables import (
    account_bindings_table,
    connection_bindings_table,
)
from crxzipple.modules.operations.application.read_models.channels_message_tables import (
    channel_events_table,
    dead_letter_table,
)
from crxzipple.modules.operations.application.read_models.channels_sections import (
    capabilities_section,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsKeyValueItemModel,
)


def runtime_details(
    *,
    runtimes: tuple[Any, ...],
    runtime_records: tuple[dict[str, Any], ...],
    account_bindings: tuple[Any, ...],
    connection_bindings: tuple[Any, ...],
    events: tuple[ChannelEventRecord, ...],
    dead_letters: tuple[ChannelEventRecord, ...],
    now: datetime,
) -> tuple[ChannelRuntimeDetailModel, ...]:
    record_by_id = {row["runtime_id"]: row for row in runtime_records}
    accounts_by_runtime = group_by_runtime(account_bindings)
    connections_by_runtime = group_by_runtime(connection_bindings)
    details: list[ChannelRuntimeDetailModel] = []
    for runtime in runtimes:
        runtime_id = text(getattr(runtime, "runtime_id", None), "")
        if not runtime_id:
            continue
        runtime_connections = connections_by_runtime.get(runtime_id, ())
        runtime_events = tuple(
            event
            for event in events
            if event_matches_runtime(event, runtime_id, runtime_connections)
        )
        runtime_dead_letters = tuple(
            event
            for event in dead_letters
            if event_matches_runtime(event, runtime_id, runtime_connections)
        )
        status = text(
            record_by_id.get(runtime_id, {}).get("status"),
            runtime_status(runtime, now=now),
        )
        details.append(
            ChannelRuntimeDetailModel(
                runtime_id=runtime_id,
                title=runtime_id,
                status=status,
                tone=tone_for_status(status),
                summary=(
                    OperationsKeyValueItemModel("Runtime ID", runtime_id, "neutral"),
                    OperationsKeyValueItemModel(
                        "Channel Type",
                        text(getattr(runtime, "channel_type", None)),
                        "info",
                    ),
                    OperationsKeyValueItemModel("Status", status, tone_for_status(status)),
                    OperationsKeyValueItemModel(
                        "Service Key",
                        text(getattr(runtime, "service_key", None)),
                        "neutral",
                    ),
                    OperationsKeyValueItemModel(
                        "Heartbeat Age",
                        age_label(
                            seconds_since(
                                getattr(runtime, "last_heartbeat_at", None),
                                now=now,
                            ),
                        ),
                        tone_for_status(status),
                    ),
                    OperationsKeyValueItemModel(
                        "Connections",
                        str(len(runtime_connections)),
                        "info",
                    ),
                    OperationsKeyValueItemModel(
                        "Dead Letters",
                        str(len(runtime_dead_letters)),
                        "danger" if runtime_dead_letters else "success",
                    ),
                ),
                capabilities=capabilities_section(getattr(runtime, "capabilities", None)),
                account_bindings=account_bindings_table(
                    tuple(accounts_by_runtime.get(runtime_id, ())),
                    profiles=(),
                ),
                connection_bindings=connection_bindings_table(tuple(runtime_connections)),
                events=channel_events_table(runtime_events[:40], total=len(runtime_events)),
                dead_letters=dead_letter_table(runtime_dead_letters),
                raw_payload=payload_from_runtime(runtime),
            )
        )
    return tuple(details)
