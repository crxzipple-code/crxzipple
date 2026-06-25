from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.channels_sections import (
    table,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableSectionModel,
)


def channel_status_table(
    rows: tuple[dict[str, Any], ...],
    *,
    total: int,
) -> OperationsTableSectionModel:
    return table(
        "channel_status",
        "Channel Runtimes",
        (
            ("runtime_id", "Runtime ID"),
            ("channel_type", "Channel Type"),
            ("status", "Status"),
            ("heartbeat_age", "Heartbeat Age"),
            ("account_count", "Accounts"),
            ("connection_count", "Connections"),
            ("event_count", "Events"),
            ("action", "Action"),
        ),
        rows,
        total=total,
        empty_state="No channel runtimes registered.",
    )
