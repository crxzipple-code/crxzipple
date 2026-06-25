from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from crxzipple.modules.llm.domain import (
    LlmInputItem,
    LlmInputItemKind,
    LlmInvocation,
    LlmMessage,
    LlmMessageRole,
)
from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.llm_response_events import (
    events_by_invocation,
    response_event_retention_policy,
    response_events_by_invocation,
)


class _LlmService:
    def __init__(self) -> None:
        self.requested: list[tuple[str, int]] = []

    def list_response_events(self, invocation_id: str, *, limit: int):
        self.requested.append((invocation_id, limit))
        return (f"event:{invocation_id}",)

    def response_event_retention_policy(self):
        return SimpleNamespace(
            to_payload=lambda: {
                "full_event_window_seconds": 300,
                "detail_event_limit": 100,
            },
        )


def _invocation(invocation_id: str) -> LlmInvocation:
    return LlmInvocation(
        id=invocation_id,
        llm_id="openai.gpt",
        messages=(LlmMessage(role=LlmMessageRole.USER, content="hello"),),
        input_items=(
            LlmInputItem(
                kind=LlmInputItemKind.MESSAGE,
                payload={"role": "user", "content": "hello"},
            ),
        ),
    )


def _event(
    event_id: str,
    *,
    event_name: str = "llm.invocation_started",
    entity_id: str = "invocation-1",
    payload: dict[str, object] | None = None,
    occurred_at: datetime | None = None,
) -> OperationsObservedEvent:
    return OperationsObservedEvent(
        id=event_id,
        cursor=event_id,
        topic=f"events.named.{event_name}",
        event_name=event_name,
        module="llm",
        owner="llm",
        kind="fact",
        level="info",
        status="observed",
        entity_id=entity_id,
        run_id=None,
        trace_id=None,
        source_event_name=event_name,
        occurred_at=occurred_at or datetime(2026, 6, 21, tzinfo=timezone.utc),
        payload=dict(payload or {}),
    )


def test_events_by_invocation_groups_payload_and_entity_ids() -> None:
    newer = _event(
        "event-new",
        payload={"invocation_id": "invocation-1"},
        occurred_at=datetime(2026, 6, 21, 1, tzinfo=timezone.utc),
    )
    older = _event(
        "event-old",
        payload={"llm_invocation_id": "invocation-1"},
        occurred_at=datetime(2026, 6, 21, tzinfo=timezone.utc),
    )
    entity_event = _event(
        "event-entity",
        event_name="llm.invocation_failed",
        entity_id="invocation-2",
    )

    grouped = events_by_invocation((older, entity_event, newer))

    assert [event.id for event in grouped["invocation-1"]] == [
        "event-new",
        "event-old",
    ]
    assert [event.id for event in grouped["invocation-2"]] == ["event-entity"]


def test_response_events_by_invocation_reads_each_invocation_with_detail_limit() -> None:
    service = _LlmService()

    grouped = response_events_by_invocation(
        service,  # type: ignore[arg-type]
        (_invocation("invocation-1"), _invocation("invocation-2")),
    )

    assert grouped == {
        "invocation-1": ("event:invocation-1",),
        "invocation-2": ("event:invocation-2",),
    }
    assert service.requested == [("invocation-1", 100), ("invocation-2", 100)]


def test_response_event_retention_policy_accepts_payload_object_or_dict() -> None:
    service = _LlmService()
    assert response_event_retention_policy(service) == {
        "full_event_window_seconds": 300,
        "detail_event_limit": 100,
    }

    dict_service = SimpleNamespace(
        response_event_retention_policy=lambda: {"detail_event_limit": 50},
    )
    assert response_event_retention_policy(dict_service) == {
        "detail_event_limit": 50,
    }


def test_response_event_retention_policy_returns_empty_for_missing_or_failed_port() -> None:
    missing = SimpleNamespace()
    failing = SimpleNamespace(
        response_event_retention_policy=lambda: (_ for _ in ()).throw(RuntimeError()),
    )

    assert response_event_retention_policy(missing) == {}
    assert response_event_retention_policy(failing) == {}
