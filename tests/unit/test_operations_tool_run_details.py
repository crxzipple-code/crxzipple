from __future__ import annotations

from datetime import datetime, timezone

from crxzipple.modules.operations.application.read_models.tool_run_assignment_details import (
    assignment_history_section,
)
from crxzipple.modules.operations.application.read_models.tool_run_browser_details import (
    browser_run_label,
)
from crxzipple.modules.operations.application.read_models.tool_run_detail_payloads import (
    detail_value,
    invocation_context_items,
    json_safe_payload,
)
from crxzipple.modules.operations.application.read_models.tool_run_details import (
    tool_run_details,
)
from crxzipple.modules.tool.domain import (
    Tool,
    ToolEnvironment,
    ToolExecutionStrategy,
    ToolExecutionTarget,
    ToolMode,
    ToolRun,
    ToolRunAssignment,
    ToolRunResult,
)


def _run() -> ToolRun:
    run = ToolRun.create(
        run_id="run-detail-1",
        tool_id="tool.flight",
        call_id="call-detail-1",
        function_id="tool.flight",
        source_id="source.local",
        input_payload={},
        target=ToolExecutionTarget(
            mode=ToolMode.INLINE,
            strategy=ToolExecutionStrategy.ASYNC,
            environment=ToolEnvironment.LOCAL,
        ),
    )
    run.invocation_context_payload = {
        "z": {"nested": datetime(2026, 6, 21, tzinfo=timezone.utc)},
        "a": "plain text",
    }
    return run


def test_invocation_context_items_are_sorted_and_json_safe() -> None:
    items = invocation_context_items(_run())

    assert [item.label for item in items] == ["a", "z"]
    assert items[0].value == "plain text"
    assert "2026-06-21" in items[1].value


def test_assignment_history_section_projects_assignment_rows() -> None:
    assignment = ToolRunAssignment.create(
        assignment_id="assign-1",
        run_id="run-detail-1",
        tool_id="tool.flight",
        worker_id="worker-1",
        attempt_count=2,
        lease_seconds=60,
    )
    assignment.start()
    assignment.succeed()

    section = assignment_history_section([assignment])

    assert section.id == "assignment_history"
    assert section.total == 1
    row = section.rows[0]
    assert row.cells["assignment"] == "assign-1"
    assert row.cells["worker"] == "worker-1"
    assert row.cells["status"] == "Succeeded"
    assert row.cells["attempt"] == "2"
    assert row.tone == "success"


def test_json_safe_payload_and_detail_value_are_bounded() -> None:
    payload = json_safe_payload(
        {
            "time": datetime(2026, 6, 21, tzinfo=timezone.utc),
            "items": list(range(120)),
        },
    )

    assert "2026-06-21" in payload["time"]
    assert len(payload["items"]) == 80
    assert detail_value("x" * 200).endswith("...")


def test_tool_run_details_project_browser_profile_summary() -> None:
    now = datetime.now(timezone.utc)
    tool = Tool(
        id="browser.navigate",
        name="browser.navigate",
        description="Open browser tab.",
    )
    run = ToolRun.create(
        run_id="run-browser-1",
        tool_id=tool.id,
        call_id="call-browser-1",
        source_id="bundled.local_package.browser",
        input_payload={"url": "https://example.com"},
        target=ToolExecutionTarget(
            mode=ToolMode.INLINE,
            strategy=ToolExecutionStrategy.ASYNC,
            environment=ToolEnvironment.LOCAL,
        ),
    )
    run.start()
    run.succeed(
        ToolRunResult.text(
            "opened",
            metadata={
                "tool": "browser.navigate",
                "profile_name": "user",
                "profile_source": "browser.default_profile",
                "browser_profile_pool": "collector",
                "browser_allocation_id": "browser_alloc_1",
                "browser_target_host": "example.com",
            },
        ),
    )

    details = tool_run_details(
        [run],
        tools=[tool],
        assignments=[],
        observed_events=(),
        artifact_service=None,
        run_contexts={
            run.id: {
                "run_id": "orch-1",
                "trace_id": "trace-1",
                "step_id": "step-1",
                "step_kind": "tool_call",
            },
        },
        now=now,
    )

    assert browser_run_label(run) == "user · pool:collector · alloc:browser_alloc_1 · example.com"
    detail = details[0]
    assert detail.run_id == run.id
    assert detail.result_summary == "opened"
    summary = {item.label: item.value for item in detail.summary}
    assert summary["Browser Profile"] == "user"
    assert summary["Profile Source"] == "browser.default_profile"
    assert summary["Browser Profile Pool"] == "collector"
    assert summary["Browser Allocation"] == "browser_alloc_1"
    assert summary["Target Host"] == "example.com"
    assert summary["Turn ID"] == "orch-1"
    assert summary["Step ID"] == "step-1"
