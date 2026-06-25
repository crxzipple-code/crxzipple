from __future__ import annotations

from types import SimpleNamespace

from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmInputItem,
    LlmInputItemKind,
    LlmMessage,
    LlmMessageRole,
    ToolSchema,
)
from crxzipple.modules.llm.application.provider_continuation import (
    build_provider_continuation_state_from_invocation,
    provider_continuation_from_state,
)
from crxzipple.modules.orchestration.application.ports import (
    RequestRenderSnapshotRecord,
)
from crxzipple.modules.orchestration.application.runtime_llm_request_draft import RuntimeLlmRequestDraft
from crxzipple.modules.llm.application.runtime_request_factory import (
    RuntimeLlmRequestBuilder,
)
from crxzipple.modules.orchestration.application.runtime_request_mode import RuntimeRequestMode
from crxzipple.modules.orchestration.application.runtime_request_report import RunSurfacePolicy
from crxzipple.modules.orchestration.application.tool_resolver import (
    ResolvedTool,
    ResolvedToolSet,
)
from crxzipple.modules.tool.domain import Tool, ToolExecutionTarget


def test_orchestration_builds_runtime_request_refs_not_provider_wire_input() -> None:
    snapshot = RequestRenderSnapshotRecord(
        snapshot_id="ctxsnap-runtime-request",
        included_node_ids=("runtime.contract",),
        tool_schemas=(ToolSchema(name="command.exec"),),
        metadata={
            "tree_schema_version": "2026-06-11.context_tree.v2",
            "session_budget_status": "ok",
        },
        projected_input_items=_projected_user_input_items(),
    )
    envelope = RuntimeLlmRequestBuilder().request_envelope(
        draft=_draft(),
        request_render_snapshot=snapshot,
        resolved_tools=ResolvedToolSet(
            tools=(_resolved_tool("tool.command.exec", schema_name="command.exec"),),
        ),
        snapshot_metadata=snapshot.metadata,
        persist_tool_surface_snapshot=False,
        provider_options={
            "service_tier": "default",
            "text": {"verbosity": "low"},
        },
        reasoning_config={"effort": "medium", "summary": "auto"},
        output_contract={"response_format": {"type": "json_object"}},
    )

    metadata = envelope.request_metadata()
    payload = envelope.to_payload()

    assert envelope.request_render_snapshot.snapshot_id == "ctxsnap-runtime-request"
    assert envelope.request_render_snapshot.diagnostics == {"session_budget_status": "ok"}
    assert metadata["request_render_snapshot"]["snapshot_id"] == "ctxsnap-runtime-request"
    assert metadata["tool_surface"]["id"] == "tool_surface:ctxsnap-runtime-request"
    assert metadata["reasoning_config"] == {"effort": "medium", "summary": "auto"}
    assert metadata["output_contract"] == {
        "response_format": {"type": "json_object"},
    }
    assert "provider_options" not in metadata

    assert payload["provider_options"] == {
        "service_tier": "default",
        "text": {"verbosity": "low"},
    }
    assert payload["output_contract"] == {
        "response_format": {"type": "json_object"},
    }
    assert payload["request_render_snapshot"]["kind"] == "request_render"
    assert "provider_attachment_mirror" not in payload["request_render_snapshot"]
    assert "context_slice" not in payload["request_render_snapshot"]

    wire_only_keys = {
        "input",
        "tools",
        "previous_response_id",
        "tool_choice",
        "stream",
        "model",
        "payload_preview",
        "render_report",
    }
    assert wire_only_keys.isdisjoint(payload["provider_options"])
    assert wire_only_keys.isdisjoint(metadata)
    assert wire_only_keys.isdisjoint(metadata["request_render_snapshot"])
    assert "<context_tree>" not in str(payload["messages"])
    assert "<context_tree>" not in str(payload["transcript"])
    assert "debug_body" not in payload["request_render_snapshot"]
    assert "Inspect." not in str(payload["request_render_snapshot"])
    assert payload["provider_context_messages"] == [
        {
            "role": "system",
            "content": "Runtime contract summary.",
            "metadata": {
                "provider_context_kind": "runtime_instruction",
                "source": "runtime_request_draft_message",
            },
        },
    ]
    assert "Runtime contract summary." not in str(payload["transcript"])
    assert "Runtime contract summary." not in str(payload["messages"])


def test_orchestration_keeps_tool_call_requirement_as_neutral_policy() -> None:
    envelope = RuntimeLlmRequestBuilder().request_envelope(
        draft=RuntimeLlmRequestDraft(
            llm_id="llm.test",
            session_key="session:test",
            active_session_id="session-instance-1",
            messages=(LlmMessage(role=LlmMessageRole.USER, content="Flush memory."),),
            input_items=(),
            mode=RuntimeRequestMode.MEMORY_FLUSH,
            report=None,
            tool_schemas=(ToolSchema(name="memory.flush"),),
            surface_policy=RunSurfacePolicy(
                surface="background",
                require_tool_call=True,
            ),
        ),
        request_render_snapshot=None,
        resolved_tools=ResolvedToolSet(tools=()),
        snapshot_metadata={},
        persist_tool_surface_snapshot=False,
        provider_options={},
    )

    payload = envelope.to_payload()

    assert payload["transcript"]["policy"] == {"require_tool_call": True}
    assert "tool_choice" not in payload.get("provider_options", {})
    assert "toolConfig" not in payload.get("provider_options", {})


def test_provider_continuation_state_omits_codex_websocket_until_turn_scoped_transport() -> None:
    invocation = SimpleNamespace(
        id="inv-codex-1",
        provider_request_id="resp_codex_1",
        provider_request_payload_preview={
            "api_family": LlmApiFamily.OPENAI_CODEX_RESPONSES.value,
            "transport": "websocket",
            "has_previous_response_id": False,
            "input_baseline_fingerprints": ["fp-user", "fp-call"],
            "instructions_fingerprint": "fp-instructions",
            "tool_fingerprints": ["fp-tool"],
        },
        result=SimpleNamespace(metadata={}),
    )

    state = build_provider_continuation_state_from_invocation(invocation)
    continuation = provider_continuation_from_state(state)

    assert state == {}
    assert continuation is None


def test_interactive_tool_schema_surface_uses_request_render_tool_schemas_and_metadata() -> None:
    snapshot = RequestRenderSnapshotRecord(
        snapshot_id="ctxsnap-active-tools",
        included_node_ids=("tools.tool.weather",),
        tool_schemas=(
            ToolSchema(
                name="open_meteo_weather.forecast_weather",
                description="Forecast weather.",
                input_schema={"type": "object"},
            ),
        ),
        tool_schema_refs=(
            _tool_schema_ref(
                ToolSchema(
                    name="open_meteo_weather.forecast_weather",
                    description="Forecast weather.",
                    input_schema={"type": "object"},
                ),
            ),
        ),
        projected_input_items=_projected_user_input_items(),
    )

    envelope = RuntimeLlmRequestBuilder().request_envelope(
        draft=_draft(),
        request_render_snapshot=snapshot,
        resolved_tools=ResolvedToolSet(
            tools=(
                _resolved_tool(
                    "open_meteo_weather.forecast_weather",
                    schema_name="open_meteo_weather.forecast_weather",
                ),
                _resolved_tool("stale.mirror", schema_name="stale.mirror"),
            ),
        ),
        snapshot_metadata=snapshot.metadata,
        persist_tool_surface_snapshot=False,
    )

    assert [schema.name for schema in envelope.tool_schemas] == [
        "open_meteo_weather.forecast_weather",
    ]
    assert [function.name for function in envelope.tool_surface.functions] == [
        "open_meteo_weather.forecast_weather",
    ]
    assert envelope.tool_surface.functions[0].source_id is None
    assert envelope.tool_surface.functions[0].group_key is None


def test_context_slice_runtime_control_items_do_not_become_llm_input() -> None:
    snapshot = RequestRenderSnapshotRecord(
        snapshot_id="ctxsnap-clean-input",
        included_node_ids=(
            "session.turn.current",
            "session.step.llm-1",
            "session.item.user",
        ),
        metadata={},
        projected_input_items=_projected_user_input_items(),
    )

    envelope = RuntimeLlmRequestBuilder().request_envelope(
        draft=_draft(),
        request_render_snapshot=snapshot,
        resolved_tools=ResolvedToolSet(tools=()),
        snapshot_metadata=snapshot.metadata,
        persist_tool_surface_snapshot=False,
    )

    assert [item.payload for item in envelope.transcript.items] == [
        {"role": "user", "content": "Inspect."},
    ]
    assert envelope.request_metadata()["input_item_count"] == 1
    assert "Inspect official flights." not in str(envelope.transcript.to_payload())


def test_long_request_render_snapshot_uses_projected_items_not_collapsed_tree_body() -> None:
    historical_marker = "HISTORICAL_TREE_BODY_MUST_NOT_REPLAY"
    snapshot = RequestRenderSnapshotRecord(
        snapshot_id="ctxsnap-long-history",
        included_node_ids=tuple(f"session.item.{index}" for index in range(200)),
        collapsed_refs=tuple(
            {
                "node_id": f"session.range.{index}",
                "summary": historical_marker,
            }
            for index in range(40)
        ),
        metadata={
            "session_budget_status": "truncated",
            "context_slice_item_count": 200,
            "context_slice_projected_input_item_count": 1,
            "debug_body": f"<context_tree>{historical_marker}</context_tree>",
        },
        projected_input_items=_projected_user_input_items(),
        tool_schemas=(ToolSchema(name="command.exec"),),
    )

    envelope = RuntimeLlmRequestBuilder().request_envelope(
        draft=_draft(),
        request_render_snapshot=snapshot,
        resolved_tools=ResolvedToolSet(
            tools=(_resolved_tool("tool.command.exec", schema_name="command.exec"),),
        ),
        snapshot_metadata=snapshot.metadata,
        persist_tool_surface_snapshot=False,
    )

    payload = envelope.to_payload()
    metadata = envelope.request_metadata()

    assert [item.payload for item in envelope.transcript.items] == [
        {"role": "user", "content": "Inspect."},
    ]
    assert payload["request_render_snapshot"]["included_node_count"] == 200
    assert payload["request_render_snapshot"]["collapsed_ref_count"] == 40
    assert metadata["context_slice_item_count"] == 200
    assert metadata["context_slice_projected_input_item_count"] == 1
    assert historical_marker not in str(payload["messages"])
    assert historical_marker not in str(payload["transcript"])
    assert historical_marker not in str(payload["request_render_snapshot"])
    assert historical_marker not in str(metadata)
    assert "debug_body" not in payload["request_render_snapshot"]


def _draft() -> RuntimeLlmRequestDraft:
    return RuntimeLlmRequestDraft(
        llm_id="llm.test",
        session_key="session:test",
        active_session_id="session-instance-1",
        messages=(
            LlmMessage(role=LlmMessageRole.SYSTEM, content="Runtime contract summary."),
            LlmMessage(
                role=LlmMessageRole.USER,
                content="Inspect.",
                metadata={
                    "session_item_id": "item-user-1",
                    "session_id": "session-instance-1",
                    "sequence_no": 1,
                },
            ),
        ),
        input_items=(
            LlmInputItem(
                kind=LlmInputItemKind.MESSAGE,
                payload={"role": "user", "content": "Inspect."},
                source="session_item",
                metadata={"session_item_id": "item-user-1"},
            ),
        ),
        mode=RuntimeRequestMode.NORMAL_TURN,
        report=None,
        tool_schemas=(ToolSchema(name="command.exec"),),
        surface_policy=RunSurfacePolicy(),
    )


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


def _tool_schema_ref(schema: ToolSchema) -> dict[str, object]:
    return {
        "name": schema.name,
        "source": "context_slice",
        "schema": schema.to_payload(),
    }


def _projected_user_input_items() -> tuple[dict[str, object], ...]:
    return (
        {
            "kind": "message",
            "source": "context_slice",
            "payload": {
                "role": "user",
                "content": "Inspect.",
            },
            "metadata": {
                "session_item_id": "item-user-1",
                "node_id": "session.item.user",
            },
        },
    )
