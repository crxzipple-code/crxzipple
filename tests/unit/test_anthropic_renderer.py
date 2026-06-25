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
)
from crxzipple.modules.llm.infrastructure.adapters.anthropic_messages_renderer import (
    AnthropicMessagesRenderer,
)
from crxzipple.modules.llm.infrastructure.adapters.provider_message_common import (
    projected_input_items_from_messages,
)


def LlmAdapterRequest(**kwargs) -> _LlmAdapterRequest:  # noqa: N802, ANN003
    if "input_items" not in kwargs and kwargs.get("messages"):
        kwargs["input_items"] = tuple(
            projected_input_items_from_messages(kwargs["messages"]),
        )
    return _LlmAdapterRequest(**kwargs)


def test_anthropic_renderer_maps_projected_tool_call_and_result() -> None:
    renderer = _renderer()
    rendered = renderer.render(
        _profile(),
        LlmAdapterRequest(
            invocation_id="inv-anthropic-tool",
            messages=(LlmMessage(role=LlmMessageRole.USER, content="legacy"),),
            input_items=(
                LlmInputItem(
                    kind=LlmInputItemKind.MESSAGE,
                    payload={"role": "user", "content": "Use replay input"},
                ),
                LlmInputItem(
                    kind=LlmInputItemKind.FUNCTION_CALL,
                    payload={
                        "call_id": "call_search",
                        "name": "search_docs",
                        "arguments": {"query": "ddd"},
                    },
                ),
                LlmInputItem(
                    kind=LlmInputItemKind.FUNCTION_CALL_OUTPUT,
                    payload={
                        "call_id": "call_search",
                        "output": '{"hits":1}',
                    },
                ),
            ),
        ),
    )

    assert rendered.payload["messages"] == [
        {
            "role": "user",
            "content": [{"type": "text", "text": "Use replay input"}],
        },
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "call_search",
                    "name": "search_docs",
                    "input": {"query": "ddd"},
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "call_search",
                    "content": '{"hits":1}',
                },
            ],
        },
    ]


def test_anthropic_renderer_downgrades_reasoning_item_to_assistant_text() -> None:
    renderer = _renderer()
    rendered = renderer.render(
        _profile(),
        LlmAdapterRequest(
            invocation_id="inv-anthropic-reasoning",
            messages=(LlmMessage(role=LlmMessageRole.USER, content="legacy"),),
            input_items=(
                LlmInputItem(
                    kind=LlmInputItemKind.MESSAGE,
                    payload={"role": "user", "content": "Find flights"},
                ),
                LlmInputItem(
                    kind=LlmInputItemKind.REASONING,
                    payload={
                        "type": "reasoning",
                        "summary": [
                            {
                                "type": "summary_text",
                                "text": "Need to inspect official site.",
                            },
                        ],
                    },
                ),
            ),
        ),
    )

    assert rendered.payload["messages"] == [
        {
            "role": "user",
            "content": [{"type": "text", "text": "Find flights"}],
        },
        {
            "role": "assistant",
            "content": [
                {
                    "type": "text",
                    "text": "Need to inspect official site.",
                },
            ],
        },
    ]


def test_anthropic_renderer_preview_reports_renderer_and_wire_shape() -> None:
    renderer = _renderer()
    preview = renderer.preview(
        _profile(),
        LlmAdapterRequest(
            invocation_id="inv-anthropic-preview",
            messages=(
                LlmMessage(role=LlmMessageRole.SYSTEM, content="System rules."),
                LlmMessage(role=LlmMessageRole.USER, content="hello"),
            ),
            request_metadata={
                "request_render_snapshot": {
                    "snapshot_id": "ctxsnap_1",
                    "included_node_ids": ["runtime.contract"],
                    "debug_body": "debug body that must not enter preview surface",
                },
            },
        ),
    )

    assert preview["preview_source"] == "provider_adapter"
    assert preview["renderer_id"] == "anthropic_messages"
    report = preview["render_report"]
    assert report["renderer_id"] == "anthropic_messages"
    assert report["transport"] == "http"
    assert report["render_strategy"] == "full_wire_payload"
    assert report["loss_report"] == {}
    assert report["tool_surface"]["source_tool_schema_count"] == 0
    assert report["tool_surface"]["provider_visible_tool_count"] == 0
    assert report["tool_surface"]["dropped_tool_schema_count"] == 0
    assert report["tool_protocol"]["schema_version"] is None
    assert report["tool_protocol"]["source_had_protocol_breaks"] is False
    assert report["tool_protocol"]["replay_has_protocol_breaks"] is False
    assert report["input_item_mapping"]
    assert preview["message_count"] == 1
    assert preview["has_system"] is True
    assert preview["request_render_snapshot_id"] == "ctxsnap_1"
    assert "debug_body" not in str(preview["request_render_snapshot_fingerprint"])


def test_anthropic_renderer_preview_reports_reasoning_downgrade_loss() -> None:
    renderer = _renderer()
    preview = renderer.preview(
        _profile(),
        LlmAdapterRequest(
            invocation_id="inv-anthropic-loss",
            messages=(LlmMessage(role=LlmMessageRole.USER, content="legacy"),),
            input_items=(
                LlmInputItem(
                    kind=LlmInputItemKind.MESSAGE,
                    payload={"role": "user", "content": "Find flights"},
                ),
                LlmInputItem(
                    kind=LlmInputItemKind.REASONING,
                    payload={
                        "type": "reasoning",
                        "summary": [
                            {
                                "type": "summary_text",
                                "text": "Need official source.",
                            },
                        ],
                    },
                ),
            ),
        ),
    )

    assert preview["render_report"]["loss_report"] == {
        "reasoning": {
            "input_item_count": 1,
            "strategy": "assistant_text_downgrade",
        },
    }


def _renderer() -> AnthropicMessagesRenderer:
    return AnthropicMessagesRenderer(
        default_base_url="https://api.anthropic.example/v1",
    )


def _profile() -> LlmProfile:
    return LlmProfile(
        id="anthropic-profile",
        provider=LlmProviderKind.ANTHROPIC,
        api_family=LlmApiFamily.ANTHROPIC_MESSAGES,
        model_name="claude-sonnet-4-5",
        model_family=LlmModelFamily.GENERAL,
    )
