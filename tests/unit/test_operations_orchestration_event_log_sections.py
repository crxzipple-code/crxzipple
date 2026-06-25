from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.orchestration_event_log_rows import (
    event_record_time,
)
from crxzipple.modules.operations.application.read_models.orchestration_event_log_sections import (
    ops_event_log_section,
)


def test_ops_event_log_section_renders_observed_events() -> None:
    occurred_at = datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)
    event = OperationsObservedEvent(
        id="event-a",
        cursor="cursor-a",
        topic="orchestration.run.failed",
        event_name="orchestration.run.failed",
        module="orchestration",
        owner="orchestration",
        kind="fact",
        level="error",
        status="failed",
        entity_id="run-a",
        run_id="run-a",
        trace_id="trace-a",
        source_event_name=None,
        occurred_at=occurred_at,
        payload={"message": "boom"},
    )

    section = ops_event_log_section(event_records=(event,))

    assert section.id == "ops_event_log"
    assert section.total == 1
    row = section.rows[0]
    assert row.id == "cursor-a"
    assert row.status == "failed"
    assert row.tone == "danger"
    assert row.cells["event"] == "Run Failed"
    assert row.cells["source"] == "Run"
    assert row.cells["route"] == "/ui/workbench/runs/run-a"
    assert row.cells["trace_route"] == "/workbench/traces/trace-a"
    assert row.cells["details"] == "message=boom"


def test_event_record_time_reads_wrapped_event_envelope() -> None:
    occurred_at = datetime(2026, 6, 21, 12, 3, tzinfo=timezone.utc)

    @dataclass(frozen=True)
    class Envelope:
        occurred_at: datetime

    @dataclass(frozen=True)
    class Record:
        envelope: Envelope

    assert event_record_time(Record(envelope=Envelope(occurred_at=occurred_at))) == occurred_at
