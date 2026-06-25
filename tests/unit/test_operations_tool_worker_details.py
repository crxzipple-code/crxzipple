from __future__ import annotations

from datetime import datetime, timedelta, timezone

from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.tool_worker_details import (
    tool_worker_details,
)
from crxzipple.modules.tool.domain import (
    ToolEnvironment,
    ToolExecutionStrategy,
    ToolExecutionTarget,
    ToolMode,
    ToolRun,
    ToolWorkerRegistration,
)


def _target() -> ToolExecutionTarget:
    return ToolExecutionTarget(
        mode=ToolMode.INLINE,
        strategy=ToolExecutionStrategy.ASYNC,
        environment=ToolEnvironment.LOCAL,
    )


def _run(run_id: str, *, worker_id: str) -> ToolRun:
    run = ToolRun.create(
        run_id=run_id,
        tool_id="flight.search",
        input_payload={},
        target=_target(),
    )
    run.dispatch(worker_id=worker_id, lease_seconds=600)
    run.start()
    return run


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
                ],
            },
        },
    )
    worker.heartbeat_at = now
    worker.lease_expires_at = now + timedelta(minutes=10)
    worker.reserve_slot()
    return worker


def _event(now: datetime, *, worker_id: str) -> OperationsObservedEvent:
    return OperationsObservedEvent(
        id="event-1",
        cursor="cursor-1",
        topic="events.named.tool.worker.registered",
        event_name="tool.worker.registered",
        module="tool",
        owner="tool",
        kind="fact",
        level="info",
        status="registered",
        entity_id=worker_id,
        run_id=None,
        trace_id=None,
        source_event_name="tool.worker.registered",
        occurred_at=now,
        payload={"worker_id": worker_id, "max_in_flight": 2},
    )


def test_tool_worker_details_project_summary_runtimes_and_events() -> None:
    now = datetime.now(timezone.utc)
    worker = _worker(now)
    active_run = _run("run-active", worker_id=worker.id)

    details = tool_worker_details(
        [worker],
        active_runs=[active_run],
        observed_events=(_event(now, worker_id=worker.id),),
        now=now,
    )

    assert len(details) == 1
    detail = details[0]
    assert detail.worker_id == worker.id
    assert detail.status == "Active"
    assert detail.tone == "info"
    summary = {item.label: item.value for item in detail.summary}
    assert summary["Worker ID"] == worker.id
    assert summary["Worker Load"] == "1/2"
    assert summary["Current Run"] == active_run.id
    assert summary["Runtime Count"] == "1"
    assert summary["Providers"] == "openapi / eastern"
    assert detail.capabilities.id == "worker_capabilities"
    assert detail.runtimes.id == "worker_runtimes"
    assert detail.runtimes.total == 1
    assert detail.runtimes.rows[0].cells["runtime_key"] == "openapi.eastern.flight"
    assert detail.provider_limits.id == "worker_provider_limits"
    assert detail.events.id == "worker_events"
    assert detail.events.total == 1
    assert detail.events.rows[0].cells["event"] == "worker.registered"
    assert detail.raw_payload["runtime_registry"]["registrations"][0]["runtime_key"] == (
        "openapi.eastern.flight"
    )
