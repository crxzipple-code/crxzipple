from __future__ import annotations

from crxzipple.modules.llm.application.runtime_request import (
    RuntimeLlmRequestRenderSnapshot,
    RuntimeLlmRequest,
    RuntimeLlmTranscript,
    RuntimeToolSurface,
    RuntimeToolSurfaceRef,
    build_runtime_llm_request_metadata,
    build_runtime_request_render_snapshot,
    dedupe_tool_schemas,
    messages_from_runtime_input_items,
    provider_context_messages_from_messages,
    request_render_snapshot_preview_payload,
    request_metadata_preview_payload,
    request_time_tool_surface,
    runtime_request_context_from_metadata,
    runtime_input_items_from_projected_payloads,
    runtime_input_item_mode_metadata,
    runtime_transcript_input_items_from_messages,
    runtime_transcript_policy,
    sanitize_runtime_input_items_for_capabilities,
    tool_schemas_from_projected_refs,
    tool_surface_request_metadata,
)
from crxzipple.modules.llm.domain import (
    LlmCapability,
    LlmInputItem,
    LlmInputItemKind,
    LlmMessage,
    LlmMessageRole,
    ToolSchema,
)


def test_llm_request_envelope_serializes_canonical_surfaces() -> None:
    tool_schema = ToolSchema(
        name="command.exec",
        description="Run a command.",
        input_schema={"type": "object"},
    )
    envelope = RuntimeLlmRequest(
        llm_id="openai.gpt-5",
        session_key="session-key",
        active_session_id="session-1",
        messages=(
            LlmMessage(role=LlmMessageRole.SYSTEM, content="Runtime contract."),
            LlmMessage(role=LlmMessageRole.USER, content="Inspect."),
        ),
        transcript=RuntimeLlmTranscript(
            items=(
                LlmInputItem(
                    kind=LlmInputItemKind.MESSAGE,
                    payload={"role": "user", "content": "Inspect."},
                    source="session_item",
                    metadata={"session_item_id": "item-user-1"},
                ),
            ),
            policy={
                "session_replay_window": {
                    "session_key": "session-key",
                    "active_session_only": True,
                },
            },
        ),
        tool_schemas=(tool_schema,),
        request_render_snapshot=RuntimeLlmRequestRenderSnapshot(
            snapshot_id="ctxsnap-1",
            included_node_ids=("runtime.contract", "tools.exec"),
            diagnostics={"session_budget_status": "ok"},
        ),
        tool_surface=RuntimeToolSurface(
            id="tool_surface:ctxsnap-1",
            functions=(
                RuntimeToolSurfaceRef(
                    tool_id="tool.command.exec",
                    name="command.exec",
                    schema=tool_schema,
                    target="local",
                    source_id="configured.shell",
                    group_key="command",
                ),
            ),
            mirrored_schema_names=("command.exec",),
            metadata={"request_render_snapshot_id": "ctxsnap-1"},
        ),
        reasoning_config={"summary": "auto"},
        output_contract={"response_format": {"type": "json_object"}},
        provider_options={"provider_transport": "websocket"},
        metadata={"request_render_snapshot_id": "ctxsnap-1"},
        blocked_tool_access=(
            {"tool_id": "browser.open", "reason": "disabled"},
        ),
    )

    payload = envelope.to_payload()

    assert payload["llm_id"] == "openai.gpt-5"
    assert payload["transcript"]["items"][0]["source"] == "session_item"
    assert payload["transcript"]["policy"]["session_replay_window"] == {
        "session_key": "session-key",
        "active_session_only": True,
    }
    assert payload["request_render_snapshot"]["snapshot_id"] == "ctxsnap-1"
    assert payload["request_render_snapshot"]["included_node_count"] == 2
    assert "included_node_ids" not in payload["request_render_snapshot"]
    assert payload["tool_surface"]["functions"][0]["schema"]["name"] == (
        "command.exec"
    )
    assert payload["blocked_tool_access"] == [
        {"tool_id": "browser.open", "reason": "disabled"},
    ]
    assert envelope.renderer_context().to_payload() == {
        "request_render_snapshot_id": "ctxsnap-1",
        "request_render_snapshot_included_node_count": 2,
        "tool_surface_id": "tool_surface:ctxsnap-1",
        "tool_surface_function_count": 1,
        "tool_surface_mirrored_schema_count": 1,
    }
    assert envelope.renderer_route().to_payload() == {
        "llm_id": "openai.gpt-5",
        "session_key": "session-key",
        "active_session_id": "session-1",
        "provider_transport": "websocket",
    }
    assert envelope.renderer_policy().to_payload() == {
        "transcript_policy": {
            "session_replay_window": {
                "session_key": "session-key",
                "active_session_only": True,
            },
        },
        "reasoning": {"summary": "auto"},
        "response_format": {"type": "json_object"},
        "provider_option_keys": ["provider_transport"],
    }


def test_llm_request_metadata_keeps_runtime_refs_separate_from_wire_payload() -> None:
    envelope = RuntimeLlmRequest(
        llm_id="openai.gpt-5",
        session_key="session-key",
        active_session_id="session-1",
        messages=(LlmMessage(role=LlmMessageRole.USER, content="hello"),),
        tool_schemas=(),
        request_render_snapshot=RuntimeLlmRequestRenderSnapshot(
            snapshot_id="ctxsnap-1",
            included_node_ids=("runtime.contract",),
        ),
        tool_surface=RuntimeToolSurface(id="tool_surface:ctxsnap-1"),
        reasoning_config={"effort": "medium"},
        output_contract={"response_format": {"type": "json_object"}},
        provider_options={"service_tier": "default"},
        metadata={"input_mode": "runtime_transcript"},
    )

    metadata = envelope.request_metadata()

    assert metadata["input_mode"] == "runtime_transcript"
    assert metadata["request_render_snapshot"]["snapshot_id"] == "ctxsnap-1"
    assert metadata["tool_surface"]["id"] == "tool_surface:ctxsnap-1"
    assert metadata["reasoning_config"] == {"effort": "medium"}
    assert metadata["output_contract"] == {
        "response_format": {"type": "json_object"},
    }
    assert "provider_options" not in metadata
    assert envelope.to_payload()["provider_options"] == {"service_tier": "default"}
    assert envelope.response_format() == {"type": "json_object"}


def test_llm_request_provider_overrides_merge_reasoning_config() -> None:
    envelope = RuntimeLlmRequest(
        llm_id="openai.gpt-5",
        session_key="session-key",
        active_session_id="session-1",
        messages=(LlmMessage(role=LlmMessageRole.USER, content="hello"),),
        tool_schemas=(),
        request_render_snapshot=RuntimeLlmRequestRenderSnapshot(),
        tool_surface=RuntimeToolSurface(id="tool_surface:empty"),
        reasoning_config={"effort": "medium", "summary": "auto"},
        provider_options={
            "service_tier": "default",
            "reasoning": {"effort": "low"},
        },
    )

    assert envelope.provider_options == {
        "service_tier": "default",
        "reasoning": {"effort": "low"},
    }
    assert envelope.provider_overrides() == {
        "service_tier": "default",
        "reasoning": {"effort": "medium", "summary": "auto"},
    }
    assert "provider_options" not in envelope.request_metadata()


def test_build_runtime_request_render_snapshot_projects_diagnostics() -> None:
    snapshot = build_runtime_request_render_snapshot(
        snapshot_id="ctxsnap-1",
        included_node_ids=("runtime.contract",),
        mirrored_node_ids=("tools.weather",),
        included_refs=({"node_id": "runtime.contract"},),
        collapsed_refs=({"node_id": "history.old"},),
        protocol_required_refs=({"item_id": "item-tool-result"},),
        estimate={"estimated_tokens": 42},
        metadata={
            "session_budget_status": "ok",
            "tool_schema_mirror_budget_status": "ok",
            "visible_input_summary": {
                "input_item_ref_count": 1,
                "tool_schema_names": ["weather.lookup"],
            },
            "request_render_timings": {
                "ensure_workspace_ms": 1.0,
                "record_context_snapshot_ms": 2.0,
            },
            "debug_body": "<tree/>",
        },
    )

    assert snapshot.snapshot_id == "ctxsnap-1"
    assert snapshot.included_node_ids == ("runtime.contract",)
    assert snapshot.mirrored_node_ids == ("tools.weather",)
    assert snapshot.included_refs == ({"node_id": "runtime.contract"},)
    assert snapshot.collapsed_refs == ({"node_id": "history.old"},)
    assert snapshot.protocol_required_refs == ({"item_id": "item-tool-result"},)
    assert snapshot.estimate == {"estimated_tokens": 42}
    assert snapshot.diagnostics == {
        "tool_schema_mirror_budget_status": "ok",
        "session_budget_status": "ok",
        "visible_input_summary": {
            "input_item_ref_count": 1,
            "tool_schema_names": ["weather.lookup"],
        },
        "request_render_timings": {
            "ensure_workspace_ms": 1.0,
            "record_context_snapshot_ms": 2.0,
        },
    }


def test_runtime_input_items_from_projected_payloads_builds_canonical_items() -> None:
    items = runtime_input_items_from_projected_payloads(
        (
            {
                "kind": "message",
                "payload": {"role": "user", "content": "hello"},
                "source": "context_slice",
                "metadata": {
                    "session_item_id": "item-user",
                    "node_id": "session.item.user",
                },
            },
            {
                "kind": "function_call_output",
                "payload": {
                    "call_id": "call-1",
                    "output": "ok",
                },
                "metadata": {"tool_name": "debug.echo"},
            },
            {
                "kind": "unknown",
                "payload": {"role": "user", "content": "ignored"},
            },
            {
                "kind": "message",
                "payload": "ignored",
            },
        ),
    )

    assert tuple(item.kind for item in items) == (
        LlmInputItemKind.MESSAGE,
        LlmInputItemKind.FUNCTION_CALL_OUTPUT,
    )
    assert items[0].payload == {"role": "user", "content": "hello"}
    assert items[0].source == "context_slice"
    assert items[0].metadata == {
        "session_item_id": "item-user",
        "node_id": "session.item.user",
    }
    assert items[1].source == "context_slice"
    assert items[1].metadata == {"tool_name": "debug.echo"}


def test_tool_schemas_from_projected_refs_builds_canonical_schema_set() -> None:
    schemas = tool_schemas_from_projected_refs(
        (
            {
                "node_id": "tool.function.weather",
                "schema": {
                    "name": "weather.lookup",
                    "description": "Lookup weather.",
                    "input_schema": {"type": "object"},
                },
            },
            {
                "node_id": "tool.function.weather.duplicate",
                "schema": {
                    "name": "weather.lookup",
                    "description": "Duplicate should be ignored.",
                    "input_schema": {"type": "object"},
                },
            },
            {"schema": "ignored"},
            {"name": "bare.schema.ignored"},
        ),
    )

    assert len(schemas) == 1
    assert schemas[0].name == "weather.lookup"
    assert schemas[0].description == "Lookup weather."


def test_runtime_request_context_from_metadata_projects_safe_control_summary() -> None:
    context = runtime_request_context_from_metadata(
        {
            "request_context_source": "context_slice",
            "context_slice_id": "ctxslice-1",
            "context_slice_projected_input_item_count": 2,
            "request_render_snapshot": {
                "snapshot_id": "ctxsnap-1",
                "included_node_count": 3,
                "debug_body": "<tree>must not project</tree>",
            },
            "tool_surface": {
                "id": "tool_surface:ctxsnap-1",
                "functions": [{"name": "weather.lookup"}],
                "mirrored_schema_names": ["weather.lookup"],
            },
            "debug_body": "<tree>must not project</tree>",
        },
    )

    assert context == {
        "request_context_source": "context_slice",
        "context_slice_id": "ctxslice-1",
        "context_slice_projected_input_item_count": 2,
        "request_render_snapshot_id": "ctxsnap-1",
        "request_render_snapshot_included_node_count": 3,
        "tool_surface_id": "tool_surface:ctxsnap-1",
        "tool_surface_function_count": 1,
        "tool_surface_mirrored_schema_count": 1,
    }
    assert "debug_body" not in context


def test_build_runtime_llm_request_metadata_projects_snapshot_whitelist() -> None:
    metadata = build_runtime_llm_request_metadata(
        runtime_request_mode="normal_turn",
        runtime_request_surface="interactive",
        request_render_snapshot_id="ctxsnap-1",
        provider_tool_schema_names=("weather.lookup",),
        snapshot_metadata={
            "tree_schema_version": "2026-06-11.context_tree.v2",
            "snapshot_kind": "request_render",
            "history_delivery": "provider_native",
            "mirrored_tool_schema_count": 1,
            "artifact_content_block_count": 2,
            "session_budget_status": "ok",
            "runtime_contract": {"version": "v1"},
            "runtime_contract_hash": "hash-1",
            "visible_input_summary": {
                "input_item_ref_count": 1,
                "tool_schema_count": 1,
            },
            "request_render_timings": {
                "ensure_workspace_ms": 1.0,
                "record_context_snapshot_ms": 2.0,
            },
            "debug_body": "<tree/>",
            "provider_attachments": {"tool_schemas": []},
        },
    )

    assert metadata["runtime_request_mode"] == "normal_turn"
    assert metadata["runtime_request_surface"] == "interactive"
    assert metadata["request_render_snapshot_id"] == "ctxsnap-1"
    assert metadata["provider_tool_schema_count"] == 1
    assert metadata["provider_tool_schema_names"] == ["weather.lookup"]
    assert metadata["mirrored_tool_schema_count"] == 1
    assert metadata["artifact_content_block_count"] == 2
    assert metadata["session_budget_status"] == "ok"
    assert metadata["runtime_contract"] == {"version": "v1"}
    assert metadata["runtime_contract_hash"] == "hash-1"
    assert metadata["visible_input_summary"] == {
        "input_item_ref_count": 1,
        "tool_schema_count": 1,
    }
    assert "request_render_timings" not in metadata
    assert "debug_body" not in metadata
    assert "provider_attachments" not in metadata


def test_messages_from_runtime_input_items_projects_provider_neutral_items() -> None:
    messages = messages_from_runtime_input_items(
        (
            LlmInputItem(
                kind=LlmInputItemKind.MESSAGE,
                payload={"role": "user", "content": "Inspect."},
                source="runtime_transcript",
                metadata={"session_item_id": "item-user-1"},
            ),
            LlmInputItem(
                kind=LlmInputItemKind.FUNCTION_CALL,
                payload={
                    "call_id": "call-1",
                    "name": "command.exec",
                    "arguments": {"cmd": "pwd"},
                },
                source="runtime_transcript",
                metadata={"llm_response_item_id": "item-tool-call-1"},
            ),
            LlmInputItem(
                kind=LlmInputItemKind.FUNCTION_CALL_OUTPUT,
                payload={"call_id": "call-1", "output": "/tmp/work"},
                source="runtime_transcript",
                metadata={"tool_name": "command.exec"},
            ),
        ),
    )

    assert [message.role for message in messages] == [
        LlmMessageRole.USER,
        LlmMessageRole.ASSISTANT,
        LlmMessageRole.TOOL,
    ]
    assert messages[1].content == {
        "type": "function_call",
        "call_id": "call-1",
        "name": "command.exec",
        "arguments": {"cmd": "pwd"},
    }
    assert messages[1].tool_call_id == "call-1"
    assert messages[2].name == "command.exec"
    assert messages[2].tool_call_id == "call-1"


def test_provider_context_messages_from_messages_promotes_system_messages() -> None:
    provider_context_messages = provider_context_messages_from_messages(
        (
            LlmMessage(role=LlmMessageRole.SYSTEM, content="Runtime contract."),
            LlmMessage(role=LlmMessageRole.SYSTEM, content=""),
            LlmMessage(role=LlmMessageRole.USER, content="hello"),
        ),
    )

    assert len(provider_context_messages) == 1
    assert provider_context_messages[0].role is LlmMessageRole.SYSTEM
    assert provider_context_messages[0].content == "Runtime contract."
    assert provider_context_messages[0].metadata == {
        "provider_context_kind": "runtime_instruction",
        "source": "runtime_request_draft_message",
    }


def test_sanitize_runtime_input_items_for_capabilities_omits_vision_blocks() -> None:
    sanitized = sanitize_runtime_input_items_for_capabilities(
        (
            LlmInputItem(
                kind=LlmInputItemKind.MESSAGE,
                payload={
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "inspect"},
                        {"type": "image_ref", "name": "screen"},
                    ],
                },
                source="context_slice",
                metadata={
                    "context_slice_debug": "legacy",
                    "session_item_id": "item-1",
                },
            ),
        ),
        llm_capabilities=(),
    )

    assert sanitized[0].source == "runtime_transcript"
    assert sanitized[0].metadata == {"session_item_id": "item-1"}
    assert sanitized[0].payload["content"] == [
        {"type": "text", "text": "inspect"},
        {
            "type": "text",
            "text": "[image omitted: model does not support vision input]",
        },
    ]


def test_sanitize_runtime_input_items_for_capabilities_keeps_vision_when_supported() -> None:
    item = LlmInputItem(
        kind=LlmInputItemKind.MESSAGE,
        payload={
            "role": "user",
            "content": [
                {"type": "image_ref", "name": "screen"},
            ],
        },
        source="runtime_transcript",
        metadata={},
    )

    assert sanitize_runtime_input_items_for_capabilities(
        (item,),
        llm_capabilities=(LlmCapability.VISION_INPUT,),
    ) == (item,)


def test_runtime_input_item_mode_metadata_counts_sources_and_kinds() -> None:
    metadata = runtime_input_item_mode_metadata(
        (
            LlmInputItem(
                kind=LlmInputItemKind.MESSAGE,
                payload={"role": "user", "content": "hello"},
                source="runtime_transcript",
                metadata={},
            ),
            LlmInputItem(
                kind=LlmInputItemKind.FUNCTION_CALL_OUTPUT,
                payload={"call_id": "call-1", "output": "done"},
                source="runtime_transcript",
                metadata={},
            ),
        ),
    )

    assert metadata == {
        "input_mode": "runtime_transcript",
        "input_item_count": 2,
        "input_item_kind_counts": {
            "message": 1,
            "function_call_output": 1,
        },
        "input_item_source_counts": {"runtime_transcript": 2},
    }


def test_runtime_transcript_input_items_from_messages_preserves_existing_items() -> None:
    item = LlmInputItem(
        kind=LlmInputItemKind.MESSAGE,
        payload={"role": "user", "content": "hello"},
        source="current_inbound",
        metadata={},
    )

    assert runtime_transcript_input_items_from_messages(
        input_items=(item,),
        messages=(LlmMessage(role=LlmMessageRole.USER, content="fallback"),),
    ) == (item,)


def test_runtime_transcript_input_items_from_messages_builds_message_fallback() -> None:
    items = runtime_transcript_input_items_from_messages(
        input_items=(),
        messages=(
            LlmMessage(role=LlmMessageRole.SYSTEM, content="runtime contract"),
            LlmMessage(role=LlmMessageRole.USER, content="hello", name="user"),
            LlmMessage(role=LlmMessageRole.ASSISTANT, content=""),
        ),
    )

    assert len(items) == 1
    assert items[0].kind is LlmInputItemKind.MESSAGE
    assert items[0].source == "runtime_transcript"
    assert items[0].payload == {
        "role": "user",
        "content": "hello",
        "name": "user",
    }


def test_tool_surface_request_metadata_projects_function_refs() -> None:
    schema = ToolSchema(
        name="weather.lookup",
        description="Lookup weather.",
        input_schema={"type": "object"},
    )

    metadata = tool_surface_request_metadata(
        RuntimeToolSurface(
            id="tool_surface:1",
            functions=(
                RuntimeToolSurfaceRef(
                    tool_id="tool.weather.lookup",
                    name="weather.lookup",
                    schema=schema,
                    target="local",
                    source_id="configured.weather",
                    group_key="weather",
                    always_visible=True,
                ),
            ),
            mirrored_schema_names=("weather.lookup",),
        ),
    )

    assert metadata["tool_surface_mirrored_schema_names"] == ["weather.lookup"]
    assert metadata["tool_surface_mirrored_schema_count"] == 1
    assert metadata["tool_surface_always_visible_count"] == 1
    assert metadata["tool_surface_context_selected_count"] == 0
    assert metadata["tool_surface_function_refs"] == [
        {
            "tool_id": "tool.weather.lookup",
            "name": "weather.lookup",
            "enabled": True,
            "always_visible": True,
            "source_id": "configured.weather",
            "group_key": "weather",
        },
    ]
    assert metadata["tool_surface_source_refs"] == [
        {"source_id": "configured.weather"},
    ]
    assert metadata["tool_surface_group_refs"] == [
        {"source_id": "configured.weather", "group_key": "weather"},
    ]


def test_runtime_transcript_policy_adds_required_tool_call_hint() -> None:
    assert runtime_transcript_policy(
        {"session_replay_window": {"active_session_only": True}},
        require_tool_call=True,
    ) == {
        "session_replay_window": {"active_session_only": True},
        "require_tool_call": True,
    }


def test_request_time_tool_surface_makes_unique_surface_copy() -> None:
    schema = ToolSchema(
        name="weather.lookup",
        description="Lookup weather.",
        input_schema={"type": "object"},
    )
    surface = RuntimeToolSurface(
        id="tool_surface:base",
        functions=(
            RuntimeToolSurfaceRef(
                tool_id="tool.weather.lookup",
                name="weather.lookup",
                schema=schema,
                target="local",
            ),
        ),
        mirrored_schema_names=("weather.lookup",),
        blocked_access_count=1,
        metadata={"request_render_snapshot_id": "ctxsnap-1"},
    )

    request_surface = request_time_tool_surface(surface)

    assert request_surface.id.startswith("tool_surface:base:")
    assert request_surface.functions == surface.functions
    assert request_surface.mirrored_schema_names == surface.mirrored_schema_names
    assert request_surface.blocked_access_count == 1
    assert request_surface.metadata["base_tool_surface_id"] == "tool_surface:base"
    assert request_surface.metadata["request_time_unique"] is True


def test_dedupe_tool_schemas_filters_duplicate_names() -> None:
    first = ToolSchema(
        name="weather.lookup",
        description="Lookup weather.",
        input_schema={"type": "object"},
    )
    duplicate = ToolSchema(
        name="weather.lookup",
        description="Duplicate.",
        input_schema={"type": "object"},
    )

    assert dedupe_tool_schemas((first, duplicate)) == (first,)
    assert dedupe_tool_schemas(None) == ()


def test_request_render_snapshot_preview_payload_excludes_observation_body_fields() -> None:
    preview = request_render_snapshot_preview_payload(
        {
            "snapshot_id": "ctxsnap-1",
            "tree_schema_version": "2026-06-11.context_tree.v2",
            "included_node_count": 1,
            "included_node_ids": ["runtime.contract"],
            "raw_tree_body": "<context_tree>full body</context_tree>",
            "debug_body": "<context_tree>full body</context_tree>",
            "provider_attachment_mirror": {
                "runtime_request_draft": {"session_item_count": 1},
                "tool_schemas": [
                    {
                        "name": "command.exec",
                        "description": "full schema description",
                        "input_schema": {"type": "object"},
                    },
                ],
            },
            "context_slice": {
                "slice_id": "ctxslice-1",
                "items": [
                    {
                        "item_id": "item-user-1",
                        "node_id": "session.item.user-1",
                        "kind": "session_item",
                        "text": "full user text stays out",
                    },
                ],
            },
        },
    )

    assert preview == {
        "snapshot_id": "ctxsnap-1",
        "tree_schema_version": "2026-06-11.context_tree.v2",
        "included_node_count": 1,
    }


def test_request_metadata_preview_payload_sanitizes_nested_runtime_payloads() -> None:
    preview = request_metadata_preview_payload(
        {
            "request_render_snapshot_id": "ctxsnap-1",
            "context_slice": {"items": [{"text": "top level slice text"}]},
            "debug_body": "<context_tree>top level body</context_tree>",
            "provider_attachment_mirror": {
                "tool_schemas": [{"description": "top level mirror schema"}],
            },
            "provider_attachments": {
                "tool_schemas": [{"description": "top level provider schema"}],
            },
            "request_render_snapshot": {
                "snapshot_id": "ctxsnap-1",
                "debug_body": "<context_tree>full body</context_tree>",
                "context_slice": {
                    "slice_id": "ctxslice-1",
                    "items": [
                        {
                            "item_id": "item-user-1",
                            "node_id": "session.item.user-1",
                            "kind": "session_item",
                            "text": "full user text stays out",
                        },
                    ],
                },
                "provider_attachment_mirror": {
                    "tool_schemas": [
                        {
                            "name": "command.exec",
                            "description": "full schema",
                            "input_schema": {"type": "object"},
                        },
                    ],
                    "files": [{"artifact_id": "artifact-1"}],
                },
            },
            "tool_surface": {
                "id": "surface-1",
                "functions": [
                    {
                        "name": "command.exec",
                        "schema": {
                            "name": "command.exec",
                            "description": "full schema",
                            "input_schema": {"type": "object"},
                        },
                    },
                ],
            },
        },
    )

    assert preview["request_render_snapshot_id"] == "ctxsnap-1"
    assert "context_slice" not in preview
    assert "debug_body" not in preview
    assert "provider_attachment_mirror" not in preview
    assert "provider_attachments" not in preview
    assert preview["request_render_snapshot"] == {
        "snapshot_id": "ctxsnap-1",
    }
    assert preview["tool_surface"] == {
        "id": "surface-1",
        "function_count": 1,
        "function_names": ["command.exec"],
    }
    assert "full user text stays out" not in str(preview)
    assert "full schema" not in str(preview)
    assert "top level slice text" not in str(preview)
    assert "top level mirror schema" not in str(preview)
    assert "top level provider schema" not in str(preview)
