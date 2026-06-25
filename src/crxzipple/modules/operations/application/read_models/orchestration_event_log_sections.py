from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.orchestration_event_log_rows import (
    event_record_row,
)


def ops_event_log_section(
    *,
    event_records: tuple[Any, ...],
) -> OperationsTableSectionModel:
    rows = tuple(event_record_row(record) for record in event_records[:30])
    return OperationsTableSectionModel(
        id="ops_event_log",
        title="Ops Event Log",
        columns=_columns(
            ("time", "Time"),
            ("level", "Level"),
            ("event", "Event"),
            ("summary", "Summary"),
            ("run_id_entity", "Run ID / Entity"),
            ("source", "Source"),
        ),
        rows=rows,
        total=len(event_records),
        view_all_route="/operations/orchestration?tab=events",
        empty_state="No orchestration events observed yet.",
    )


def _columns(*items: tuple[str, str]) -> tuple[OperationsTableColumnModel, ...]:
    return tuple(
        OperationsTableColumnModel(key=key, label=label) for key, label in items
    )
