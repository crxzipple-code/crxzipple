from __future__ import annotations

from datetime import datetime, timezone

from crxzipple.modules.llm.domain import (
    LlmInputItem,
    LlmInputItemKind,
    LlmInvocation,
    LlmMessage,
    LlmMessageRole,
)
from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.llm_resolver_problem_sections import (
    fallback_problems_section,
)
from crxzipple.modules.operations.application.read_models.llm_resolver_sections import (
    model_resolver_section,
    resolver_bucket,
    resolver_events_by_run_id,
    resolver_facts_section,
)


def _invocation(invocation_id: str = "invocation-1") -> LlmInvocation:
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
    status: str = "observed",
    payload: dict[str, object] | None = None,
    run_id: str | None = None,
    trace_id: str | None = None,
) -> OperationsObservedEvent:
    return OperationsObservedEvent(
        id=event_id,
        cursor=event_id,
        topic="events.named.orchestration.llm_resolved",
        event_name="orchestration.llm_resolved",
        module="orchestration",
        owner="orchestration",
        kind="fact",
        level="info",
        status=status,
        entity_id=run_id or event_id,
        run_id=run_id,
        trace_id=trace_id,
        source_event_name="orchestration.llm_resolved",
        occurred_at=datetime(2026, 6, 21, tzinfo=timezone.utc),
        payload=dict(payload or {}),
    )


def test_resolver_bucket_classifies_default_override_fallback_and_no_match() -> None:
    assert (
        resolver_bucket(
            _event(
                "default",
                payload={
                    "requested_llm_id": "openai.gpt",
                    "resolved_llm_id": "openai.gpt",
                },
            ),
        )
        == "agent_default"
    )
    assert (
        resolver_bucket(
            _event(
                "override",
                payload={
                    "resolved_llm_id": "openai.gpt",
                    "strategy": "explicit_override",
                },
            ),
        )
        == "explicit_override"
    )
    assert (
        resolver_bucket(
            _event(
                "fallback",
                payload={
                    "requested_llm_id": "openai.gpt",
                    "resolved_llm_id": "anthropic.claude",
                },
            ),
        )
        == "fallback_used"
    )
    assert (
        resolver_bucket(
            _event(
                "failed",
                status="failed",
                payload={"requested_llm_id": "openai.gpt"},
            ),
        )
        == "no_match"
    )


def test_resolver_sections_project_run_mapping_and_problem_rows() -> None:
    fallback = _event(
        "fallback",
        run_id="run-1",
        trace_id="trace-1",
        payload={
            "run_id": "run-1",
            "requested_llm_id": "openai.gpt",
            "resolved_llm_id": "anthropic.claude",
            "strategy": "fallback",
            "reason": "primary unavailable",
            "routing_input_block_count": 3,
            "session_replay_window": {
                "from_sequence_no": 1,
                "to_sequence_no": 5,
                "item_count": 4,
                "active_session_only": True,
                "protocol_call_ids": ["call-1"],
            },
        },
    )

    assert resolver_events_by_run_id((fallback,)) == {"run-1": fallback}

    facts = resolver_facts_section(
        _invocation(),
        resolver_event=fallback,
        run_context={"run_id": "run-1"},
    )
    assert facts.id == "resolver"
    values = {item.label: item.value for item in facts.items}
    assert values["Requested"] == "openai.gpt"
    assert values["Resolved"] == "anthropic.claude"
    assert values["Decision"] == "Fallback Used"
    assert values["Routing Input Blocks"] == "3"
    assert values["Session Replay Window"] == (
        "seq=1..5; items=4; active_only=true; calls=1"
    )

    problems = fallback_problems_section((fallback,))
    assert problems.id == "fallback_problems"
    assert problems.rows[0].status == "fallback_used"
    assert problems.rows[0].tone == "warning"
    assert problems.rows[0].cells["reason"] == "primary unavailable"


def test_model_resolver_section_counts_decision_buckets() -> None:
    default = _event(
        "default",
        payload={
            "requested_llm_id": "openai.gpt",
            "resolved_llm_id": "openai.gpt",
        },
    )
    fallback = _event(
        "fallback",
        payload={
            "requested_llm_id": "openai.gpt",
            "resolved_llm_id": "anthropic.claude",
        },
    )

    section = model_resolver_section((default, fallback))

    assert section.id == "model_resolver"
    assert section.total == 2
    assert {segment.id: segment.value for segment in section.segments} == {
        "agent_default": 1,
        "fallback_used": 1,
    }


def test_resolver_facts_section_uses_invocation_profile_without_event() -> None:
    facts = resolver_facts_section(
        _invocation(),
        resolver_event=None,
        run_context={"run_id": "run-1"},
    )

    assert {item.label: item.value for item in facts.items} == {
        "Requested": "-",
        "Resolved": "openai.gpt",
        "Strategy": "-",
        "Run ID": "run-1",
    }
