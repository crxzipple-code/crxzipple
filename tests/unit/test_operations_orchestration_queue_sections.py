from __future__ import annotations

from datetime import datetime, timedelta, timezone

from crxzipple.modules.dispatch.domain import DispatchTask, DispatchTaskStatus
from crxzipple.modules.operations.application.read_models.orchestration_queue_sections import (
    run_queue_section,
)
from crxzipple.modules.orchestration.domain import (
    InboundInstruction,
    OrchestrationRun,
    OrchestrationRunStage,
    OrchestrationRunStatus,
)


def test_run_queue_section_renders_dispatch_backed_queue_rows() -> None:
    now = datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)
    run = OrchestrationRun(
        id="run-a",
        inbound_instruction=InboundInstruction(source="test", content="hello"),
        status=OrchestrationRunStatus.QUEUED,
        stage=OrchestrationRunStage.QUEUED,
        agent_id="agent-a",
        lane_key="run-lane",
        priority=9,
        created_at=now - timedelta(seconds=180),
        queued_at=now - timedelta(seconds=150),
        updated_at=now - timedelta(seconds=120),
        metadata={"trace_id": "trace-a"},
    )
    dispatch_task = DispatchTask(
        id="dispatch-a",
        owner_kind="orchestration.step",
        owner_id="step-a",
        lane_key="dispatch-lane",
        status=DispatchTaskStatus.CLAIMED,
        priority=2,
        claimed_by="worker-a",
        waiting_reason="worker-claimed",
        created_at=now - timedelta(seconds=100),
        queued_at=now - timedelta(seconds=90),
        lease_expires_at=now + timedelta(seconds=60),
    )

    section = run_queue_section(
        [run],
        dispatch_task_by_run_id={run.id: dispatch_task},
        now=now,
    )

    assert section.id == "run_queue"
    assert section.total == 1
    row = section.rows[0]
    assert row.status == "claimed"
    assert row.tone == "info"
    assert row.cells["priority"] == "P2"
    assert row.cells["lane_key"] == "dispatch-lane"
    assert row.cells["wait_reason"] == "worker-claimed"
    assert row.cells["dispatch_status"] == "claimed"
    assert row.cells["dispatch_worker"] == "worker-a"
    assert row.cells["wait_time"] == "1m 30s"
    assert row.cells["route"] == "/ui/workbench/runs/run-a"
    assert row.cells["trace_route"] == "/workbench/traces/trace-a"
