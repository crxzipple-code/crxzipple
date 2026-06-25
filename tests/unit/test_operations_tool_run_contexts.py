from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from crxzipple.modules.orchestration.domain import ExecutionOwnerReference
from crxzipple.modules.operations.application.read_models.tool_run_contexts import (
    tool_run_contexts,
)
from crxzipple.modules.tool.domain import (
    ToolEnvironment,
    ToolExecutionStrategy,
    ToolExecutionTarget,
    ToolMode,
    ToolRun,
)


def _target() -> ToolExecutionTarget:
    return ToolExecutionTarget(
        mode=ToolMode.INLINE,
        strategy=ToolExecutionStrategy.ASYNC,
        environment=ToolEnvironment.LOCAL,
    )


class _RunQuery:
    def __init__(self, item: SimpleNamespace) -> None:
        self.item = item
        self.last_owner: ExecutionOwnerReference | None = None

    def find_execution_step_items_by_owner(
        self,
        owner: ExecutionOwnerReference,
    ) -> list[SimpleNamespace]:
        self.last_owner = owner
        return [self.item]

    def get_execution_step(self, step_id: str) -> SimpleNamespace:
        assert step_id == "step-1"
        return SimpleNamespace(
            kind=SimpleNamespace(value="tool_batch"),
            status=SimpleNamespace(value="running"),
        )

    def get_run(self, run_id: str) -> SimpleNamespace:
        assert run_id == "orch-run-1"
        return SimpleNamespace(
            id=run_id,
            metadata={
                "trace_id": "trace-1",
                "turn_id": "turn-1",
                "session_key": "agent:assistant:test",
            },
        )


def test_tool_run_contexts_project_latest_execution_owner_context() -> None:
    run = ToolRun.create(
        run_id="tool-run-1",
        tool_id="flight.search",
        input_payload={},
        target=_target(),
    )
    item = SimpleNamespace(
        id="item-1",
        step_id="step-1",
        chain_id="chain-1",
        turn_id="orch-run-1",
        correlation_key=None,
        summary_payload={"tool_call_id": "call-1"},
        owner=ExecutionOwnerReference(owner_kind="tool_run", owner_id=run.id),
        status=SimpleNamespace(value="running"),
        updated_at=datetime(2026, 6, 21, tzinfo=timezone.utc),
    )
    query = _RunQuery(item)

    contexts = tool_run_contexts(query, [run])

    assert query.last_owner == ExecutionOwnerReference(
        owner_kind="tool_run",
        owner_id=run.id,
    )
    assert contexts == {
        run.id: {
            "run_id": "orch-run-1",
            "turn_id": "turn-1",
            "trace_id": "trace-1",
            "session_key": "agent:assistant:test",
            "route": "/ui/workbench/runs/orch-run-1",
            "trace_route": "/workbench/traces/trace-1?focus_id=tool-run-1",
            "chain_id": "chain-1",
            "step_id": "step-1",
            "step_kind": "tool_batch",
            "step_status": "running",
            "item_status": "running",
            "tool_call_id": "call-1",
        },
    }


def test_tool_run_contexts_returns_empty_without_query_capability() -> None:
    run = ToolRun.create(
        run_id="tool-run-1",
        tool_id="flight.search",
        input_payload={},
        target=_target(),
    )

    assert tool_run_contexts(None, [run]) == {}
    assert tool_run_contexts(object(), [run]) == {}
