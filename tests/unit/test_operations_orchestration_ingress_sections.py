from __future__ import annotations

from datetime import datetime, timedelta, timezone

from crxzipple.modules.dispatch.domain import DispatchTask, DispatchTaskStatus
from crxzipple.modules.operations.application.read_models.orchestration_ingress_sections import (
    ingress_queue_section,
)
from crxzipple.modules.operations.application.read_models.orchestration_ingress_state import (
    pending_ingress_requests,
)
from crxzipple.modules.orchestration.domain import (
    InboundInstruction,
    OrchestrationIngressRequest,
    OrchestrationRun,
    OrchestrationRunStage,
    OrchestrationRunStatus,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    OrchestrationIngressStatus,
)


def test_pending_ingress_requests_include_active_dispatch_tasks() -> None:
    now = datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)
    completed_with_active_dispatch = OrchestrationIngressRequest(
        id="ingress-active",
        run_id="run-active",
        route_context_payload={"surface": "web"},
        status=OrchestrationIngressStatus.COMPLETED,
        created_at=now - timedelta(seconds=120),
        updated_at=now - timedelta(seconds=90),
    )
    queued_without_dispatch = OrchestrationIngressRequest(
        id="ingress-queued",
        run_id="run-queued",
        route_context_payload={"surface": "web"},
        status=OrchestrationIngressStatus.QUEUED,
        created_at=now - timedelta(seconds=60),
        updated_at=now - timedelta(seconds=30),
    )
    completed_without_dispatch = OrchestrationIngressRequest(
        id="ingress-done",
        run_id="run-done",
        route_context_payload={"surface": "web"},
        status=OrchestrationIngressStatus.COMPLETED,
        created_at=now - timedelta(seconds=60),
        updated_at=now - timedelta(seconds=30),
    )
    dispatch_task = DispatchTask(
        id="dispatch-active",
        owner_kind="orchestration.ingress",
        owner_id="ingress-active",
        status=DispatchTaskStatus.QUEUED,
    )

    pending = pending_ingress_requests(
        [
            completed_with_active_dispatch,
            queued_without_dispatch,
            completed_without_dispatch,
        ],
        dispatch_task_by_request_id={"ingress-active": dispatch_task},
    )

    assert [request.id for request in pending] == ["ingress-active", "ingress-queued"]


def test_ingress_queue_section_renders_dispatch_backed_request_rows() -> None:
    now = datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)
    run = OrchestrationRun(
        id="run-a",
        inbound_instruction=InboundInstruction(source="web", content="hello"),
        status=OrchestrationRunStatus.QUEUED,
        stage=OrchestrationRunStage.QUEUED,
        lane_key="run-lane",
        priority=7,
        metadata={"session_key": "session-a", "trace_id": "trace-a"},
        created_at=now - timedelta(seconds=240),
        queued_at=now - timedelta(seconds=210),
        updated_at=now - timedelta(seconds=180),
    )
    request = OrchestrationIngressRequest(
        id="ingress-a",
        run_id=run.id,
        route_context_payload={"surface": "web", "main_key": "route-lane"},
        priority=5,
        status=OrchestrationIngressStatus.QUEUED,
        created_at=now - timedelta(seconds=120),
        updated_at=now - timedelta(seconds=90),
    )
    dispatch_task = DispatchTask(
        id="dispatch-a",
        owner_kind="orchestration.ingress",
        owner_id=request.id,
        status=DispatchTaskStatus.CLAIMED,
        priority=2,
        claimed_by="worker-a",
        created_at=now - timedelta(seconds=90),
        queued_at=now - timedelta(seconds=80),
        lease_expires_at=now + timedelta(seconds=60),
    )

    section = ingress_queue_section(
        [request],
        fallback_runs=[],
        run_by_id={run.id: run},
        dispatch_task_by_request_id={request.id: dispatch_task},
        now=now,
    )

    assert section.id == "ingress_queue"
    assert section.total == 1
    row = section.rows[0]
    assert row.status == "claimed"
    assert row.tone == "info"
    assert row.cells["source"] == "web"
    assert row.cells["target_lane"] == "run-lane"
    assert row.cells["priority"] == "P2"
    assert row.cells["dispatch_worker"] == "worker-a"
    assert row.cells["summary"] == "hello"
    assert row.cells["trace_route"] == "/workbench/traces/trace-a"
