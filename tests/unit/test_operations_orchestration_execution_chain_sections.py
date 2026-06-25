from __future__ import annotations

from datetime import datetime, timedelta, timezone

from crxzipple.modules.dispatch.domain import DispatchTask, DispatchTaskStatus
from crxzipple.modules.operations.application.read_models.orchestration_execution_chain_sections import (
    execution_chain_section,
)
from crxzipple.modules.orchestration.domain import (
    ExecutionChain,
    ExecutionStep,
    ExecutionStepItem,
    InboundInstruction,
    OrchestrationRun,
    OrchestrationRunStage,
    OrchestrationRunStatus,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    ExecutionChainStatus,
    ExecutionStepItemKind,
    ExecutionStepItemStatus,
    ExecutionStepKind,
    ExecutionStepStatus,
)


class _ExecutionQuery:
    def __init__(
        self,
        *,
        chains: list[ExecutionChain],
        steps: list[ExecutionStep],
        items_by_step_id: dict[str, list[ExecutionStepItem]],
    ) -> None:
        self._chains = chains
        self._steps = steps
        self._items_by_step_id = items_by_step_id

    def list_execution_chains(self, run_id: str) -> list[ExecutionChain]:
        return self._chains

    def list_execution_steps(self, chain_id: str) -> list[ExecutionStep]:
        return self._steps

    def list_execution_step_items(self, step_id: str) -> list[ExecutionStepItem]:
        return self._items_by_step_id.get(step_id, [])


def test_execution_chain_section_renders_continuation_and_tool_only_diagnostics() -> None:
    now = datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)
    run = OrchestrationRun(
        id="run-a",
        inbound_instruction=InboundInstruction(source="test", content="hello"),
        status=OrchestrationRunStatus.RUNNING,
        stage=OrchestrationRunStage.LLM,
        created_at=now - timedelta(seconds=120),
        updated_at=now - timedelta(seconds=30),
        metadata={"trace_id": "trace-a"},
    )
    chain = ExecutionChain(
        id="chain-a",
        turn_id="turn-a",
        status=ExecutionChainStatus.RUNNING,
        active_step_id="step-llm",
        step_count=2,
        created_at=now - timedelta(seconds=100),
        started_at=now - timedelta(seconds=90),
        updated_at=now - timedelta(seconds=20),
    )
    intake_step = ExecutionStep(
        id="step-intake",
        chain_id=chain.id,
        turn_id=chain.turn_id,
        step_index=0,
        kind=ExecutionStepKind.INTAKE,
        status=ExecutionStepStatus.COMPLETED,
    )
    llm_step = ExecutionStep(
        id="step-llm",
        chain_id=chain.id,
        turn_id=chain.turn_id,
        step_index=1,
        kind=ExecutionStepKind.LLM,
        status=ExecutionStepStatus.RUNNING,
    )
    continuation_item = ExecutionStepItem(
        id="item-continuation",
        step_id=llm_step.id,
        chain_id=chain.id,
        turn_id=chain.turn_id,
        item_index=0,
        kind=ExecutionStepItemKind.CONTINUATION_DECISION,
        status=ExecutionStepItemStatus.COMPLETED,
        summary_payload={
            "reason": "tool_result_wait",
            "end_turn": False,
            "needs_follow_up": True,
            "provider_continuation_state": {
                "mode": "native",
                "transport": "http",
                "previous_response_id": "resp-1",
            },
        },
        created_at=now - timedelta(seconds=18),
    )
    tool_call_item = ExecutionStepItem(
        id="item-tool",
        step_id=llm_step.id,
        chain_id=chain.id,
        turn_id=chain.turn_id,
        item_index=1,
        kind=ExecutionStepItemKind.TOOL_CALL,
        status=ExecutionStepItemStatus.RUNNING,
        summary_payload={"tool_call_names": ["shell"]},
        created_at=now - timedelta(seconds=16),
    )
    dispatch_task = DispatchTask(
        id="dispatch-a",
        owner_kind="orchestration.step",
        owner_id="step-llm",
        status=DispatchTaskStatus.CLAIMED,
        claimed_by="worker-a",
    )
    query = _ExecutionQuery(
        chains=[chain],
        steps=[intake_step, llm_step],
        items_by_step_id={llm_step.id: [continuation_item, tool_call_item]},
    )

    section = execution_chain_section(
        query,
        [run],
        dispatch_task_by_run_id={run.id: dispatch_task},
        now=now,
    )

    assert section.id == "execution_chains"
    assert section.total == 1
    row = section.rows[0]
    assert row.status == "running"
    assert row.tone == "info"
    assert row.cells["active_step"] == "1:llm/running"
    assert row.cells["items"] == "2 / 1 active"
    assert row.cells["continuation"] == "1 decisions / 1 follow-up"
    assert "previous_response_id=resp-1" in row.cells["latest_decision"]
    assert row.cells["tool_only_streak"] == "max 1 / current 1 / total 1"
    assert row.cells["dispatch_worker"] == "worker-a"
    assert row.cells["trace_route"] == "/workbench/traces/trace-a"
