from __future__ import annotations

from collections import Counter

from crxzipple.modules.llm.domain import (
    LlmMessagePhase,
    LlmMessageRole,
    LlmResponseItem,
    LlmResponseItemKind,
)
from crxzipple.modules.session.application.runtime_response_projection import (
    ProjectLlmResponseItemsInput,
    RuntimeResponseProjector,
    runtime_semantic_kind_from_llm_response_item,
)
from crxzipple.modules.session.domain import SessionItemKind, SessionItemPhase


def _response_item(
    *,
    item_id: str,
    sequence_no: int,
    kind: LlmResponseItemKind,
    phase: LlmMessagePhase = LlmMessagePhase.UNKNOWN,
    role: LlmMessageRole | None = LlmMessageRole.ASSISTANT,
    content_payload: dict[str, object] | None = None,
    provider_replay_candidate: bool = True,
    user_timeline_candidate: bool = False,
    call_id: str | None = None,
    tool_name: str | None = None,
) -> LlmResponseItem:
    return LlmResponseItem(
        id=item_id,
        invocation_id="llm-invocation-1",
        sequence_no=sequence_no,
        kind=kind,
        role=role,
        phase=phase,
        content_payload=content_payload or {},
        provider_payload={"type": kind.value},
        provider_item_id=f"provider-{item_id}",
        provider_item_type=kind.value,
        call_id=call_id,
        tool_name=tool_name,
        provider_replay_candidate=provider_replay_candidate,
        user_timeline_candidate=user_timeline_candidate,
    )


def test_runtime_response_projector_preserves_phase_and_fact_shape() -> None:
    projected = RuntimeResponseProjector().project_llm_response_items(
        ProjectLlmResponseItemsInput(
            session_key="agent:assistant:main",
            active_session_id="session-instance-1",
            invocation_id="llm-invocation-1",
            response_items=(
                _response_item(
                    item_id="commentary",
                    sequence_no=1,
                    kind=LlmResponseItemKind.ASSISTANT_MESSAGE,
                    phase=LlmMessagePhase.COMMENTARY,
                    content_payload={"text": "I will inspect this."},
                    user_timeline_candidate=True,
                ),
                _response_item(
                    item_id="final",
                    sequence_no=2,
                    kind=LlmResponseItemKind.ASSISTANT_MESSAGE,
                    phase=LlmMessagePhase.FINAL_ANSWER,
                    content_payload={"text": "Done."},
                    user_timeline_candidate=True,
                ),
                _response_item(
                    item_id="reasoning",
                    sequence_no=3,
                    kind=LlmResponseItemKind.REASONING,
                    content_payload={"summary": [{"text": "Need more facts."}]},
                    user_timeline_candidate=False,
                ),
            ),
        ),
    )

    commentary, final, reasoning, progress = projected.items
    assert commentary.kind is SessionItemKind.ASSISTANT_MESSAGE
    assert commentary.phase is SessionItemPhase.COMMENTARY
    assert commentary.metadata["runtime_semantic_kind"] == "runtime.assistant_progress"

    assert final.kind is SessionItemKind.ASSISTANT_MESSAGE
    assert final.phase is SessionItemPhase.FINAL_ANSWER
    assert final.metadata["runtime_semantic_kind"] == "runtime.final_answer"

    assert reasoning.kind is SessionItemKind.REASONING
    assert reasoning.metadata["runtime_semantic_kind"] == "runtime.reasoning"

    assert progress.kind is SessionItemKind.AGENT_PROGRESS
    assert progress.phase is SessionItemPhase.COMMENTARY
    assert progress.metadata["runtime_semantic_kind"] == "runtime.assistant_progress"
    assert progress.content_payload["text"] == "Need more facts."
    assert progress.content_payload["projection_source"] == "reasoning_summary"
    assert progress.source_id == "reasoning"


def test_runtime_response_projector_projects_commentary_as_trace_progress() -> None:
    projected = RuntimeResponseProjector().project_llm_response_items(
        ProjectLlmResponseItemsInput(
            session_key="agent:assistant:main",
            active_session_id="session-instance-1",
            invocation_id="llm-invocation-1",
            response_items=(
                _response_item(
                    item_id="commentary",
                    sequence_no=1,
                    kind=LlmResponseItemKind.ASSISTANT_MESSAGE,
                    phase=LlmMessagePhase.COMMENTARY,
                    content_payload={"text": "I will inspect this."},
                    user_timeline_candidate=True,
                ),
            ),
        ),
    )

    (commentary,) = projected.items

    assert commentary.kind is SessionItemKind.ASSISTANT_MESSAGE
    assert commentary.phase is SessionItemPhase.COMMENTARY
    assert commentary.metadata["runtime_semantic_kind"] == "runtime.assistant_progress"


def test_runtime_response_projector_keeps_commentary_out_of_chat_final_view() -> None:
    projected = RuntimeResponseProjector().project_llm_response_items(
        ProjectLlmResponseItemsInput(
            session_key="agent:assistant:main",
            active_session_id="session-instance-1",
            invocation_id="llm-invocation-1",
            response_items=(
                _response_item(
                    item_id="commentary-visible",
                    sequence_no=1,
                    kind=LlmResponseItemKind.ASSISTANT_MESSAGE,
                    phase=LlmMessagePhase.COMMENTARY,
                    content_payload={"text": "I will inspect the site first."},
                    user_timeline_candidate=True,
                ),
                _response_item(
                    item_id="final-visible",
                    sequence_no=2,
                    kind=LlmResponseItemKind.ASSISTANT_MESSAGE,
                    phase=LlmMessagePhase.FINAL_ANSWER,
                    content_payload={"text": "The answer is ready."},
                    user_timeline_candidate=True,
                ),
            ),
        ),
    )

    commentary, final = projected.items

    assert commentary.phase is SessionItemPhase.COMMENTARY

    assert final.phase is SessionItemPhase.FINAL_ANSWER


def test_runtime_response_projector_preserves_tool_protocol_refs() -> None:
    projected = RuntimeResponseProjector().project_llm_response_items(
        ProjectLlmResponseItemsInput(
            session_key="agent:assistant:main",
            active_session_id="session-instance-1",
            invocation_id="llm-invocation-1",
            response_items=(
                _response_item(
                    item_id="tool-call",
                    sequence_no=1,
                    kind=LlmResponseItemKind.TOOL_CALL,
                    content_payload={"arguments": {"cmd": "date"}},
                    call_id="call-1",
                    tool_name="command.exec",
                ),
            ),
        ),
    )

    tool_call = projected.items[0]
    assert tool_call.kind is SessionItemKind.TOOL_CALL
    assert tool_call.role == "assistant"
    assert tool_call.call_id == "call-1"
    assert tool_call.tool_name == "command.exec"
    assert tool_call.provider_item_id == "provider-tool-call"
    assert tool_call.source_module == "llm"
    assert tool_call.source_kind == "llm_response_item"
    assert tool_call.metadata["llm_invocation_id"] == "llm-invocation-1"
    assert tool_call.metadata["runtime_semantic_kind"] == "runtime.assistant_tool_call"
    assert runtime_semantic_kind_from_llm_response_item(
        _response_item(
            item_id="tool-call-helper",
            sequence_no=2,
            kind=LlmResponseItemKind.TOOL_CALL,
            call_id="call-2",
            tool_name="command.exec",
        ),
    ) == "runtime.assistant_tool_call"
    assert projected.tool_calls[0].id == "call-1"
    assert projected.tool_calls[0].name == "command.exec"
    assert projected.tool_calls[0].arguments == {"cmd": "date"}


def test_runtime_response_projector_records_known_items_without_visibility_filter() -> None:
    projected = RuntimeResponseProjector().project_llm_response_items(
        ProjectLlmResponseItemsInput(
            session_key="agent:assistant:main",
            active_session_id="session-instance-1",
            invocation_id="llm-invocation-1",
            response_items=(
                _response_item(
                    item_id="hidden-tool-call",
                    sequence_no=1,
                    kind=LlmResponseItemKind.TOOL_CALL,
                    content_payload={"arguments": {"cmd": "date"}},
                    provider_replay_candidate=False,
                    user_timeline_candidate=False,
                    call_id="call-hidden",
                    tool_name="command.exec",
                ),
                _response_item(
                    item_id="hidden-reasoning",
                    sequence_no=2,
                    kind=LlmResponseItemKind.REASONING,
                    content_payload={"summary": [{"text": "I need a probe."}]},
                    provider_replay_candidate=False,
                    user_timeline_candidate=False,
                ),
            ),
        ),
    )

    tool_call, reasoning, progress = projected.items

    assert tool_call.kind is SessionItemKind.TOOL_CALL
    assert tool_call.call_id == "call-hidden"
    assert reasoning.kind is SessionItemKind.REASONING
    assert progress.kind is SessionItemKind.AGENT_PROGRESS
    assert progress.source_id == "hidden-reasoning"
    assert projected.tool_calls[0].id == "call-hidden"


def test_runtime_response_projector_closes_latest_run_agent_progress_gap() -> None:
    response_items = tuple(
        _response_item(
            item_id=f"reasoning-{index}",
            sequence_no=index,
            kind=LlmResponseItemKind.REASONING,
            content_payload={"summary": [{"text": f"Progress note {index}."}]},
            provider_replay_candidate=False,
            user_timeline_candidate=False,
        )
        for index in range(1, 35)
    ) + tuple(
        _response_item(
            item_id=f"tool-call-{index}",
            sequence_no=34 + index,
            kind=LlmResponseItemKind.TOOL_CALL,
            content_payload={"arguments": {"cmd": "date"}},
            call_id=f"call-{index}",
            tool_name="command.exec",
        )
        for index in range(1, 43)
    ) + (
        _response_item(
            item_id="assistant-final",
            sequence_no=77,
            kind=LlmResponseItemKind.ASSISTANT_MESSAGE,
            phase=LlmMessagePhase.FINAL_ANSWER,
            content_payload={"text": "Done."},
            user_timeline_candidate=True,
        ),
    )

    projected = RuntimeResponseProjector().project_llm_response_items(
        ProjectLlmResponseItemsInput(
            session_key="agent:assistant:main",
            active_session_id="session-instance-1",
            invocation_id="llm-invocation-1",
            response_items=response_items,
        ),
    )

    source_counts = Counter(item.kind for item in response_items)
    projected_counts = Counter(item.kind for item in projected.items)

    assert source_counts == {
        LlmResponseItemKind.REASONING: 34,
        LlmResponseItemKind.TOOL_CALL: 42,
        LlmResponseItemKind.ASSISTANT_MESSAGE: 1,
    }
    assert projected_counts[SessionItemKind.REASONING] == 34
    assert projected_counts[SessionItemKind.TOOL_CALL] == 42
    assert projected_counts[SessionItemKind.ASSISTANT_MESSAGE] == 1
    assert projected_counts[SessionItemKind.AGENT_PROGRESS] == 34
    assert len(projected.tool_calls) == 42


def test_runtime_response_projector_records_provider_external_as_runtime_item() -> None:
    projected = RuntimeResponseProjector().project_llm_response_items(
        ProjectLlmResponseItemsInput(
            session_key="agent:assistant:main",
            active_session_id="session-instance-1",
            invocation_id="llm-invocation-1",
            response_items=(
                _response_item(
                    item_id="provider-external",
                    sequence_no=1,
                    kind=LlmResponseItemKind.PROVIDER_EXTERNAL_ITEM,
                    phase=LlmMessagePhase.COMMENTARY,
                    content_payload={"status": "completed"},
                    user_timeline_candidate=True,
                ),
            ),
        ),
    )

    provider_item = projected.items[0]

    assert provider_item.kind is SessionItemKind.PROVIDER_EXTERNAL_ACTIVITY
    assert provider_item.phase is SessionItemPhase.COMMENTARY
    assert provider_item.source_kind == "llm_response_item"
    assert provider_item.source_id == "provider-external"
    assert provider_item.provider_item_id == "provider-provider-external"
    assert provider_item.provider_item_type == "provider_external_item"


def test_runtime_response_projector_drops_unknown_items() -> None:
    projected = RuntimeResponseProjector().project_llm_response_items(
        ProjectLlmResponseItemsInput(
            session_key="agent:assistant:main",
            active_session_id="session-instance-1",
            invocation_id="llm-invocation-1",
            response_items=(
                _response_item(
                    item_id="unknown",
                    sequence_no=1,
                    kind=LlmResponseItemKind.UNKNOWN,
                    role=None,
                    provider_replay_candidate=False,
                    user_timeline_candidate=False,
                ),
            ),
        ),
    )

    assert projected.items == ()
