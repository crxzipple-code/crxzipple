from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from crxzipple.modules.llm.application.adapters import LlmAdapterRequest
from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmInputItem,
    LlmInputItemKind,
    LlmMessage,
    LlmMessageRole,
    LlmModelFamily,
    LlmProfile,
    LlmProviderContinuation,
    LlmProviderKind,
    ToolSchema,
)
from crxzipple.modules.llm.infrastructure.adapters.provider_request_preview import (
    openai_provider_payload_fingerprint,
    openai_response_input_fingerprints,
)
from crxzipple.modules.llm.infrastructure.adapters.openai_codex_responses_renderer import (
    OpenAICodexResponsesRenderer,
)
from crxzipple.modules.llm.infrastructure.adapters.provider_protocol import (
    ProviderRenderInput,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "provider_request_traces"


def test_crxzipple_failed_run_provider_preview_fixture() -> None:
    rendered = _stable_preview(_renderer().preview(_profile(), _crxzipple_request()))

    assert rendered == _fixture("crxzipple_failed_run_provider_preview.json")
    assert "context_tree" not in json.dumps(rendered, ensure_ascii=False)
    assert "must not leak" not in json.dumps(rendered, ensure_ascii=False)


def test_codex_http_trace_fixture() -> None:
    rendered = _stable_preview(_renderer().preview(_profile(), _codex_http_request()))

    assert rendered == _fixture("codex_http_provider_preview.json")
    assert rendered["transport"] == "http"
    assert rendered["has_previous_response_id"] is False
    assert "previous_response_id" not in rendered["payload_keys"]


def test_codex_websocket_trace_fixture() -> None:
    renderer = _renderer()
    rendered = _stable_preview(renderer.preview(_profile(), _codex_websocket_request(renderer)))

    assert rendered == _fixture("codex_websocket_provider_preview.json")
    assert rendered["transport"] == "websocket"
    assert rendered["message_type"] == "response.create"
    assert rendered["previous_response_id"] == "resp_previous"
    assert rendered["input_delta_mode"] is True


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _stable_preview(preview: dict[str, Any]) -> dict[str, Any]:
    payload = preview["payload_preview"]
    render_report = preview["render_report"]
    stable = {
        "provider": preview["provider"],
        "api_family": preview["api_family"],
        "model": preview["model"],
        "transport": preview["transport"],
        "renderer_id": preview["renderer_id"],
        "render_strategy": preview["render_strategy"],
        "message_type": preview.get("message_type"),
        "payload_keys": preview["payload_keys"],
        "input_item_count": preview["input_item_count"],
        "input_item_types": list(preview["input_item_types"]),
        "input_delta_mode": preview["input_delta_mode"],
        "input_delta_count": preview["input_delta_count"],
        "has_previous_response_id": preview["has_previous_response_id"],
        "previous_response_id": preview["previous_response_id"],
        "request_context_source": preview.get("request_context_source"),
        "context_slice_id": preview.get("context_slice_id"),
        "context_slice_projected_input_item_count": preview.get(
            "context_slice_projected_input_item_count",
        ),
        "context_slice_unresolved_ref_count": preview.get(
            "context_slice_unresolved_ref_count",
        ),
        "option_summary": preview["option_summary"],
        "instructions": payload.get("instructions"),
        "input": payload.get("input"),
        "tools": payload.get("tools"),
        "render_report": {
            "render_strategy": render_report["render_strategy"],
            "input_item_mapping": render_report.get("input_item_mapping"),
            "input_item_mapping_coverage": render_report.get(
                "input_item_mapping_coverage",
            ),
            "tool_surface": render_report.get("tool_surface"),
            "loss_report": render_report.get("loss_report"),
        },
    }
    return json.loads(json.dumps(stable, ensure_ascii=False, sort_keys=True))


def _crxzipple_request() -> LlmAdapterRequest:
    return LlmAdapterRequest(
        invocation_id="inv-crx-failed-run-fixture",
        messages=(),
        input_items=(
            LlmInputItem(
                kind=LlmInputItemKind.MESSAGE,
                payload={"role": "system", "content": "Runtime contract."},
                source="context_slice",
                metadata={"node_id": "runtime.contract"},
            ),
            LlmInputItem(
                kind=LlmInputItemKind.MESSAGE,
                payload={
                    "role": "user",
                    "content": "去东航官网查昆明到上海周日的票",
                },
                source="session_item",
                metadata={
                    "node_id": "session.item.user-1",
                    "session_item_id": "session-item-user-1",
                },
            ),
            LlmInputItem(
                kind=LlmInputItemKind.FUNCTION_CALL,
                payload={
                    "type": "function_call",
                    "call_id": "call-exec-1",
                    "name": "command.exec",
                    "arguments": {
                        "cmd": 'python - <<PY\nprint("probe")\nPY',
                    },
                },
                source="session_item",
                metadata={
                    "node_id": "session.step.item.call-1",
                    "session_item_id": "session-item-call-1",
                    "tool_call_id": "call-exec-1",
                    "tool_name": "command.exec",
                },
            ),
            LlmInputItem(
                kind=LlmInputItemKind.FUNCTION_CALL_OUTPUT,
                payload={
                    "type": "function_call_output",
                    "call_id": "call-exec-1",
                    "output": "probe",
                },
                source="session_item",
                metadata={
                    "node_id": "session.step.item.result-1",
                    "session_item_id": "session-item-result-1",
                    "tool_call_id": "call-exec-1",
                    "tool_run_id": "tool-run-1",
                },
            ),
        ),
        tool_schemas=(ToolSchema(name="command.exec"),),
        request_metadata={
            "request_context_source": "context_slice",
            "context_slice_id": "ctxslice-crx-failed-run",
            "context_slice_projected_input_item_count": 3,
            "context_slice_unresolved_ref_count": 0,
            "tool_surface": {
                "functions": [
                    {
                        "tool_id": "tool.command.exec",
                        "name": "command.exec",
                        "source_id": "configured.command",
                        "metadata": {
                            "source": "context_slice",
                            "node_id": "tools.command.exec",
                            "tool_ref_id": "tools.command.exec",
                            "function_name": "command.exec",
                        },
                    },
                ],
            },
            "request_render_snapshot": {
                "snapshot_id": "ctxsnap-crx-failed-run",
                "debug_body": "<context_tree>must not leak</context_tree>",
            },
        },
    )


def _codex_http_request() -> LlmAdapterRequest:
    return LlmAdapterRequest(
        invocation_id="inv-codex-http-fixture",
        messages=(
            LlmMessage(role=LlmMessageRole.SYSTEM, content="Runtime contract."),
            LlmMessage(role=LlmMessageRole.USER, content="Original task."),
            LlmMessage(
                role=LlmMessageRole.TOOL,
                tool_call_id="call_http",
                content="http output",
            ),
        ),
        input_items=(
            LlmInputItem(
                kind=LlmInputItemKind.MESSAGE,
                payload={"role": "user", "content": "Original task."},
                source="session_item",
            ),
            LlmInputItem(
                kind=LlmInputItemKind.FUNCTION_CALL_OUTPUT,
                payload={
                    "type": "function_call_output",
                    "call_id": "call_http",
                    "output": "http output",
                },
                source="session_item",
            ),
        ),
        continuation=LlmProviderContinuation(
            mode="provider_native",
            previous_response_id="resp_previous",
        ),
    )


def _codex_websocket_request(
    renderer: OpenAICodexResponsesRenderer,
) -> LlmAdapterRequest:
    baseline_input = (
        LlmInputItem(
            kind=LlmInputItemKind.MESSAGE,
            payload={"role": "system", "content": "Runtime contract."},
            source="context_slice",
        ),
        LlmInputItem(
            kind=LlmInputItemKind.MESSAGE,
            payload={"role": "user", "content": "Original task."},
            source="session_item",
        ),
        LlmInputItem(
            kind=LlmInputItemKind.FUNCTION_CALL,
            payload={
                "type": "function_call",
                "call_id": "call_ws",
                "name": "exec",
                "arguments": {"cmd": "echo ws"},
            },
            source="session_item",
        ),
    )
    baseline_request = LlmAdapterRequest(
        invocation_id="inv-baseline",
        messages=(),
        input_items=baseline_input,
    )
    baseline_items = renderer.build_full_input_items_input(
        render_input=ProviderRenderInput.from_request(
            profile=_profile(),
            request=baseline_request,
        ),
    )
    return LlmAdapterRequest(
        invocation_id="inv-codex-ws-fixture",
        messages=(),
        provider_transport="websocket",
        input_items=(
            *baseline_input,
            LlmInputItem(
                kind=LlmInputItemKind.FUNCTION_CALL_OUTPUT,
                payload={
                    "type": "function_call_output",
                    "call_id": "call_ws",
                    "output": "ws output",
                },
                source="session_item",
            ),
        ),
        continuation=LlmProviderContinuation(
            mode="provider_native",
            previous_response_id="resp_previous",
            input_item_fingerprints=openai_response_input_fingerprints(
                baseline_items,
            ),
            instructions_fingerprint=openai_provider_payload_fingerprint(
                "Runtime contract.",
            ),
            tool_fingerprints=(),
        ),
    )


def _renderer() -> OpenAICodexResponsesRenderer:
    return OpenAICodexResponsesRenderer(
        default_base_url="https://chatgpt.example/backend-api/codex",
        default_instructions="You are Codex.",
    )


def _profile() -> LlmProfile:
    return LlmProfile(
        id="codex-profile",
        provider=LlmProviderKind.OPENAI_CODEX,
        api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
        model_name="gpt-5.5",
        model_family=LlmModelFamily.CODEX,
    )
