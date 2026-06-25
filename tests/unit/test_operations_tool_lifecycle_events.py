from __future__ import annotations

from datetime import datetime, timezone

from crxzipple.modules.operations.application.observation_models import (
    OperationsModuleObservation,
    OperationsObservedEvent,
)
from crxzipple.modules.operations.application.read_models.tool_lifecycle_event_sources import (
    recent_tool_events,
)
from crxzipple.modules.operations.application.read_models.tool_lifecycle_events import (
    tool_lifecycle_events_section,
)
from crxzipple.modules.tool.domain import (
    Tool,
    ToolEnvironment,
    ToolExecutionStrategy,
    ToolExecutionTarget,
    ToolMode,
    ToolRun,
)


class _Observation:
    def __init__(self, events: tuple[OperationsObservedEvent, ...]) -> None:
        self._events = events

    def get_module_observation(self, module: str) -> OperationsModuleObservation:
        assert module == "tool"
        return OperationsModuleObservation(
            module="tool",
            owner="tool",
            recent_events=self._events,
        )


def _event(
    event_id: str,
    *,
    cursor: str | None = None,
    event_name: str = "tool.run.failed",
    status: str = "failed",
    payload: dict[str, object] | None = None,
    run_id: str | None = None,
    trace_id: str | None = None,
) -> OperationsObservedEvent:
    return OperationsObservedEvent(
        id=event_id,
        cursor=cursor or event_id,
        topic=f"events.named.{event_name}",
        event_name=event_name,
        module="tool",
        owner="tool",
        kind="fact",
        level="error" if status == "failed" else "info",
        status=status,
        entity_id=run_id or event_id,
        run_id=run_id,
        trace_id=trace_id,
        source_event_name=event_name,
        occurred_at=datetime.now(timezone.utc),
        payload=dict(payload or {}),
    )


def _target() -> ToolExecutionTarget:
    return ToolExecutionTarget(
        mode=ToolMode.INLINE,
        strategy=ToolExecutionStrategy.ASYNC,
        environment=ToolEnvironment.LOCAL,
    )


def test_recent_tool_events_dedupes_observation_events_by_topic_cursor() -> None:
    first = _event("event-1", cursor="cursor-1")
    duplicate = _event("event-duplicate", cursor="cursor-1")

    events = recent_tool_events(
        operations_observation=_Observation((first, duplicate)),
        events_service=None,
        definition_registry=None,
        limit=10,
    )

    assert len(events) == 1
    assert events[0].cursor == "cursor-1"


def test_tool_lifecycle_events_section_renders_run_context() -> None:
    tool = Tool(
        id="browser.navigate",
        name="Navigate",
        description="Open a page.",
    )
    run = ToolRun.create(
        run_id="tool-run-1",
        tool_id=tool.id,
        call_id="call-1",
        input_payload={},
        metadata={
            "orchestration_run_id": "orch-run-1",
            "tool_call_id": "call-1",
        },
        invocation_context_payload={
            "trace_id": "trace-1",
            "step_id": "step-1",
        },
        target=_target(),
    )
    event = _event(
        "event-1",
        run_id=run.id,
        payload={
            "run_id": run.id,
            "tool_id": tool.id,
            "worker_id": "worker-1",
            "error_message": "401 auth failed",
        },
    )

    section = tool_lifecycle_events_section(
        (event,),
        tools=[tool],
        runs=[run],
    )

    assert section.id == "tool_lifecycle_events"
    assert section.total == 1
    row = section.rows[0]
    assert row.tone == "danger"
    assert row.cells["event"] == "run.failed"
    assert row.cells["tool"] == "Navigate (browser.navigate)"
    assert row.cells["run_id"] == run.id
    assert row.cells["worker"] == "worker-1"
    assert row.cells["source"] == "orch-run-1 / call-1"
    assert row.cells["trace"] == "trace-1"
    assert row.cells["trace_route"] == "/workbench/traces/trace-1"
    assert "error_message=401 auth failed" in row.cells["details"]
