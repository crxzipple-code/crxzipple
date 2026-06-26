from __future__ import annotations

import pytest

from crxzipple.modules.llm.domain import (
    LlmInputItem,
    LlmInputItemKind,
    LlmMessage,
    LlmMessageRole,
    ToolSchema,
)
from crxzipple.modules.llm.domain import LlmCapability
from crxzipple.modules.llm.application.provider_continuation import (
    provider_continuation_from_state,
)
from crxzipple.modules.orchestration.application.ports import (
    RequestRenderSnapshotRecord,
)
from crxzipple.modules.orchestration.application.engine_runtime_helpers import (
    llm_request_options_from_run,
    llm_request_options_from_run_metadata,
)
from crxzipple.modules.orchestration.application.runtime_llm_request_draft import RuntimeLlmRequestDraft
from crxzipple.modules.llm.application.runtime_request_factory import (
    RuntimeLlmRequestBuilder,
)
from crxzipple.modules.orchestration.application.runtime_request_mode import RuntimeRequestMode
from crxzipple.modules.orchestration.application.runtime_request_report import (
    RuntimeRequestReport,
    RunSurfacePolicy,
)
from crxzipple.modules.orchestration.application.tool_resolver import (
    ResolvedTool,
    ResolvedToolSet,
)
from crxzipple.modules.orchestration.domain import (
    InboundInstruction,
    OrchestrationRun,
    OrchestrationValidationError,
)
from crxzipple.modules.tool.domain import Tool, ToolExecutionTarget


def test_draft_with_request_render_snapshot_keeps_tree_out_of_provider_messages() -> None:
    builder = RuntimeLlmRequestBuilder()
    draft = _draft(
        messages=(
            LlmMessage(role=LlmMessageRole.SYSTEM, content="system one"),
            LlmMessage(role=LlmMessageRole.SYSTEM, content="system two"),
            LlmMessage(role=LlmMessageRole.USER, content="hello"),
        ),
        tool_schemas=(ToolSchema(name="old.tool"),),
    )
    snapshot = RequestRenderSnapshotRecord(
        snapshot_id="ctxsnap_1",
        tool_schemas=(ToolSchema(name="weather.lookup"),),
        tool_schema_refs=(_tool_schema_ref("weather.lookup"),),
        projected_input_items=_projected_user_message("hello"),
        artifact_content_blocks=(
            {
                "type": "image_ref",
                "image_ref": {"artifact_id": "artifact-1"},
            },
        ),
    )

    result = builder.draft_with_request_render_snapshot(draft, snapshot)

    assert tuple(message.role for message in result.messages) == (
        LlmMessageRole.SYSTEM,
        LlmMessageRole.SYSTEM,
        LlmMessageRole.USER,
    )
    assert "<context_tree" not in str([message.content for message in result.messages])
    assert [schema.name for schema in result.tool_schemas] == ["old.tool"]


def test_request_envelope_can_use_snapshot_without_replaying_context_messages() -> None:
    builder = RuntimeLlmRequestBuilder()
    draft = _draft(
        messages=(
            LlmMessage(role=LlmMessageRole.SYSTEM, content="system"),
            LlmMessage(role=LlmMessageRole.USER, content="hello"),
        ),
        tool_schemas=(ToolSchema(name="old.tool"),),
    )
    snapshot = RequestRenderSnapshotRecord(
        snapshot_id="ctxsnap_delta",
        included_node_ids=("session.current",),
        mirrored_node_ids=("tools.browser.network",),
        included_refs=(
            {
                "node_id": "session.current",
                "kind": "session",
                "title": "Current session",
                "source_ref": "session:internal",
            },
        ),
        tool_schemas=(ToolSchema(name="weather.lookup"),),
        tool_schema_refs=(_tool_schema_ref("weather.lookup"),),
        projected_input_items=_projected_user_message("hello"),
        artifact_content_blocks=(
            {
                "type": "image_ref",
                "image_ref": {"artifact_id": "artifact-1"},
            },
        ),
    )
    resolved_tools = ResolvedToolSet(
        tools=(_resolved_tool("tool.weather", schema_name="weather.lookup"),),
    )

    envelope = builder.request_envelope(
        draft=draft,
        request_render_snapshot=snapshot,
        resolved_tools=resolved_tools,
        snapshot_metadata=snapshot.metadata,
    )

    assert tuple(message.content for message in envelope.messages) == (
        [{"type": "text", "text": "hello"}],
    )
    assert tuple(message.role for message in envelope.messages) == (LlmMessageRole.USER,)
    assert tuple(message.content for message in envelope.provider_context_messages) == (
        "system",
    )
    assert envelope.provider_context_messages[0].metadata == {
        "provider_context_kind": "runtime_instruction",
        "source": "runtime_request_draft_message",
    }
    assert envelope.request_metadata()["provider_context_message_count"] == 1
    assert envelope.request_metadata()["provider_context_message_kinds"] == [
        "runtime_instruction",
    ]
    assert "<context_tree" not in str(envelope.to_payload()["messages"])
    assert tuple(item.kind for item in envelope.transcript.items) == (
        LlmInputItemKind.MESSAGE,
    )
    assert [schema.name for schema in envelope.tool_schemas] == ["weather.lookup"]
    assert envelope.request_render_snapshot.snapshot_id == "ctxsnap_delta"
    assert "raw_tree_body" not in envelope.request_render_snapshot.to_payload()
    assert envelope.tool_surface.functions[0].name == "weather.lookup"
    assert envelope.metadata["request_render_snapshot_id"] == "ctxsnap_delta"
    assert "context_snapshot_id" not in envelope.metadata
    assert envelope.metadata["input_mode"] == "runtime_transcript"
    assert envelope.metadata["input_item_count"] == 1
    assert envelope.metadata["input_item_source_counts"] == {"runtime_transcript": 1}
    assert "context_slice_item_count" not in envelope.metadata


def test_request_envelope_uses_request_snapshot_session_refs_to_filter_input() -> None:
    builder = RuntimeLlmRequestBuilder()
    draft = _draft(
        input_items=(
            LlmInputItem(
                kind=LlmInputItemKind.MESSAGE,
                payload={
                    "role": "user",
                    "content": "older replay item",
                },
                source="session_item",
                metadata={"session_item_id": "item-old"},
            ),
            LlmInputItem(
                kind=LlmInputItemKind.MESSAGE,
                payload={
                    "role": "user",
                    "content": "slice-selected task",
                },
                source="session_item",
                metadata={"session_item_id": "item-selected"},
            ),
        ),
    )
    snapshot = RequestRenderSnapshotRecord(
        snapshot_id="ctxsnap_context_slice_input",
        included_refs=(
            {
                "owner_module": "session",
                "kind": "session_item",
                "item_id": "item-selected",
            },
        ),
        projected_input_items=_projected_user_message(
            "slice-selected task",
            session_item_id="item-selected",
        ),
    )

    envelope = builder.request_envelope(
        draft=draft,
        request_render_snapshot=snapshot,
        resolved_tools=ResolvedToolSet(tools=()),
        snapshot_metadata=snapshot.metadata,
    )

    assert tuple(item.source for item in envelope.transcript.items) == (
        "runtime_transcript",
    )
    assert tuple(item.kind for item in envelope.transcript.items) == (
        LlmInputItemKind.MESSAGE,
    )
    assert envelope.transcript.items[0].payload == {
        "role": "user",
        "content": [{"type": "text", "text": "slice-selected task"}],
    }
    assert envelope.metadata["input_mode"] == "runtime_transcript"
    assert envelope.metadata["runtime_input_filter"] == {
        "mode": "request_render_projected_input",
        "input_before_filter_count": 1,
        "input_after_filter_count": 1,
        "dropped_input_item_count": 0,
        "dropped_orphan_function_call_count": 0,
    }
    assert "context_slice_item_count" not in envelope.metadata
    assert "older replay item" not in str(envelope.transcript.to_payload())


def test_request_envelope_prefers_snapshot_projected_input_items() -> None:
    builder = RuntimeLlmRequestBuilder()
    draft = _draft(
        input_items=(
            LlmInputItem(
                kind=LlmInputItemKind.MESSAGE,
                payload={"role": "user", "content": "draft replay should not drive input"},
                source="session_item",
                metadata={"session_item_id": "draft-item"},
            ),
        ),
    )
    snapshot = RequestRenderSnapshotRecord(
        snapshot_id="ctxsnap_projected_input",
        included_refs=(
            {
                "owner_module": "session",
                "kind": "session_item",
                "item_id": "slice-item",
            },
        ),
        projected_input_items=(
            {
                "kind": "message",
                "payload": {
                    "role": "user",
                    "content": "slice projected input",
                },
                "source": "context_slice",
                "metadata": {
                    "session_item_id": "slice-item",
                    "node_id": "session.item.slice-item",
                },
            },
        ),
    )

    envelope = builder.request_envelope(
        draft=draft,
        request_render_snapshot=snapshot,
        resolved_tools=ResolvedToolSet(tools=()),
        snapshot_metadata=snapshot.metadata,
    )

    assert envelope.transcript.items[0].payload == {
        "role": "user",
        "content": "slice projected input",
    }
    assert envelope.transcript.items[0].source == "runtime_transcript"
    assert envelope.transcript.items[0].metadata["session_item_id"] == "slice-item"
    assert envelope.transcript.items[0].metadata["node_id"] == "session.item.slice-item"
    assert envelope.metadata["runtime_input_source"] == "request_render_snapshot"
    assert envelope.metadata["request_render_projected_input_item_count"] == 1
    assert envelope.metadata["runtime_input_filter"] == {
        "mode": "request_render_projected_input",
        "input_before_filter_count": 1,
        "input_after_filter_count": 1,
        "dropped_input_item_count": 0,
        "dropped_orphan_function_call_count": 0,
    }
    assert "draft replay should not drive input" not in str(
        envelope.transcript.to_payload(),
    )


def test_request_envelope_projected_input_bounds_long_session_replay() -> None:
    builder = RuntimeLlmRequestBuilder()
    draft = _draft(
        input_items=tuple(
            LlmInputItem(
                kind=LlmInputItemKind.MESSAGE,
                payload={
                    "role": "user",
                    "content": f"old replay item {index}",
                },
                source="session_item",
                metadata={"session_item_id": f"old-item-{index}"},
            )
            for index in range(50)
        ),
    )
    snapshot = RequestRenderSnapshotRecord(
        snapshot_id="ctxsnap_compacted_session_projection",
        metadata={"request_context_source": "context_slice"},
        projected_input_items=(
            {
                "kind": "message",
                "payload": {
                    "role": "assistant",
                    "content": "Compacted old segment summary.",
                },
                "source": "context_slice",
                "metadata": {
                    "session_item_id": "summary-item",
                    "node_id": "session.segment.compacted.session-old",
                },
            },
            {
                "kind": "message",
                "payload": {
                    "role": "user",
                    "content": "Current active request.",
                },
                "source": "context_slice",
                "metadata": {
                    "session_item_id": "current-item",
                    "node_id": "session.item.current",
                },
            },
        ),
    )

    envelope = builder.request_envelope(
        draft=draft,
        request_render_snapshot=snapshot,
        resolved_tools=ResolvedToolSet(tools=()),
        snapshot_metadata=snapshot.metadata,
    )

    payload_text = str(envelope.transcript.to_payload())
    assert len(envelope.transcript.items) == 2
    assert envelope.metadata["runtime_input_source"] == "request_render_snapshot"
    assert envelope.metadata["request_render_projected_input_item_count"] == 2
    assert envelope.metadata["input_item_count"] == 2
    assert "Compacted old segment summary." in payload_text
    assert "Current active request." in payload_text
    assert "old replay item 0" not in payload_text
    assert "old replay item 49" not in payload_text


def test_context_slice_snapshot_requires_projected_input_items() -> None:
    builder = RuntimeLlmRequestBuilder()
    draft = _draft(
        input_items=(
            LlmInputItem(
                kind=LlmInputItemKind.MESSAGE,
                payload={"role": "user", "content": "draft fallback"},
                source="session_item",
                metadata={"session_item_id": "draft-item"},
            ),
        ),
    )
    snapshot = RequestRenderSnapshotRecord(
        snapshot_id="ctxsnap_missing_projected_input",
        included_refs=(
            {
                "owner_module": "session",
                "kind": "session_item",
                "item_id": "draft-item",
            },
        ),
        metadata={"request_context_source": "context_slice"},
    )

    with pytest.raises(OrchestrationValidationError) as exc:
        builder.request_envelope(
            draft=draft,
            request_render_snapshot=snapshot,
            resolved_tools=ResolvedToolSet(tools=()),
            snapshot_metadata=snapshot.metadata,
        )

    assert exc.value.code == "request_render_projected_input_required"
    assert exc.value.details["request_render_snapshot_id"] == (
        "ctxsnap_missing_projected_input"
    )
    assert exc.value.details["request_context_source"] == "context_slice"


def test_request_envelope_does_not_expose_context_slice_as_input_mode() -> None:
    builder = RuntimeLlmRequestBuilder()
    draft = _draft(
        input_items=(
            LlmInputItem(
                kind=LlmInputItemKind.MESSAGE,
                payload={
                    "role": "user",
                    "content": "legacy source item",
                },
                source="context_slice",
                metadata={"context_slice_item_id": "slice-legacy"},
            ),
        ),
    )

    envelope = builder.request_envelope(
        draft=draft,
        request_render_snapshot=RequestRenderSnapshotRecord(
            snapshot_id="ctxsnap-legacy-source",
            projected_input_items=_projected_user_message("legacy source item"),
        ),
        resolved_tools=ResolvedToolSet(tools=()),
        snapshot_metadata={},
    )

    assert envelope.metadata["input_mode"] == "runtime_transcript"
    assert envelope.metadata["input_item_source_counts"] == {"runtime_transcript": 1}
    assert envelope.metadata["runtime_input_filter"] == {
        "mode": "request_render_projected_input",
        "input_before_filter_count": 1,
        "input_after_filter_count": 1,
        "dropped_input_item_count": 0,
        "dropped_orphan_function_call_count": 0,
    }
    assert envelope.transcript.items[0].source == "runtime_transcript"
    assert "context_slice_item_id" not in envelope.transcript.items[0].metadata


def test_request_envelope_does_not_project_context_slice_tool_interaction_to_input() -> None:
    builder = RuntimeLlmRequestBuilder()
    draft = _draft(
        input_items=(
            LlmInputItem(
                kind=LlmInputItemKind.MESSAGE,
                payload={"role": "user", "content": "Inspect."},
                source="session_item",
            ),
        ),
    )
    snapshot = RequestRenderSnapshotRecord(
        snapshot_id="ctxsnap_tool_interaction_input",
        projected_input_items=_projected_user_message("Inspect."),
    )

    envelope = builder.request_envelope(
        draft=draft,
        request_render_snapshot=snapshot,
        resolved_tools=ResolvedToolSet(tools=()),
        snapshot_metadata=snapshot.metadata,
    )

    assert tuple(item.kind for item in envelope.transcript.items) == (
        LlmInputItemKind.MESSAGE,
    )
    assert envelope.transcript.items[0].payload["content"] == [
        {"type": "text", "text": "Inspect."},
    ]
    assert "tool_interaction" not in str(envelope.transcript.to_payload())


def test_request_envelope_drops_orphan_context_slice_tool_protocol_items() -> None:
    builder = RuntimeLlmRequestBuilder()
    draft = _draft(messages=(LlmMessage(role=LlmMessageRole.USER, content="Inspect."),))
    snapshot = RequestRenderSnapshotRecord(
        snapshot_id="ctxsnap_orphan_tool_protocol",
        projected_input_items=(
            *_projected_user_message("Inspect."),
            {
                "kind": "function_call",
                "payload": {
                    "type": "function_call",
                    "call_id": "call-without-output",
                    "name": "browser.navigate",
                    "arguments": {"url": "https://example.com"},
                },
                "source": "context_slice",
                "metadata": {"session_item_id": "tool-call-item"},
            },
            {
                "kind": "function_call_output",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-without-call",
                    "output": "historical tool output",
                },
                "source": "context_slice",
                "metadata": {"session_item_id": "tool-result-item"},
            },
        ),
    )

    envelope = builder.request_envelope(
        draft=draft,
        request_render_snapshot=snapshot,
        resolved_tools=ResolvedToolSet(tools=()),
        snapshot_metadata=snapshot.metadata,
    )

    assert tuple(item.kind for item in envelope.transcript.items) == (
        LlmInputItemKind.MESSAGE,
    )
    assert envelope.transcript.items[0].payload["content"] == [
        {"type": "text", "text": "Inspect."},
    ]
    assert "call-without-output" not in str(envelope.transcript.to_payload())
    assert "call-without-call" not in str(envelope.transcript.to_payload())
    assert "historical tool output" not in str(envelope.transcript.to_payload())
    assert envelope.metadata["runtime_input_filter"][
        "dropped_orphan_function_call_count"
    ] == 1
    assert envelope.metadata["runtime_input_filter"][
        "dropped_orphan_function_call_output_count"
    ] == 1


def test_request_envelope_drops_context_slice_tool_role_messages() -> None:
    builder = RuntimeLlmRequestBuilder()
    draft = _draft(messages=(LlmMessage(role=LlmMessageRole.USER, content="Inspect."),))
    snapshot = RequestRenderSnapshotRecord(
        snapshot_id="ctxsnap_tool_role_message",
        projected_input_items=_projected_user_message("Inspect."),
    )

    envelope = builder.request_envelope(
        draft=draft,
        request_render_snapshot=snapshot,
        resolved_tools=ResolvedToolSet(tools=()),
        snapshot_metadata=snapshot.metadata,
    )

    assert tuple(item.kind for item in envelope.transcript.items) == (
        LlmInputItemKind.MESSAGE,
    )
    assert envelope.transcript.items[0].payload["content"] == [
        {"type": "text", "text": "Inspect."},
    ]
    assert "tool_result" not in str(envelope.transcript.to_payload())


def test_request_envelope_keeps_workspace_handle_only_slice_item_body_out_of_input() -> None:
    builder = RuntimeLlmRequestBuilder()
    draft = _draft(
        messages=(LlmMessage(role=LlmMessageRole.USER, content="Inspect workspace."),),
    )
    snapshot = RequestRenderSnapshotRecord(
        snapshot_id="ctxsnap_workspace_handle",
        projected_input_items=_projected_user_message("Inspect workspace."),
    )

    envelope = builder.request_envelope(
        draft=draft,
        request_render_snapshot=snapshot,
        resolved_tools=ResolvedToolSet(tools=()),
        snapshot_metadata=snapshot.metadata,
    )

    payload = envelope.transcript.to_payload()
    assert envelope.metadata["input_mode"] == "runtime_transcript"
    assert envelope.transcript.items[0].payload == {
        "role": "user",
        "content": [{"type": "text", "text": "Inspect workspace."}],
    }
    assert "workspace_read" not in str(payload)
    assert "RAW AGENTS BODY MUST NOT ENTER MODEL INPUT" not in str(payload)


def test_request_envelope_does_not_inject_agent_instruction_as_provider_context() -> None:
    builder = RuntimeLlmRequestBuilder()
    draft = _draft(
        messages=(LlmMessage(role=LlmMessageRole.USER, content="Inspect."),),
        agent_instruction="Be precise.",
    )

    snapshot = RequestRenderSnapshotRecord(
        snapshot_id="ctxsnap-agent-instruction",
        projected_input_items=_projected_user_message("Inspect."),
    )

    envelope = builder.request_envelope(
        draft=draft,
        request_render_snapshot=snapshot,
        resolved_tools=ResolvedToolSet(tools=()),
        snapshot_metadata=snapshot.metadata,
    )

    assert envelope.provider_context_messages == ()
    assert tuple(item.payload["content"] for item in envelope.transcript.items) == (
        [{"type": "text", "text": "Inspect."}],
    )
    assert "provider_context_message_count" not in envelope.request_metadata()
    assert "provider_context_message_kinds" not in envelope.request_metadata()
    assert "provider_context_messages" not in envelope.request_metadata()


def test_request_envelope_rejects_draft_transcript_fallback_when_snapshot_is_absent() -> None:
    builder = RuntimeLlmRequestBuilder()
    draft = _draft(
        messages=(
            LlmMessage(role=LlmMessageRole.USER, content="Inspect."),
            LlmMessage(
                role=LlmMessageRole.ASSISTANT,
                content={
                    "type": "function_call",
                    "call_id": "call_1",
                    "name": "command.exec",
                    "arguments": {"cmd": "pwd"},
                },
                tool_call_id="call_1",
            ),
            LlmMessage(
                role=LlmMessageRole.TOOL,
                content={"stdout": "/tmp"},
                tool_call_id="call_1",
            ),
        ),
    )

    with pytest.raises(OrchestrationValidationError) as exc:
        builder.request_envelope(
            draft=draft,
            request_render_snapshot=None,
            resolved_tools=ResolvedToolSet(tools=()),
            snapshot_metadata={},
        )

    assert exc.value.code == "request_render_snapshot_required"


def test_request_envelope_requires_request_render_snapshot_for_normal_transcript() -> None:
    builder = RuntimeLlmRequestBuilder()
    draft = _draft(messages=(LlmMessage(role=LlmMessageRole.USER, content="Inspect."),))

    with pytest.raises(OrchestrationValidationError) as exc:
        builder.request_envelope(
            draft=draft,
            request_render_snapshot=None,
            resolved_tools=ResolvedToolSet(tools=()),
            snapshot_metadata={},
        )

    assert exc.value.code == "request_render_snapshot_required"
    assert exc.value.details["mode"] == "normal_turn"


def test_request_envelope_ignores_context_slice_tool_result_for_provider_input() -> None:
    builder = RuntimeLlmRequestBuilder()
    draft = _draft(
        input_items=(
            LlmInputItem(
                kind=LlmInputItemKind.MESSAGE,
                payload={"role": "user", "content": "Inspect."},
                source="session_item",
            ),
        ),
    )
    snapshot = RequestRenderSnapshotRecord(
        snapshot_id="ctxsnap-tool-result",
        projected_input_items=_projected_user_message("Inspect."),
    )

    envelope = builder.request_envelope(
        draft=draft,
        request_render_snapshot=snapshot,
        resolved_tools=ResolvedToolSet(tools=()),
        snapshot_metadata=snapshot.metadata,
    )

    assert tuple(item.source for item in envelope.transcript.items) == (
        "runtime_transcript",
    )
    assert "fare list captured" not in str(envelope.transcript.to_payload())


def test_request_envelope_uses_snapshot_projected_items_when_draft_contains_reasoning() -> None:
    builder = RuntimeLlmRequestBuilder()
    draft = _draft(
        messages=(
            LlmMessage(role=LlmMessageRole.SYSTEM, content="system"),
            LlmMessage(
                role=LlmMessageRole.ASSISTANT,
                content=[{"type": "text", "text": "Need to inspect network."}],
                metadata={
                    "session_item_id": "item-reasoning",
                    "kind": "reasoning",
                },
            ),
            LlmMessage(role=LlmMessageRole.USER, content="hello"),
        ),
        input_items=(
            LlmInputItem(
                kind=LlmInputItemKind.REASONING,
                payload={
                    "type": "reasoning",
                    "content": [
                        {"type": "text", "text": "Need to inspect network."},
                    ],
                },
                source="session_item",
                metadata={
                    "session_item_id": "item-reasoning",
                    "kind": "reasoning",
                },
            ),
        ),
    )
    snapshot = RequestRenderSnapshotRecord(
        snapshot_id="ctxsnap_projection",
        included_node_ids=("session.current",),
        projected_input_items=_projected_user_message("hello"),
    )

    envelope = builder.request_envelope(
        draft=draft,
        request_render_snapshot=snapshot,
        resolved_tools=ResolvedToolSet(tools=()),
        snapshot_metadata=snapshot.metadata,
    )

    assert envelope.metadata["input_mode"] == "runtime_transcript"
    assert tuple(item.source for item in envelope.transcript.items) == (
        "runtime_transcript",
    )


def test_request_envelope_carries_transcript_policy() -> None:
    builder = RuntimeLlmRequestBuilder()
    draft = _draft(
        transcript_policy={
            "session_replay_window": {
                "session_key": "session:test",
                "active_session_only": True,
                "from_sequence_no": 1,
                "to_sequence_no": 3,
            },
        },
    )

    snapshot = RequestRenderSnapshotRecord(
        snapshot_id="ctxsnap-transcript-policy",
        projected_input_items=_projected_user_message("hello"),
    )

    envelope = builder.request_envelope(
        draft=draft,
        request_render_snapshot=snapshot,
        resolved_tools=ResolvedToolSet(tools=()),
        snapshot_metadata=snapshot.metadata,
    )

    assert envelope.transcript.policy == {
        "session_replay_window": {
            "session_key": "session:test",
            "active_session_only": True,
            "from_sequence_no": 1,
            "to_sequence_no": 3,
        },
    }
    assert envelope.to_payload()["transcript"]["policy"] == envelope.transcript.policy


def test_request_metadata_does_not_expose_direct_tool_protocol_health_summary() -> None:
    builder = RuntimeLlmRequestBuilder()
    draft = _draft(
        report=RuntimeRequestReport(
            mode=RuntimeRequestMode.NORMAL_TURN,
            context_budget_source="test",
            context_budget_chars=0,
            context_budget_estimated_tokens=0,
            llm_context_window_tokens=None,
            context_chars=0,
            context_estimated_tokens=0,
            transcript_message_count=2,
            transcript_chars=10,
            transcript_estimated_tokens=3,
            transcript_tool_result_stats={},
            transcript_budget={
                "tool_protocol_diagnostics": {
                    "orphan_tool_output_count": 0,
                    "missing_tool_output_count": 0,
                    "duplicate_tool_call_id_count": 0,
                    "duplicate_tool_output_id_count": 0,
                },
                "source_tool_protocol_diagnostics": {
                    "orphan_tool_output_count": 1,
                    "missing_tool_output_count": 1,
                    "duplicate_tool_call_id_count": 0,
                    "duplicate_tool_output_id_count": 0,
                },
                "tool_protocol_normalization": {
                    "source_had_protocol_breaks": True,
                    "replay_has_protocol_breaks": False,
                    "dropped_orphan_tool_output_count": 1,
                    "dropped_missing_tool_output_count": 1,
                },
            },
        ),
    )

    snapshot = RequestRenderSnapshotRecord(
        snapshot_id="ctxsnap-protocol-health",
        projected_input_items=_projected_user_message("hello"),
    )

    envelope = builder.request_envelope(
        draft=draft,
        request_render_snapshot=snapshot,
        resolved_tools=ResolvedToolSet(tools=()),
        snapshot_metadata=snapshot.metadata,
    )

    assert "direct_tool_protocol_health" not in envelope.metadata
    assert "draft_input_budget" not in envelope.metadata


def test_request_envelope_keeps_context_projection_out_of_provider_messages() -> None:
    builder = RuntimeLlmRequestBuilder()
    draft = _draft(
        messages=(
            LlmMessage(role=LlmMessageRole.SYSTEM, content="system"),
            LlmMessage(role=LlmMessageRole.USER, content="hello"),
        ),
        tool_schemas=(ToolSchema(name="old.tool"),),
    )
    snapshot = RequestRenderSnapshotRecord(
        snapshot_id="ctxsnap_delta",
        metadata={
            "context_delta": {
                "baseline_snapshot_id": "ctxsnap_parent",
                "baseline_revision": 10,
                "current_revision": 12,
                "added_node_ids": ["tools.tool.echo"],
                "removed_node_ids": [],
                "added_tool_schema_names": ["echo"],
                "removed_tool_schema_names": [],
                "debug_body": (
                    "<context_tree_delta><added_tool_schemas>"
                    "<item>echo</item></added_tool_schemas></context_tree_delta>"
                ),
            },
        },
        tool_schemas=(ToolSchema(name="echo"),),
        tool_schema_refs=(_tool_schema_ref("echo"),),
        projected_input_items=_projected_user_message("hello"),
    )

    envelope = builder.request_envelope(
        draft=draft,
        request_render_snapshot=snapshot,
        resolved_tools=ResolvedToolSet(
            tools=(_resolved_tool("tool.echo", schema_name="echo"),),
        ),
        snapshot_metadata=snapshot.metadata,
    )

    assert tuple(message.role for message in envelope.messages) == (LlmMessageRole.USER,)
    assert tuple(message.content for message in envelope.messages) == (
        [{"type": "text", "text": "hello"}],
    )
    assert "full tree must not replay" not in str(envelope.to_payload()["messages"])
    assert "context_delta" not in envelope.metadata
    assert "<context_tree" not in str(envelope.to_payload()["messages"])


def test_resolved_tools_for_draft_filters_to_mirrored_interactive_schemas() -> None:
    builder = RuntimeLlmRequestBuilder()
    weather = _resolved_tool("tool.weather", schema_name="weather.lookup")
    search = _resolved_tool("tool.search", schema_name="search.web")
    draft = _draft(tool_schemas=(ToolSchema(name="weather.lookup"),))
    snapshot = RequestRenderSnapshotRecord(
        snapshot_id="ctxsnap_1",
        tool_schemas=(ToolSchema(name="weather.lookup"),),
        tool_schema_refs=(_tool_schema_ref("weather.lookup"),),
    )

    result = builder.resolved_tools_for_draft(
        ResolvedToolSet(tools=(weather, search)),
        draft,
        snapshot,
    )

    assert tuple(item.schema.name for item in result.tools) == ("weather.lookup",)


def test_resolved_tools_for_draft_clears_interactive_tools_without_snapshot_schema() -> None:
    builder = RuntimeLlmRequestBuilder()
    draft = _draft(tool_schemas=(ToolSchema(name="weather.lookup"),))
    snapshot = RequestRenderSnapshotRecord(snapshot_id="ctxsnap_1", tool_schemas=None)
    draft_with_snapshot = builder.draft_with_request_render_snapshot(draft, snapshot)

    result = builder.resolved_tools_for_draft(
        ResolvedToolSet(tools=(_resolved_tool("tool.weather", schema_name="weather.lookup"),)),
        draft_with_snapshot,
        snapshot,
    )

    assert result.tools == ()


def test_request_snapshot_ignores_unreferenced_tool_schemas() -> None:
    builder = RuntimeLlmRequestBuilder()
    draft = _draft(tool_schemas=(ToolSchema(name="weather.lookup"),))
    snapshot = RequestRenderSnapshotRecord(
        snapshot_id="ctxsnap_unreferenced_schema",
        tool_schemas=(ToolSchema(name="weather.lookup"),),
        projected_input_items=_projected_user_message("hello"),
    )

    envelope = builder.request_envelope(
        draft=draft,
        request_render_snapshot=snapshot,
        resolved_tools=ResolvedToolSet(
            tools=(_resolved_tool("tool.weather", schema_name="weather.lookup"),),
        ),
        snapshot_metadata={},
    )

    assert envelope.tool_schemas == ()
    assert envelope.tool_surface.functions == ()


def test_request_envelope_carries_context_and_tool_surface() -> None:
    builder = RuntimeLlmRequestBuilder()
    draft = _draft(
        messages=(
            LlmMessage(role=LlmMessageRole.SYSTEM, content="system"),
            LlmMessage(
                role=LlmMessageRole.USER,
                content="hello",
                metadata={
                    "session_item_id": "item-user-1",
                    "session_id": "session-instance-1",
                    "sequence_no": 3,
                    "kind": "user_message",
                },
            ),
        ),
        tool_schemas=(ToolSchema(name="browser.network.inspect"),),
    )
    snapshot = RequestRenderSnapshotRecord(
        snapshot_id="ctxsnap-envelope-1",
        estimate={"estimated_tokens": 42},
        included_node_ids=("runtime.contract",),
        mirrored_node_ids=("tools.browser.network",),
        included_refs=({"node_id": "runtime.contract", "kind": "runtime"},),
        collapsed_refs=({"node_id": "history.old", "kind": "history"},),
        protocol_required_refs=(
            {"item_id": "item-tool-result-1", "call_id": "call-1"},
        ),
        metadata={
            "tree_schema_version": "2026-06-11",
            "tool_schema_mirror_budget_status": "ok",
        },
        tool_schemas=(ToolSchema(name="browser.network.inspect"),),
        tool_schema_refs=(
            {
                "name": "browser.network.inspect",
                "source": "context_slice",
                "node_id": "tools.browser.network",
                "tool_ref_id": "tools.browser.network",
                "source_id": "configured.browser",
                "schema": ToolSchema(name="browser.network.inspect").to_payload(),
            },
        ),
        projected_input_items=_projected_user_message("hello"),
    )
    resolved_tools = ResolvedToolSet(
        tools=(
            _resolved_tool(
                "tool.browser.network.inspect",
                schema_name="browser.network.inspect",
            ),
        ),
    )

    envelope = builder.request_envelope(
        draft=draft,
        request_render_snapshot=snapshot,
        resolved_tools=resolved_tools,
        snapshot_metadata=snapshot.metadata,
        provider_options={"service_tier": "default"},
        reasoning_config={"summary": "auto"},
        output_contract={"final_answer": "required"},
    )

    assert envelope.request_render_snapshot.snapshot_id == "ctxsnap-envelope-1"
    assert envelope.request_render_snapshot.included_refs[0]["node_id"] == "runtime.contract"
    assert envelope.request_render_snapshot.protocol_required_refs[0]["call_id"] == "call-1"
    assert envelope.request_render_snapshot.diagnostics["tool_schema_mirror_budget_status"] == "ok"
    assert envelope.tool_surface.id == "tool_surface:ctxsnap-envelope-1"
    assert envelope.tool_surface.functions[0].source_id == "configured.browser"
    assert envelope.tool_surface.functions[0].group_key is None
    assert envelope.tool_surface.functions[0].metadata == {
        "source": "context_slice",
        "node_id": "tools.browser.network",
        "tool_ref_id": "tools.browser.network",
        "function_name": "browser.network.inspect",
    }
    assert envelope.tool_surface.metadata["function_count"] == 1
    assert envelope.metadata["tool_surface_function_refs"][0]["node_id"] == (
        "tools.browser.network"
    )
    assert envelope.metadata["tool_surface_function_refs"][0]["tool_ref_id"] == (
        "tools.browser.network"
    )
    assert envelope.metadata["tool_surface_function_refs"][0]["source"] == (
        "context_slice"
    )
    assert envelope.metadata["tool_surface_source_refs"] == [
        {"source_id": "configured.browser"},
    ]
    assert envelope.metadata["request_render_snapshot_id"] == "ctxsnap-envelope-1"
    assert "context_snapshot_id" not in envelope.metadata
    assert envelope.metadata["tool_surface_id"] == "tool_surface:ctxsnap-envelope-1"
    assert "draft_input_session_item_refs" not in envelope.metadata
    payload = envelope.to_payload()
    assert payload["request_render_snapshot"]["kind"] == "request_render"
    assert "provider_attachment_mirror" not in payload["request_render_snapshot"]
    assert "context_slice" not in payload["request_render_snapshot"]
    assert payload["tool_surface"]["functions"][0]["schema"]["name"] == (
        "browser.network.inspect"
    )
    assert payload["tool_surface"]["functions"][0]["source_id"] == "configured.browser"
    assert payload["tool_surface"]["functions"][0]["metadata"]["node_id"] == (
        "tools.browser.network"
    )
    assert payload["provider_options"]["service_tier"] == "default"
    assert payload["reasoning_config"]["summary"] == "auto"
    assert payload["output_contract"]["final_answer"] == "required"


def test_request_envelope_persists_visible_tool_surface_snapshot() -> None:
    calls: list[dict[str, object]] = []

    def build_tool_surface(**kwargs: object) -> dict[str, object]:
        calls.append(dict(kwargs))
        return {"surface_id": str(kwargs["surface_id"])}

    builder = RuntimeLlmRequestBuilder(
        tool_surface_snapshot_builder=build_tool_surface,
    )
    draft = _draft(
        tool_schemas=(
            ToolSchema(name="browser.network.inspect"),
            ToolSchema(name="browser.form.fill"),
        ),
    )
    snapshot = RequestRenderSnapshotRecord(
        snapshot_id="ctxsnap-visible-tools",
        tool_schemas=(ToolSchema(name="browser.network.inspect"),),
        tool_schema_refs=(_tool_schema_ref("browser.network.inspect"),),
        projected_input_items=_projected_user_message("hello"),
    )
    network = _resolved_tool(
        "tool.browser.network.inspect",
        schema_name="browser.network.inspect",
    )
    form = _resolved_tool("tool.browser.form.fill", schema_name="browser.form.fill")

    envelope = builder.request_envelope(
        draft=draft,
        request_render_snapshot=snapshot,
        resolved_tools=ResolvedToolSet(tools=(network, form)),
        snapshot_metadata={},
        run_id="run-visible-tools",
        agent_id="assistant",
    )

    assert len(calls) == 1
    assert str(calls[0]["surface_id"]).startswith(
        "tool_surface:ctxsnap-visible-tools:",
    )
    assert calls[0]["session_id"] == "session-instance-1"
    assert calls[0]["run_id"] == "run-visible-tools"
    assert calls[0]["agent_id"] == "assistant"
    assert calls[0]["tool_ids"] == ("tool.browser.network.inspect",)
    assert calls[0]["persist"] is True
    assert calls[0]["runtime_context"] == {
        "agent_id": "assistant",
        "run_id": "run-visible-tools",
        "session_key": "session:test",
        "active_session_id": "session-instance-1",
        "request_render_snapshot_id": "ctxsnap-visible-tools",
        "provider_visible_tool_count": 1,
    }
    assert envelope.metadata["tool_surface_snapshot_persisted"] is True
    assert str(envelope.metadata["tool_surface_snapshot_id"]).startswith(
        "tool_surface:ctxsnap-visible-tools:",
    )
    assert str(envelope.metadata["tool_surface_id"]).startswith(
        "tool_surface:ctxsnap-visible-tools:",
    )
    assert envelope.tool_surface.metadata["base_tool_surface_id"] == (
        "tool_surface:ctxsnap-visible-tools"
    )
    assert [function.tool_id for function in envelope.tool_surface.functions] == [
        "tool.browser.network.inspect",
    ]
    assert envelope.tool_surface.functions[0].source_id is None
    assert envelope.tool_surface.functions[0].group_key is None


def test_request_envelope_does_not_derive_tool_source_refs_from_context_slice() -> None:
    builder = RuntimeLlmRequestBuilder()
    snapshot = RequestRenderSnapshotRecord(
        snapshot_id="ctxsnap-context-slice-source-is-observation-only",
        tool_schemas=(ToolSchema(name="browser.network.inspect"),),
        tool_schema_refs=(
            _tool_schema_ref("browser.network.inspect"),
        ),
        projected_input_items=_projected_user_message("hello"),
    )

    envelope = builder.request_envelope(
        draft=_draft(tool_schemas=(ToolSchema(name="browser.network.inspect"),)),
        request_render_snapshot=snapshot,
        resolved_tools=ResolvedToolSet(
            tools=(
                _resolved_tool(
                    "tool.browser.network.inspect",
                    schema_name="browser.network.inspect",
                ),
            ),
        ),
        snapshot_metadata={},
    )

    function = envelope.tool_surface.functions[0]
    assert function.source_id is None
    assert function.group_key is None
    assert "source_refs" not in envelope.tool_surface.metadata


def test_request_envelope_can_skip_tool_surface_snapshot_persistence() -> None:
    calls: list[dict[str, object]] = []
    builder = RuntimeLlmRequestBuilder(
        tool_surface_snapshot_builder=lambda **kwargs: calls.append(dict(kwargs)),
    )

    envelope = builder.request_envelope(
        draft=_draft(tool_schemas=(ToolSchema(name="browser.network.inspect"),)),
        request_render_snapshot=RequestRenderSnapshotRecord(
            snapshot_id="ctxsnap-preview",
            tool_schemas=(ToolSchema(name="browser.network.inspect"),),
            tool_schema_refs=(_tool_schema_ref("browser.network.inspect"),),
            projected_input_items=_projected_user_message("hello"),
        ),
        resolved_tools=ResolvedToolSet(
            tools=(
                _resolved_tool(
                    "tool.browser.network.inspect",
                    schema_name="browser.network.inspect",
                ),
            ),
        ),
        snapshot_metadata={},
        persist_tool_surface_snapshot=False,
    )

    assert calls == []
    assert "tool_surface_snapshot_persisted" not in envelope.metadata
    assert envelope.metadata["tool_surface_id"] == "tool_surface:ctxsnap-preview"


def test_run_metadata_llm_request_options_split_provider_reasoning_and_output() -> None:
    run = OrchestrationRun(
        id="run-request-options",
        inbound_instruction=InboundInstruction(source="web", content="hello"),
        metadata={
            "llm_request_options": {
                "provider_options": {
                    "service_tier": "default",
                    "max_output_tokens": 1200,
                },
                "reasoning_config": {"effort": "medium", "summary": "auto"},
                "output_contract": {"final_answer": "required"},
                "response_format": {"type": "json_object"},
                "output_schema": {"name": "flight_answer"},
            },
        },
    )

    options = llm_request_options_from_run_metadata(run)

    assert options["provider_options"]["service_tier"] == "default"
    assert options["provider_options"]["max_output_tokens"] == 1200
    assert options["reasoning_config"] == {"effort": "medium", "summary": "auto"}
    assert options["output_contract"]["final_answer"] == "required"
    assert options["output_contract"]["response_format"] == {"type": "json_object"}
    assert options["output_contract"]["output_schema"] == {"name": "flight_answer"}


def test_effective_llm_request_policy_merges_model_defaults_and_run_override() -> None:
    run = OrchestrationRun(
        id="run-effective-policy",
        inbound_instruction=InboundInstruction(source="web", content="hello"),
        metadata={
            "llm_request_options": {
                "provider_options": {"service_tier": "default"},
                "reasoning_config": {"summary": "auto"},
            },
        },
    )
    draft = _draft(
        llm_capabilities=(LlmCapability.REASONING,),
        llm_defaults={
            "max_output_tokens": 800,
            "reasoning_effort": "medium",
        },
    )

    options = llm_request_options_from_run(run, draft=draft)

    assert options["provider_options"] == {
        "max_output_tokens": 800,
        "service_tier": "default",
    }
    assert options["reasoning_config"] == {
        "effort": "medium",
        "summary": "auto",
    }
    policy_payload = options["policy"].to_payload()
    assert policy_payload["resolution_trace"][0]["source"] == (
        "model_profile.default_params"
    )
    assert {
        item["field"]
        for item in policy_payload["resolution_trace"]
    } >= {
        "provider_options.max_output_tokens",
        "provider_options.service_tier",
        "reasoning_config.effort",
        "reasoning_config.summary",
    }


def test_effective_llm_request_policy_applies_runtime_defaults_before_model_and_run() -> None:
    run = OrchestrationRun(
        id="run-effective-runtime-defaults",
        inbound_instruction=InboundInstruction(source="web", content="hello"),
        metadata={
            "llm_request_options": {
                "provider_options": {"service_tier": "run-tier"},
            },
        },
    )
    draft = _draft(
        llm_capabilities=(LlmCapability.REASONING,),
        runtime_llm_defaults={
            "max_output_tokens": 400,
            "reasoning_effort": "low",
            "service_tier": "runtime-tier",
            "parallel_tool_calls": True,
            "trace_raw_provider_payload": True,
        },
        llm_defaults={
            "max_output_tokens": 800,
            "reasoning_effort": "medium",
        },
    )

    options = llm_request_options_from_run(run, draft=draft)

    assert options["provider_options"] == {
        "max_output_tokens": 800,
        "service_tier": "run-tier",
        "parallel_tool_calls": True,
        "trace_raw_provider_payload": True,
    }
    assert options["reasoning_config"] == {"effort": "medium"}
    trace = options["policy"].to_payload()["resolution_trace"]
    assert any(
        item["source"] == "settings.llm_request_defaults"
        and item["field"] == "provider_options.max_output_tokens"
        for item in trace
    )
    assert trace[-1] == {
        "field": "provider_options.service_tier",
        "source": "run.metadata.llm_request_options.provider_options",
        "status": "applied",
        "value": "configured",
    }


def test_effective_llm_request_policy_applies_codex_style_provider_options() -> None:
    run = OrchestrationRun(
        id="run-effective-codex-options",
        inbound_instruction=InboundInstruction(source="web", content="hello"),
        agent_id="assistant",
        metadata={"session_key": "session:codex-like"},
    )
    draft = _draft(
        llm_capabilities=(LlmCapability.REASONING,),
        llm_api_family="openai_codex_responses",
        runtime_llm_defaults={
            "service_tier": "priority",
        },
        llm_defaults={
            "parallel_tool_calls": True,
            "prompt_cache_enabled": True,
            "response_verbosity": "low",
            "include_reasoning_encrypted_content": True,
            "include": ["other.provider.item"],
        },
    )

    options = llm_request_options_from_run(run, draft=draft)

    assert options["provider_options"] == {
        "service_tier": "priority",
        "parallel_tool_calls": True,
        "prompt_cache_enabled": True,
        "text": {"verbosity": "low"},
        "include": ["other.provider.item", "reasoning.encrypted_content"],
        "prompt_cache_key": "crxzipple:assistant:session:codex-like",
    }
    trace = options["policy"].to_payload()["resolution_trace"]
    assert {
        item["field"]
        for item in trace
    } >= {
        "provider_options.parallel_tool_calls",
        "provider_options.prompt_cache_enabled",
        "provider_options.text.verbosity",
        "provider_options.include.reasoning.encrypted_content",
        "provider_options.include",
        "provider_options.prompt_cache_key",
    }


def test_effective_llm_request_policy_filters_responses_only_options_for_non_responses_provider() -> None:
    run = OrchestrationRun(
        id="run-effective-non-responses-options",
        inbound_instruction=InboundInstruction(source="web", content="hello"),
        agent_id="assistant",
        metadata={"session_key": "session:anthropic"},
    )
    draft = _draft(
        llm_capabilities=(LlmCapability.REASONING,),
        llm_api_family="anthropic_messages",
        runtime_llm_defaults={
            "service_tier": "default",
            "parallel_tool_calls": True,
            "prompt_cache_enabled": True,
            "response_verbosity": "low",
            "include_reasoning_encrypted_content": True,
        },
        llm_defaults={"max_output_tokens": 1000},
    )

    options = llm_request_options_from_run(run, draft=draft)

    assert options["provider_options"] == {
        "service_tier": "default",
        "max_output_tokens": 1000,
    }
    trace = options["policy"].to_payload()["resolution_trace"]
    downgraded = [
        item
        for item in trace
        if item["source"] == "provider_capability_filter"
    ]
    assert {
        item["field"]
        for item in downgraded
    } == {
        "provider_options.parallel_tool_calls",
        "provider_options.prompt_cache_enabled",
        "provider_options.prompt_cache_key",
        "provider_options.text",
        "provider_options.include",
    }
    assert all(item["status"] == "downgraded" for item in downgraded)


def test_effective_llm_request_policy_applies_agent_llm_policy() -> None:
    run = OrchestrationRun(
        id="run-effective-agent-policy",
        inbound_instruction=InboundInstruction(source="web", content="hello"),
    )
    draft = _draft(
        llm_capabilities=(LlmCapability.REASONING,),
        llm_policy={
            "reasoning_summary_policy": "visible_and_replay_when_provider_supports",
            "final_answer_policy": "phase_or_codex_unknown_fallback",
            "tool_use_policy": "auto",
            "parallel_tool_calls_policy": "disabled",
        },
    )

    options = llm_request_options_from_run(run, draft=draft)

    assert options["reasoning_config"] == {"summary": "auto"}
    assert options["provider_options"] == {"parallel_tool_calls": False}
    assert options["output_contract"] == {
        "final_answer_policy": "phase_or_codex_unknown_fallback",
        "tool_use_policy": "auto",
    }
    trace = options["policy"].to_payload()["resolution_trace"]
    assert {
        item["field"]
        for item in trace
        if item["source"] == "agent_profile.llm_policy"
    } == {
        "reasoning_config.summary",
        "output_contract.final_answer_policy",
        "output_contract.tool_use_policy",
        "provider_options.parallel_tool_calls",
    }


def test_provider_native_continuation_can_be_restored_from_run_state() -> None:
    run = OrchestrationRun(
        id="run-provider-continuation-capability-gate",
        inbound_instruction=InboundInstruction(source="web", content="hello"),
        metadata={
            "provider_continuation_state": {
                "mode": "provider_native",
                "previous_response_id": "resp_previous",
                "previous_invocation_id": "llminv_previous",
                "provider_family": "openai_responses",
            },
        },
    )
    continuation = provider_continuation_from_state(
        run.metadata.get("provider_continuation_state"),
    )

    assert continuation is not None
    assert continuation.previous_response_id == "resp_previous"


def test_effective_llm_request_policy_downgrades_unsupported_reasoning() -> None:
    run = OrchestrationRun(
        id="run-effective-policy-downgrade",
        inbound_instruction=InboundInstruction(source="web", content="hello"),
        metadata={
            "llm_request_options": {
                "reasoning_config": {"summary": "auto"},
            },
        },
    )
    draft = _draft(
        llm_capabilities=(),
        llm_defaults={"reasoning_effort": "high"},
    )

    options = llm_request_options_from_run(run, draft=draft)

    assert options["reasoning_config"] == {}
    trace = options["policy"].to_payload()["resolution_trace"]
    downgraded = [item for item in trace if item["status"] == "downgraded"]
    assert [item["field"] for item in downgraded] == [
        "reasoning_config.effort",
        "reasoning_config.summary",
    ]
    assert all(
        item["reason"] == "llm_capability_not_supported"
        for item in downgraded
    )


def test_request_metadata_carries_budget_fields_from_snapshot_metadata() -> None:
    builder = RuntimeLlmRequestBuilder()
    tool_schemas = (
        ToolSchema(name="capability.search"),
        ToolSchema(name="open_meteo_weather.forecast_weather"),
    )
    draft = _draft()

    metadata = builder.request_metadata(
        draft=draft,
        request_render_snapshot_id="ctxsnap_1",
        tool_schemas=tool_schemas,
        snapshot_metadata={
            "tree_schema_version": "2026-06-05",
            "draft_input_estimated_tokens": 2,
            "mirrored_tool_schema_estimated_tokens": 3,
            "artifact_content_estimated_tokens": 4,
            "estimated_provider_input_tokens": 19,
            "tool_schema_mirror_budget_status": "ok",
            "tool_schema_mirror_default_schema_source": "source_runtime_request.default",
            "tool_schema_mirror_default_group_refs": [
                {
                    "source_id": "bundled.local_package.browser",
                    "group_key": "network",
                    "reason": "browser_starter_network",
                },
            ],
            "tool_schema_mirror_default_group_ref_count": 1,
            "tool_schema_mirror_default_schema_reasons": {
                "browser.network.inspect": "browser_starter_network",
            },
            "tool_schema_mirror_default_mirrored": [
                {
                    "node_id": "tools.tool.browser.network.inspect",
                    "name": "browser.network.inspect",
                    "priority": 200,
                    "bootstrap_reason": "browser_starter_network",
                },
            ],
            "tool_schema_mirror_skipped": [
                {
                    "node_id": "tools.tool.browser.form.fill",
                    "name": "browser.form.fill",
                    "reason": "count_limit",
                    "selection": "default",
                    "priority": 900,
                    "bootstrap_reason": "forms_on_demand",
                },
            ],
            "tool_schema_mirror_skipped_by_reason": {"count_limit": 1},
            "work_plan_status": "in_progress",
            "work_plan_phase": "in_progress:Inspect runtime",
            "work_plan_update_reason": "observed_fact",
            "work_plan_phase_changed": False,
            "work_plan_update_count": 3,
            "artifact_content_budget": {"status": "ok"},
            "top_rendered_nodes": [{"node_id": "runtime.contract"}],
            "mirrored_node_count": 1,
            "request_context_source": "context_slice",
            "context_slice_id": "ctxslice_test",
            "context_slice_item_count": 1,
            "context_slice_included_node_count": 1,
            "context_slice_active_tool_count": 1,
            "context_slice_projected_input_item_count": 1,
            "context_slice": {
                "slice_id": "ctxslice_test",
                "audience": "llm_request",
                "run_id": "run-slice",
                "session_key": "session:slice",
                "items": [
                    {
                        "item_id": "slice.item.user",
                        "node_id": "session.item.user",
                        "kind": "message",
                        "role": "user",
                        "section": "task",
                        "text": "hidden user text",
                        "owner_ref": {
                            "owner_module": "session",
                            "session_item_id": "session-item-1",
                            "raw_text": "hidden owner text",
                        },
                    },
                ],
                "active_tools": [
                    {
                        "tool_ref_id": "tools.tool.command.exec",
                        "source_id": "configured.command",
                        "group_key": "shell",
                        "function_name": "command.exec",
                        "schema": {"description": "hidden schema body"},
                    },
                ],
                "report": {
                    "included_count": 1,
                    "omitted_count": 2,
                    "loss": {"omitted_node_count": 2, "hidden": ""},
                },
            },
        },
    )

    assert metadata["runtime_request_surface"] == "interactive"
    assert metadata["request_render_snapshot_id"] == "ctxsnap_1"
    assert "context_snapshot_id" not in metadata
    assert metadata["provider_tool_schema_count"] == 2
    assert metadata["provider_tool_schema_names"] == [
        "capability.search",
        "open_meteo_weather.forecast_weather",
    ]
    assert "debug_body_estimated_tokens" not in metadata
    assert metadata["draft_input_estimated_tokens"] == 2
    assert metadata["mirrored_tool_schema_estimated_tokens"] == 3
    assert metadata["artifact_content_estimated_tokens"] == 4
    assert metadata["estimated_provider_input_tokens"] == 19
    assert metadata["tool_schema_mirror_budget_status"] == "ok"
    assert metadata["tool_schema_mirror_default_schema_source"] == (
        "source_runtime_request.default"
    )
    assert metadata["tool_schema_mirror_default_group_ref_count"] == 1
    assert "tool_schema_mirror_default_group_refs" not in metadata
    assert "tool_schema_mirror_default_schema_reasons" not in metadata
    assert metadata["request_context_source"] == "context_slice"
    assert metadata["context_slice_id"] == "ctxslice_test"
    assert metadata["context_slice_item_count"] == 1
    assert metadata["context_slice_included_node_count"] == 1
    assert metadata["context_slice_active_tool_count"] == 1
    assert metadata["context_slice_projected_input_item_count"] == 1
    assert "context_slice" not in metadata
    assert "tool_schema_mirror_default_mirrored" not in metadata
    assert "tool_schema_mirror_skipped" not in metadata
    assert metadata["tool_schema_mirror_skipped_by_reason"] == {"count_limit": 1}
    for key in (
        "work_plan_status",
        "work_plan_phase",
        "work_plan_update_reason",
        "work_plan_phase_changed",
        "work_plan_update_count",
    ):
        assert key not in metadata
    assert metadata["artifact_content_budget"] == {"status": "ok"}
    assert "top_rendered_nodes" not in metadata
    assert metadata["mirrored_node_count"] == 1
    assert metadata["request_render_snapshot_id"] == "ctxsnap_1"
    assert "context_slice_summary" not in metadata
    assert "llm_request_slice_id" not in metadata
    assert "hidden user text" not in str(metadata)
    assert "hidden schema body" not in str(metadata)


def test_request_envelope_keeps_runtime_context_for_renderer() -> None:
    builder = RuntimeLlmRequestBuilder()
    draft = _draft(
        runtime_context={
            "agent_id": "assistant",
            "llm_id": "llm.test",
            "workspace_dir": "/workspace",
            "current_step": 29,
            "max_steps": 30,
            "remaining_steps": 1,
            "step_budget_status": "finalize_now",
            "debug_body": "must not leak",
        },
    )
    snapshot = RequestRenderSnapshotRecord(
        snapshot_id="ctxsnap-runtime-context",
        projected_input_items=_projected_user_message("hello"),
    )

    envelope = builder.request_envelope(
        draft=draft,
        request_render_snapshot=snapshot,
        resolved_tools=ResolvedToolSet(tools=()),
        snapshot_metadata={},
        run_id="run-runtime-context",
        agent_id="assistant",
    )

    assert envelope.provider_context_messages == ()
    assert envelope.metadata["run_id"] == "run-runtime-context"
    assert envelope.metadata["agent_id"] == "assistant"
    assert envelope.metadata["session_key"] == "session:test"
    assert envelope.metadata["active_session_id"] == "session-instance-1"
    assert envelope.metadata["runtime_context"]["run_id"] == "run-runtime-context"
    assert envelope.metadata["runtime_context"]["agent_id"] == "assistant"
    assert envelope.metadata["runtime_context"]["session_key"] == "session:test"
    assert envelope.metadata["runtime_context"]["active_session_id"] == (
        "session-instance-1"
    )
    assert envelope.metadata["runtime_context"]["step_budget_status"] == "finalize_now"
    assert "must not leak" not in str(envelope.metadata["runtime_context"])
    assert envelope.renderer_context().to_payload()["run_id"] == "run-runtime-context"
    assert envelope.renderer_context().to_payload()["step_budget_status"] == (
        "finalize_now"
    )


def _draft(
    *,
    messages: tuple[LlmMessage, ...] | None = None,
    input_items: tuple[LlmInputItem, ...] = (),
    tool_schemas: tuple[ToolSchema, ...] = (),
    surface_policy: RunSurfacePolicy | None = None,
    llm_capabilities: tuple[LlmCapability, ...] = (),
    llm_api_family: str | None = None,
    runtime_llm_defaults: dict[str, object] | None = None,
    llm_defaults: dict[str, object] | None = None,
    llm_policy: dict[str, object] | None = None,
    transcript_policy: dict[str, object] | None = None,
    agent_instruction: str | None = None,
    report: RuntimeRequestReport | None = None,
    runtime_context: dict[str, object] | None = None,
) -> RuntimeLlmRequestDraft:
    return RuntimeLlmRequestDraft(
        llm_id="llm.test",
        session_key="session:test",
        active_session_id="session-instance-1",
        messages=messages
        or (
            LlmMessage(
                role=LlmMessageRole.USER,
                content="hello",
                metadata={
                    "session_item_id": "item-1",
                    "session_id": "session-instance-1",
                    "sequence_no": 1,
                },
            ),
        ),
        input_items=input_items,
        transcript_policy=dict(transcript_policy or {}),
        mode=RuntimeRequestMode.NORMAL_TURN,
        report=report,
        agent_instruction=agent_instruction,
        llm_capabilities=llm_capabilities,
        llm_api_family=llm_api_family,
        runtime_llm_defaults=dict(runtime_llm_defaults or {}),
        llm_defaults=dict(llm_defaults or {}),
        llm_policy=dict(llm_policy or {}),
        runtime_context=dict(runtime_context or {}),
        tool_schemas=tool_schemas,
        surface_policy=surface_policy or RunSurfacePolicy(),
    )


def _context_slice_with_active_tool(
    name: str,
    *,
    source_id: str = "bundled.openapi.test",
    group_key: str = "default",
) -> dict[str, object]:
    return {
        "run_id": "run-context",
        "items": _context_slice_with_task("hello")["items"],
        "active_tools": [
            {
                "tool_ref_id": f"tools.tool.{name}",
                "source_id": source_id,
                "function_name": name,
                "schema": {
                    "name": name,
                    "description": f"{name} description.",
                    "input_schema": {"type": "object"},
                },
                "owner_ref": {
                    "source_id": source_id,
                    "group_key": group_key,
                },
            },
        ],
    }


def _provider_attachments_with_tool(name: str) -> dict[str, object]:
    return {
        "tool_schemas": [
            {
                "name": name,
                "description": f"{name} description.",
                "input_schema": {"type": "object"},
            },
        ],
    }


def _tool_schema_ref(name: str, *, source: str = "context_slice") -> dict[str, object]:
    return {
        "name": name,
        "source": source,
        "schema": ToolSchema(name=name, description=f"{name} description.").to_payload(),
    }


def _projected_user_message(
    text: str = "hello",
    *,
    session_item_id: str = "item-projected-user",
) -> tuple[dict[str, object], ...]:
    return (
        {
            "kind": "message",
            "payload": {
                "role": "user",
                "content": [{"type": "text", "text": text}],
            },
            "source": "context_slice",
            "metadata": {
                "owner": "session",
                "kind": "session_item",
                "session_item_id": session_item_id,
                "node_id": "session.item.projected-user",
            },
        },
    )


def _context_slice_with_task(text: str) -> dict[str, object]:
    return {
        "slice_id": "ctxslice_test",
        "audience": "llm_request",
        "run_id": "run-context",
        "items": [
            {
                "item_id": "session.item.task",
                "node_id": "session.item.task",
                "section": "task",
                "owner": "session",
                "kind": "session_item",
                "text": text,
                "owner_ref": {"role": "user"},
            },
        ],
    }


def _resolved_tool(tool_id: str, *, schema_name: str) -> ResolvedTool:
    return ResolvedTool(
        tool=Tool(
            id=tool_id,
            name=schema_name,
            description=f"{schema_name} description.",
        ),
        schema=ToolSchema(name=schema_name, description=f"{schema_name} description."),
        target=ToolExecutionTarget(),
    )
