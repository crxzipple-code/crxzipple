from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.modules.llm.application.adapters import LlmAdapterRequest
from crxzipple.modules.llm.domain.entities import LlmProfile
from crxzipple.modules.llm.domain.value_objects import LlmInputItemKind
from crxzipple.modules.llm.infrastructure.adapters.adapter_utils import (
    coerce_text_content,
    default_base_url,
)
from crxzipple.modules.llm.infrastructure.adapters.provider_message_projection import (
    anthropic_messages,
)
from crxzipple.modules.llm.infrastructure.adapters.http_helpers import join_url
from crxzipple.modules.llm.infrastructure.adapters.provider_request_preview import (
    provider_wire_request_preview,
)
from crxzipple.modules.llm.infrastructure.adapters.provider_protocol import (
    ProviderRenderInput,
)
from crxzipple.modules.llm.infrastructure.adapters.tool_schemas import (
    anthropic_tool_schema,
)
from crxzipple.modules.llm.infrastructure.rendering.input_projection import (
    messages_from_projected_input_items,
    provider_context_messages,
)


@dataclass(frozen=True, slots=True)
class AnthropicMessagesRenderedRequest:
    endpoint: str
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AnthropicMessagesRenderer:
    default_base_url: str
    renderer_id: str = "anthropic_messages"

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
        profile = render_input.profile
        request = render_input.request
        rendered = self.render_input(render_input)
        return provider_wire_request_preview(
            profile=profile,
            endpoint=rendered.endpoint,
            payload=rendered.payload,
            renderer_id=self.renderer_id,
            loss_report=_loss_report(render_input),
            request_metadata=request.request_metadata,
            runtime_context=request.runtime_context,
            runtime_route=request.runtime_route,
            runtime_policy=request.runtime_policy,
            canonical_input_items=render_input.input_items,
        )

    def render(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
    ) -> AnthropicMessagesRenderedRequest:
        return self.render_input(
            ProviderRenderInput.from_request(profile=profile, request=request),
        )

    def render_input(
        self,
        render_input: ProviderRenderInput,
    ) -> AnthropicMessagesRenderedRequest:
        profile = render_input.profile
        request_messages = messages_from_projected_input_items(render_input.input_items)
        explicit_provider_context = provider_context_messages(render_input)
        system_messages = [
            coerce_text_content(message.content)
            for message in (*explicit_provider_context, *request_messages)
            if message.role.value == "system"
        ]
        payload: dict[str, Any] = {
            "model": profile.model_name,
            "messages": anthropic_messages(
                tuple(
                    message
                    for message in request_messages
                    if message.role.value != "system"
                ),
            ),
            "max_tokens": render_input.provider_options.get("max_tokens")
            or profile.default_params.max_output_tokens
            or 1024,
        }
        if system_messages:
            payload["system"] = "\n\n".join(system_messages)
        if render_input.tool_schemas:
            payload["tools"] = [
                anthropic_tool_schema(tool) for tool in render_input.tool_schemas
            ]
            if render_input.request_policy.get("require_tool_call") is True:
                payload["tool_choice"] = {"type": "any"}
        if profile.default_params.temperature is not None:
            payload["temperature"] = profile.default_params.temperature
        if profile.default_params.top_p is not None:
            payload["top_p"] = profile.default_params.top_p

        for key, value in render_input.provider_options.items():
            if key not in {"model", "messages", "system", "tools"}:
                payload[key] = value

        return AnthropicMessagesRenderedRequest(
            endpoint=join_url(default_base_url(profile, self.default_base_url), "/messages"),
            payload=payload,
        )


def _loss_report(render_input: ProviderRenderInput) -> dict[str, Any]:
    reasoning_count = sum(
        1
        for item in render_input.input_items
        if item.kind is LlmInputItemKind.REASONING
    )
    if reasoning_count <= 0:
        return {}
    return {
        "reasoning": {
            "input_item_count": reasoning_count,
            "strategy": "assistant_text_downgrade",
        },
    }
