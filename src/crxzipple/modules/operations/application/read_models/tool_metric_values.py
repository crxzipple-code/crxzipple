from __future__ import annotations

from datetime import datetime

from crxzipple.modules.operations.application.read_models.tool_run_time import (
    tool_run_time,
)
from crxzipple.modules.tool.domain import ToolRun
from crxzipple.shared.time import coerce_utc_datetime


def terminal_run_duration_seconds(run: ToolRun) -> int | None:
    if not run.is_terminal() or run.started_at is None or run.completed_at is None:
        return None
    return max(
        int(
            (
                coerce_utc_datetime(run.completed_at)
                - coerce_utc_datetime(run.started_at)
            ).total_seconds(),
        ),
        0,
    )


def runs_since(runs: list[ToolRun], *, since: datetime) -> list[ToolRun]:
    cutoff = coerce_utc_datetime(since)
    return [run for run in runs if coerce_utc_datetime(tool_run_time(run)) >= cutoff]


def duration_label(seconds: int) -> str:
    seconds = max(seconds, 0)
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


def percentile_int(values: list[int], percentile: int) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    pct = min(max(int(percentile), 0), 100)
    index = round((pct / 100) * (len(ordered) - 1))
    return ordered[index]


def throughput_label(count_24h: int) -> str:
    per_hour = count_24h / 24
    if per_hour <= 0:
        return "0/h"
    if per_hour < 1:
        return f"{per_hour:.1f}/h"
    return f"{int(round(per_hour))}/h"
