from __future__ import annotations

import pytest

from crxzipple.modules.llm.application.adapters import LlmAdapterRequest as _LlmAdapterRequest
from crxzipple.modules.llm.domain.entities import LlmProfile
from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmProviderContinuation,
    LlmMessage,
    LlmMessageRole,
    LlmModelFamily,
    LlmProviderKind,
)
from crxzipple.modules.llm.infrastructure.adapters.provider_message_common import (
    projected_input_items_from_messages,
)
from crxzipple.modules.llm.infrastructure.adapters.provider_router import (
    ProviderProtocolRenderRouter,
)
from crxzipple.modules.llm.infrastructure.adapters.provider_protocol import (
    ProviderRenderInput,
)


def _request(*, provider_transport: str = "auto") -> _LlmAdapterRequest:
    messages = (LlmMessage(role=LlmMessageRole.USER, content="hello"),)
    return _LlmAdapterRequest(
        invocation_id="inv-router",
        messages=messages,
        input_items=tuple(projected_input_items_from_messages(messages)),
        provider_transport=provider_transport,
        resolved_credential="token",
    )


def _profile(
    *,
    api_family: LlmApiFamily,
    provider: LlmProviderKind,
    model_name: str = "model-1",
) -> LlmProfile:
    return LlmProfile(
        id=f"profile-{api_family.value}",
        provider=provider,
        api_family=api_family,
        model_name=model_name,
        model_family=LlmModelFamily.GENERAL,
    )


@pytest.mark.parametrize(
    ("api_family", "provider", "renderer_id"),
    (
        (
            LlmApiFamily.OPENAI_RESPONSES,
            LlmProviderKind.OPENAI,
            "openai_responses",
        ),
        (
            LlmApiFamily.OPENAI_CODEX_RESPONSES,
            LlmProviderKind.OPENAI_CODEX,
            "openai_codex_responses",
        ),
        (
            LlmApiFamily.ANTHROPIC_MESSAGES,
            LlmProviderKind.ANTHROPIC,
            "anthropic_messages",
        ),
        (
            LlmApiFamily.GEMINI_GENERATE_CONTENT,
            LlmProviderKind.GOOGLE,
            "gemini_generate_content",
        ),
        (
            LlmApiFamily.OPENAI_CHAT_COMPATIBLE,
            LlmProviderKind.OPENAI_COMPATIBLE,
            "openai_chat_compatible",
        ),
    ),
)
def test_provider_protocol_render_router_selects_renderer_by_api_family(
    api_family: LlmApiFamily,
    provider: LlmProviderKind,
    renderer_id: str,
) -> None:
    router = ProviderProtocolRenderRouter()
    profile = _profile(api_family=api_family, provider=provider)

    renderer = router.renderer_for(api_family)
    preview = router.preview(profile, _request())

    assert renderer.renderer_id == renderer_id
    assert preview["preview_source"] == "provider_adapter"
    assert preview["renderer_id"] == renderer_id
    assert preview["render_report"]["renderer_id"] == renderer_id


def test_provider_protocol_render_router_preserves_codex_transport_choice() -> None:
    router = ProviderProtocolRenderRouter()
    profile = _profile(
        api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
        provider=LlmProviderKind.OPENAI_CODEX,
        model_name="gpt-5.5",
    )

    preview = router.preview(profile, _request(provider_transport="websocket"))

    assert preview["renderer_id"] == "openai_codex_responses"
    assert preview["transport"] == "websocket"
    assert preview["message_type"] == "response.create"


def test_provider_protocol_render_router_returns_provider_wire_request() -> None:
    router = ProviderProtocolRenderRouter()
    profile = _profile(
        api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
        provider=LlmProviderKind.OPENAI_CODEX,
        model_name="gpt-5.5",
    )

    wire_request = router.render_request(
        profile,
        _request(provider_transport="websocket"),
    )

    assert wire_request.renderer_id == "openai_codex_responses"
    assert wire_request.transport == "websocket"
    assert wire_request.endpoint.startswith("wss://")
    assert wire_request.payload["type"] == "response.create"
    assert wire_request.payload["model"] == "gpt-5.5"
    assert wire_request.render_report["renderer_id"] == "openai_codex_responses"


def test_provider_protocol_render_router_accepts_formal_render_input() -> None:
    router = ProviderProtocolRenderRouter()
    profile = _profile(
        api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
        provider=LlmProviderKind.OPENAI_CODEX,
        model_name="gpt-5.5",
    )
    request = _request(provider_transport="websocket")
    request = _LlmAdapterRequest(
        invocation_id=request.invocation_id,
        messages=request.messages,
        input_items=request.input_items,
        tool_schemas=(),
        request_policy={"parallel_tool_calls": False},
        overrides={"provider_transport": "websocket"},
        response_format={"type": "json_object"},
        runtime_context={
            "request_context_source": "context_slice",
            "context_slice_id": "ctxslice-router",
        },
        runtime_route={
            "llm_id": profile.id,
            "provider_transport": "websocket",
        },
        runtime_policy={
            "provider_option_keys": ["provider_transport"],
        },
        provider_transport=request.provider_transport,
        continuation=LlmProviderContinuation(
            mode="provider_native",
            previous_response_id="resp-router",
        ),
        resolved_credential=request.resolved_credential,
    )
    render_input = ProviderRenderInput.from_request(
        profile=profile,
        request=request,
    )

    preview = router.preview_input(render_input)
    wire_request = router.render_input(render_input)

    assert render_input.runtime_context == {
        "request_context_source": "context_slice",
        "context_slice_id": "ctxslice-router",
    }
    assert render_input.runtime_route == {
        "llm_id": profile.id,
        "provider_transport": "websocket",
    }
    assert render_input.runtime_policy == {
        "provider_option_keys": ["provider_transport"],
    }
    assert render_input.input_items == request.input_items
    assert render_input.request_policy == {"parallel_tool_calls": False}
    assert render_input.provider_options == {"provider_transport": "websocket"}
    assert render_input.response_format == {"type": "json_object"}
    assert render_input.provider_transport == "websocket"
    assert render_input.continuation is not None
    assert render_input.continuation.previous_response_id == "resp-router"
    assert preview["context_slice_id"] == "ctxslice-router"
    assert preview["runtime_route"]["provider_transport"] == "websocket"
    assert preview["runtime_policy"]["provider_option_keys"] == [
        "provider_transport",
    ]
    assert wire_request.transport == "websocket"
    assert wire_request.render_report["renderer_id"] == "openai_codex_responses"


@pytest.mark.parametrize(
    ("api_family", "provider", "renderer_id"),
    (
        (
            LlmApiFamily.OPENAI_RESPONSES,
            LlmProviderKind.OPENAI,
            "openai_responses",
        ),
        (
            LlmApiFamily.ANTHROPIC_MESSAGES,
            LlmProviderKind.ANTHROPIC,
            "anthropic_messages",
        ),
        (
            LlmApiFamily.GEMINI_GENERATE_CONTENT,
            LlmProviderKind.GOOGLE,
            "gemini_generate_content",
        ),
        (
            LlmApiFamily.OPENAI_CHAT_COMPATIBLE,
            LlmProviderKind.OPENAI_COMPATIBLE,
            "openai_chat_compatible",
        ),
    ),
)
def test_provider_protocol_render_router_returns_wire_request_for_all_renderers(
    api_family: LlmApiFamily,
    provider: LlmProviderKind,
    renderer_id: str,
) -> None:
    router = ProviderProtocolRenderRouter()
    profile = _profile(api_family=api_family, provider=provider)

    wire_request = router.render_request(profile, _request())

    assert wire_request.renderer_id == renderer_id
    assert wire_request.endpoint.startswith("http")
    assert wire_request.payload
    assert wire_request.render_report["renderer_id"] == renderer_id


def test_provider_protocol_render_router_rejects_unsupported_api_family() -> None:
    router = ProviderProtocolRenderRouter()

    with pytest.raises(ValueError, match="Unsupported LLM API family"):
        router.renderer_for(LlmApiFamily.OLLAMA_NATIVE)
