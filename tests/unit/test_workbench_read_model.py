from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from crxzipple.modules.workbench.application.thread_projector import (
    WorkbenchThreadListProjector,
)
from crxzipple.modules.workbench.application.run_projector import (
    WorkbenchRunDetailProjector,
)
from crxzipple.modules.workbench.application.step_projector import (
    WorkbenchRunStepProjector,
)
from crxzipple.modules.workbench.application.timeline_projector import (
    WorkbenchRunTimelineProjector,
    timeline_items_from_steps,
)
from crxzipple.modules.workbench.application.timeline_response_items import (
    timeline_items_from_llm_response_items,
)
from crxzipple.modules.workbench.application.timeline_tool_lifecycle import (
    timeline_items_with_tool_lifecycle,
)
from crxzipple.modules.workbench.application.tool_run_projection import (
    display_tool_runs,
)
from crxzipple.modules.workbench.application.inspector_projector import (
    _loop_health_section,
)
from crxzipple.modules.workbench.application.view_models import (
    TurnStepView,
)
from crxzipple.modules.llm.domain import (
    LlmMessagePhase,
    LlmResponseItem,
    LlmResponseItemKind,
)
from crxzipple.modules.orchestration.domain import (
    ExecutionStep,
    ExecutionStepItem,
    OrchestrationRun,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    ExecutionOwnerReference,
    ExecutionStepItemKind,
    ExecutionStepKind,
    InboundInstruction,
    OrchestrationRunStage,
    OrchestrationRunStatus,
)
from crxzipple.modules.tool.application.result_envelope import (
    TOOL_RESULT_ENVELOPE_METADATA_KEY,
)
from crxzipple.modules.tool.domain import ToolRun
from crxzipple.modules.tool.domain.value_objects import (
    ToolExecutionTarget,
    ToolMode,
    ToolRunResult,
)
from crxzipple.shared.runtime_console import TraceContext


def test_thread_list_projector_builds_home_view_from_latest_session_runs() -> None:
    older_run = _run(
        run_id="run-older",
        session_key="session-a",
        content="older task",
        status=OrchestrationRunStatus.COMPLETED,
        stage=OrchestrationRunStage.COMPLETED,
        updated_at=datetime(2026, 6, 21, 8, 0, tzinfo=timezone.utc),
    )
    latest_run = _run(
        run_id="run-latest",
        session_key="session-a",
        content="latest task",
        status=OrchestrationRunStatus.RUNNING,
        stage=OrchestrationRunStage.LLM,
        updated_at=datetime(2026, 6, 21, 9, 0, tzinfo=timezone.utc),
    )
    failed_run = _run(
        run_id="run-failed",
        session_key="session-b",
        content="failed task",
        status=OrchestrationRunStatus.FAILED,
        stage=OrchestrationRunStage.FAILED,
        updated_at=datetime(2026, 6, 21, 10, 0, tzinfo=timezone.utc),
    )

    home = WorkbenchThreadListProjector(
        _RunQuery([older_run, latest_run, failed_run]),
    ).project_home_view(session_key="session-a")

    assert [thread.run_id for thread in home.threads] == ["run-failed", "run-latest"]
    assert home.active_run_id == "run-latest"
    assert home.active_thread_id == "session-a"
    assert {item.id: item.count for item in home.filters} == {
        "all": 2,
        "running": 1,
        "completed": 0,
        "failed": 1,
    }


def test_thread_list_projector_builds_stable_empty_home_view() -> None:
    home = WorkbenchThreadListProjector(_RunQuery([])).project_home_view()

    assert home.connection.status == "connected"
    assert home.connection.updated_at is None
    assert home.threads == ()
    assert home.active_run_id is None
    assert home.active_thread_id is None
    assert {item.id: item.count for item in home.filters} == {
        "all": 0,
        "running": 0,
        "completed": 0,
        "failed": 0,
    }


def test_run_detail_projector_is_stable_without_optional_owner_queries() -> None:
    run = _run(
        run_id="run-detail-minimal",
        session_key="session-detail-minimal",
        content="inspect minimal run detail",
        status=OrchestrationRunStatus.RUNNING,
        stage=OrchestrationRunStage.LLM,
        updated_at=datetime(2026, 6, 21, 11, 0, tzinfo=timezone.utc),
    )
    run.current_step = 1

    view = WorkbenchRunDetailProjector(
        run_query=_RunQuery([run]),
        list_step_views_for_run=lambda *_args, **_kwargs: (),
    ).project_run_view(run.id, include_timeline=False)

    assert view.run_id == run.id
    assert view.session_key == "session-detail-minimal"
    assert view.agent.id == "agent-1"
    assert view.model.id == "auto"
    assert view.timeline == ()
    assert view.cover_artifact is None
    assert [turn.turn_id for turn in view.turns] == [run.id]
    assert view.projection_diagnostics.timeline_item_count == 0
    assert view.projection_diagnostics.owner_call_sources == (
        "orchestration.get_run",
        "orchestration.list_runs",
        "orchestration.list_execution_chains",
    )
    assert 3 <= view.projection_diagnostics.owner_call_count <= 4
    assert view.projection_diagnostics.processed_item_count >= 1


def test_run_detail_projector_exposes_pending_approval_actions() -> None:
    run = _run(
        run_id="run-waiting-approval",
        session_key="session-waiting-approval",
        content="needs command approval",
        status=OrchestrationRunStatus.WAITING,
        stage=OrchestrationRunStage.WAITING_FOR_CONFIRMATION,
        updated_at=datetime(2026, 6, 21, 11, 30, tzinfo=timezone.utc),
    )
    run.pending_approval_request_payload = {
        "request_id": "approval-1",
        "effect_id": "command_execution",
        "label": "Command execution",
        "reason": "Run exec with current arguments.",
        "tool_ids": ["exec"],
        "tool_name": "exec",
        "tool_arguments": {"command": "pwd && date"},
    }

    view = WorkbenchRunDetailProjector(
        run_query=_RunQuery([run]),
        list_step_views_for_run=lambda *_args, **_kwargs: (),
    ).project_run_view(run.id, include_timeline=False)

    approval_actions = [
        action for action in view.actions if action.id.startswith("approval:")
    ]

    assert [action.id for action in approval_actions] == [
        "approval:allow_once",
        "approval:allow_for_session",
        "approval:always_for_agent",
        "approval:deny",
    ]
    assert {
        action.endpoint for action in approval_actions
    } == {"/turns/run-waiting-approval/approvals/approval-1"}
    assert {action.trace.approval_request_id for action in approval_actions} == {
        "approval-1",
    }


def test_timeline_filters_empty_agent_progress_fallback_steps() -> None:
    empty_progress = _step(
        step_id="step-empty-progress",
        step_type="agent_progress",
        summary="",
        markdown=None,
    )
    empty_thinking = _step(
        step_id="step-empty-thinking",
        step_type="agent_thinking",
        summary="",
        markdown=None,
    )
    visible_progress = _step(
        step_id="step-visible-progress",
        step_type="agent_progress",
        summary="I found the endpoint; next I will replay it.",
        markdown=None,
    )

    timeline = timeline_items_from_steps(
        (empty_progress, empty_thinking, visible_progress),
    )

    assert [item.id for item in timeline] == ["timeline:step-visible-progress:2"]
    assert [item.kind for item in timeline] == ["assistant_commentary"]
    assert timeline[0].content["text"] == "I found the endpoint; next I will replay it."


def test_timeline_projects_llm_response_items_as_runtime_semantic_nodes() -> None:
    llm_step = _step(
        step_id="step-llm",
        step_type="llm",
        summary="LLM invocation completed.",
        markdown=None,
    )
    llm_step = replace(
        llm_step,
        trace=TraceContext(
            trace_id="trace-llm",
            run_id="run-1",
            turn_id="turn-1",
            llm_invocation_id="llm-main",
        ),
    )
    response_item = LlmResponseItem(
        id="item-agent-progress",
        invocation_id="llm-main",
        sequence_no=1,
        kind=LlmResponseItemKind.ASSISTANT_MESSAGE,
        phase=LlmMessagePhase.COMMENTARY,
        content_payload={"text": "I found the endpoint; next I will replay it."},
        user_timeline_candidate=True,
    )

    timeline = timeline_items_from_steps(
        (llm_step,),
        llm_invocations_by_id={
            "llm-main": SimpleNamespace(response_items=(response_item,)),
        },
    )

    assert len(timeline) == 1
    assert timeline[0].kind == "assistant_commentary"
    assert timeline[0].title == "Agent Progress"
    assert timeline[0].content["text"] == "I found the endpoint; next I will replay it."
    assert timeline[0].source_refs["llm_response_item_id"] == "item-agent-progress"


def test_loop_health_section_surfaces_streak_and_validation_warnings() -> None:
    section = _loop_health_section(
        {
            "warnings": ["tool_only_streak", "validation_lag"],
            "max_tool_only_streak": 4,
            "current_tool_only_streak": 2,
            "tool_only_streak_segments": [
                {"start_step_index": 3, "end_step_index": 6, "length": 4},
            ],
            "validation_delta": 12,
            "validation_lag_suspected": True,
        },
    )

    values = {item.label: item for item in section.items}

    assert section.id == "loop_health"
    assert values["Warnings"].value == "tool_only_streak, validation_lag"
    assert values["Warnings"].tone == "warning"
    assert values["Max tool-only streak"].value == "4"
    assert values["Current tool-only streak"].value == "2"
    assert values["Tool-only segments"].value == "1"
    assert values["Validation delta"].value == "12"
    assert values["Validation delta"].tone == "warning"
    assert values["Validation lag"].value == "yes"
    assert values["Validation lag"].tone == "warning"


def test_loop_health_section_marks_clean_state_successfully() -> None:
    section = _loop_health_section(
        {
            "warnings": [],
            "max_tool_only_streak": 1,
            "current_tool_only_streak": 0,
            "tool_only_streak_segments": [],
            "validation_delta": None,
            "validation_lag_suspected": False,
        },
    )

    values = {item.label: item for item in section.items}

    assert values["Warnings"].value == "none"
    assert values["Warnings"].tone == "success"
    assert values["Validation delta"].value == "-"
    assert values["Validation lag"].value == "no"
    assert values["Validation lag"].tone == "success"


def test_loop_health_section_handles_unavailable_baseline() -> None:
    section = _loop_health_section(None)

    assert section.id == "loop_health"
    assert [(item.label, item.value) for item in section.items] == [
        ("Status", "unavailable"),
    ]


def test_display_tool_runs_uses_tool_owner_metadata_without_execution_fallback() -> None:
    run = _run(
        run_id="run-with-owner-tool",
        session_key="session-owner-tool",
        content="collect owner-scoped tool runs",
        status=OrchestrationRunStatus.RUNNING,
        stage=OrchestrationRunStage.TOOL,
        updated_at=datetime(2026, 6, 21, 9, 0, tzinfo=timezone.utc),
    )
    owned_tool_run = ToolRun(
        id="tool-run-owned",
        tool_id="command.exec",
        target=ToolExecutionTarget(),
        metadata={"orchestration_run_id": run.id},
    )
    orphan_tool_run = ToolRun(
        id="tool-run-orphan",
        tool_id="command.exec",
        target=ToolExecutionTarget(),
        metadata={},
    )

    display_runs = display_tool_runs(
        _NoExecutionFallbackRunQuery(),
        SimpleNamespace(),
        run,
        candidate_runs=[run],
        tool_runs=[owned_tool_run, orphan_tool_run],
    )

    assert [item.tool_run.id for item in display_runs] == ["tool-run-owned"]
    assert display_runs[0].source_run.id == run.id


def test_tool_lifecycle_timeline_surfaces_provider_visible_result_excerpt() -> None:
    run = OrchestrationRun.accept(
        run_id="run-tool-excerpt",
        inbound_instruction=InboundInstruction(source="cli", content="inspect"),
        metadata={"turn_id": "turn-tool-excerpt"},
    )
    step = ExecutionStep.create(
        step_id="step-tool-excerpt",
        chain_id="chain-tool-excerpt",
        turn_id="turn-tool-excerpt",
        step_index=0,
        kind=ExecutionStepKind.TOOL_BATCH,
    )
    call_item = ExecutionStepItem.create(
        item_id="item-call",
        step_id=step.id,
        chain_id=step.chain_id,
        turn_id=step.turn_id,
        item_index=0,
        kind=ExecutionStepItemKind.TOOL_CALL,
        correlation_key="call-tool-excerpt",
    )
    call_item.complete(
        summary_payload={
            "tool_call_id": "call-tool-excerpt",
            "tool_name": "command.exec",
            "tool_id": "command.exec",
        },
    )
    run_item = ExecutionStepItem.create(
        item_id="item-run",
        step_id=step.id,
        chain_id=step.chain_id,
        turn_id=step.turn_id,
        item_index=1,
        kind=ExecutionStepItemKind.TOOL_RUN,
        correlation_key="call-tool-excerpt",
    )
    run_item.complete(
        summary_payload={
            "tool_run_id": "tool-run-excerpt",
            "tool_call_id": "call-tool-excerpt",
            "tool_name": "command.exec",
            "tool_id": "command.exec",
        },
    )
    result_item = ExecutionStepItem.create(
        item_id="item-result",
        step_id=step.id,
        chain_id=step.chain_id,
        turn_id=step.turn_id,
        item_index=2,
        kind=ExecutionStepItemKind.TOOL_RESULT,
        correlation_key="call-tool-excerpt",
    )
    result_item.complete(
        summary_payload={
            "tool_run_id": "tool-run-excerpt",
            "tool_call_id": "call-tool-excerpt",
            "tool_name": "command.exec",
            "tool_id": "command.exec",
        },
    )
    tool_run = ToolRun.create(
        run_id="tool-run-excerpt",
        tool_id="command.exec",
        input_payload={"cmd": "node query.js"},
        target=ToolExecutionTarget(mode=ToolMode.INLINE),
        call_id="call-tool-excerpt",
    )
    tool_run.start()
    tool_run.succeed(
        ToolRunResult(
            content=[{"type": "text", "text": "command completed"}],
            details={
                "command": "node query.js",
                "exit_code": 1,
                "stdout": "loaded home page",
                "stderr": "Error: missing fare list",
            },
            metadata={
                TOOL_RESULT_ENVELOPE_METADATA_KEY: {
                    "status": "error",
                    "summary": "Command ran but no fare list was obtained.",
                    "read_handles": [{"kind": "raw_output_block", "name": "stderr"}],
                },
            },
        ),
    )

    timeline = timeline_items_with_tool_lifecycle(
        (),
        run_query=_FakeRunQuery(step, (call_item, run_item, result_item)),
        runs=(run,),
        tool_runs=(tool_run,),
    )

    assert len(timeline) == 1
    item = timeline[0]
    assert item.kind == "tool_call"
    assert item.content["provider_visible_excerpt"].startswith("tool_result:")
    assert "summary: Command ran but no fare list was obtained." in item.content["markdown"]
    assert "exit_code: 1" in item.content["markdown"]
    assert "stderr_excerpt: Error: missing fare list" in item.content["markdown"]
    assert item.content["read_handles"] == [{"kind": "raw_output_block", "name": "stderr"}]


def test_tool_lifecycle_timeline_does_not_embed_raw_execution_summary_payload() -> None:
    run = OrchestrationRun.accept(
        run_id="run-tool-heavy-summary",
        inbound_instruction=InboundInstruction(source="cli", content="inspect"),
        metadata={"turn_id": "turn-tool-heavy-summary"},
    )
    step = ExecutionStep.create(
        step_id="step-tool-heavy-summary",
        chain_id="chain-tool-heavy-summary",
        turn_id="turn-tool-heavy-summary",
        step_index=0,
        kind=ExecutionStepKind.TOOL_BATCH,
    )
    large_blob = "x" * 20_000
    call_item = ExecutionStepItem.create(
        item_id="item-heavy-call",
        step_id=step.id,
        chain_id=step.chain_id,
        turn_id=step.turn_id,
        item_index=0,
        kind=ExecutionStepItemKind.TOOL_CALL,
        correlation_key="call-tool-heavy-summary",
    )
    call_item.complete(
        summary_payload={
            "tool_call_id": "call-tool-heavy-summary",
            "tool_name": "command.exec",
            "tool_id": "command.exec",
            "tool_execution_plan": {
                "tool_call_id": "call-tool-heavy-summary",
                "tool_name": "command.exec",
                "arguments_digest": "digest-heavy-summary",
                "arguments": {"raw": large_blob},
            },
            "raw_arguments": large_blob,
            "provider_wire_preview": {"input": large_blob},
        },
    )
    result_item = ExecutionStepItem.create(
        item_id="item-heavy-result",
        step_id=step.id,
        chain_id=step.chain_id,
        turn_id=step.turn_id,
        item_index=1,
        kind=ExecutionStepItemKind.TOOL_RESULT,
        correlation_key="call-tool-heavy-summary",
    )
    result_item.complete(
        summary_payload={
            "tool_call_id": "call-tool-heavy-summary",
            "tool_name": "command.exec",
            "tool_id": "command.exec",
            "result_summary": "command completed",
            "stdout": large_blob,
        },
    )

    timeline = timeline_items_with_tool_lifecycle(
        (),
        run_query=_FakeRunQuery(step, (call_item, result_item)),
        runs=(run,),
        tool_runs=(),
    )

    assert len(timeline) == 1
    item = timeline[0]
    assert "payload" not in item.content
    assert item.content["tool_execution_plan"] == {
        "tool_call_id": "call-tool-heavy-summary",
        "tool_name": "command.exec",
        "arguments_digest": "digest-heavy-summary",
    }
    lifecycle = item.content["lifecycle"]
    assert isinstance(lifecycle, list)
    assert all("payload" not in entry["content"] for entry in lifecycle)
    assert large_blob not in str(item.content)


def test_tool_lifecycle_timeline_stays_lightweight_for_long_session() -> None:
    large_blob = "x" * 20_000
    runs: list[OrchestrationRun] = []
    step_items_by_run_id: dict[str, tuple[ExecutionStep, tuple[ExecutionStepItem, ...]]] = {}

    for index in range(100):
        turn_id = f"turn-heavy-{index}"
        call_id = f"call-heavy-{index}"
        run = OrchestrationRun.accept(
            run_id=f"run-heavy-{index}",
            inbound_instruction=InboundInstruction(source="cli", content="inspect"),
            metadata={"turn_id": turn_id, "turn_ordinal": index + 1},
        )
        step = ExecutionStep.create(
            step_id=f"step-heavy-{index}",
            chain_id=f"chain-heavy-{index}",
            turn_id=turn_id,
            step_index=0,
            kind=ExecutionStepKind.TOOL_BATCH,
        )
        call_item = ExecutionStepItem.create(
            item_id=f"item-heavy-call-{index}",
            step_id=step.id,
            chain_id=step.chain_id,
            turn_id=step.turn_id,
            item_index=0,
            kind=ExecutionStepItemKind.TOOL_CALL,
            correlation_key=call_id,
        )
        call_item.complete(
            summary_payload={
                "tool_call_id": call_id,
                "tool_name": "command.exec",
                "tool_id": "command.exec",
                "tool_execution_plan": {
                    "tool_call_id": call_id,
                    "tool_name": "command.exec",
                    "arguments_digest": f"digest-heavy-{index}",
                    "arguments": {"raw": large_blob},
                },
                "raw_arguments": large_blob,
            },
        )
        result_item = ExecutionStepItem.create(
            item_id=f"item-heavy-result-{index}",
            step_id=step.id,
            chain_id=step.chain_id,
            turn_id=step.turn_id,
            item_index=1,
            kind=ExecutionStepItemKind.TOOL_RESULT,
            correlation_key=call_id,
        )
        result_item.complete(
            summary_payload={
                "tool_call_id": call_id,
                "tool_name": "command.exec",
                "tool_id": "command.exec",
                "result_summary": "command completed",
                "stdout": large_blob,
                "provider_wire_preview": {"output": large_blob},
            },
        )
        runs.append(run)
        step_items_by_run_id[run.id] = (step, (call_item, result_item))

    timeline = timeline_items_with_tool_lifecycle(
        (),
        run_query=_MappedRunQuery(step_items_by_run_id),
        runs=tuple(runs),
        tool_runs=(),
    )

    encoded = json.dumps(
        [item.content for item in timeline],
        ensure_ascii=False,
        sort_keys=True,
    )
    assert len(timeline) == 100
    assert len(encoded) < 160_000
    assert large_blob not in encoded
    assert all("payload" not in item.content for item in timeline)
    assert all(
        entry["content"].get("tool_execution_plan", {}).keys()
        <= {"tool_call_id", "tool_name", "arguments_digest"}
        for item in timeline
        for entry in item.content["lifecycle"]
    )


def test_workbench_timeline_hides_debug_only_context_tree_payload() -> None:
    step = _step(
        step_id="step-llm-debug-context",
        step_type="llm",
        summary="",
        markdown=None,
    )
    response_items = (
        LlmResponseItem(
            id="item-assistant",
            invocation_id="llm-debug-context",
            sequence_no=1,
            kind=LlmResponseItemKind.ASSISTANT_MESSAGE,
            phase=LlmMessagePhase.COMMENTARY,
                content_payload={
                    "text": "I will inspect the endpoint next.",
                    "debug_body": "<context_tree>secret tree body</context_tree>",
                    "provider_request_payload_preview": {
                        "payload_preview": {
                            "input": "<context_tree>provider debug body</context_tree>",
                        },
                    },
                    "runtime_request_summary": {
                        "context_snapshot": {
                            "debug_body": "<context_tree>summary debug body</context_tree>",
                        },
                        "request_render_snapshot": {
                            "raw_tree_body": "<context_tree>request render debug body</context_tree>",
                        },
                    },
                    "request_render_snapshot": {
                        "raw_tree_body": "<context_tree>request render body</context_tree>",
                    },
                },
            user_timeline_candidate=True,
        ),
        LlmResponseItem(
            id="item-hidden-reasoning",
            invocation_id="llm-debug-context",
            sequence_no=2,
            kind=LlmResponseItemKind.REASONING,
            phase=LlmMessagePhase.COMMENTARY,
            content_payload={
                "text": "hidden reasoning text",
                "debug_body": "<context_tree>hidden reasoning tree</context_tree>",
            },
            user_timeline_candidate=False,
        ),
    )

    timeline = timeline_items_from_llm_response_items(
        step,
        response_items=response_items,
        base_index=0,
    )

    assert [item.kind for item in timeline] == [
        "assistant_commentary",
        "reasoning_summary",
    ]
    assert timeline[0].content == {
        "text": "I will inspect the endpoint next.",
        "payload": {"text": "I will inspect the endpoint next."},
    }
    assert timeline[1].content == {
        "reasoning_present": True,
        "reasoning_item_count": 1,
        "reasoning_hidden": True,
        "hidden_reason": "policy",
    }
    assert "<context_tree>" not in str(timeline)


def test_workbench_timeline_hides_context_tree_control_tool_calls() -> None:
    step = _step(
        step_id="step-llm-control-tool",
        step_type="llm",
        summary="",
        markdown=None,
    )
    response_item = LlmResponseItem(
        id="item-context-tree-update-plan",
        invocation_id="llm-control-tool",
        sequence_no=1,
        kind=LlmResponseItemKind.TOOL_CALL,
        phase=LlmMessagePhase.COMMENTARY,
        content_payload={
            "tool_name": "context_tree.update_plan",
            "arguments": {
                "objective": "Inspect the airline site",
                "current_step": "Looking for official API",
                "next_steps": "Replay the request",
            },
        },
        provider_item_id="provider-context-tree-update-plan",
        provider_item_type="function_call",
        call_id="call-context-tree-update-plan",
        tool_name="context_tree.update_plan",
        user_timeline_candidate=True,
    )

    timeline = timeline_items_from_llm_response_items(
        step,
        response_items=(response_item,),
        base_index=0,
    )

    assert timeline == ()


def test_workbench_timeline_golden_keeps_long_chain_user_visible_shape() -> None:
    run = OrchestrationRun.accept(
        run_id="run-long-chain",
        inbound_instruction=InboundInstruction(
            source="user",
            content="inspect official site and report verified result",
        ),
        metadata={"session_key": "session-long-chain", "turn_id": "turn-long-chain"},
    )
    run.route(agent_id="agent-1")
    run.bind_session(active_session_id="session-long-chain")
    run.enqueue()
    run.claim(worker_id="worker-1")
    run.advance(worker_id="worker-1", stage=OrchestrationRunStage.LLM, step_increment=4)
    run.complete(
        worker_id="worker-1",
        result_payload={"text": "Verified result from official source."},
    )
    run.created_at = datetime(2026, 6, 20, 23, 59, tzinfo=timezone.utc)
    run.started_at = datetime(2026, 6, 21, 0, 0, tzinfo=timezone.utc)
    run.completed_at = datetime(2026, 6, 21, 0, 5, tzinfo=timezone.utc)
    run.updated_at = run.completed_at

    intake_step = _execution_step(
        step_id="step-intake",
        chain_id="chain-long-chain",
        turn_id=run.id,
        step_index=0,
        kind=ExecutionStepKind.INTAKE,
    )
    llm_step = _execution_step(
        step_id="step-llm-progress",
        chain_id="chain-long-chain",
        turn_id=run.id,
        step_index=1,
        kind=ExecutionStepKind.LLM,
    )
    llm_item = _execution_item(
        item_id="item-llm-progress",
        step=llm_step,
        item_index=0,
        kind=ExecutionStepItemKind.LLM_INVOCATION,
        owner=ExecutionOwnerReference.of("llm_invocation", "llm-progress"),
        summary_payload={
            "llm_invocation_id": "llm-progress",
            "request_render_snapshot_id": "render-progress",
        },
    )
    progress_session_item = _execution_item(
        item_id="item-session-progress",
        step=llm_step,
        item_index=1,
        kind=ExecutionStepItemKind.SESSION_MESSAGE,
        summary_payload={
            "message_kind": "assistant_progress",
            "assistant_progress_text": "I found the official endpoint and will verify it.",
            "session_item_id": "session-item-progress",
            "llm_invocation_id": "llm-progress",
            "request_render_snapshot_id": "render-progress",
        },
    )
    hidden_continuation = _execution_item(
        item_id="item-continuation-hidden",
        step=llm_step,
        item_index=2,
        kind=ExecutionStepItemKind.CONTINUATION_DECISION,
        summary_payload={
            "reason": "none",
            "needs_follow_up": False,
            "end_turn": True,
        },
    )
    tool_step = _execution_step(
        step_id="step-tool-batch",
        chain_id="chain-long-chain",
        turn_id=run.id,
        step_index=2,
        kind=ExecutionStepKind.TOOL_BATCH,
    )
    tool_call = _execution_item(
        item_id="item-tool-call",
        step=tool_step,
        item_index=0,
        kind=ExecutionStepItemKind.TOOL_CALL,
        correlation_key="call-official-query",
        summary_payload={
            "tool_call_id": "call-official-query",
            "tool_name": "command.exec",
            "tool_id": "command.exec",
            "tool_execution_plan": {
                "tool_call_id": "call-official-query",
                "tool_name": "command.exec",
                "arguments_digest": "digest-official-query",
                "raw_arguments": "x" * 5000,
            },
        },
    )
    tool_run_item = _execution_item(
        item_id="item-tool-run",
        step=tool_step,
        item_index=1,
        kind=ExecutionStepItemKind.TOOL_RUN,
        owner=ExecutionOwnerReference.of("tool_run", "tool-run-official-query"),
        correlation_key="call-official-query",
        summary_payload={
            "tool_run_id": "tool-run-official-query",
            "tool_call_id": "call-official-query",
            "tool_name": "command.exec",
            "tool_id": "command.exec",
        },
    )
    tool_result = _execution_item(
        item_id="item-tool-result",
        step=tool_step,
        item_index=2,
        kind=ExecutionStepItemKind.TOOL_RESULT,
        correlation_key="call-official-query",
        summary_payload={
            "tool_run_id": "tool-run-official-query",
            "tool_call_id": "call-official-query",
            "tool_name": "command.exec",
            "tool_id": "command.exec",
            "result_session_item_id": "session-item-tool-result",
        },
    )
    final_llm_step = _execution_step(
        step_id="step-llm-final",
        chain_id="chain-long-chain",
        turn_id=run.id,
        step_index=3,
        kind=ExecutionStepKind.LLM,
    )
    final_llm_item = _execution_item(
        item_id="item-llm-final",
        step=final_llm_step,
        item_index=0,
        kind=ExecutionStepItemKind.LLM_INVOCATION,
        owner=ExecutionOwnerReference.of("llm_invocation", "llm-final"),
        summary_payload={
            "llm_invocation_id": "llm-final",
            "request_render_snapshot_id": "render-final",
        },
    )
    final_response_step = _execution_step(
        step_id="step-final-response",
        chain_id="chain-long-chain",
        turn_id=run.id,
        step_index=4,
        kind=ExecutionStepKind.FINAL_RESPONSE,
    )

    tool_run = ToolRun.create(
        run_id="tool-run-official-query",
        tool_id="command.exec",
        input_payload={"cmd": "python query_official.py"},
        target=ToolExecutionTarget(mode=ToolMode.INLINE),
        call_id="call-official-query",
    )
    tool_run.start()
    tool_run.succeed(
        ToolRunResult(
            content=[{"type": "text", "text": "official response captured"}],
            details={
                "command": "python query_official.py",
                "exit_code": 0,
                "stdout": "official result: available",
            },
            metadata={
                TOOL_RESULT_ENVELOPE_METADATA_KEY: {
                    "status": "success",
                    "summary": "Official result captured.",
                    "read_handles": [{"kind": "raw_output_block", "name": "stdout"}],
                },
            },
        ),
    )

    llm_query = _FakeLlmQuery(
        {
            "llm-progress": SimpleNamespace(
                id="llm-progress",
                llm_id="codex-http",
                result=SimpleNamespace(text=""),
                response_items=(
                    LlmResponseItem(
                        id="response-progress",
                        invocation_id="llm-progress",
                        sequence_no=0,
                        kind=LlmResponseItemKind.ASSISTANT_MESSAGE,
                        phase=LlmMessagePhase.COMMENTARY,
                        content_payload={
                            "text": "I found the official endpoint and will verify it.",
                        },
                        user_timeline_candidate=True,
                        created_at=llm_step.created_at + timedelta(seconds=2),
                    ),
                    LlmResponseItem(
                        id="response-hidden-reasoning",
                        invocation_id="llm-progress",
                        sequence_no=1,
                        kind=LlmResponseItemKind.REASONING,
                        phase=LlmMessagePhase.COMMENTARY,
                        content_payload={"text": "internal reasoning"},
                        user_timeline_candidate=False,
                        created_at=llm_step.created_at + timedelta(seconds=3),
                    ),
                ),
            ),
            "llm-final": SimpleNamespace(
                id="llm-final",
                llm_id="codex-http",
                result=SimpleNamespace(text="Verified result from official source."),
                response_items=(
                    LlmResponseItem(
                        id="response-final",
                        invocation_id="llm-final",
                        sequence_no=0,
                        kind=LlmResponseItemKind.ASSISTANT_MESSAGE,
                        phase=LlmMessagePhase.FINAL_ANSWER,
                        content_payload={"text": "Verified result from official source."},
                        user_timeline_candidate=True,
                        created_at=final_llm_step.created_at + timedelta(seconds=2),
                    ),
                ),
            ),
        },
    )
    run_query = _MultiStepRunQuery(
        run_id=run.id,
        steps=(intake_step, llm_step, tool_step, final_llm_step, final_response_step),
        items_by_step_id={
            intake_step.id: (),
            llm_step.id: (llm_item, progress_session_item, hidden_continuation),
            tool_step.id: (tool_call, tool_run_item, tool_result),
            final_llm_step.id: (final_llm_item,),
            final_response_step.id: (),
        },
    )
    step_projector = WorkbenchRunStepProjector(
        run_query,
        llm_query=llm_query,
        session_query=_FakeSessionQuery(
            {"session-item-progress": "I found the official endpoint and will verify it."},
        ),
    )

    timeline = WorkbenchRunTimelineProjector(
        run_query,
        list_step_views_for_run=step_projector.project_step_views_for_run,
        llm_query=llm_query,
    ).project_timeline(
        run=run,
        candidate_runs=[run],
        tool_runs=[tool_run],
    )

    assert [(item.kind, item.title) for item in timeline] == [
        ("user_input", "User Input"),
        ("assistant_commentary", "Agent Progress"),
        ("reasoning_summary", "Reasoning Summary"),
        ("tool_call", "Tool Interaction: command.exec"),
        ("final_answer", "Final Response"),
    ]
    assert [item.turn_id for item in timeline] == ["turn-long-chain"] * 5
    assert timeline[1].source_refs["llm_response_item_id"] == "response-progress"
    assert timeline[1].source_refs["request_render_snapshot_id"] == "render-progress"
    assert timeline[2].content == {
        "reasoning_present": True,
        "reasoning_item_count": 1,
        "reasoning_hidden": True,
        "hidden_reason": "policy",
    }
    tool_item = timeline[3]
    assert tool_item.source_refs["tool_call_id"] == "call-official-query"
    assert tool_item.source_refs["tool_run_id"] == "tool-run-official-query"
    assert tool_item.source_refs["session_item_id"] == "session-item-tool-result"
    assert tool_item.trace.tool_call_id == "call-official-query"
    assert tool_item.trace.tool_run_id == "tool-run-official-query"
    assert tool_item.trace.session_item_id == "session-item-tool-result"
    assert tool_item.content["tool_execution_plan"] == {
        "tool_call_id": "call-official-query",
        "tool_name": "command.exec",
        "arguments_digest": "digest-official-query",
    }
    assert tool_item.content["read_handles"] == [
        {"kind": "raw_output_block", "name": "stdout"},
    ]
    assert timeline[-1].source_refs["llm_response_item_id"] == "response-final"
    assert "timeline:run-long-chain:execution:step-final-response" not in {
        item.id for item in timeline
    }
    assert "none;" not in str(timeline)
    assert "raw_arguments" not in str(timeline)


def _step(
    *,
    step_id: str,
    step_type: str,
    summary: str,
    markdown: str | None,
) -> TurnStepView:
    return TurnStepView(
        step_id=step_id,
        turn_id="turn-1",
        run_id="run-1",
        type=step_type,
        status="success",
        title="Agent Progress",
        summary=summary,
        markdown=markdown,
        started_at=None,
        completed_at=None,
        duration_ms=None,
        artifacts=(),
        badges=(),
        linked_entities=(),
        actions=(),
        approval=None,
        details_available=True,
        trace=TraceContext(trace_id="trace-1", run_id="run-1", turn_id="turn-1"),
    )


def _run(
    *,
    run_id: str,
    session_key: str,
    content: str,
    status: OrchestrationRunStatus,
    stage: OrchestrationRunStage,
    updated_at: datetime,
) -> OrchestrationRun:
    return OrchestrationRun(
        id=run_id,
        inbound_instruction=InboundInstruction(source="user", content=content),
        status=status,
        stage=stage,
        agent_id="agent-1",
        metadata={"session_key": session_key},
        updated_at=updated_at,
    )


class _RunQuery:
    def __init__(self, runs: list[OrchestrationRun]) -> None:
        self._runs = list(runs)

    def get_run(self, run_id: str) -> OrchestrationRun:
        for run in self._runs:
            if run.id == run_id:
                return run
        raise KeyError(run_id)

    def list_runs(self, *, session_key: str | None = None) -> list[OrchestrationRun]:
        if session_key is None:
            return list(self._runs)
        return [run for run in self._runs if run.session_key == session_key]

    def list_execution_chains(self, _run_id: str) -> list[object]:
        return []

    def list_execution_steps(self, _chain_id: str) -> list[object]:
        return []

    def list_execution_step_items(self, _step_id: str) -> list[object]:
        return []


class _NoExecutionFallbackRunQuery:
    def get_run(self, run_id: str) -> OrchestrationRun:  # pragma: no cover
        raise AssertionError(f"unexpected run lookup: {run_id}")

    def list_runs(self) -> list[OrchestrationRun]:  # pragma: no cover
        raise AssertionError("unexpected run list lookup")

    def list_execution_chains(self, run_id: str) -> list[object]:  # pragma: no cover
        raise AssertionError(f"unexpected execution chain lookup: {run_id}")

    def list_execution_steps(self, chain_id: str) -> list[object]:  # pragma: no cover
        raise AssertionError(f"unexpected execution step lookup: {chain_id}")

    def list_execution_step_items(self, step_id: str) -> list[object]:  # pragma: no cover
        raise AssertionError(f"unexpected execution item lookup: {step_id}")


class _FakeRunQuery:
    def __init__(
        self,
        step: ExecutionStep,
        items: tuple[ExecutionStepItem, ...],
    ) -> None:
        self._step = step
        self._items = items

    def list_execution_chains(self, _turn_id: str) -> list[SimpleNamespace]:
        return [SimpleNamespace(id=self._step.chain_id)]

    def list_execution_steps(self, _chain_id: str) -> list[ExecutionStep]:
        return [self._step]

    def list_execution_step_items(self, _step_id: str) -> list[ExecutionStepItem]:
        return list(self._items)


class _MappedRunQuery:
    def __init__(
        self,
        items_by_run_id: dict[str, tuple[ExecutionStep, tuple[ExecutionStepItem, ...]]],
    ) -> None:
        self._items_by_run_id = items_by_run_id
        self._chain_to_run_id = {
            step.chain_id: run_id for run_id, (step, _items) in items_by_run_id.items()
        }
        self._step_to_run_id = {
            step.id: run_id for run_id, (step, _items) in items_by_run_id.items()
        }

    def list_execution_chains(self, run_id: str) -> list[SimpleNamespace]:
        step, _items = self._items_by_run_id[run_id]
        return [SimpleNamespace(id=step.chain_id)]

    def list_execution_steps(self, chain_id: str) -> list[ExecutionStep]:
        run_id = self._chain_to_run_id[chain_id]
        step, _items = self._items_by_run_id[run_id]
        return [step]

    def list_execution_step_items(self, step_id: str) -> list[ExecutionStepItem]:
        run_id = self._step_to_run_id[step_id]
        _step, items = self._items_by_run_id[run_id]
        return list(items)


def _execution_step(
    *,
    step_id: str,
    chain_id: str,
    turn_id: str,
    step_index: int,
    kind: ExecutionStepKind,
) -> ExecutionStep:
    timestamp = datetime(2026, 6, 21, 0, 0, tzinfo=timezone.utc) + timedelta(
        minutes=step_index,
    )
    step = ExecutionStep.create(
        step_id=step_id,
        chain_id=chain_id,
        turn_id=turn_id,
        step_index=step_index,
        kind=kind,
    )
    step.start()
    step.complete()
    step.created_at = timestamp
    step.started_at = timestamp
    step.completed_at = timestamp + timedelta(seconds=50)
    step.updated_at = step.completed_at
    return step


def _execution_item(
    *,
    item_id: str,
    step: ExecutionStep,
    item_index: int,
    kind: ExecutionStepItemKind,
    owner: ExecutionOwnerReference | None = None,
    correlation_key: str | None = None,
    summary_payload: dict[str, object] | None = None,
) -> ExecutionStepItem:
    timestamp = step.created_at + timedelta(seconds=item_index)
    item = ExecutionStepItem.create(
        item_id=item_id,
        step_id=step.id,
        chain_id=step.chain_id,
        turn_id=step.turn_id,
        item_index=item_index,
        kind=kind,
        owner=owner,
        correlation_key=correlation_key,
    )
    item.complete(summary_payload=summary_payload or {})
    item.created_at = timestamp
    item.completed_at = timestamp + timedelta(seconds=1)
    item.updated_at = item.completed_at
    return item


class _MultiStepRunQuery:
    def __init__(
        self,
        *,
        run_id: str,
        steps: tuple[ExecutionStep, ...],
        items_by_step_id: dict[str, tuple[ExecutionStepItem, ...]],
    ) -> None:
        self._run_id = run_id
        self._chain_id = steps[0].chain_id if steps else "chain"
        self._steps = tuple(steps)
        self._items_by_step_id = dict(items_by_step_id)

    def list_execution_chains(self, run_id: str) -> list[SimpleNamespace]:
        if run_id != self._run_id:
            return []
        return [SimpleNamespace(id=self._chain_id)]

    def list_execution_steps(self, chain_id: str) -> list[ExecutionStep]:
        if chain_id != self._chain_id:
            return []
        return list(self._steps)

    def list_execution_step_items(self, step_id: str) -> list[ExecutionStepItem]:
        return list(self._items_by_step_id.get(step_id, ()))


class _FakeLlmQuery:
    def __init__(self, invocations: dict[str, object]) -> None:
        self._invocations = dict(invocations)

    def get_invocation(self, invocation_id: str) -> object:
        return self._invocations[invocation_id]


class _FakeSessionQuery:
    def __init__(self, items: dict[str, str]) -> None:
        self._items = dict(items)

    def get_item(self, item_id: str) -> object:
        return SimpleNamespace(content_payload={"text": self._items[item_id]})
