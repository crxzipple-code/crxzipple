from __future__ import annotations

from datetime import datetime, timezone

from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.orchestration_projection_diagnostics import (
    orchestration_projection_diagnostics,
)


def test_orchestration_projection_diagnostics_declares_owner_sources_and_cost() -> None:
    event = OperationsObservedEvent(
        id="event-1",
        cursor="event-1",
        topic="events.named.orchestration.run.queued",
        event_name="orchestration.run.queued",
        module="orchestration",
        owner="orchestration",
        kind="fact",
        level="info",
        status="queued",
        entity_id="run-1",
        run_id="run-1",
        trace_id="trace-1",
        source_event_name="orchestration.run.queued",
        occurred_at=datetime(2026, 6, 21, 12, tzinfo=timezone.utc),
        payload={"run_id": "run-1"},
    )

    diagnostics = orchestration_projection_diagnostics(
        runs=[],
        leases=[],
        ingress_requests=[],
        continuation_tasks=[],
        dispatch_tasks=[],
        observed_events=(event,),
        owner_call_count=5,
        elapsed_ms=12.34567,
        freshness_at="2026-06-21T12:00:00Z",
    )

    assert diagnostics.module == "orchestration"
    assert diagnostics.owner_call_count == 5
    assert diagnostics.processed_item_count == 1
    assert diagnostics.elapsed_ms == 12.346
    assert diagnostics.freshness_at == "2026-06-21T12:00:00Z"
    owner_modules = {source.module for source in diagnostics.owner_sources}
    assert owner_modules == {"orchestration", "dispatch", "operations"}
    orchestration_source = next(
        source
        for source in diagnostics.owner_sources
        if source.module == "orchestration"
    )
    assert "execution_chains" in orchestration_source.facts
    assert "continuation_tasks" in orchestration_source.facts
