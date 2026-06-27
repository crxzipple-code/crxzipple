from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import UUID

from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmProfile,
    LlmProviderKind,
    LlmResponseItem,
    LlmResponseItemKind,
)
from crxzipple.modules.llm.infrastructure.adapters.anthropic_messages import (
    AnthropicMessagesAdapter,
)
from crxzipple.modules.llm.infrastructure.adapters.gemini_generate_content import (
    GeminiGenerateContentAdapter,
)
from crxzipple.modules.llm.infrastructure.adapters.openai_chat_compatible_events import (
    build_openai_chat_adapter_response,
)
from crxzipple.modules.llm.infrastructure.adapters.openai_codex_event_projection import (
    codex_response_items_from_completed_event,
    consume_codex_event,
)
from crxzipple.modules.llm.infrastructure.adapters.openai_response_projection import (
    build_openai_response_items,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "provider_response_items"


def test_primary_provider_response_item_projection_golden() -> None:
    actual = _provider_response_item_fixture()

    assert actual == _fixture("canonical_response_items.json")
    assert set(actual) == {
        "anthropic_messages",
        "gemini_generate_content",
        "openai_chat_compatible",
        "openai_codex_responses",
        "openai_responses",
    }
    for provider_items in actual.values():
        assert [item["kind"] for item in provider_items] == [
            "assistant_message",
            "tool_call",
        ]
        assert provider_items[0]["user_timeline_candidate"] is True
        assert provider_items[1]["user_timeline_candidate"] is False
        assert provider_items[1]["provider_replay_candidate"] is True


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _provider_response_item_fixture() -> dict[str, Any]:
    return _stable_json(
        {
            "anthropic_messages": _stable_response_items(_anthropic_items()),
            "gemini_generate_content": _stable_response_items(_gemini_items()),
            "openai_chat_compatible": _stable_response_items(_chat_items()),
            "openai_codex_responses": _stable_response_items(_codex_items()),
            "openai_responses": _stable_response_items(_openai_items()),
        },
    )


def _stable_json(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True))


def _stable_response_items(
    items: tuple[LlmResponseItem, ...],
) -> list[dict[str, Any]]:
    return [_stable_response_item(item) for item in items]


def _stable_response_item(item: LlmResponseItem) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "kind": item.kind.value,
        "phase": item.phase.value,
        "provider_item_id": item.provider_item_id,
        "provider_item_type": item.provider_item_type,
        "provider_replay_candidate": item.provider_replay_candidate,
        "role": item.role.value if item.role is not None else None,
        "sequence_no": item.sequence_no,
        "user_timeline_candidate": item.user_timeline_candidate,
    }
    if item.kind is LlmResponseItemKind.TOOL_CALL:
        payload["arguments"] = item.content_payload.get("arguments")
        payload["call_id"] = item.call_id
        payload["tool_name"] = item.tool_name
    else:
        payload["text"] = item.content_payload.get("text")
    return {key: value for key, value in payload.items() if value is not None}


def _openai_items() -> tuple[LlmResponseItem, ...]:
    return build_openai_response_items(
        invocation_id="inv-openai-fixture",
        response_payload={
            "id": "resp_openai_fixture",
            "model": "gpt-5",
            "status": "completed",
            "end_turn": False,
            "output": [
                {
                    "type": "message",
                    "id": "msg_openai_1",
                    "role": "assistant",
                    "phase": "final_answer",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "I will check the official source.",
                        },
                    ],
                },
                {
                    "type": "function_call",
                    "id": "fc_openai_1",
                    "call_id": "call_openai_1",
                    "name": "command_exec",
                    "arguments": '{"cmd":"curl https://example.test"}',
                },
            ],
        },
        tool_name_aliases={"command_exec": "command.exec"},
    )


def _codex_items() -> tuple[LlmResponseItem, ...]:
    event, completed = consume_codex_event(
        _profile(
            LlmProviderKind.OPENAI_CODEX,
            LlmApiFamily.OPENAI_CODEX_RESPONSES,
            "gpt-5-codex",
        ),
        "response.completed",
        [
            json.dumps(
                {
                    "type": "response.completed",
                    "response": {
                        "id": "resp_codex_fixture",
                        "model": "gpt-5-codex",
                        "status": "completed",
                        "end_turn": False,
                        "output": [
                            {
                                "type": "message",
                                "id": "msg_codex_1",
                                "role": "assistant",
                                "phase": "commentary",
                                "content": [
                                    {
                                        "type": "output_text",
                                        "text": "I will inspect the official site.",
                                    },
                                ],
                            },
                            {
                                "type": "function_call",
                                "id": "fc_codex_1",
                                "call_id": "call_codex_1",
                                "name": "command_exec",
                                "arguments": '{"cmd":"python scrape.py"}',
                            },
                        ],
                    },
                },
            ),
        ],
        sequence=1,
        description="Codex fixture",
        invocation_id="inv-codex-fixture",
        tool_name_aliases={"command_exec": "command.exec"},
        transport="sse",
    )
    assert completed is True
    assert event is not None
    return codex_response_items_from_completed_event(event)


def _chat_items() -> tuple[LlmResponseItem, ...]:
    response = build_openai_chat_adapter_response(
        _profile(
            LlmProviderKind.OPENAI_COMPATIBLE,
            LlmApiFamily.OPENAI_CHAT_COMPATIBLE,
            "gpt-5-compatible",
        ),
        invocation_id="inv-chat-fixture",
        payload={
            "id": "chatcmpl_fixture",
            "model": "gpt-5-compatible",
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": "I will query the API.",
                        "tool_calls": [
                            {
                                "id": "call_chat_1",
                                "type": "function",
                                "function": {
                                    "name": "command_exec",
                                    "arguments": (
                                        '{"cmd":"curl https://example.test"}'
                                    ),
                                },
                            },
                        ],
                    },
                },
            ],
        },
        tool_name_aliases={"command_exec": "command.exec"},
    )
    return response.response_items


def _anthropic_items() -> tuple[LlmResponseItem, ...]:
    response = AnthropicMessagesAdapter._response_from_payload(
        _profile(
            LlmProviderKind.ANTHROPIC,
            LlmApiFamily.ANTHROPIC_MESSAGES,
            "claude-sonnet-4-5",
        ),
        {
            "id": "msg_anthropic_fixture",
            "model": "claude-sonnet-4-5",
            "stop_reason": "tool_use",
            "content": [
                {
                    "type": "text",
                    "text": "I will use a shell command.",
                },
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "command.exec",
                    "input": {"cmd": "curl https://example.test"},
                },
            ],
        },
        invocation_id="inv-anthropic-fixture",
    )
    return response.response_items


def _gemini_items() -> tuple[LlmResponseItem, ...]:
    with patch(
        "crxzipple.modules.llm.infrastructure.adapters.gemini_generate_content.uuid4",
        return_value=UUID("12345678-1234-5678-1234-567812345678"),
    ):
        response = GeminiGenerateContentAdapter._response_from_payload(
            _profile(
                LlmProviderKind.GOOGLE,
                LlmApiFamily.GEMINI_GENERATE_CONTENT,
                "gemini-2.5-pro",
            ),
            {
                "responseId": "gemini_fixture",
                "modelVersion": "gemini-2.5-pro",
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {
                            "parts": [
                                {"text": "I will query the docs."},
                                {
                                    "functionCall": {
                                        "name": "command.exec",
                                        "args": {"cmd": "curl https://example.test"},
                                    },
                                },
                            ],
                        },
                    },
                ],
            },
            invocation_id="inv-gemini-fixture",
        )
    return response.response_items


def _profile(
    provider: LlmProviderKind,
    api_family: LlmApiFamily,
    model_name: str,
) -> LlmProfile:
    return LlmProfile(
        id=f"{provider.value}-fixture",
        provider=provider,
        api_family=api_family,
        model_name=model_name,
    )
