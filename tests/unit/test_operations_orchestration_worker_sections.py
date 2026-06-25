from __future__ import annotations

from datetime import datetime, timedelta, timezone

from crxzipple.modules.operations.application.read_models.orchestration_worker_sections import (
    executor_section,
    lane_locks_section,
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
    status: OrchestrationRunStatus = OrchestrationRunStatus.RUNNING,
    stage: OrchestrationRunStage = OrchestrationRunStage.RUNNING,
    lane_key: str | None = None,
    lane_lock_key: str | None = None,
    worker_id: str | None = None,
    current_step: int = 1,
    max_steps: int = 10,
    started_age_seconds: int = 60,
    updated_age_seconds: int = 10,
    completed_age_seconds: int | None = None,
) -> OrchestrationRun:
    return OrchestrationRun(
        id=run_id,
        inbound_instruction=InboundInstruction(source="test", content="hello"),
        status=status,
        stage=stage,
        lane_key=lane_key,
        lane_lock_key=lane_lock_key,
        worker_id=worker_id,
        current_step=current_step,
        max_steps=max_steps,
        created_at=now - timedelta(seconds=started_age_seconds + 30),
        queued_at=now - timedelta(seconds=started_age_seconds + 20),
        started_at=now - timedelta(seconds=started_age_seconds),
        updated_at=now - timedelta(seconds=updated_age_seconds),
        completed_at=(
            now - timedelta(seconds=completed_age_seconds)
            if completed_age_seconds is not None
            else None
        ),
    )


def test_lane_locks_section_renders_lock_owner_and_lease_ttl() -> None:
    now = datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)
    lease = OrchestrationExecutorLease(
        id="worker-a",
        lease_expires_at=now + timedelta(seconds=45),
        last_heartbeat_at=now - timedelta(seconds=5),
    )
    run = _run(
        "run-a",
        now=now,
        stage=OrchestrationRunStage.TOOL,
        lane_key="lane-a",
        lane_lock_key="lane-a-lock",
        worker_id="worker-a",
        current_step=5,
        max_steps=10,
    )

    section = lane_locks_section([run], leases=[lease], now=now)

    assert section.id == "lane_locks"
    assert section.total == 1
    row = section.rows[0]
    assert row.cells["lane_key"] == "lane-a-lock"
    assert row.cells["holder_run_id"] == "run-a"
    assert row.cells["type"] == "tool.call"
    assert row.cells["progress"] == "50%"
    assert row.cells["ttl"] == "45s"
    assert row.cells["trace_route"] == "/workbench/traces/run-a"


def test_executor_section_renders_capacity_and_recent_worker_runs() -> None:
    now = datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)
    lease = OrchestrationExecutorLease(
        id="worker-a",
        max_inflight_assignments=2,
        inflight_assignment_count=1,
        metadata={"service_set": "local-dev"},
        last_heartbeat_at=now - timedelta(seconds=15),
    )
    running = _run("run-running", now=now, worker_id="worker-a")
    recent_done = _run(
        "run-done",
        now=now,
        status=OrchestrationRunStatus.COMPLETED,
        stage=OrchestrationRunStage.COMPLETED,
        worker_id="worker-a",
        completed_age_seconds=30,
    )
    old_done = _run(
        "run-old",
        now=now,
        status=OrchestrationRunStatus.COMPLETED,
        stage=OrchestrationRunStage.COMPLETED,
        worker_id="worker-a",
        completed_age_seconds=360,
    )

    section = executor_section(
        [lease],
        runs=[running, recent_done, old_done],
        running_runs=[running],
        now=now,
    )

    assert section.id == "executor_overview"
    row = section.rows[0]
    assert row.cells["worker_id"] == "worker-a"
    assert row.cells["current_run"] == "run-running"
    assert row.cells["load"] == "50%"
    assert row.cells["available_slots"] == "1"
    assert row.cells["capabilities"] == "local-dev"
    assert row.cells["runs_5m"] == "1"
