from __future__ import annotations

from datetime import datetime, timedelta, timezone

from crxzipple.modules.dispatch.domain import DispatchTask, DispatchTaskStatus
from crxzipple.modules.operations.application.read_models.orchestration_overview_rows import (
    executor_capabilities_label,
    executor_rows,
    lane_lock_rows,
    queue_rows,
)
from crxzipple.modules.orchestration.domain import (
    InboundInstruction,
    OrchestrationExecutorLease,
    OrchestrationRun,
    OrchestrationRunStage,
    OrchestrationRunStatus,
)


def _run(
    run_id: str,
    *,
    now: datetime,
    status: OrchestrationRunStatus = OrchestrationRunStatus.QUEUED,
    stage: OrchestrationRunStage = OrchestrationRunStage.QUEUED,
    priority: int = 100,
    lane_key: str | None = None,
    lane_lock_key: str | None = None,
    worker_id: str | None = None,
    created_age_seconds: int = 120,
    queued_age_seconds: int | None = 90,
    updated_age_seconds: int = 30,
) -> OrchestrationRun:
    return OrchestrationRun(
        id=run_id,
        inbound_instruction=InboundInstruction(source="test", content="hello"),
        status=status,
        stage=stage,
        priority=priority,
        lane_key=lane_key,
        lane_lock_key=lane_lock_key,
        worker_id=worker_id,
        created_at=now - timedelta(seconds=created_age_seconds),
        queued_at=(
            now - timedelta(seconds=queued_age_seconds)
            if queued_age_seconds is not None
            else None
        ),
        updated_at=now - timedelta(seconds=updated_age_seconds),
        started_at=now - timedelta(seconds=updated_age_seconds),
    )


def test_queue_rows_prefers_dispatch_projection_values() -> None:
    now = datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)
    run = _run("run-a", now=now, priority=10, lane_key="run-lane")
    dispatch_task = DispatchTask(
        id="dispatch-a",
        owner_kind="orchestration.step",
        owner_id="step-a",
        lane_key="dispatch-lane",
        status=DispatchTaskStatus.QUEUED,
        priority=2,
        waiting_reason="waiting-slot",
        created_at=now - timedelta(seconds=300),
        queued_at=now - timedelta(seconds=90),
    )

    rows = queue_rows(
        [run],
        dispatch_task_by_run_id={run.id: dispatch_task},
        now=now,
    )

    assert rows == (
        {
            "Priority": "P2",
            "Run ID": "run-a",
            "Lane Key": "dispatch-lane",
            "Wait Reason": "waiting-slot",
            "Dispatch": "queued",
            "Wait Time": "1m 30s",
        },
    )


def test_lane_lock_rows_show_active_holders_newest_first() -> None:
    now = datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)
    older = _run(
        "run-old",
        now=now,
        status=OrchestrationRunStatus.RUNNING,
        stage=OrchestrationRunStage.RUNNING,
        lane_lock_key="lane-old",
        updated_age_seconds=60,
    )
    newer = _run(
        "run-new",
        now=now,
        status=OrchestrationRunStatus.RUNNING,
        stage=OrchestrationRunStage.TOOL,
        lane_lock_key="lane-new",
        updated_age_seconds=5,
    )

    rows = lane_lock_rows([older, newer], now=now)

    assert rows[0]["Holder Run ID"] == "run-new"
    assert rows[0]["Lane Key"] == "lane-new"
    assert rows[0]["Reason"] == "active tool"
    assert rows[1]["Holder Run ID"] == "run-old"


def test_executor_rows_render_load_current_run_and_capabilities() -> None:
    now = datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)
    lease = OrchestrationExecutorLease(
        id="worker-a",
        max_inflight_assignments=4,
        inflight_assignment_count=2,
        metadata={
            "runtime_registry": {
                "tool_names": ["shell", "python", "browser", "weather", "extra"],
            },
        },
        last_heartbeat_at=now - timedelta(seconds=10),
    )
    run = _run(
        "run-a",
        now=now,
        status=OrchestrationRunStatus.RUNNING,
        stage=OrchestrationRunStage.RUNNING,
        worker_id="worker-a",
    )

    rows = executor_rows([lease], running_runs=[run], now=now)

    assert rows[0]["Worker ID"] == "worker-a"
    assert rows[0]["Status"] == "online"
    assert rows[0]["Current Run"] == "run-a"
    assert rows[0]["Load"] == "50%"
    assert rows[0]["Capabilities"] == "shell, python, browser, weather"


def test_executor_capabilities_label_uses_explicit_capabilities_first() -> None:
    lease = OrchestrationExecutorLease(
        id="worker-a",
        max_inflight_assignments=2,
        metadata={"capabilities": "shell, python, browser, extra, ignored"},
    )

    assert executor_capabilities_label(lease) == "shell, python, browser, extra"
