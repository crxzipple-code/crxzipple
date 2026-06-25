from __future__ import annotations

from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.orchestration_failure_rows import (
    recent_failure_rows,
    repeated_probe_rows,
)


def repeated_probe_section(
    runs: list[OrchestrationRun],
) -> OperationsTableSectionModel:
    rows = repeated_probe_rows(runs)
    return OperationsTableSectionModel(
        id="repeated_probes",
        title="Repeated Probes",
        columns=_columns(
            ("run_id", "Run ID"),
            ("tool_id", "Tool"),
            ("kind", "Kind"),
            ("target", "Target"),
            ("count", "Count"),
            ("last_seen_step", "Last Seen"),
        ),
        rows=rows[:50],
        total=len(rows),
        view_all_route="/operations/orchestration?tab=repeated_probes",
        empty_state="No repeated probes detected.",
    )


def recent_failures_section(
    runs: list[OrchestrationRun],
) -> OperationsTableSectionModel:
    rows = recent_failure_rows(runs)
    return OperationsTableSectionModel(
        id="recent_failures",
        title="Recent Failures",
        columns=_columns(
            ("time", "Time"),
            ("run_id", "Run ID"),
            ("error", "Error"),
            ("status", "Status"),
            ("module", "Module"),
            ("details", "Details"),
            ("trace", "Trace"),
            ("actions", "Actions"),
        ),
        rows=rows,
        total=len(runs),
        view_all_route="/operations/orchestration?tab=failures",
        empty_state="No failed runs retained.",
    )


def _columns(*items: tuple[str, str]) -> tuple[OperationsTableColumnModel, ...]:
    return tuple(
        OperationsTableColumnModel(key=key, label=label) for key, label in items
    )
