from __future__ import annotations

from datetime import datetime

from crxzipple.modules.operations.application.read_models.models import (
    OperationsKeyValueItemModel,
    OperationsKeyValueSectionModel,
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.tool_metric_values import (
    duration_label,
)
from crxzipple.modules.operations.application.read_models.tool_run_time import (
    tool_run_duration_seconds,
)
from crxzipple.modules.tool.domain import (
    ToolRun,
    ToolRunAssignment,
    ToolRunStatus,
)

LONG_RUNNING_SECONDS = 300


def inline_risk_section(
    runs: list[ToolRun],
    *,
    active_runs: list[ToolRun],
    assignment_by_run: dict[str, ToolRunAssignment],
    now: datetime,
) -> OperationsKeyValueSectionModel:
    inline_runs = [run for run in runs if run.target.mode.value == "inline"]
    active_inline_runs = [
        run for run in active_runs if run.target.mode.value == "inline"
    ]
    failed_inline_runs = [
        run
        for run in inline_runs
        if run.status in {ToolRunStatus.FAILED, ToolRunStatus.TIMED_OUT}
    ]
    longest_inline_seconds = max(
        (
            tool_run_duration_seconds(
                run,
                assignment=assignment_by_run.get(run.id),
                now=now,
            )
            for run in inline_runs
        ),
        default=0,
    )
    inline_share = percent_label(len(inline_runs), len(runs))
    return OperationsKeyValueSectionModel(
        id="inline_risk",
        title="Inline Risk",
        items=(
            OperationsKeyValueItemModel(
                label="Active Inline Runs",
                value=str(len(active_inline_runs)),
                tone="warning" if active_inline_runs else "success",
            ),
            OperationsKeyValueItemModel(
                label="Inline Share",
                value=f"{inline_share} ({len(inline_runs)} / {len(runs)})",
                tone=(
                    "warning"
                    if inline_runs and len(inline_runs) == len(runs)
                    else "neutral"
                ),
            ),
            OperationsKeyValueItemModel(
                label="Inline Failures",
                value=str(len(failed_inline_runs)),
                tone="danger" if failed_inline_runs else "success",
            ),
            OperationsKeyValueItemModel(
                label="Longest Inline Duration",
                value=duration_label(longest_inline_seconds),
                tone=(
                    "warning"
                    if longest_inline_seconds >= LONG_RUNNING_SECONDS
                    else "neutral"
                ),
            ),
        ),
    )


def strategies_section(runs: list[ToolRun]) -> OperationsTableSectionModel:
    grouped: dict[tuple[str, str, str], list[ToolRun]] = {}
    for run in runs:
        key = (
            run.target.mode.value,
            run.target.strategy.value,
            run.target.environment.value,
        )
        grouped.setdefault(key, []).append(run)
    rows = []
    for (mode, strategy, environment), strategy_runs in sorted(grouped.items()):
        active = [run for run in strategy_runs if not run.is_terminal()]
        failures = [
            run
            for run in strategy_runs
            if run.status in {ToolRunStatus.FAILED, ToolRunStatus.TIMED_OUT}
        ]
        succeeded_count = len(
            [run for run in strategy_runs if run.status is ToolRunStatus.SUCCEEDED],
        )
        rows.append(
            OperationsTableRowModel(
                id=f"{mode}:{strategy}:{environment}",
                cells={
                    "mode": mode,
                    "strategy": strategy,
                    "environment": environment,
                    "runs": str(len(strategy_runs)),
                    "active": str(len(active)),
                    "failures": str(len(failures)),
                    "success_rate": percent_label(
                        succeeded_count,
                        len(strategy_runs),
                    ),
                },
                status="active" if active else "retained",
                tone="warning" if active else "danger" if failures else "success",
            ),
        )
    return OperationsTableSectionModel(
        id="strategies",
        title="Execution Strategies",
        columns=columns(
            ("mode", "Mode"),
            ("strategy", "Strategy"),
            ("environment", "Environment"),
            ("runs", "Runs"),
            ("active", "Active"),
            ("failures", "Failures"),
            ("success_rate", "Success Rate"),
        ),
        rows=tuple(rows),
        total=len(rows),
        view_all_route="/operations/tool?tab=strategies",
        empty_state="No tool execution strategies observed.",
    )


def percent_label(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0%"
    return f"{round((numerator / denominator) * 100)}%"


def columns(*items: tuple[str, str]) -> tuple[OperationsTableColumnModel, ...]:
    return tuple(
        OperationsTableColumnModel(key=column_id, label=label)
        for column_id, label in items
    )
