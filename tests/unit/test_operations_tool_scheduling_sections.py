from __future__ import annotations

from datetime import datetime, timedelta, timezone

from crxzipple.modules.operations.application.read_models.tool_scheduling_blocker_sections import (
    run_blockers_section,
)
from crxzipple.modules.operations.application.read_models.tool_scheduling_capability_sections import (
    capability_limits_section,
)
from crxzipple.modules.operations.application.read_models.tool_scheduling_queue_sections import (
    tool_queue_section,
    tool_waiting_io_section,
)
from crxzipple.modules.tool.application.concurrency import ToolRunConcurrencyPolicy
from crxzipple.modules.tool.domain import (
    Tool,
    ToolEnvironment,
    ToolExecutionStrategy,
    ToolExecutionSupport,
    ToolExecutionTarget,
    ToolMode,
    ToolRun,
    ToolWorkerRegistration,
)


def _background_target() -> ToolExecutionTarget:
    return ToolExecutionTarget(
        mode=ToolMode.BACKGROUND,
        strategy=ToolExecutionStrategy.ASYNC,
        environment=ToolEnvironment.LOCAL,
    )


def _browser_tool() -> Tool:
    return Tool(
        id="browser.navigate",
        name="browser.navigate",
        description="Open a page",
        tags=("browser",),
        execution_support=ToolExecutionSupport(
            supported_modes=(ToolMode.BACKGROUND,),
        ),
    )


def _run(run_id: str) -> ToolRun:
    return ToolRun.create(
        run_id=run_id,
        tool_id="browser.navigate",
        input_payload={},
        target=_background_target(),
        invocation_context_payload={
            "run_id": "orch-run-1",
            "trace_id": "trace-1",
            "step_id": "step-1",
        },
    )


def test_queue_and_capability_sections_report_missing_worker_blocker() -> None:
    now = datetime.now(timezone.utc)
    queued = _run("run-queued")
    queued.queue()
    policy = ToolRunConcurrencyPolicy(shared_state_max_in_flight=1)

    queue = tool_queue_section(
        [queued],
        active_runs=[queued],
        tools=[_browser_tool()],
        workers=[],
        assignments=[],
        assignment_by_run={},
        concurrency_policy=policy,
        now=now,
    )
    capability = capability_limits_section(
        tools=[_browser_tool()],
        runs=[queued],
        workers=[],
        assignments=[],
        concurrency_policy=policy,
        now=now,
    )
    blockers = run_blockers_section(
        [queued],
        tools=[_browser_tool()],
        workers=[],
        assignments=[],
        assignment_by_run={},
        concurrency_policy=policy,
        now=now,
    )

    assert queue.rows[0].id == "waiting for online worker"
    assert queue.rows[0].cells["count"] == "1"
    capability_row = capability.rows[0]
    assert capability_row.id == "capability:browser"
    assert capability_row.cells["state"] == "No Worker"
    assert capability_row.cells["waiting"] == "1"
    blocker_row = blockers.rows[0]
    assert blocker_row.cells["reason"] == "waiting for online worker"
    assert blocker_row.cells["blocked_by"] == "worker_pool"
    assert blocker_row.cells["next_step"] == "start or recover worker"


def test_waiting_io_section_filters_capability_capacity_waits() -> None:
    now = datetime.now(timezone.utc)
    worker = ToolWorkerRegistration.create(
        worker_id="worker-1",
        lease_seconds=600,
        max_in_flight=2,
    )
    worker.heartbeat_at = now
    worker.lease_expires_at = now + timedelta(minutes=10)
    busy = _run("run-busy")
    busy.dispatch(worker_id=worker.id, lease_seconds=600)
    busy.start()
    queued = _run("run-queued")
    queued.queue()

    section = tool_waiting_io_section(
        [queued],
        active_runs=[busy, queued],
        tools=[_browser_tool()],
        workers=[worker],
        assignments=[],
        assignment_by_run={},
        concurrency_policy=ToolRunConcurrencyPolicy(shared_state_max_in_flight=1),
        now=now,
    )

    assert section.total == 1
    row = section.rows[0]
    assert row.id == queued.id
    assert row.cells["reason"] == "waiting for capability capacity"
    assert row.cells["external_service"] == "Local"
    assert row.cells["route"] == "/ui/workbench/runs/orch-run-1"
    assert row.cells["trace_route"] == "/workbench/traces/trace-1"
