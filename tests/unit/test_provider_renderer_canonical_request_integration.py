from __future__ import annotations

from crxzipple.modules.llm.application.adapters import LlmAdapterRequest
from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmInputItem,
    LlmInputItemKind,
    LlmModelFamily,
    LlmProfile,
    LlmProviderKind,
)
from crxzipple.modules.llm.infrastructure.adapters.anthropic_messages_renderer import (
    AnthropicMessagesRenderer,
)
from crxzipple.modules.llm.infrastructure.adapters.openai_codex_responses_renderer import (
    OpenAICodexResponsesRenderer,
)


def test_same_canonical_request_renders_codex_native_and_anthropic_downgraded_reasoning() -> None:
    request = LlmAdapterRequest(
        invocation_id="inv-cross-renderer",
        messages=(),
        input_items=(
            LlmInputItem(
                kind=LlmInputItemKind.MESSAGE,
                payload={"role": "user", "content": "Find flights"},
                source="session_item",
                metadata={
                    "runtime_input_item_id": "slice.item.user",
                    "runtime_input_node_id": "session.item.user",
                    "runtime_input_section": "history",
                    "owner": "session",
                    "kind": "session_item",
                    "session_item_id": "session-item-1",
                    "context_slice_debug_body": "<context_tree>hidden</context_tree>",
                    "unsafe_runtime_hint": "browser.special.path",
                    "raw_trace": {"secret": "must-not-leak"},
                },
            ),
            LlmInputItem(
                kind=LlmInputItemKind.REASONING,
                payload={
                    "type": "reasoning",
                    "summary": [
                        {
                            "type": "summary_text",
                            "text": "Need official source and validation.",
                        },
                    ],
                },
                source="session_item",
            ),
        ),
    )

    codex_preview = OpenAICodexResponsesRenderer(
        default_base_url="https://chatgpt.example/backend-api/codex",
        default_instructions="You are Codex.",
    ).preview(_codex_profile(), request)
    anthropic_preview = AnthropicMessagesRenderer(
        default_base_url="https://api.anthropic.example/v1",
    ).preview(_anthropic_profile(), request)

    codex_payload = codex_preview["payload_preview"]
    anthropic_payload = anthropic_preview["payload_preview"]
    assert isinstance(codex_payload, dict)
    assert isinstance(anthropic_payload, dict)

    assert codex_preview["renderer_id"] == "openai_codex_responses"
    assert codex_preview["render_report"]["loss_report"] == {}
    assert codex_preview["render_report"]["input_item_mapping"][0] == {
        "provider_payload_index": 0,
        "input_item_index": 0,
        "input_item_kind": "message",
        "input_item_source": "session_item",
        "owner": "session",
        "kind": "session_item",
        "session_item_id": "session-item-1",
        "trace_status": "runtime_input_item",
    }
    assert codex_preview["render_report"]["input_item_mapping_coverage"] == {
        "provider_input_item_count": 2,
        "canonical_input_item_count": 2,
        "traced_input_item_count": 2,
        "untraced_input_item_count": 0,
        "provider_generated_or_unattributed": [],
    }
    assert codex_payload["input"] == [
        {
            "role": "user",
            "content": [{"type": "input_text", "text": "Find flights"}],
        },
        {
            "type": "reasoning",
            "summary": [
                {
                    "type": "summary_text",
                    "text": "Need official source and validation.",
                },
            ],
        },
    ]
    assert "context_tree" not in str(codex_preview["render_report"]["input_item_mapping"])
    assert "browser.special.path" not in str(codex_preview["render_report"])
    assert "must-not-leak" not in str(codex_payload)

    assert anthropic_preview["renderer_id"] == "anthropic_messages"
    assert anthropic_preview["render_report"]["input_item_mapping"][0] == {
        "provider_payload_index": 0,
        "input_item_index": 0,
        "input_item_kind": "message",
        "input_item_source": "session_item",
        "owner": "session",
        "kind": "session_item",
        "session_item_id": "session-item-1",
        "trace_status": "runtime_input_item",
    }
    assert anthropic_preview["render_report"]["input_item_mapping_coverage"] == {
        "provider_input_item_count": 2,
        "canonical_input_item_count": 2,
        "traced_input_item_count": 2,
        "untraced_input_item_count": 0,
        "provider_generated_or_unattributed": [],
    }
    assert anthropic_preview["render_report"]["loss_report"] == {
        "reasoning": {
            "input_item_count": 1,
            "strategy": "assistant_text_downgrade",
        },
    }
    assert "context_tree" not in str(
        anthropic_preview["render_report"]["input_item_mapping"],
    )
    assert "browser.special.path" not in str(anthropic_preview["render_report"])
    assert "must-not-leak" not in str(anthropic_payload)
    assert anthropic_payload["messages"] == [
        {
            "role": "user",
            "content": [{"type": "text", "text": "Find flights"}],
        },
        {
            "role": "assistant",
            "content": [
                {
                    "type": "text",
                    "text": "Need official source and validation.",
                },
            ],
        },
    ]


def test_provider_render_report_flags_unattributed_input_items() -> None:
    request = LlmAdapterRequest(
        invocation_id="inv-unattributed-renderer",
        messages=(),
        input_items=(
            LlmInputItem(
                kind=LlmInputItemKind.MESSAGE,
                payload={"role": "user", "content": "Find flights"},
                source="",
            ),
        ),
    )

    preview = OpenAICodexResponsesRenderer(
        default_base_url="https://chatgpt.example/backend-api/codex",
        default_instructions="You are Codex.",
    ).preview(_codex_profile(), request)

    assert preview["render_report"]["input_item_mapping"][0]["trace_status"] == (
        "provider_renderer_generated_or_unattributed"
    )
    assert preview["render_report"]["input_item_mapping_coverage"] == {
        "provider_input_item_count": 1,
        "canonical_input_item_count": 1,
        "traced_input_item_count": 0,
        "untraced_input_item_count": 1,
        "provider_generated_or_unattributed": [
            {
                "provider_payload_index": 0,
                "input_item_index": 0,
                "input_item_kind": "message",
            },
        ],
    }


def test_provider_wire_payload_excludes_context_diagnostics_and_debug_body() -> None:
    noisy_text = "DO_NOT_SEND_UNCERTAIN_CONTEXT_DIAGNOSTIC"
    request = LlmAdapterRequest(
        invocation_id="inv-noise-boundary",
        messages=(),
        input_items=(
            LlmInputItem(
                kind=LlmInputItemKind.MESSAGE,
                payload={"role": "user", "content": "Use official sources."},
                source="session_item",
                metadata={
                    "runtime_input_item_id": "session.item.user",
                    "runtime_input_node_id": "session.item.user",
                    "runtime_input_section": "history",
                    "session_item_id": "session-item-user",
                },
            ),
        ),
        request_metadata={
            "request_render_snapshot": {
                "snapshot_id": "ctxsnap-noise",
                "debug_body": f"<context_tree>{noisy_text}</context_tree>",
                "diagnostics": {"uncertain": noisy_text},
                "context_slice": {
                    "slice_id": "ctxslice-noise",
                    "audience": "llm_request",
                    "items": [
                        {
                            "item_id": "session.item.user",
                            "node_id": "session.item.user",
                            "section": "history",
                            "owner": "session",
                            "kind": "session_item",
                            "title": "User Message",
                            "summary": noisy_text,
                            "text": noisy_text,
                        },
                    ],
                    "report": {
                        "included_node_ids": ["session.item.user"],
                        "omitted_node_ids": ["debug.hidden"],
                        "archived_refs": [
                            {
                                "node_id": "session.item.archived",
                                "reason": noisy_text,
                            },
                        ],
                        "collapsed_refs": [
                            {
                                "node_id": "session.range.collapsed",
                                "title": noisy_text,
                            },
                        ],
                        "unresolved_refs": [
                            {
                                "node_id": "session.item.unresolved",
                                "reason": noisy_text,
                            },
                        ],
                        "loss": {
                            "omitted_node_count": 1,
                            "unresolved_ref_count": 1,
                            "raw_diagnostic": noisy_text,
                        },
                        "budget": {
                            "text_tokens": 8,
                            "raw_budget_note": noisy_text,
                        },
                    },
                },
            },
        },
    )

    codex_preview = OpenAICodexResponsesRenderer(
        default_base_url="https://chatgpt.example/backend-api/codex",
        default_instructions="You are Codex.",
    ).preview(_codex_profile(), request)
    anthropic_preview = AnthropicMessagesRenderer(
        default_base_url="https://api.anthropic.example/v1",
    ).preview(_anthropic_profile(), request)

    codex_payload = codex_preview["payload_preview"]
    anthropic_payload = anthropic_preview["payload_preview"]
    assert isinstance(codex_payload, dict)
    assert isinstance(anthropic_payload, dict)

    assert noisy_text not in str(codex_payload)
    assert noisy_text not in str(anthropic_payload)
    assert "context_slice_report" not in codex_preview
    assert "context_slice_report" not in anthropic_preview


def _codex_profile() -> LlmProfile:
    return LlmProfile(
        id="codex-profile",
        provider=LlmProviderKind.OPENAI_CODEX,
        api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
        model_name="gpt-5.5",
        model_family=LlmModelFamily.CODEX,
    )


def _anthropic_profile() -> LlmProfile:
    return LlmProfile(
        id="anthropic-profile",
        provider=LlmProviderKind.ANTHROPIC,
        api_family=LlmApiFamily.ANTHROPIC_MESSAGES,
        model_name="claude-sonnet-4-5",
        model_family=LlmModelFamily.GENERAL,
    )
