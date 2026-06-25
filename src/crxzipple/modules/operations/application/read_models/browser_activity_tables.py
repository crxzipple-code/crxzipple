from __future__ import annotations

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)


def network_activity_table(
    rows: tuple[OperationsTableRowModel, ...],
    *,
    total: int,
) -> OperationsTableSectionModel:
    return OperationsTableSectionModel(
        id="network_activity",
        title="Browser Network Activity",
        columns=(
            OperationsTableColumnModel("time", "Time"),
            OperationsTableColumnModel("event", "Event"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("profile", "Profile"),
            OperationsTableColumnModel("target_id", "Target"),
            OperationsTableColumnModel("capture", "Capture"),
            OperationsTableColumnModel("request", "Request"),
            OperationsTableColumnModel("method", "Method"),
            OperationsTableColumnModel("http_status", "HTTP"),
            OperationsTableColumnModel("resource", "Resource"),
            OperationsTableColumnModel("url", "URL"),
            OperationsTableColumnModel("summary", "Summary"),
        ),
        rows=rows,
        total=total,
        view_all_route="/operations/browser?tab=network",
        empty_state="No browser network activity observed.",
    )


def diagnostics_table(
    rows: tuple[OperationsTableRowModel, ...],
    *,
    total: int,
) -> OperationsTableSectionModel:
    return OperationsTableSectionModel(
        id="diagnostics",
        title="Browser Diagnostics",
        columns=(
            OperationsTableColumnModel("time", "Time"),
            OperationsTableColumnModel("event", "Event"),
            OperationsTableColumnModel("kind", "Kind"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("profile", "Profile"),
            OperationsTableColumnModel("target_id", "Target"),
            OperationsTableColumnModel("issues", "Issues"),
            OperationsTableColumnModel("console", "Console"),
            OperationsTableColumnModel("errors", "Errors"),
            OperationsTableColumnModel("ready_state", "Ready"),
            OperationsTableColumnModel("trace", "Trace"),
            OperationsTableColumnModel("trace_size", "Trace Size"),
            OperationsTableColumnModel("changed", "Changed"),
            OperationsTableColumnModel("summary", "Summary"),
        ),
        rows=rows,
        total=total,
        view_all_route="/operations/browser?tab=diagnostics",
        empty_state="No browser diagnostics observed.",
    )
