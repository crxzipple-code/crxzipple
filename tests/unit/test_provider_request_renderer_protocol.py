from __future__ import annotations

from crxzipple.modules.llm.application.adapters import LlmAdapterRequest as _LlmAdapterRequest
from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmInputItem,
    LlmInputItemKind,
    LlmMessage,
    LlmMessageRole,
    LlmModelFamily,
    LlmProfile,
    LlmProviderKind,
    ToolSchema,
)
from crxzipple.modules.llm.infrastructure.adapters.anthropic_messages_renderer import (
    AnthropicMessagesRenderer,
)
from crxzipple.modules.llm.infrastructure.adapters.provider_message_projection import (
    projected_input_items_from_messages,
)
from crxzipple.modules.llm.infrastructure.adapters.gemini_generate_content_renderer import (
    GeminiGenerateContentRenderer,
)
from crxzipple.modules.llm.infrastructure.adapters.openai_chat_compatible_renderer import (
    OpenAIChatCompatibleRequestRenderer,
)
from crxzipple.modules.llm.infrastructure.adapters.openai_codex_responses_renderer import (
    OpenAICodexResponsesRenderer,
)
from crxzipple.modules.llm.infrastructure.adapters.openai_responses_renderer import (
    OpenAIResponsesRenderer,
)
from crxzipple.modules.llm.infrastructure.adapters.provider_protocol import (
    ProviderRequestPreviewRenderer,
)


def LlmAdapterRequest(**kwargs) -> _LlmAdapterRequest:  # noqa: N802, ANN003
    if "input_items" not in kwargs and kwargs.get("messages"):
        kwargs["input_items"] = tuple(
            projected_input_items_from_messages(kwargs["messages"]),
        )
    return _LlmAdapterRequest(**kwargs)


def test_provider_request_renderers_expose_preview_protocol() -> None:
    renderers: tuple[ProviderRequestPreviewRenderer, ...] = (
        OpenAICodexResponsesRenderer(
            default_base_url="https://api.openai.test/v1",
            default_instructions="You are Codex.",
        ),
        OpenAIResponsesRenderer(default_base_url="https://api.openai.test/v1"),
        AnthropicMessagesRenderer(default_base_url="https://api.anthropic.test/v1"),
        GeminiGenerateContentRenderer(
            default_base_url="https://generativelanguage.googleapis.test/v1beta",
        ),
        OpenAIChatCompatibleRequestRenderer(
            default_base_url="https://chat-compatible.test/v1",
        ),
    )

    request = _request()
    for renderer in renderers:
        preview = renderer.preview(_profile(), request)
        assert preview["preview_source"] == "provider_adapter"
        assert preview["renderer_id"] == renderer.renderer_id
        assert preview["render_report"]["renderer_id"] == renderer.renderer_id


def test_codex_websocket_preview_reports_provider_native_delta_strategy() -> None:
    renderer = OpenAICodexResponsesRenderer(
        default_base_url="https://api.openai.test/v1",
        default_instructions="You are Codex.",
    )
    request = LlmAdapterRequest(
        invocation_id="inv-1",
        messages=(LlmMessage(role=LlmMessageRole.USER, content="continue"),),
        resolved_credential="token",
        request_metadata={},
        provider_transport="websocket",
        continuation=None,
    )

    preview = renderer.preview(_profile(), request)

    assert preview["renderer_id"] == "openai_codex_responses"
    assert preview["transport"] == "websocket"
    assert preview["render_report"]["render_strategy"] == "full_wire_payload"


def test_renderer_preview_uses_adapter_request_runtime_context() -> None:
    renderer = OpenAICodexResponsesRenderer(
        default_base_url="https://api.openai.test/v1",
        default_instructions="You are Codex.",
    )
    request = LlmAdapterRequest(
        invocation_id="inv-runtime-context",
        messages=(LlmMessage(role=LlmMessageRole.USER, content="hello"),),
        runtime_context={
            "request_context_source": "context_slice",
            "context_slice_id": "ctxslice-preview",
            "context_slice_projected_input_item_count": 1,
            "request_render_snapshot_id": "ctxsnap-preview",
        },
    )

    preview = renderer.preview(_profile(), request)

    assert preview["runtime_context_source"] == "adapter_request"
    assert preview["request_context_source"] == "context_slice"
    assert preview["context_slice_id"] == "ctxslice-preview"
    assert preview["context_slice_projected_input_item_count"] == 1
    assert preview["request_render_snapshot_id"] == "ctxsnap-preview"


def test_renderers_translate_neutral_require_tool_call_policy() -> None:
    request = LlmAdapterRequest(
        invocation_id="inv-require-tool",
        messages=(LlmMessage(role=LlmMessageRole.USER, content="use a tool"),),
        tool_schemas=(ToolSchema(name="exec"),),
        request_policy={"require_tool_call": True},
    )

    codex_payload = OpenAICodexResponsesRenderer(
        default_base_url="https://api.openai.test/v1",
        default_instructions="You are Codex.",
    ).render_http(_profile(), request).payload
    responses_payload = OpenAIResponsesRenderer(
        default_base_url="https://api.openai.test/v1",
    ).render(_profile(), request).payload
    chat_payload = OpenAIChatCompatibleRequestRenderer(
        default_base_url="https://chat-compatible.test/v1",
    ).render(_profile(), request).payload
    anthropic_payload = AnthropicMessagesRenderer(
        default_base_url="https://api.anthropic.test/v1",
    ).render(_profile(), request).payload
    gemini_payload = GeminiGenerateContentRenderer(
        default_base_url="https://generativelanguage.googleapis.test/v1beta",
    ).render(_profile(), request).payload

    assert codex_payload["tool_choice"] == "required"
    assert responses_payload["tool_choice"] == "required"
    assert chat_payload["tool_choice"] == "required"
    assert anthropic_payload["tool_choice"] == {"type": "any"}
    assert gemini_payload["toolConfig"] == {
        "functionCallingConfig": {
            "mode": "ANY",
        },
    }


def test_chat_compatible_renderer_maps_runtime_transcript_input_items_to_messages_and_tools() -> None:
    request = LlmAdapterRequest(
        invocation_id="inv-chat-runtime-transcript",
        messages=(
            LlmMessage(
                role=LlmMessageRole.USER,
                content="legacy direct message should not render",
            ),
        ),
        input_items=(
            LlmInputItem(
                kind=LlmInputItemKind.MESSAGE,
                payload={
                    "role": "user",
                    "content": "Use runtime transcript task item.",
                },
                source="session_item",
                metadata={
                    "runtime_input_item_id": "session.item.user-1",
                    "node_id": "session.item.user-1",
                },
            ),
            LlmInputItem(
                kind=LlmInputItemKind.FUNCTION_CALL,
                payload={
                    "type": "function_call",
                    "call_id": "call-command-1",
                    "name": "command.exec",
                    "arguments": {"cmd": "echo hello"},
                },
                source="session_item",
                metadata={
                    "runtime_input_item_id": "session.step.item.call-1",
                    "node_id": "session.step.item.call-1",
                },
            ),
            LlmInputItem(
                kind=LlmInputItemKind.FUNCTION_CALL_OUTPUT,
                payload={
                    "type": "function_call_output",
                    "call_id": "call-command-1",
                    "output": "hello",
                },
                source="session_item",
                metadata={
                    "runtime_input_item_id": "session.step.item.result-1",
                    "node_id": "session.step.item.result-1",
                },
            ),
        ),
        tool_schemas=(
            ToolSchema(
                name="command.exec",
                description="Run a shell command.",
                input_schema={"type": "object"},
            ),
        ),
        request_metadata={
            "request_render_snapshot": {
                "snapshot_id": "ctxsnap-chat",
                "context_slice": {
                    "items": [
                        {
                            "item_id": "session.item.user-1",
                            "node_id": "session.item.user-1",
                            "section": "task",
                            "owner": "session",
                            "kind": "session_item",
                            "title": "User Message",
                            "text": "This metadata text must not render directly.",
                        },
                    ],
                    "active_tools": [
                        {
                            "tool_ref_id": "tools.tool.command.exec",
                            "node_id": "tools.tool.command.exec",
                            "source_id": "configured.command",
                            "function_name": "command.exec",
                        },
                    ],
                },
            },
        },
    )

    rendered = OpenAIChatCompatibleRequestRenderer(
        default_base_url="https://chat-compatible.test/v1",
    ).render(_profile(), request)
    preview = OpenAIChatCompatibleRequestRenderer(
        default_base_url="https://chat-compatible.test/v1",
    ).preview(_profile(), request)

    messages = rendered.payload["messages"]
    assert messages[0] == {
        "role": "user",
        "content": [{"type": "text", "text": "Use runtime transcript task item."}],
    }
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] is None
    assert messages[1]["tool_calls"][0]["id"] == "call-command-1"
    assert messages[1]["tool_calls"][0]["function"]["name"] == "command_exec"
    assert messages[2] == {
        "role": "tool",
        "tool_call_id": "call-command-1",
        "content": "hello",
    }
    assert rendered.payload["tools"][0]["function"]["name"] == "command_exec"
    rendered_text = str(rendered.payload)
    assert "legacy direct message should not render" not in rendered_text
    assert "This metadata text must not render directly." not in rendered_text
    assert "context_slice_item_count" not in preview
    assert "context_slice_active_tool_count" not in preview


def test_renderers_map_provider_context_messages_to_system_instruction_fields() -> None:
    request = LlmAdapterRequest(
        invocation_id="inv-provider-context",
        provider_context_messages=(
            LlmMessage(role=LlmMessageRole.SYSTEM, content="Skill index."),
        ),
        messages=(
            LlmMessage(
                role=LlmMessageRole.SYSTEM,
                content="legacy direct system message should not render",
            ),
        ),
        input_items=(
            LlmInputItem(
                kind=LlmInputItemKind.MESSAGE,
                payload={"role": "system", "content": "Runtime contract."},
                source="context_slice",
            ),
            LlmInputItem(
                kind=LlmInputItemKind.MESSAGE,
                payload={"role": "user", "content": "hello"},
                source="session_item",
            ),
        ),
    )

    codex_payload = OpenAICodexResponsesRenderer(
        default_base_url="https://api.openai.test/v1",
        default_instructions="You are Codex.",
    ).render_http(_profile(), request).payload
    responses_payload = OpenAIResponsesRenderer(
        default_base_url="https://api.openai.test/v1",
    ).render(_profile(), request).payload
    chat_payload = OpenAIChatCompatibleRequestRenderer(
        default_base_url="https://chat-compatible.test/v1",
    ).render(_profile(), request).payload
    anthropic_payload = AnthropicMessagesRenderer(
        default_base_url="https://api.anthropic.test/v1",
    ).render(_profile(), request).payload
    gemini_payload = GeminiGenerateContentRenderer(
        default_base_url="https://generativelanguage.googleapis.test/v1beta",
    ).render(_profile(), request).payload

    assert codex_payload["instructions"] == "Skill index.\n\nRuntime contract."
    assert responses_payload["instructions"] == "Skill index.\n\nRuntime contract."
    assert chat_payload["messages"][0] == {
        "role": "system",
        "content": "Skill index.\n\nRuntime contract.",
    }
    assert anthropic_payload["system"] == "Skill index.\n\nRuntime contract."
    assert gemini_payload["system_instruction"] == {
        "parts": [{"text": "Skill index.\n\nRuntime contract."}],
    }
    assert "legacy direct system message should not render" not in str(
        (
            codex_payload,
            responses_payload,
            chat_payload,
            anthropic_payload,
            gemini_payload,
        ),
    )


def test_renderers_do_not_project_context_slice_metadata_into_system_prompt() -> None:
    request = LlmAdapterRequest(
        invocation_id="inv-context-slice",
        request_metadata={
            "request_render_snapshot": {
                "snapshot_id": "ctxsnap-1",
                "debug_body": "<context_tree>debug-only body must not render</context_tree>",
                "context_slice": {
                    "run_id": "run-1",
                    "tree_revision": 8,
                    "items": [
                        {
                            "section": "task",
                            "owner": "session",
                            "kind": "session_item",
                            "title": "User Message",
                            "text": "Need Sunday KMG to SHA fares.",
                        },
                        {
                            "section": "runtime",
                            "owner": "runtime",
                            "kind": "runtime_contract",
                            "title": "Runtime Contract",
                            "summary": "Use available tools until the task is done.",
                        },
                    ],
                    "active_tools": [{"function_name": "command.exec"}],
                    "report": {
                        "unresolved_refs": [{"node_id": "unresolved.secret"}],
                        "loss": {"unresolved_ref_count": 1},
                    },
                },
            },
        },
        messages=(
            LlmMessage(role=LlmMessageRole.SYSTEM, content="Runtime contract."),
            LlmMessage(role=LlmMessageRole.USER, content="hello"),
        ),
    )

    codex_payload = OpenAICodexResponsesRenderer(
        default_base_url="https://api.openai.test/v1",
        default_instructions="You are Codex.",
    ).render_http(_profile(), request).payload
    responses_payload = OpenAIResponsesRenderer(
        default_base_url="https://api.openai.test/v1",
    ).render(_profile(), request).payload
    chat_payload = OpenAIChatCompatibleRequestRenderer(
        default_base_url="https://chat-compatible.test/v1",
    ).render(_profile(), request).payload
    anthropic_payload = AnthropicMessagesRenderer(
        default_base_url="https://api.anthropic.test/v1",
    ).render(_profile(), request).payload
    gemini_payload = GeminiGenerateContentRenderer(
        default_base_url="https://generativelanguage.googleapis.test/v1beta",
    ).render(_profile(), request).payload

    system_texts = (
        codex_payload["instructions"],
        responses_payload["instructions"],
        chat_payload["messages"][0]["content"],
        anthropic_payload["system"],
        gemini_payload["system_instruction"]["parts"][0]["text"],
    )
    for system_text in system_texts:
        assert system_text == "Runtime contract."
        assert "Current runtime context slice:" not in system_text
        assert "Need Sunday KMG to SHA fares." not in system_text
        assert "command.exec" not in system_text
        assert "unresolved_refs" not in system_text
        assert "unresolved.secret" not in system_text
        assert "<context_tree>" not in system_text
        assert "debug-only body must not render" not in system_text

    payload_texts = (
        str(codex_payload),
        str(responses_payload),
        str(chat_payload),
        str(anthropic_payload),
        str(gemini_payload),
    )
    for payload_text in payload_texts:
        assert "debug-only body must not render" not in payload_text


def test_renderers_keep_context_slice_metadata_out_of_provider_payload() -> None:
    request = LlmAdapterRequest(
        invocation_id="inv-context-slice-long",
        request_metadata={
            "request_render_snapshot": {
                "snapshot_id": "ctxsnap-long",
                "context_slice": {
                    "items": [
                        {
                            "section": "workspace",
                            "owner": "workspace",
                            "kind": "workspace_file",
                            "title": "AGENTS.md",
                            "text": "x" * 10_000,
                        },
                    ],
                },
            },
        },
        messages=(LlmMessage(role=LlmMessageRole.USER, content="hello"),),
    )

    payload = OpenAIResponsesRenderer(
        default_base_url="https://api.openai.test/v1",
    ).render(_profile(), request).payload

    assert "instructions" not in payload
    assert "x" * 100 not in str(payload)


def _request() -> LlmAdapterRequest:
    return LlmAdapterRequest(
        invocation_id="inv-1",
        messages=(LlmMessage(role=LlmMessageRole.USER, content="hello"),),
        resolved_credential="token",
        request_metadata={},
    )


def _profile() -> LlmProfile:
    return LlmProfile(
        id="profile-1",
        provider=LlmProviderKind.OPENAI,
        api_family=LlmApiFamily.OPENAI_RESPONSES,
        model_name="gpt-5",
        model_family=LlmModelFamily.GENERAL,
    )
