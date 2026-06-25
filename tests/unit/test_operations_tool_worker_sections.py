from __future__ import annotations

from datetime import datetime, timedelta, timezone

from crxzipple.modules.operations.application.read_models.tool_worker_pool_sections import (
    worker_pool_section,
)
from crxzipple.modules.operations.application.read_models.tool_worker_sections import (
    workers_section,
)
from crxzipple.modules.tool.domain import (
    ToolEnvironment,
    ToolExecutionStrategy,
    ToolExecutionTarget,
    ToolMode,
    ToolRun,
    ToolRunResult,
    ToolWorkerRegistration,
)


def _target() -> ToolExecutionTarget:
    return ToolExecutionTarget(
        mode=ToolMode.INLINE,
        strategy=ToolExecutionStrategy.ASYNC,
        environment=ToolEnvironment.LOCAL,
    )


def _run(run_id: str) -> ToolRun:
    return ToolRun.create(
        run_id=run_id,
        tool_id="flight.search",
        input_payload={},
        target=_target(),
    )


def _worker(now: datetime) -> ToolWorkerRegistration:
    worker = ToolWorkerRegistration.create(
        worker_id="worker-1",
        lease_seconds=600,
        max_in_flight=2,
        capabilities_payload={
            "concurrency_policy": {
                "default_max_in_flight": 2,
                "image_max_in_flight": 1,
                "shared_state_max_in_flight": 1,
            },
            "runtime_registry": {
                "registrations": [
                    {
                        "runtime_key": "openapi.eastern.flight",
                        "concurrency_key": "openapi:eastern",
                        "max_concurrency": 2,
                    },
                    {
                        "runtime_key": "mcp.weather",
                        "max_concurrency": 1,
                    },
                ],
            },
        },
    )
    worker.heartbeat_at = now
    worker.lease_expires_at = now + timedelta(minutes=10)
    worker.reserve_slot()
    return worker


def test_worker_pool_section_projects_registered_worker_buckets() -> None:
    now = datetime.now(timezone.utc)
    section = worker_pool_section(
        [_worker(now)],
        active_runs=[],
        now=now,
    )

    assert section.id == "worker_pool"
    assert section.total == 1
    assert [(segment.id, segment.label, segment.value, segment.tone) for segment in section.segments] == [
        ("active", "Active", 1, "info"),
    ]


def test_workers_section_projects_runtime_and_capacity_cells() -> None:
    now = datetime.now(timezone.utc)
    worker = _worker(now)
    active_run = _run("run-active")
    active_run.dispatch(worker_id=worker.id, lease_seconds=600)
    active_run.start()
    active_run.heartbeat_at = now
    active_run.lease_expires_at = now + timedelta(minutes=10)
    completed_run = _run("run-done")
    completed_run.dispatch(worker_id=worker.id, lease_seconds=600)
    completed_run.start()
    completed_run.succeed(ToolRunResult.text("done"))

    section = workers_section(
        [worker],
        active_runs=[active_run],
        runs=[active_run, completed_run],
        assignment_by_run={},
        now=now,
    )

    assert section.id == "workers"
    assert section.total == 1
    row = section.rows[0]
    assert row.id == worker.id
    assert row.status == "Active"
    assert row.tone == "info"
    assert row.cells["current_run"] == active_run.id
    assert row.cells["load"] == "1/2"
    assert row.cells["load_percent"] == "50%"
    assert row.cells["running"] == "1"
    assert row.cells["success_rate"] == "100%"
    assert row.cells["runtimes"] == "2"
    assert row.cells["providers"] == "mcp / weather, openapi / eastern"
    assert row.cells["capabilities"] == "image 1/worker, shared 1/worker, default 2/worker"
