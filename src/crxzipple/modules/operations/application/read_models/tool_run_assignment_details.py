from __future__ import annotations

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.presenters import (
    display_value,
    title_label,
)
from crxzipple.modules.tool.domain import ToolRunAssignment, ToolRunAssignmentStatus
from crxzipple.shared.time import format_datetime_utc


def assignment_history_section(
    assignments: list[ToolRunAssignment],
) -> OperationsTableSectionModel:
    rows = tuple(
        OperationsTableRowModel(
            id=assignment.id,
            cells={
                "assignment": assignment.id,
                "worker": assignment.worker_id,
                "status": title_label(assignment.status.value),
                "attempt": str(assignment.attempt_count),
                "assigned_at": format_datetime_utc(assignment.assigned_at),
                "started_at": (
                    format_datetime_utc(assignment.started_at)
                    if assignment.started_at is not None
                    else "-"
                ),
                "completed_at": (
                    format_datetime_utc(assignment.completed_at)
                    if assignment.completed_at is not None
                    else "-"
                ),
                "lease_expires_at": (
                    format_datetime_utc(assignment.lease_expires_at)
                    if assignment.lease_expires_at is not None
                    else "-"
                ),
                "reason": display_value(assignment.terminal_reason),
            },
            status=assignment.status.value,
            tone=assignment_tone(assignment.status),
        )
        for assignment in sorted(
            assignments,
            key=lambda item: item.assigned_at,
            reverse=True,
        )
    )
    return OperationsTableSectionModel(
        id="assignment_history",
        title="Assignment History",
        columns=_columns(
            ("assignment", "Assignment"),
            ("worker", "Worker ID"),
            ("status", "Status"),
            ("attempt", "Attempt"),
            ("assigned_at", "Assigned At"),
            ("started_at", "Started At"),
            ("completed_at", "Completed At"),
            ("lease_expires_at", "Lease Expires At"),
            ("reason", "Reason"),
        ),
        rows=rows,
        total=len(assignments),
        empty_state="No assignments recorded for this run.",
    )


def assignment_tone(status: ToolRunAssignmentStatus) -> str:
    if status is ToolRunAssignmentStatus.SUCCEEDED:
        return "success"
    if status in {ToolRunAssignmentStatus.FAILED, ToolRunAssignmentStatus.EXPIRED}:
        return "danger"
    if status is ToolRunAssignmentStatus.CANCELLED:
        return "warning"
    if status is ToolRunAssignmentStatus.RUNNING:
        return "info"
    return "neutral"


def _columns(*items: tuple[str, str]) -> tuple[OperationsTableColumnModel, ...]:
    return tuple(
        OperationsTableColumnModel(key=key, label=label) for key, label in items
    )
