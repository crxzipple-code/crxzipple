from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

from crxzipple.modules.workbench.application.read_models import (
    TurnStepView,
    _loop_health_section,
    _timeline_items_from_llm_response_items,
    _timeline_items_with_tool_lifecycle,
    _timeline_items_from_steps,
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
    ExecutionStepItemKind,
    ExecutionStepKind,
    InboundInstruction,
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

    timeline = _timeline_items_from_steps(
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

    timeline = _timeline_items_from_steps(
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

    timeline = _timeline_items_with_tool_lifecycle(
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

    timeline = _timeline_items_with_tool_lifecycle(
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

    timeline = _timeline_items_with_tool_lifecycle(
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

    timeline = _timeline_items_from_llm_response_items(
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

    timeline = _timeline_items_from_llm_response_items(
        step,
        response_items=(response_item,),
        base_index=0,
    )

    assert timeline == ()


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
