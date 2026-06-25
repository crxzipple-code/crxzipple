from __future__ import annotations

from datetime import datetime
from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.tool_metric_values import (
    terminal_run_duration_seconds,
)
from crxzipple.modules.operations.application.read_models.tool_provider_identity import (
    provider_history_label,
    tool_provider_key,
)
from crxzipple.modules.operations.application.read_models.tool_provider_history_rows import (
    provider_history_bucket,
    provider_history_row,
)
from crxzipple.modules.operations.application.read_models.tool_run_time import (
    tool_run_duration_seconds,
    tool_run_time,
)
from crxzipple.modules.tool.domain import (
    Tool,
    ToolRun,
    ToolRunAssignment,
    ToolRunStatus,
)
from crxzipple.shared.time import coerce_utc_datetime


def provider_history_section(
    *,
    tools: list[Tool],
    runs: list[ToolRun],
    assignment_by_run: dict[str, ToolRunAssignment],
    now: datetime,
) -> OperationsTableSectionModel:
    tools_by_id = _tool_lookup(tools)
    grouped: dict[str, dict[str, Any]] = {}
    for tool in tools:
        bucket = grouped.setdefault(tool_provider_key(tool), provider_history_bucket())
        bucket["tools"].add(tool.id)

    for run in runs:
        tool = tools_by_id.get(run.tool_id)
        bucket = grouped.setdefault(tool_provider_key(tool), provider_history_bucket())
        bucket["tools"].add(run.tool_id)
        bucket["runs"] += 1
        bucket["last_run"] = _latest_datetime(bucket.get("last_run"), tool_run_time(run))
        if run.is_terminal():
            bucket["terminal"] += 1
            if run.status is ToolRunStatus.SUCCEEDED:
                bucket["succeeded"] += 1
            elif run.status in {ToolRunStatus.FAILED, ToolRunStatus.TIMED_OUT}:
                bucket["failures"] += 1
            elif run.status is ToolRunStatus.CANCELLED:
                bucket["cancelled"] += 1
            duration_seconds = terminal_run_duration_seconds(run)
            if duration_seconds is not None:
                bucket["duration_count"] += 1
                bucket["total_duration_seconds"] += duration_seconds
                bucket["max_duration_seconds"] = max(
                    bucket["max_duration_seconds"],
                    duration_seconds,
                )
        else:
            bucket["active"] += 1
            bucket["active_duration_seconds"] = max(
                bucket["active_duration_seconds"],
                tool_run_duration_seconds(
                    run,
                    assignment=assignment_by_run.get(run.id),
                    now=now,
                ),
            )

    rows = tuple(
        provider_history_row(provider_key, bucket)
        for provider_key, bucket in sorted(
            grouped.items(),
            key=lambda item: (-int(item[1]["runs"]), provider_history_label(item[0])),
        )
        if bucket["tools"] or bucket["runs"]
    )
    return OperationsTableSectionModel(
        id="provider_history",
        title="Provider History",
        columns=_columns(
            ("provider", "Provider"),
            ("state", "State"),
            ("tools", "Tools"),
            ("runs", "Runs"),
            ("active", "Active"),
            ("failures", "Failures"),
            ("success_rate", "Success Rate"),
            ("avg_duration", "Avg Duration"),
            ("max_duration", "Max Duration"),
            ("last_run", "Last Run"),
        ),
        rows=rows,
        total=len(rows),
        view_all_route="/operations/tool?tab=provider_history",
        empty_state="No provider runtime history observed.",
    )


def _latest_datetime(
    left: object | None,
    right: datetime,
) -> datetime:
    if not isinstance(left, datetime):
        return right
    return max(coerce_utc_datetime(left), coerce_utc_datetime(right))


def _tool_lookup(tools: list[Tool]) -> dict[str, Tool]:
    return {tool.id: tool for tool in tools}


def _columns(*items: tuple[str, str]) -> tuple[OperationsTableColumnModel, ...]:
    return tuple(
        OperationsTableColumnModel(key=key, label=label) for key, label in items
    )
