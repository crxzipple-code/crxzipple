from __future__ import annotations

from datetime import datetime

from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.orchestration.domain.value_objects import OrchestrationRunStatus
from crxzipple.shared.time import coerce_utc_datetime


def duration_label(duration_ms: int | None) -> str:
    if duration_ms is None:
        return "-"
    if duration_ms < 1000:
        return f"{duration_ms}ms"
    seconds = round(duration_ms / 1000)
    minutes = seconds // 60
    remaining = seconds % 60
    if minutes:
        return f"{minutes}m {remaining}s"
    return f"{remaining}s"


def duration_ms(run: OrchestrationRun) -> int | None:
    started_at = run.started_at or run.queued_at or run.created_at
    ended_at = run.completed_at
    if ended_at is None and run.status not in {
        OrchestrationRunStatus.COMPLETED,
        OrchestrationRunStatus.FAILED,
        OrchestrationRunStatus.CANCELLED,
    }:
        ended_at = run.updated_at
    return span_ms(started_at, ended_at)


def span_ms(started_at: datetime | None, ended_at: datetime | None) -> int | None:
    if started_at is None or ended_at is None:
        return None
    start = coerce_utc_datetime(started_at)
    end = coerce_utc_datetime(ended_at)
    return max(int((end - start).total_seconds() * 1000), 0)
