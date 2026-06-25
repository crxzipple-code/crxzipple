from __future__ import annotations

from datetime import datetime, timedelta, timezone

from crxzipple.modules.operations.application.read_models.tool_run_table_facts import (
    ToolRunTableFacts,
    tool_run_table_facts_by_run_id,
)
from crxzipple.modules.operations.application.read_models.tool_run_tables import (
    active_tool_runs_section,
    tool_runs_section,
)
from crxzipple.modules.tool.domain import (
    Tool,
    ToolEnvironment,
    ToolExecutionPolicy,
    ToolExecutionStrategy,
    ToolExecutionTarget,
    ToolMode,
    ToolRun,
    ToolRunAssignment,
    ToolRunResult,
)


def _run(run_id: str) -> ToolRun:
    return ToolRun.create(
        run_id=run_id,
        tool_id="tool.flight",
        call_id=f"call-{run_id}",
        function_id="tool.flight",
        source_id="source.local",
        input_payload={},
        target=ToolExecutionTarget(
            mode=ToolMode.INLINE,
            strategy=ToolExecutionStrategy.ASYNC,
            environment=ToolEnvironment.LOCAL,
        ),
    )


def _facts(*, has_artifact: bool = False) -> ToolRunTableFacts:
    return ToolRunTableFacts(
        tool_label="Flight Search (tool.flight)",
        provider="provider:eastern",
        source="run-1 / step-1",
        orchestration_run_id="run-1",
        chain_id="chain-1",
        step_id="step-1",
        browser="-",
        assignment_status="-",
        assignment_id="-",
        lease_state="-",
        lease_expires_at="-",
        duration="1s",
        progress="20%",
        result="Completed",
        has_artifact=has_artifact,
        route="/ui/workbench/runs/run-1",
        trace="trace-1",
        trace_route="/workbench/traces/trace-1",
        search_text="flight trace-1",
    )


def test_tool_runs_section_projects_row_cells_and_table_metadata() -> None:
    run = _run("run-table-1")
    run.start()
    run.succeed(ToolRunResult.text("done"))

    section = tool_runs_section(
        [run],
        facts_by_run_id={run.id: _facts(has_artifact=True)},
        total_count=3,
        empty_state="empty",
    )

    assert section.id == "tool_runs"
    assert section.total == 3
    assert section.empty_state == "empty"
    assert section.view_all_route == "/operations/tool?tab=runs"
    row = section.rows[0]
    assert row.id == run.id
    assert row.tone == "success"
    assert row.cells["tool"] == "Flight Search (tool.flight)"
    assert row.cells["provider"] == "provider:eastern"
    assert row.cells["has_artifact"] == "yes"
    assert row.cells["retryable"] == "no"
    assert row.cells["actions"] == "Open / Trace"
    assert row.cells["trace_route"] == "/workbench/traces/trace-1"


def test_active_tool_runs_section_projects_running_action_and_progress() -> None:
    run = _run("run-active-1")
    run.start()

    section = active_tool_runs_section(
        [run],
        facts_by_run_id={run.id: _facts()},
    )

    assert section.id == "active_tool_runs"
    assert section.total == 1
    row = section.rows[0]
    assert row.tone == "info"
    assert row.cells["progress"] == "20%"
    assert row.cells["actions"] == "Open / Trace / Cancel"


def test_tool_run_table_facts_project_assignment_source_trace_and_progress() -> None:
    now = datetime.now(timezone.utc)
    tool = Tool(
        id="tool.flight",
        name="Flight Search",
        description="Search flights.",
        execution_policy=ToolExecutionPolicy(timeout_seconds=60),
    )
    run = _run("run-facts-1")
    run.start()
    run.started_at = now - timedelta(seconds=30)
    assignment = ToolRunAssignment.create(
        assignment_id="assignment-1",
        run_id=run.id,
        tool_id=run.tool_id,
        worker_id="worker-1",
        attempt_count=1,
        lease_seconds=120,
    )
    assignment.start()
    assignment.assigned_at = now - timedelta(seconds=30)
    assignment.started_at = now - timedelta(seconds=30)
    assignment.lease_expires_at = now + timedelta(seconds=90)

    facts = tool_run_table_facts_by_run_id(
        [run],
        tools_by_id={tool.id: tool},
        assignment_by_run={run.id: assignment},
        artifact_service=None,
        run_contexts={
            run.id: {
                "run_id": "orch-1",
                "tool_call_id": "call-1",
                "chain_id": "chain-1",
                "step_id": "step-1",
                "trace_id": "trace-1",
                "route": "/ui/workbench/runs/orch-1",
                "trace_route": "/workbench/traces/trace-1?focus_id=call-1",
            },
        },
        now=now,
    )[run.id]

    assert facts.tool_label == "Flight Search (tool.flight)"
    assert facts.provider == "local"
    assert facts.source == "orch-1 / call-1"
    assert facts.orchestration_run_id == "orch-1"
    assert facts.chain_id == "chain-1"
    assert facts.step_id == "step-1"
    assert facts.assignment_status == "Running"
    assert facts.assignment_id == "assignment-1"
    assert facts.lease_state == "Active"
    assert facts.duration == "30s"
    assert facts.progress == "50%"
    assert facts.route == "/ui/workbench/runs/orch-1"
    assert facts.trace == "trace-1"
    assert facts.trace_route == "/workbench/traces/trace-1?focus_id=call-1"
    assert "Flight Search" in facts.search_text
    assert "trace-1" in facts.search_text
