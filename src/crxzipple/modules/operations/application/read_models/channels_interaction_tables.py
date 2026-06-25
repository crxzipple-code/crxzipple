from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.channels_sections import (
    table,
)
from crxzipple.modules.operations.application.read_models.channels_table_rows import (
    interaction_row,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableSectionModel,
)


def interactions_table(
    interactions: tuple[Any, ...],
    *,
    total: int,
) -> OperationsTableSectionModel:
    rows = tuple(interaction_row(interaction) for interaction in interactions)
    return table(
        "interactions",
        "Interactions",
        (
            ("interaction_id", "Interaction ID"),
            ("channel_type", "Channel Type"),
            ("status", "Status"),
            ("account_id", "Account ID"),
            ("run_id", "Run ID"),
            ("session_key", "Session Key"),
            ("agent_id", "Agent"),
            ("updated_at", "Updated At"),
            ("last_error", "Last Error"),
        ),
        rows,
        total=total,
        empty_state="No channel interactions registered.",
    )
