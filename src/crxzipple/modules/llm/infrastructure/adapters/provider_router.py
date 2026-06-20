from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from crxzipple.modules.llm.application.adapters import LlmAdapterRequest
from crxzipple.modules.llm.domain.entities import LlmProfile
from crxzipple.modules.llm.domain.value_objects import LlmApiFamily
from crxzipple.modules.llm.infrastructure.adapters.anthropic_messages import (
    AnthropicMessagesAdapter,
)
from crxzipple.modules.llm.infrastructure.adapters.anthropic_messages_renderer import (
    AnthropicMessagesRenderer,
)
from crxzipple.modules.llm.infrastructure.adapters.gemini_generate_content import (
    GeminiGenerateContentAdapter,
)
from crxzipple.modules.llm.infrastructure.adapters.gemini_generate_content_renderer import (
    GeminiGenerateContentRenderer,
)
from crxzipple.modules.llm.infrastructure.adapters.openai_chat_compatible import (
    OpenAIChatCompatibleAdapter,
)
from crxzipple.modules.llm.infrastructure.adapters.openai_chat_compatible_renderer import (
    OpenAIChatCompatibleRequestRenderer,
)
from crxzipple.modules.llm.infrastructure.adapters.openai_codex_responses import (
    OpenAICodexResponsesAdapter,
)
from crxzipple.modules.llm.infrastructure.adapters.openai_codex_responses_renderer import (
    OpenAICodexResponsesRenderer,
    _websocket_endpoint_from_http,
    requested_provider_transport_input,
)
from crxzipple.modules.llm.infrastructure.adapters.openai_responses import (
    OpenAIResponsesAdapter,
)
from crxzipple.modules.llm.infrastructure.adapters.openai_responses_renderer import (
    OpenAIResponsesRenderer,
)
from crxzipple.modules.llm.infrastructure.adapters.provider_protocol import (
    ProviderRenderInput,
    ProviderRequestPreviewRenderer,
    ProviderWireRequest,
)


@dataclass(frozen=True, slots=True)
class ProviderProtocolRenderRouter:
    openai_responses: OpenAIResponsesRenderer = field(
        default_factory=lambda: OpenAIResponsesRenderer(
            default_base_url=OpenAIResponsesAdapter.DEFAULT_BASE_URL,
        ),
    )
    openai_codex_responses: OpenAICodexResponsesRenderer = field(
        default_factory=lambda: OpenAICodexResponsesRenderer(
            default_base_url=OpenAICodexResponsesAdapter.DEFAULT_BASE_URL,
            default_instructions=OpenAICodexResponsesAdapter.DEFAULT_INSTRUCTIONS,
        ),
    )
    anthropic_messages: AnthropicMessagesRenderer = field(
        default_factory=lambda: AnthropicMessagesRenderer(
            default_base_url=AnthropicMessagesAdapter.DEFAULT_BASE_URL,
        ),
    )
    gemini_generate_content: GeminiGenerateContentRenderer = field(
        default_factory=lambda: GeminiGenerateContentRenderer(
            default_base_url=GeminiGenerateContentAdapter.DEFAULT_BASE_URL,
        ),
    )
    openai_chat_compatible: OpenAIChatCompatibleRequestRenderer = field(
        default_factory=lambda: OpenAIChatCompatibleRequestRenderer(
            default_base_url=OpenAIChatCompatibleAdapter.DEFAULT_BASE_URL,
        ),
    )

    def renderer_for(
        self,
        api_family: LlmApiFamily,
    ) -> ProviderRequestPreviewRenderer:
        if api_family is LlmApiFamily.OPENAI_RESPONSES:
            return self.openai_responses
        if api_family is LlmApiFamily.OPENAI_CODEX_RESPONSES:
            return self.openai_codex_responses
        if api_family is LlmApiFamily.ANTHROPIC_MESSAGES:
            return self.anthropic_messages
        if api_family is LlmApiFamily.GEMINI_GENERATE_CONTENT:
            return self.gemini_generate_content
        if api_family is LlmApiFamily.OPENAI_CHAT_COMPATIBLE:
            return self.openai_chat_compatible
        raise ValueError(f"Unsupported LLM API family for provider rendering: {api_family}")

    def preview(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
    ) -> dict[str, Any]:
        return self.preview_input(
            ProviderRenderInput.from_request(profile=profile, request=request),
        )

    def preview_input(
        self,
        render_input: ProviderRenderInput,
    ) -> dict[str, Any]:
        renderer = self.renderer_for(render_input.profile.api_family)
        preview_input = getattr(renderer, "preview_input", None)
        if callable(preview_input):
            return preview_input(render_input)
        return renderer.preview(render_input.profile, render_input.request)

    def render_request(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
    ) -> ProviderWireRequest:
        return self.render_input(
            ProviderRenderInput.from_request(profile=profile, request=request),
        )

    def render_input(
        self,
        render_input: ProviderRenderInput,
    ) -> ProviderWireRequest:
        profile = render_input.profile
        request = render_input.request
        renderer = self.renderer_for(profile.api_family)
        if renderer is self.openai_codex_responses:
            rendered_http = self.openai_codex_responses.render_http_input(render_input)
            if requested_provider_transport_input(render_input) == "websocket":
                rendered = self.openai_codex_responses.render_websocket_create_input(
                    render_input,
                    endpoint=_websocket_endpoint_from_http(rendered_http.endpoint),
                )
            else:
                rendered = rendered_http
        else:
            render_input_fn = getattr(renderer, "render_input", None)
            if callable(render_input_fn):
                rendered = render_input_fn(render_input)
            else:
                rendered = renderer.render(profile, request)  # type: ignore[attr-defined]
        return ProviderWireRequest.from_rendered(
            renderer_id=renderer.renderer_id,
            rendered=rendered,
            preview=self.preview_input(render_input),
        )


__all__ = ["ProviderProtocolRenderRouter"]
