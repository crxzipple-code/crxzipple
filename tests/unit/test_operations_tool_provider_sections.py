from __future__ import annotations

from datetime import datetime, timezone

from crxzipple.modules.operations.application.read_models.tool_provider_limits import (
    provider_limits_section,
)
from crxzipple.modules.operations.application.read_models.tool_worker_provider_limits import (
    tool_worker_provider_limits_section,
)
from crxzipple.modules.operations.application.read_models.tool_provider_sections import (
    provider_history_section,
)
from crxzipple.modules.tool.application.concurrency import ToolRunConcurrencyPolicy
from crxzipple.modules.tool.domain import (
    Tool,
    ToolEnvironment,
    ToolExecutionStrategy,
    ToolExecutionTarget,
    ToolMode,
    ToolRun,
    ToolRunResult,
    ToolWorkerRegistration,
)


class _RuntimeMetrics:
    def snapshot(self, *, prefixes: tuple[str, ...]) -> dict[str, object]:
        assert prefixes == ("tool.remote_provider_limiter.",)
        return {
            "gauges": [
                {
                    "name": "tool.remote_provider_limiter.active",
                    "value": 2,
                    "labels": {"provider_key": "provider:openai"},
                },
                {
                    "name": "tool.remote_provider_limiter.waiters",
                    "value": 1,
                    "labels": {"provider_key": "provider:openai"},
                },
            ],
            "timings": [
                {
                    "name": "tool.remote_provider_limiter.wait_seconds",
                    "count": 2,
                    "total_seconds": 1.0,
                    "max_seconds": 0.75,
                    "labels": {"provider_key": "provider:openai"},
                },
            ],
        }


class _RuntimeRegistry:
    def snapshot(self) -> dict[str, object]:
        return {
            "registrations": [
                {
                    "runtime_key": "openai.responses",
                    "concurrency_key": "provider:openai",
                    "max_concurrency": 4,
                },
            ],
        }


def _target() -> ToolExecutionTarget:
    return ToolExecutionTarget(
        mode=ToolMode.INLINE,
        strategy=ToolExecutionStrategy.ASYNC,
        environment=ToolEnvironment.LOCAL,
    )


def test_provider_limits_section_combines_registry_and_metrics() -> None:
    section = provider_limits_section(
        tools=[],
        runs=[],
        workers=[],
        assignments=[],
        concurrency_policy=ToolRunConcurrencyPolicy(),
        runtime_metrics=_RuntimeMetrics(),
        runtime_registry=_RuntimeRegistry(),
        now=datetime.now(timezone.utc),
    )

    assert section.id == "provider_limits"
    assert section.total == 1
    row = section.rows[0]
    assert row.id == "provider:openai"
    assert row.cells["provider"] == "openai"
    assert row.cells["state"] == "Waiting"
    assert row.cells["limit"] == "4/proc"
    assert row.cells["capacity"] == "2/4"
    assert row.cells["waiting"] == "1"
    assert row.cells["runtimes"] == "1"
    assert row.cells["wait_count"] == "2"
    assert row.cells["avg_wait"] == "500ms"
    assert row.cells["max_wait"] == "750ms"
    assert row.cells["sources"] == "api-process"


def test_provider_history_section_groups_runs_by_provider_key() -> None:
    tool = Tool(
        id="flight.search",
        name="flight.search",
        description="Search flights",
        runtime_key="openapi.eastern.flight",
    )
    run = ToolRun.create(
        run_id="run-1",
        tool_id=tool.id,
        input_payload={},
        target=_target(),
    )
    run.start()
    run.succeed(ToolRunResult.text("done"))

    section = provider_history_section(
        tools=[tool],
        runs=[run],
        assignment_by_run={},
        now=datetime.now(timezone.utc),
    )

    assert section.id == "provider_history"
    row = section.rows[0]
    assert row.id == "openapi:eastern"
    assert row.cells["provider"] == "openapi / eastern"
    assert row.cells["state"] == "Healthy"
    assert row.cells["tools"] == "1"
    assert row.cells["runs"] == "1"
    assert row.cells["success_rate"] == "100%"


def test_worker_provider_limits_section_projects_worker_runtime_metrics() -> None:
    worker = ToolWorkerRegistration.create(
        worker_id="worker-1",
        lease_seconds=600,
        max_in_flight=2,
        capabilities_payload={
            "runtime_registry": {
                "registrations": [
                    {
                        "runtime_key": "mcp.weather",
                        "concurrency_key": "mcp:weather",
                        "max_concurrency": 3,
                    },
                ],
            },
            "runtime_metrics": {
                "gauges": [
                    {
                        "name": "tool.remote_provider_limiter.active",
                        "value": 1,
                        "labels": {"provider_key": "mcp:weather"},
                    },
                ],
                "timings": [],
            },
        },
    )

    section = tool_worker_provider_limits_section(worker)

    assert section.id == "worker_provider_limits"
    row = section.rows[0]
    assert row.id == "mcp:weather"
    assert row.cells["provider"] == "mcp / weather"
    assert row.cells["limit"] == "3/worker"
    assert row.cells["capacity"] == "1/3"
