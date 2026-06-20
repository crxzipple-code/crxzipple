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
    LlmProviderContinuation,
    LlmProviderKind,
    ToolSchema,
)
from crxzipple.modules.llm.infrastructure.adapters.provider_message_projection import (
    projected_input_items_from_messages,
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


def LlmAdapterRequest(**kwargs) -> _LlmAdapterRequest:  # noqa: N802, ANN003
    if "input_items" not in kwargs and kwargs.get("messages"):
        kwargs["input_items"] = tuple(
            projected_input_items_from_messages(
                tuple(
                    message
                    for message in kwargs["messages"]
                    if message.role != LlmMessageRole.SYSTEM
                ),
            ),
        )
    return _LlmAdapterRequest(**kwargs)


def test_openai_codex_renderer_http_uses_full_replay_without_previous_response_id() -> None:
    renderer = _renderer()
    profile = _profile()
    request = LlmAdapterRequest(
        invocation_id="inv-codex-http",
        messages=(
            LlmMessage(role=LlmMessageRole.SYSTEM, content="Runtime contract."),
            LlmMessage(role=LlmMessageRole.USER, content="Original task."),
            LlmMessage(
                role=LlmMessageRole.ASSISTANT,
                content={
                    "type": "function_call",
                    "call_id": "call_1",
                    "name": "exec",
                    "arguments": {"cmd": "echo hello"},
                },
            ),
            LlmMessage(
                role=LlmMessageRole.TOOL,
                tool_call_id="call_1",
                content="hello",
            ),
        ),
        continuation=LlmProviderContinuation(
            mode="provider_native",
            previous_response_id="resp_previous",
        ),
    )

    rendered = renderer.render_http(profile, request)
    preview = renderer.preview(profile, request)

    assert rendered.transport == "http"
    assert "previous_response_id" not in rendered.payload
    assert rendered.payload["input"] == [
        {
            "role": "user",
            "content": [{"type": "input_text", "text": "Original task."}],
        },
        {
            "type": "function_call",
            "call_id": "call_1",
            "name": "exec",
            "arguments": '{"cmd": "echo hello"}',
        },
        {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": "hello",
        },
    ]
    assert preview["transport"] == "http"
    assert preview["has_previous_response_id"] is False
    assert preview["input_delta_mode"] is False
    assert "previous_response_id" not in preview["payload_keys"]


def test_openai_codex_renderer_matches_codex_responses_wire_shape() -> None:
    renderer = _renderer()
    profile = _profile()
    request = LlmAdapterRequest(
        invocation_id="inv-codex-wire-shape",
        messages=(
            LlmMessage(role=LlmMessageRole.SYSTEM, content="Runtime contract."),
            LlmMessage(role=LlmMessageRole.USER, content="Original task."),
        ),
        tool_schemas=(ToolSchema(name="command.exec"),),
        request_policy={"parallel_tool_calls": False},
        overrides={
            "service_tier": "default",
            "prompt_cache_key": "prompt-cache-key",
            "client_metadata": {"x-codex-window-id": "window-1"},
            "include": ["reasoning.encrypted_content"],
        },
    )

    rendered = renderer.render_http(profile, request)

    assert rendered.payload["tools"] == [
        {
            "type": "function",
            "name": "command_exec",
            "description": "",
            "parameters": {},
        },
    ]
    assert rendered.payload["tool_choice"] == "auto"
    assert rendered.payload["parallel_tool_calls"] is False
    assert rendered.payload["include"] == ["reasoning.encrypted_content"]
    assert rendered.payload["service_tier"] == "default"
    assert rendered.payload["prompt_cache_key"] == "prompt-cache-key"
    assert rendered.payload["client_metadata"] == {"x-codex-window-id": "window-1"}


def test_openai_codex_renderer_adds_provider_context_to_instructions() -> None:
    renderer = _renderer()
    profile = _profile()
    request = LlmAdapterRequest(
        invocation_id="inv-codex-skills",
        provider_context_messages=(
            LlmMessage(
                role=LlmMessageRole.SYSTEM,
                content="## Skills\n\n- browser: inspect pages",
                metadata={"provider_context_kind": "available_skills"},
            ),
        ),
        messages=(
            LlmMessage(
                role=LlmMessageRole.SYSTEM,
                content="legacy direct message should not render",
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
                payload={"role": "user", "content": "Original task."},
                source="session_item",
            ),
        ),
    )

    rendered = renderer.render_http(profile, request)

    assert rendered.payload["instructions"] == (
        "## Skills\n\n- browser: inspect pages\n\nRuntime contract."
    )
    assert rendered.payload["input"] == [
        {
            "role": "user",
            "content": [{"type": "input_text", "text": "Original task."}],
        },
    ]
    assert "legacy direct message should not render" not in str(rendered.payload)


def test_openai_codex_renderer_projects_runtime_transcript_input_items_only() -> None:
    renderer = _renderer()
    profile = _profile()
    request = LlmAdapterRequest(
        invocation_id="inv-codex-runtime-transcript",
        input_items=(
            LlmInputItem(
                kind=LlmInputItemKind.MESSAGE,
                payload={
                    "role": "system",
                    "content": "Runtime contract.",
                },
                source="context_slice",
                metadata={
                    "runtime_input_item_id": "runtime.contract",
                    "node_id": "runtime.contract",
                },
            ),
            LlmInputItem(
                kind=LlmInputItemKind.MESSAGE,
                payload={
                    "role": "user",
                    "content": "查昆明到上海周日机票",
                },
                source="session_item",
                metadata={
                    "session_item_id": "session-item-user-1",
                    "runtime_input_item_id": "session.item.user-1",
                    "node_id": "session.item.user-1",
                },
            ),
            LlmInputItem(
                kind=LlmInputItemKind.FUNCTION_CALL,
                payload={
                    "type": "function_call",
                    "call_id": "call-exec-1",
                    "name": "command.exec",
                    "arguments": {"cmd": "echo hello"},
                },
                source="session_item",
                metadata={
                    "session_item_id": "session-item-call-1",
                    "runtime_input_item_id": "session.step.item.call-1",
                    "node_id": "session.step.item.call-1",
                },
            ),
            LlmInputItem(
                kind=LlmInputItemKind.FUNCTION_CALL_OUTPUT,
                payload={
                    "type": "function_call_output",
                    "call_id": "call-exec-1",
                    "output": "hello",
                },
                source="session_item",
                metadata={
                    "session_item_id": "session-item-result-1",
                    "runtime_input_item_id": "session.step.item.result-1",
                    "node_id": "session.step.item.result-1",
                },
            ),
        ),
        tool_schemas=(ToolSchema(name="command.exec"),),
        request_metadata={
            "request_context_source": "context_slice",
            "context_slice_id": "ctxslice_renderer",
            "context_slice_item_count": 3,
            "context_slice_included_node_count": 3,
            "context_slice_omitted_node_count": 1,
            "context_slice_active_tool_count": 1,
            "context_slice_projected_input_item_count": 3,
            "context_slice_unresolved_ref_count": 1,
            "context_slice_loss": {"unresolved_ref_count": 1, "omitted_node_count": 1},
            "tool_surface": {
                "id": "tool_surface:ctxsnap-1",
                "functions": [
                    {
                        "tool_id": "tool.command.exec",
                        "name": "command.exec",
                        "source_id": "configured.command",
                        "enabled": True,
                        "always_visible": True,
                        "metadata": {
                            "source": "context_slice",
                            "node_id": "tools.tool.command.exec",
                            "tool_ref_id": "tools.tool.command.exec",
                            "function_name": "command.exec",
                        },
                    },
                ],
                "mirrored_schema_names": ["command.exec"],
            },
            "request_render_snapshot": {
                "snapshot_id": "ctxsnap-1",
                "debug_body": "<context_tree>debug-only body must not render</context_tree>",
                "context_slice": {
                    "slice_id": "ctxslice_renderer",
                    "audience": "llm_request",
                    "run_id": "run-1",
                    "tree_revision": 3,
                    "items": [
                        {
                            "item_id": "session.item.user-1",
                            "node_id": "session.item.user-1",
                            "section": "task",
                            "owner": "session",
                            "kind": "session_item",
                            "title": "User Message",
                            "text": "查昆明到上海周日机票",
                            "metadata": {"owner_resolution": "owner_resolved"},
                        },
                        {
                            "section": "runtime",
                            "owner": "runtime",
                            "kind": "runtime_contract",
                            "title": "Runtime Contract",
                            "summary": "Use tools until task is done.",
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
                    "report": {
                        "included_node_ids": ["session.item.user-1", "runtime.contract"],
                        "omitted_node_ids": ["hidden.omitted"],
                        "unresolved_refs": [{"node_id": "hidden"}],
                        "loss": {"unresolved_ref_count": 1, "omitted_node_count": 1},
                    },
                },
            },
        },
        messages=(
            LlmMessage(role=LlmMessageRole.SYSTEM, content="Runtime contract."),
            LlmMessage(role=LlmMessageRole.USER, content="Original task."),
        ),
    )

    rendered = renderer.render_http(profile, request)
    preview = renderer.preview(profile, request)

    instructions = rendered.payload["instructions"]
    assert instructions == "Runtime contract."
    assert "Current runtime context slice:" not in instructions
    assert "查昆明到上海周日机票" not in instructions
    assert "command.exec" not in instructions
    assert "unresolved_refs" not in instructions
    assert "hidden" not in instructions
    assert "<context_tree>" not in str(rendered.payload)
    assert "debug-only body must not render" not in str(rendered.payload)
    assert rendered.payload["input"] == [
        {
            "role": "user",
            "content": [{"type": "input_text", "text": "查昆明到上海周日机票"}],
        },
        {
            "type": "function_call",
            "call_id": "call-exec-1",
            "name": "command_exec",
            "arguments": '{"cmd": "echo hello"}',
        },
        {
            "type": "function_call_output",
            "call_id": "call-exec-1",
            "output": "hello",
        },
    ]
    assert "llm_request_slice_id" not in preview
    assert preview["request_context_source"] == "context_slice"
    assert preview["context_slice_id"] == "ctxslice_renderer"
    assert preview["context_slice_item_count"] == 3
    assert preview["context_slice_included_node_count"] == 3
    assert preview["context_slice_omitted_node_count"] == 1
    assert preview["context_slice_active_tool_count"] == 1
    assert preview["context_slice_projected_input_item_count"] == 3
    assert preview["context_slice_unresolved_ref_count"] == 1
    assert preview["context_slice_loss"] == {
        "unresolved_ref_count": 1,
        "omitted_node_count": 1,
    }
    assert "context_slice_audience" not in preview
    assert "context_slice_items" not in preview
    assert "context_slice_active_tools" not in preview
    assert "context_slice_report" not in preview
    input_mapping = preview["render_report"]["input_item_mapping"]
    assert input_mapping[0]["node_id"] == "session.item.user-1"
    assert input_mapping[0]["session_item_id"] == "session-item-user-1"
    tool_surface_report = preview["render_report"]["tool_surface"]
    assert tool_surface_report["provider_visible_tool_names"] == ("command_exec",)
    assert tool_surface_report["provider_tool_mapping"] == [
        {
            "provider_name": "command_exec",
            "runtime_tool_name": "command.exec",
            "tool_id": "tool.command.exec",
            "trace_status": "runtime_tool_surface",
            "source_id": "configured.command",
            "source": "context_slice",
            "node_id": "tools.tool.command.exec",
            "tool_ref_id": "tools.tool.command.exec",
        },
    ]


def test_openai_codex_renderer_websocket_uses_provider_native_delta() -> None:
    renderer = _renderer()
    profile = _profile()
    baseline_input_items = (
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
                "call_id": "call_1",
                "name": "exec",
                "arguments": {"cmd": "echo hello"},
            },
            source="session_item",
        ),
    )
    baseline_request = LlmAdapterRequest(
        invocation_id="inv-codex-baseline",
        messages=(),
        input_items=baseline_input_items,
    )
    baseline_items = renderer.build_full_input_items_input(
        render_input=ProviderRenderInput.from_request(
            profile=profile,
            request=baseline_request,
        ),
    )
    request = LlmAdapterRequest(
        invocation_id="inv-codex-websocket",
        messages=(),
        input_items=(
            *baseline_input_items,
            LlmInputItem(
                kind=LlmInputItemKind.FUNCTION_CALL_OUTPUT,
                payload={
                    "type": "function_call_output",
                    "call_id": "call_1",
                    "output": "hello",
                },
                source="session_item",
            ),
        ),
        provider_transport="websocket",
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

    rendered = renderer.render_websocket_create(
        profile,
        request,
        endpoint="wss://chatgpt.example/backend-api/codex/responses",
    )
    preview = renderer.preview(profile, request)

    assert rendered.transport == "websocket"
    assert rendered.payload["type"] == "response.create"
    assert rendered.payload["previous_response_id"] == "resp_previous"
    assert rendered.payload["input"] == [
        {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": "hello",
        },
    ]
    assert preview["transport"] == "websocket"
    assert preview["message_type"] == "response.create"
    assert preview["previous_response_id"] == "resp_previous"
    assert preview["input_delta_mode"] is True
    assert preview["render_report"]["render_strategy"] == "provider_native_delta"


def test_openai_codex_renderer_websocket_allows_additive_tool_surface_delta() -> None:
    renderer = _renderer()
    profile = _profile()
    old_tool = ToolSchema(name="capability.search")
    new_tool = ToolSchema(name="browser.navigate")
    baseline_input_items = (
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
                "call_id": "call_search",
                "name": "capability.search",
                "arguments": {"query": "browser"},
            },
            source="session_item",
        ),
    )
    baseline_request = LlmAdapterRequest(
        invocation_id="inv-codex-additive-baseline",
        messages=(),
        input_items=baseline_input_items,
        tool_schemas=(old_tool,),
    )
    baseline_items = renderer.build_full_input_items_input(
        render_input=ProviderRenderInput.from_request(
            profile=profile,
            request=baseline_request,
        ),
    )
    baseline_preview = renderer.preview(profile, baseline_request)
    request = LlmAdapterRequest(
        invocation_id="inv-codex-additive-delta",
        messages=(),
        input_items=(
            *baseline_input_items,
            LlmInputItem(
                kind=LlmInputItemKind.FUNCTION_CALL_OUTPUT,
                payload={
                    "type": "function_call_output",
                    "call_id": "call_search",
                    "output": "browser.navigate is enabled",
                },
                source="session_item",
            ),
        ),
        tool_schemas=(new_tool, old_tool),
        provider_transport="websocket",
        continuation=LlmProviderContinuation(
            mode="provider_native",
            previous_response_id="resp_previous",
            input_item_fingerprints=openai_response_input_fingerprints(
                baseline_items,
            ),
            instructions_fingerprint=openai_provider_payload_fingerprint(
                "Runtime contract.",
            ),
            tool_fingerprints=tuple(baseline_preview["tool_fingerprints"]),
        ),
    )

    rendered = renderer.render_websocket_create(
        profile,
        request,
        endpoint="wss://chatgpt.example/backend-api/codex/responses",
    )
    preview = renderer.preview(profile, request)

    assert rendered.payload["previous_response_id"] == "resp_previous"
    assert rendered.payload["input"] == [
        {
            "type": "function_call_output",
            "call_id": "call_search",
            "output": "browser.navigate is enabled",
        },
    ]
    assert [tool["name"] for tool in rendered.payload["tools"]] == [
        "browser_navigate",
        "capability_search",
    ]
    assert preview["input_delta_mode"] is True
    assert preview["render_report"]["render_strategy"] == "provider_native_delta"


def test_openai_codex_renderer_websocket_allows_empty_provider_native_delta() -> None:
    renderer = _renderer()
    profile = _profile()
    input_items = (
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
                "call_id": "call_search",
                "name": "capability.search",
                "arguments": {"query": "browser"},
            },
            source="session_item",
        ),
    )
    baseline_request = LlmAdapterRequest(
        invocation_id="inv-codex-empty-baseline",
        messages=(),
        input_items=input_items,
    )
    baseline_items = renderer.build_full_input_items_input(
        render_input=ProviderRenderInput.from_request(
            profile=profile,
            request=baseline_request,
        ),
    )
    request = LlmAdapterRequest(
        invocation_id="inv-codex-empty-delta",
        messages=(),
        input_items=input_items,
        provider_transport="websocket",
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

    rendered = renderer.render_websocket_create(
        profile,
        request,
        endpoint="wss://chatgpt.example/backend-api/codex/responses",
    )
    preview = renderer.preview(profile, request)

    assert rendered.payload["previous_response_id"] == "resp_previous"
    assert rendered.payload["input"] == []
    assert preview["input_delta_mode"] is True
    assert preview["input_item_count"] == 0
    assert preview["input_delta_count"] == 0


def test_openai_codex_renderer_websocket_uses_full_request_without_fingerprints() -> None:
    renderer = _renderer()
    profile = _profile()
    request = LlmAdapterRequest(
        invocation_id="inv-codex-websocket-full",
        messages=(
            LlmMessage(role=LlmMessageRole.SYSTEM, content="Runtime contract."),
            LlmMessage(role=LlmMessageRole.USER, content="Original task."),
            LlmMessage(
                role=LlmMessageRole.TOOL,
                tool_call_id="call_missing",
                content="orphan output",
            ),
        ),
        provider_transport="websocket",
        continuation=LlmProviderContinuation(
            mode="provider_native",
            previous_response_id="resp_previous",
        ),
    )

    rendered = renderer.render_websocket_create(
        profile,
        request,
        endpoint="wss://chatgpt.example/backend-api/codex/responses",
    )
    preview = renderer.preview(profile, request)

    assert "previous_response_id" not in rendered.payload
    assert rendered.payload["input"] == [
        {
            "role": "user",
            "content": [{"type": "input_text", "text": "Original task."}],
        },
        {
            "type": "function_call_output",
            "call_id": "call_missing",
            "output": "orphan output",
        },
    ]
    assert preview["transport"] == "websocket"
    assert preview["input_delta_mode"] is False
    assert preview["render_report"]["render_strategy"] == "full_wire_payload"


def test_openai_codex_renderer_downgrades_artifact_refs_to_text() -> None:
    renderer = _renderer()
    profile = _profile()
    request = LlmAdapterRequest(
        invocation_id="inv-codex-artifact-ref",
        messages=(),
        input_items=(
            LlmInputItem(
                kind=LlmInputItemKind.MESSAGE,
                payload={"role": "user", "content": "Inspect trace."},
                source="session_item",
            ),
            LlmInputItem(
                kind=LlmInputItemKind.FUNCTION_CALL_OUTPUT,
                payload={
                    "type": "function_call_output",
                    "call_id": "call_trace",
                    "output": [
                        {"type": "text", "text": "Browser action trace captured."},
                        {
                            "type": "file_ref",
                            "artifact_id": "artifact-trace-1",
                            "mime_type": "application/json",
                            "name": "trace.json",
                            "download_url": "/artifacts/artifact-trace-1/download",
                        },
                    ],
                },
                source="session_item",
            ),
        ),
    )

    rendered = renderer.render_http(profile, request)

    assert rendered.payload["input"] == [
        {
            "role": "user",
            "content": [{"type": "input_text", "text": "Inspect trace."}],
        },
        {
            "type": "function_call_output",
            "call_id": "call_trace",
            "output": "Browser action trace captured.\n[file:trace.json]",
        },
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "Browser action trace captured."},
                {
                    "type": "input_text",
                    "text": "[file_ref: name=trace.json; mime_type=application/json; artifact_id=artifact-trace-1]",
                },
            ],
        },
    ]


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
