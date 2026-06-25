from __future__ import annotations

from datetime import datetime, timedelta, timezone

from crxzipple.modules.operations.application.observation_models import (
    OperationsModuleObservation,
    OperationsObservedEvent,
)
from crxzipple.modules.operations.application.read_models.llm_lifecycle_event_rows import (
    event_continuation_label,
    event_input_delta_label,
    event_transport_label,
    event_tone,
)
from crxzipple.modules.operations.application.read_models.llm_lifecycle_event_sources import (
    recent_llm_events,
    recent_resolver_events,
)
from crxzipple.modules.operations.application.read_models.llm_lifecycle_events import (
    llm_lifecycle_events_section,
)


class _Observation:
    def __init__(
        self,
        events_by_module: dict[str, tuple[OperationsObservedEvent, ...]],
    ) -> None:
        self._events_by_module = events_by_module

    def get_module_observation(self, module: str) -> OperationsModuleObservation:
        return OperationsModuleObservation(
            module=module,
            owner=module,
            recent_events=self._events_by_module.get(module, ()),
        )


def _event(
    event_id: str,
    *,
    cursor: str | None = None,
    event_name: str = "llm.invocation_failed",
    module: str = "llm",
    owner: str = "llm",
    occurred_at: datetime | None = None,
    payload: dict[str, object] | None = None,
) -> OperationsObservedEvent:
    return OperationsObservedEvent(
        id=event_id,
        cursor=cursor or event_id,
        topic=f"events.named.{event_name}",
        event_name=event_name,
        module=module,
        owner=owner,
        kind="fact",
        level="error" if "failed" in event_name else "info",
        status="failed" if "failed" in event_name else "observed",
        entity_id=event_id,
        run_id=None,
        trace_id=None,
        source_event_name=event_name,
        occurred_at=occurred_at or datetime(2026, 6, 21, tzinfo=timezone.utc),
        payload={"invocation_id": event_id, **dict(payload or {})},
    )


def test_recent_llm_events_dedupes_observation_events_by_topic_cursor() -> None:
    first = _event("event-1", cursor="cursor-1")
    duplicate = _event("event-duplicate", cursor="cursor-1")

    events = recent_llm_events(
        operations_observation=_Observation({"llm": (first, duplicate)}),
        events_service=None,
        definition_registry=None,
        limit=10,
    )

    assert len(events) == 1
    assert events[0].cursor == "cursor-1"


def test_recent_resolver_events_collects_llm_and_orchestration_observations() -> None:
    now = datetime(2026, 6, 21, tzinfo=timezone.utc)
    older = _event(
        "resolver-old",
        event_name="orchestration.llm_resolved",
        module="orchestration",
        owner="orchestration",
        occurred_at=now - timedelta(minutes=2),
    )
    newer = _event(
        "resolver-new",
        event_name="orchestration.llm_resolved",
        module="llm",
        owner="llm",
        occurred_at=now,
    )
    unrelated = _event("event-unrelated", event_name="llm.invocation_started")

    events = recent_resolver_events(
        operations_observation=_Observation(
            {
                "orchestration": (older, unrelated),
                "llm": (newer,),
            },
        ),
        events_service=None,
        definition_registry=None,
        limit=10,
    )

    assert [event.id for event in events] == ["resolver-new", "resolver-old"]


def test_lifecycle_event_section_projects_transport_continuation_and_delta_labels() -> None:
    event = _event(
        "event-prepared",
        event_name="llm.invocation_provider_request_prepared",
        occurred_at=datetime(2026, 6, 21, 12, tzinfo=timezone.utc),
        payload={
            "transport": "websocket",
            "has_previous_response_id": True,
            "previous_response_id": "resp_previous",
            "input_delta_mode": True,
            "input_delta_count": 2,
            "input_baseline_count": 3,
        },
    )

    section = llm_lifecycle_events_section((event,))

    assert section.id == "llm_lifecycle_events"
    assert section.total == 1
    assert event_transport_label(event) == "websocket"
    assert event_continuation_label(event) == "previous_response_id=resp_previous"
    assert event_input_delta_label(event) == "mode=true; delta=2; baseline=3"
    assert event_tone(event) == "neutral"
    assert section.rows[0].cells["transport"] == "websocket"
    assert section.rows[0].cells["continuation"] == "previous_response_id=resp_previous"
    assert section.rows[0].cells["input_delta"] == "mode=true; delta=2; baseline=3"
