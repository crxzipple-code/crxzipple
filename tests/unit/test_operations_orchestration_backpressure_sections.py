from __future__ import annotations

from datetime import datetime, timedelta, timezone

from crxzipple.modules.operations.application.read_models.orchestration_backpressure_sections import (
    active_lane_keys,
    backpressure_section,
)
from crxzipple.modules.operations.application.read_models.orchestration_stuck_run_sections import (
    stuck_runs_section,
)
from crxzipple.modules.orchestration.domain import (
    InboundInstruction,
    OrchestrationRun,
    OrchestrationRunStage,
    OrchestrationRunStatus,
)


def _run(
    run_id: str,
    *,
    now: datetime,
    status: OrchestrationRunStatus,
    stage: OrchestrationRunStage,
    lane_key: str | None = None,
    lane_lock_key: str | None = None,
    waiting_reason: str | None = None,
    pending_tool_run_ids: tuple[str, ...] = (),
    created_age_seconds: int = 120,
    queued_age_seconds: int | None = 90,
    updated_age_seconds: int = 30,
) -> OrchestrationRun:
    return OrchestrationRun(
        id=run_id,
        inbound_instruction=InboundInstruction(source="test", content="hello"),
        status=status,
        stage=stage,
        lane_key=lane_key,
        lane_lock_key=lane_lock_key,
        waiting_reason=waiting_reason,
        pending_tool_run_ids=pending_tool_run_ids,
        created_at=now - timedelta(seconds=created_age_seconds),
        queued_at=(
            now - timedelta(seconds=queued_age_seconds)
            if queued_age_seconds is not None
            else None
        ),
        updated_at=now - timedelta(seconds=updated_age_seconds),
        started_at=now - timedelta(seconds=updated_age_seconds),
    )


def test_backpressure_section_groups_runs_by_generic_wait_reason() -> None:
    now = datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)
    running_holder = _run(
        "run-holder",
        now=now,
        status=OrchestrationRunStatus.RUNNING,
        stage=OrchestrationRunStage.RUNNING,
        lane_lock_key="lane-a",
    )
    queued_lane_blocked = _run(
        "run-lane",
        now=now,
        status=OrchestrationRunStatus.QUEUED,
        stage=OrchestrationRunStage.QUEUED,
        lane_key="lane-a",
    )
    waiting_tool = _run(
        "run-tool",
        now=now,
        status=OrchestrationRunStatus.WAITING,
        stage=OrchestrationRunStage.WAITING_ON_TOOL,
        pending_tool_run_ids=("tool-a",),
    )

    section = backpressure_section(
        queued_runs=[queued_lane_blocked],
        waiting_runs=[waiting_tool],
        active_lane_keys=active_lane_keys([running_holder], []),
        available_executor_slots=0,
    )

    segments = {segment.id: segment.value for segment in section.segments}
    assert section.id == "backpressure"
    assert section.total == 2
    assert segments == {"lane_lock": 1, "tool": 1}


def test_stuck_runs_section_reports_time_based_buckets() -> None:
    now = datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)
    queued_stuck = _run(
        "run-queued",
        now=now,
        status=OrchestrationRunStatus.QUEUED,
        stage=OrchestrationRunStage.QUEUED,
        queued_age_seconds=360,
        updated_age_seconds=360,
    )
    running_stale = _run(
        "run-running",
        now=now,
        status=OrchestrationRunStatus.RUNNING,
        stage=OrchestrationRunStage.RUNNING,
        updated_age_seconds=660,
    )
    waiting_approval = _run(
        "run-approval",
        now=now,
        status=OrchestrationRunStatus.WAITING,
        stage=OrchestrationRunStage.WAITING_FOR_CONFIRMATION,
    )

    section = stuck_runs_section(
        queued_runs=[queued_stuck],
        running_runs=[running_stale],
        waiting_runs=[waiting_approval],
        now=now,
    )

    rows = {row.id: row for row in section.rows}
    assert section.id == "stuck_runs"
    assert rows["queued_over_5m"].cells["count"] == "1"
    assert rows["queued_over_5m"].cells["oldest"] == "6m 0s"
    assert rows["running_stale"].tone == "danger"
    assert rows["waiting_approval"].cells["recommended_action"] == "Resolve approval"
