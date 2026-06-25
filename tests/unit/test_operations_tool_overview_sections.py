from __future__ import annotations

from datetime import datetime, timedelta, timezone

from crxzipple.modules.operations.application.read_models.tool_overview_actions import (
    tool_actions,
)
from crxzipple.modules.operations.application.read_models.tool_overview_execution_sections import (
    inline_risk_section,
    strategies_section,
)
from crxzipple.modules.operations.application.read_models.tool_overview_rows import (
    queue_rows,
    risk_rows,
    worker_rows,
)
from crxzipple.modules.operations.application.read_models.tool_overview_type_sections import (
    tool_types_section,
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


def _tool(
    tool_id: str,
    *,
    name: str | None = None,
    execution_policy: ToolExecutionPolicy | None = None,
    access_requirement_sets: tuple[tuple[str, ...], ...] = (),
    runtime_requirement_sets: tuple[tuple[str, ...], ...] = (),
) -> Tool:
    return Tool(
        id=tool_id,
        name=name or tool_id,
        description=f"{tool_id} test tool.",
        execution_policy=execution_policy or ToolExecutionPolicy(),
        access_requirement_sets=access_requirement_sets,
        runtime_requirement_sets=runtime_requirement_sets,
    )


def _run(run_id: str, *, tool_id: str) -> ToolRun:
    return ToolRun.create(
        run_id=run_id,
        tool_id=tool_id,
        input_payload={},
        target=_target(),
    )


def test_tool_actions_expose_runtime_navigation_and_control_actions() -> None:
    actions = {action.id: action for action in tool_actions()}

    assert list(actions) == [
        "open_tool",
        "open_trace",
        "cancel_tool_run",
        "retry_tool_run",
        "prune_expired_workers",
        "open_access",
    ]
    assert actions["cancel_tool_run"].requires_confirmation is True
    assert actions["open_access"].endpoint == "/operations/access"


def test_queue_risk_and_worker_rows_project_overview_tables() -> None:
    now = datetime.now(timezone.utc)
    risky_tool = _tool(
        "browser.click",
        execution_policy=ToolExecutionPolicy(
            timeout_seconds=45,
            requires_confirmation=True,
            mutates_state=True,
        ),
        access_requirement_sets=(("browser.profile",),),
        runtime_requirement_sets=(("browser-runtime",),),
    )
    run = _run("run-queued", tool_id=risky_tool.id)
    run.queue()
    run.created_at = now - timedelta(seconds=90)
    worker = ToolWorkerRegistration.create(
        worker_id="worker-1",
        lease_seconds=600,
        max_in_flight=2,
    )
    worker.heartbeat_at = now

    queue = queue_rows([run], assignment_by_run={}, now=now)
    risks = risk_rows([risky_tool])
    workers = worker_rows([worker], active_runs=[run])

    assert queue[0]["Run ID"] == run.id
    assert queue[0]["Wait Reason"] == "queued"
    assert queue[0]["Wait Time"] == "1m 30s"
    assert risks[0]["Lane Key"] == risky_tool.id
    assert risks[0]["TTL"] == "45s"
    assert "confirmation" in risks[0]["Reason"]
    assert "access: browser.profile" in risks[0]["Reason"]
    assert workers[0]["Worker ID"] == worker.id
    assert workers[0]["Load"] == "0/2"


def test_tool_types_inline_risk_and_strategies_project_run_mix() -> None:
    now = datetime.now(timezone.utc)
    flight_tool = _tool("flight.search", name="Flight Search")
    browser_tool = _tool("browser.snapshot", name="Browser Snapshot")
    succeeded = _run("run-succeeded", tool_id=flight_tool.id)
    succeeded.start()
    succeeded.succeed(ToolRunResult.text("ok"))
    failed = _run("run-failed", tool_id=flight_tool.id)
    failed.start()
    failed.fail("blocked")
    active = _run("run-active", tool_id=browser_tool.id)
    active.start()
    active.started_at = now - timedelta(minutes=6)

    types = tool_types_section([flight_tool, browser_tool], [succeeded, failed, active])
    inline_risk = inline_risk_section(
        [succeeded, failed, active],
        active_runs=[active],
        assignment_by_run={},
        now=now,
    )
    strategies = strategies_section([succeeded, failed, active])

    assert types.title == "Tool Call Share"
    assert types.total == 3
    assert [(segment.id, segment.label, segment.value) for segment in types.segments] == [
        ("flight.search", "Flight Search", 2),
        ("browser.snapshot", "Browser Snapshot", 1),
    ]
    inline_items = {item.label: item for item in inline_risk.items}
    assert inline_items["Active Inline Runs"].value == "1"
    assert inline_items["Inline Failures"].value == "1"
    assert inline_items["Longest Inline Duration"].value == "6m 0s"
    assert inline_items["Longest Inline Duration"].tone == "warning"
    assert strategies.total == 1
    strategy_row = strategies.rows[0]
    assert strategy_row.cells["runs"] == "3"
    assert strategy_row.cells["active"] == "1"
    assert strategy_row.cells["failures"] == "1"
    assert strategy_row.cells["success_rate"] == "33%"
