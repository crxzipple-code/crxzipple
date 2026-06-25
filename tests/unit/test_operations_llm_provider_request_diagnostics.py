from __future__ import annotations

from crxzipple.modules.llm.domain import (
    LlmInputItem,
    LlmInputItemKind,
    LlmInvocation,
    LlmMessage,
    LlmMessageRole,
    LlmResult,
)
from crxzipple.modules.operations.application.read_models.llm_provider_render_labels import (
    provider_request_render_report_label,
    provider_request_render_strategy_label,
    provider_request_renderer_label,
    provider_tool_mapping_label,
)
from crxzipple.modules.operations.application.read_models.llm_provider_request_labels import (
    provider_continuation_fallback_label,
    provider_request_continuation_label,
    provider_request_input_delta_label,
    provider_request_input_items_label,
    provider_request_options_label,
    provider_request_tool_count_label,
    provider_request_transport_label,
)
from crxzipple.modules.operations.application.read_models.llm_provider_context_mapping import (
    provider_context_mapping_table,
)
from crxzipple.modules.operations.application.read_models.llm_provider_request_diagnostics import (
    provider_wire_preview,
    request_payload,
    runtime_request_summary,
)


def _invocation() -> LlmInvocation:
    return LlmInvocation(
        id="inv-provider-diagnostics",
        llm_id="openai.codex",
        messages=(LlmMessage(role=LlmMessageRole.USER, content="hello"),),
        input_items=(
            LlmInputItem(
                kind=LlmInputItemKind.MESSAGE,
                payload={"role": "user", "content": "hello"},
                source="session_item",
            ),
        ),
        result=LlmResult(
            metadata={
                "provider_continuation_fallback": True,
                "provider_continuation_fallback_reason": "websocket_failed",
            },
        ),
        request_metadata={
            "request_render_snapshot_id": "ctxsnap-1",
            "request_render_snapshot_kind": "request_render",
            "request_context_source": "context_slice",
            "context_slice_item_count": 2,
            "tool_surface": {
                "id": "tool-surface-1",
                "functions": [{"name": "command_exec"}],
                "mirrored_schema_names": ["command_exec"],
                "blocked_access_count": 1,
            },
        },
        provider_request_payload_preview={
            "renderer_id": "openai_codex_responses",
            "transport": "websocket",
            "render_strategy": "provider_native_delta",
            "has_previous_response_id": True,
            "previous_response_id": "resp-prev",
            "input_delta_mode": True,
            "input_delta_count": 1,
            "input_baseline_count": 3,
            "input_item_types": ["function_call_output"],
            "tool_count": 2,
            "option_summary": {"text": {"verbosity": "low"}, "empty": {}},
            "payload_preview": {"type": "response.create"},
            "render_report": {
                "renderer_id": "openai_codex_responses",
                "transport": "websocket",
                "render_strategy": "provider_native_delta",
                "loss_report": {},
                "input_item_mapping_coverage": {
                    "provider_input_item_count": 1,
                    "canonical_input_item_count": 1,
                    "traced_input_item_count": 1,
                    "untraced_input_item_count": 0,
                },
                "input_item_mapping": [
                    {
                        "provider_payload_index": 0,
                        "input_item_index": 0,
                        "input_item_kind": "message",
                        "input_item_source": "session_item",
                        "session_item_id": "session-item-user",
                        "trace_status": "runtime_input_item",
                    },
                ],
                "tool_surface": {
                    "provider_tool_mapping": [
                        {
                            "provider_name": "command_exec",
                            "node_id": "tools.tool.command.exec",
                            "trace_status": "runtime_tool_surface",
                        },
                        {
                            "provider_name": "unknown_tool",
                            "tool_id": "untraced_tool",
                            "trace_status": "provider_generated",
                        },
                    ],
                },
            },
        },
    )


def test_provider_request_diagnostics_project_wire_preview_and_labels() -> None:
    invocation = _invocation()

    assert provider_wire_preview(invocation) == {
        "renderer_id": "openai_codex_responses",
        "transport": "websocket",
        "render_strategy": "provider_native_delta",
        "has_previous_response_id": True,
        "previous_response_id": "resp-prev",
        "input_delta_mode": True,
        "input_delta_count": 1,
        "input_baseline_count": 3,
        "input_item_types": ["function_call_output"],
        "tool_count": 2,
        "option_summary": {"text": {"verbosity": "low"}, "empty": {}},
        "payload_preview": {"type": "response.create"},
    }
    assert provider_request_continuation_label(invocation) == (
        "previous_response_id=resp-prev"
    )
    assert provider_request_transport_label(invocation) == "websocket"
    assert provider_request_renderer_label(invocation) == "openai_codex_responses"
    assert provider_request_render_strategy_label(invocation) == "provider_native_delta"
    assert provider_request_render_report_label(invocation) == (
        "renderer=openai_codex_responses; transport=websocket; "
        "strategy=provider_native_delta; loss=none"
    )
    assert provider_tool_mapping_label(invocation) == (
        "traced=1; untraced=1; "
        "sample=command_exec->tools.tool.command.exec, unknown_tool->untraced_tool"
    )
    assert provider_request_input_delta_label(invocation) == "mode=true; delta=1; baseline=3"
    assert provider_continuation_fallback_label(invocation) == "websocket_failed"
    assert provider_request_input_items_label(invocation) == "function_call_output"
    assert provider_request_tool_count_label(invocation) == "2"
    assert provider_request_options_label(invocation) == "text"


def test_provider_request_diagnostics_project_runtime_summary_and_context_mapping() -> None:
    invocation = _invocation()

    summary = runtime_request_summary(invocation)
    assert summary["message_count"] == 1
    assert summary["input_item_count"] == 1
    assert summary["request_render_snapshot_id"] == "ctxsnap-1"
    assert summary["request_context_source"] == "context_slice"
    assert summary["context_slice_item_count"] == 2
    assert summary["tool_surface"] == {
        "id": "tool-surface-1",
        "function_count": 1,
        "mirrored_schema_count": 1,
        "blocked_access_count": 1,
    }
    assert summary["provider_input_item_mapping_coverage"] == {
        "provider_input_item_count": 1,
        "canonical_input_item_count": 1,
        "traced_input_item_count": 1,
        "untraced_input_item_count": 0,
    }

    mapping = provider_context_mapping_table(invocation)
    row = mapping.rows[0].cells
    assert mapping.title == "Provider Context Mapping"
    assert row["provider_index"] == "0"
    assert row["input_kind"] == "message"
    assert row["source"] == "session_item"
    assert row["session_item"] == "session-item-user"
    assert row["trace_status"] == "runtime_input_item"

    payload = request_payload(invocation)
    assert payload["llm_id"] == "openai.codex"
    assert payload["request_metadata"]["request_render_snapshot_id"] == "ctxsnap-1"
    assert "provider_request_payload_preview" in payload
