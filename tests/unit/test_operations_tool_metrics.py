from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from crxzipple.modules.operations.application.read_models.tool_metrics import (
    tool_health,
    tool_metric_cards,
)
from crxzipple.modules.tool.domain import (
    Tool,
    ToolEnvironment,
    ToolExecutionPolicy,
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


def test_tool_health_reflects_failed_active_and_empty_catalog_states() -> None:
    tool = Tool(id="browser.navigate", name="browser.navigate", description="Open tab")
    active_run = ToolRun.create(
        run_id="run-active",
        tool_id=tool.id,
        input_payload={},
        target=_target(),
    )
    failed_run = ToolRun.create(
        run_id="run-failed",
        tool_id=tool.id,
        input_payload={},
        target=_target(),
    )
    failed_run.start()
    failed_run.fail("boom")

    assert tool_health(tools=[], active_runs=[], failed_runs=[]) == "warning"
    assert tool_health(tools=[tool], active_runs=[active_run], failed_runs=[]) == "healthy"
    assert tool_health(tools=[tool], active_runs=[], failed_runs=[failed_run]) == "warning"


def test_tool_metric_cards_include_runtime_policy_and_online_capacity() -> None:
    now = datetime.now(timezone.utc)
    tool = Tool(
        id="browser.navigate",
        name="browser.navigate",
        description="Open tab",
        access_requirement_sets=(("browser.profile",),),
        execution_policy=ToolExecutionPolicy(requires_confirmation=True),
    )
    succeeded_run = ToolRun.create(
        run_id="run-succeeded",
        tool_id=tool.id,
        input_payload={},
        target=_target(),
    )
    succeeded_run.start()
    succeeded_run.succeed(ToolRunResult.text("ok"))
    queued_run = ToolRun.create(
        run_id="run-queued",
        tool_id=tool.id,
        input_payload={},
        target=_target(),
    )
    queued_run.queue()
    worker = ToolWorkerRegistration(
        id="worker-1",
        max_in_flight=3,
        current_in_flight=1,
        lease_expires_at=now + timedelta(minutes=5),
    )
    runtime_config = SimpleNamespace(
        tool_worker_max_in_flight=4,
        tool_worker_default_run_concurrency=2,
        tool_worker_image_run_concurrency=1,
        tool_worker_shared_state_run_concurrency=1,
        tool_run_max_attempts=5,
        tool_run_lease_seconds=30,
        tool_run_heartbeat_seconds=10,
        tool_remote_default_max_concurrency=6,
    )

    cards = tool_metric_cards(
        tools=[tool],
        runs=[succeeded_run, queued_run],
        active_runs=[queued_run],
        failed_runs=[],
        health="healthy",
        workers=[worker],
        now=now,
        runtime_bootstrap_config=runtime_config,
    )
    by_id = {card.id: card for card in cards}

    assert list(by_id) == [
        "health",
        "catalog",
        "active_runs",
        "failed_runs",
        "avg_latency",
        "p95_latency",
        "throughput",
        "confirmation",
        "access_gated",
        "worker_policy",
        "retry_policy",
    ]
    assert by_id["active_runs"].delta == "1 queued / 3 capacity"
    assert by_id["confirmation"].value == "1"
    assert by_id["access_gated"].value == "1"
    assert by_id["worker_policy"].value == "4"
    assert by_id["worker_policy"].delta == "default 2 / image 1 / shared 1"
    assert by_id["retry_policy"].value == "5x / 30s / 10s"
    assert by_id["retry_policy"].delta == "remote 6"
