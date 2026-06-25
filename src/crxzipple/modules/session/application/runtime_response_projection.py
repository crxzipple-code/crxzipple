from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.modules.llm.domain import (
    LlmMessagePhase,
    LlmMessageRole,
    LlmResponseItem,
    LlmResponseItemKind,
    ToolCallIntent,
)
from crxzipple.modules.session.application.item_append import AppendSessionItemInput
from crxzipple.modules.session.domain import (
    SessionItemKind,
    SessionItemPhase,
)


@dataclass(frozen=True, slots=True)
class ProjectLlmResponseItemsInput:
    session_key: str
    active_session_id: str
    invocation_id: str
    response_items: tuple[LlmResponseItem, ...]


@dataclass(frozen=True, slots=True)
class ProjectedSessionItems:
    items: tuple[AppendSessionItemInput, ...]
    tool_calls: tuple[ToolCallIntent, ...] = ()


@dataclass(frozen=True, slots=True)
class RuntimeResponseProjector:
    """Project provider-neutral LLM response items into runtime session items."""

    def project_llm_response_items(
        self,
        data: ProjectLlmResponseItemsInput,
    ) -> ProjectedSessionItems:
        item_inputs: list[AppendSessionItemInput] = []
        for item in data.response_items:
            if not _should_record_llm_response_item(item):
                continue
            item_inputs.append(
                _llm_response_item_input(
                    session_key=data.session_key,
                    active_session_id=data.active_session_id,
                    invocation_id=data.invocation_id,
                    response_item=item,
                ),
            )
            progress_item = _agent_progress_input_from_llm_response_item(
                session_key=data.session_key,
                active_session_id=data.active_session_id,
                invocation_id=data.invocation_id,
                response_item=item,
            )
            if progress_item is not None:
                item_inputs.append(progress_item)
        return ProjectedSessionItems(
            items=tuple(item_inputs),
            tool_calls=tuple(
                tool_call
                for item in data.response_items
                if (tool_call := _tool_call_intent_from_llm_response_item(item))
                is not None
            ),
        )


def project_llm_response_items(
    data: ProjectLlmResponseItemsInput,
) -> ProjectedSessionItems:
    return RuntimeResponseProjector().project_llm_response_items(data)


def runtime_semantic_kind_from_llm_response_item(item: LlmResponseItem) -> str:
    return _runtime_semantic_kind_from_llm_response_item(item)


def _llm_response_item_input(
    *,
    session_key: str,
    active_session_id: str,
    invocation_id: str,
    response_item: LlmResponseItem,
) -> AppendSessionItemInput:
    kind = _session_item_kind_from_llm_response_item(response_item.kind)
    phase = _session_item_phase_from_llm_phase(response_item.phase)
    role = _session_item_role_from_llm_response_item(response_item)
    metadata: dict[str, object] = {
        "llm_invocation_id": invocation_id,
        "llm_response_sequence_no": response_item.sequence_no,
        "runtime_semantic_kind": _runtime_semantic_kind_from_llm_response_item(
            response_item,
        ),
    }
    if response_item.completed_at is not None:
        metadata["llm_response_completed_at"] = response_item.completed_at.isoformat()
    return AppendSessionItemInput(
        session_key=session_key,
        session_id=active_session_id,
        role=role,
        kind=kind,
        phase=phase,
        content_payload=dict(response_item.content_payload),
        source_module="llm",
        source_kind="llm_response_item",
        source_id=response_item.id,
        provider_item_id=response_item.provider_item_id,
        provider_item_type=response_item.provider_item_type,
        call_id=response_item.call_id,
        tool_name=response_item.tool_name,
        metadata=metadata,
    )


def _agent_progress_input_from_llm_response_item(
    *,
    session_key: str,
    active_session_id: str,
    invocation_id: str,
    response_item: LlmResponseItem,
) -> AppendSessionItemInput | None:
    if response_item.kind is not LlmResponseItemKind.REASONING:
        return None
    text = _visible_text_from_reasoning_payload(response_item.content_payload)
    if text is None:
        return None
    return _agent_progress_input(
        session_key=session_key,
        active_session_id=active_session_id,
        invocation_id=invocation_id,
        response_item=response_item,
        text=text,
        projection_source="reasoning_summary",
    )


def _agent_progress_input(
    *,
    session_key: str,
    active_session_id: str,
    invocation_id: str,
    response_item: LlmResponseItem,
    text: str,
    projection_source: str,
) -> AppendSessionItemInput:
    metadata: dict[str, object] = {
        "llm_invocation_id": invocation_id,
        "source_llm_response_item_id": response_item.id,
        "llm_response_sequence_no": response_item.sequence_no,
        "projection_source": projection_source,
        "runtime_semantic_kind": "runtime.assistant_progress",
    }
    if response_item.completed_at is not None:
        metadata["llm_response_completed_at"] = response_item.completed_at.isoformat()
    return AppendSessionItemInput(
        session_key=session_key,
        session_id=active_session_id,
        role="assistant",
        kind=SessionItemKind.AGENT_PROGRESS,
        phase=SessionItemPhase.COMMENTARY,
        content_payload={
            "text": text,
            "projection_source": projection_source,
        },
        source_module="llm",
        source_kind="llm_response_item",
        source_id=response_item.id,
        provider_item_id=response_item.provider_item_id,
        provider_item_type=response_item.provider_item_type,
        call_id=response_item.call_id,
        tool_name=response_item.tool_name,
        metadata=metadata,
    )


def _should_record_llm_response_item(item: LlmResponseItem) -> bool:
    return item.kind is not LlmResponseItemKind.UNKNOWN


def _tool_call_intent_from_llm_response_item(
    item: LlmResponseItem,
) -> ToolCallIntent | None:
    if item.kind is not LlmResponseItemKind.TOOL_CALL:
        return None
    content = item.content_payload
    tool_name = _non_empty_text(content.get("tool_name")) or _non_empty_text(
        item.tool_name,
    )
    if tool_name is None:
        return None
    call_id = (
        _non_empty_text(content.get("call_id"))
        or _non_empty_text(item.call_id)
        or _non_empty_text(item.provider_item_id)
        or _non_empty_text(item.id)
    )
    if call_id is None:
        return None
    arguments = content.get("arguments")
    return ToolCallIntent(
        id=call_id,
        name=tool_name,
        arguments=dict(arguments) if isinstance(arguments, dict) else {},
    )


def _session_item_kind_from_llm_response_item(
    kind: LlmResponseItemKind,
) -> SessionItemKind:
    if kind is LlmResponseItemKind.ASSISTANT_MESSAGE:
        return SessionItemKind.ASSISTANT_MESSAGE
    if kind is LlmResponseItemKind.REASONING:
        return SessionItemKind.REASONING
    if kind is LlmResponseItemKind.TOOL_CALL:
        return SessionItemKind.TOOL_CALL
    if kind is LlmResponseItemKind.TOOL_RESULT:
        return SessionItemKind.TOOL_RESULT
    if kind is LlmResponseItemKind.PROVIDER_EXTERNAL_ITEM:
        return SessionItemKind.PROVIDER_EXTERNAL_ACTIVITY
    if kind is LlmResponseItemKind.COMPACTION:
        return SessionItemKind.CONTEXT_COMPACTION
    return SessionItemKind.UNKNOWN


def _runtime_semantic_kind_from_llm_response_item(item: LlmResponseItem) -> str:
    if item.kind is LlmResponseItemKind.ASSISTANT_MESSAGE:
        if item.phase is LlmMessagePhase.FINAL_ANSWER:
            return "runtime.final_answer"
        if item.phase is LlmMessagePhase.COMMENTARY:
            return "runtime.assistant_progress"
        return "runtime.assistant_message"
    if item.kind is LlmResponseItemKind.REASONING:
        return "runtime.reasoning"
    if item.kind is LlmResponseItemKind.TOOL_CALL:
        return "runtime.assistant_tool_call"
    if item.kind is LlmResponseItemKind.TOOL_RESULT:
        return "runtime.tool_result"
    if item.kind is LlmResponseItemKind.PROVIDER_EXTERNAL_ITEM:
        return "runtime.provider_external_activity"
    if item.kind is LlmResponseItemKind.COMPACTION:
        return "runtime.context_compaction"
    if item.kind is LlmResponseItemKind.STRUCTURED_OUTPUT:
        return "runtime.structured_output"
    return "runtime.unknown"


def _session_item_phase_from_llm_phase(phase: LlmMessagePhase) -> SessionItemPhase:
    if phase is LlmMessagePhase.COMMENTARY:
        return SessionItemPhase.COMMENTARY
    if phase is LlmMessagePhase.FINAL_ANSWER:
        return SessionItemPhase.FINAL_ANSWER
    return SessionItemPhase.UNKNOWN


def _session_item_role_from_llm_response_item(item: LlmResponseItem) -> str | None:
    if item.role is not None:
        return item.role.value
    if item.kind in {
        LlmResponseItemKind.ASSISTANT_MESSAGE,
        LlmResponseItemKind.REASONING,
        LlmResponseItemKind.TOOL_CALL,
        LlmResponseItemKind.PROVIDER_EXTERNAL_ITEM,
        LlmResponseItemKind.COMPACTION,
    }:
        return LlmMessageRole.ASSISTANT.value
    if item.kind is LlmResponseItemKind.TOOL_RESULT:
        return LlmMessageRole.TOOL.value
    return None


def _reasoning_summary_has_visible_text(content_payload: dict[str, object]) -> bool:
    return _visible_text_from_reasoning_payload(content_payload) is not None


def _visible_text_from_reasoning_payload(
    content_payload: dict[str, object],
) -> str | None:
    text = _non_empty_text(content_payload.get("text"))
    if text is not None:
        return text
    summary = content_payload.get("summary")
    if not isinstance(summary, (list, tuple)):
        return _non_empty_text(summary)
    parts: list[str] = []
    for item in summary:
        if isinstance(item, dict):
            part = _non_empty_text(item.get("text"))
            if part is not None:
                parts.append(part)
            continue
        part = _non_empty_text(item)
        if part is not None:
            parts.append(part)
    text = "\n".join(parts).strip()
    return text or None


def _non_empty_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
