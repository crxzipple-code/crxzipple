from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.modules.llm.application.adapters import LlmAdapterRequest
from crxzipple.modules.llm.domain.entities import LlmProfile
from crxzipple.modules.llm.domain import (
    LlmMessageRole,
    LlmProviderContinuation,
)
from crxzipple.modules.llm.infrastructure.adapters.adapter_utils import (
    coerce_text_content,
    default_base_url,
)
from crxzipple.modules.llm.infrastructure.adapters.provider_openai_message_projection import (
    openai_response_projected_input_items,
)
from crxzipple.modules.llm.infrastructure.adapters.http_helpers import join_url
from crxzipple.modules.llm.infrastructure.adapters.provider_request_preview import (
    openai_provider_request_preview,
)
from crxzipple.modules.llm.infrastructure.adapters.provider_protocol import (
    ProviderRenderInput,
)
from crxzipple.modules.llm.infrastructure.adapters.tool_schemas import (
    build_openai_tool_name_aliases,
    openai_tool_schema,
)
from crxzipple.modules.llm.infrastructure.rendering.input_projection import (
    messages_from_projected_input_items,
    provider_context_messages,
)


@dataclass(frozen=True, slots=True)
class OpenAIResponsesRenderedRequest:
    endpoint: str
    payload: dict[str, Any]
    tool_name_aliases: dict[str, str]


@dataclass(frozen=True, slots=True)
class OpenAIResponsesRenderer:
    default_base_url: str
    renderer_id: str = "openai_responses"

    def render(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
    ) -> OpenAIResponsesRenderedRequest:
        return self.render_input(
            ProviderRenderInput.from_request(profile=profile, request=request),
        )

    def render_input(
        self,
        render_input: ProviderRenderInput,
    ) -> OpenAIResponsesRenderedRequest:
        profile = render_input.profile
        tool_name_aliases = build_openai_tool_name_aliases(render_input.tool_schemas)
        return OpenAIResponsesRenderedRequest(
            endpoint=join_url(default_base_url(profile, self.default_base_url), "/responses"),
            payload=self.build_payload_input(
                render_input,
                tool_name_aliases=tool_name_aliases,
            ),
            tool_name_aliases=tool_name_aliases,
        )

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
        return openai_provider_request_preview(
            profile=profile,
            endpoint=rendered.endpoint,
            payload=rendered.payload,
            renderer_id=self.renderer_id,
            request_metadata=request.request_metadata,
            runtime_context=request.runtime_context,
            runtime_route=request.runtime_route,
            runtime_policy=request.runtime_policy,
            canonical_input_items=render_input.input_items,
        )

    def build_payload(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
        *,
        render_input: ProviderRenderInput | None = None,
        tool_name_aliases: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return self.build_payload_input(
            render_input
            or ProviderRenderInput.from_request(
                profile=profile,
                request=request,
            ),
            tool_name_aliases=tool_name_aliases,
        )

    def build_payload_input(
        self,
        render_input: ProviderRenderInput,
        *,
        tool_name_aliases: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        model_input = render_input
        profile = render_input.profile
        payload: dict[str, Any] = {
            "model": profile.model_name,
            "input": openai_response_request_input_items(
                model_input,
                tool_name_aliases=tool_name_aliases,
            ),
        }
        instructions = resolve_openai_responses_instructions(model_input)
        if instructions:
            payload["instructions"] = instructions
        apply_provider_continuation_input(payload, model_input)
        if model_input.tool_schemas:
            payload["tools"] = [
                openai_tool_schema(tool, tool_name_aliases=tool_name_aliases)
                for tool in model_input.tool_schemas
            ]
            if model_input.request_policy.get("require_tool_call") is True:
                payload["tool_choice"] = "required"
        if model_input.response_format is not None:
            payload["text"] = {"format": dict(model_input.response_format)}

        defaults = profile.default_params
        if defaults.temperature is not None:
            payload["temperature"] = defaults.temperature
        if defaults.top_p is not None:
            payload["top_p"] = defaults.top_p
        if defaults.max_output_tokens is not None:
            payload["max_output_tokens"] = defaults.max_output_tokens
        reasoning = merged_reasoning_payload(
            defaults_reasoning_effort=defaults.reasoning_effort,
            override_reasoning=model_input.provider_options.get("reasoning"),
        )
        if reasoning:
            payload["reasoning"] = reasoning

        for key, value in model_input.provider_options.items():
            if key not in {
                "model",
                "input",
                "tools",
                "reasoning",
                "provider_transport",
            }:
                payload[key] = value

        payload["stream"] = True
        return payload


def merged_reasoning_payload(
    *,
    defaults_reasoning_effort: str | None,
    override_reasoning: object,
) -> dict[str, Any]:
    reasoning: dict[str, Any] = {}
    if defaults_reasoning_effort is not None:
        reasoning["effort"] = defaults_reasoning_effort
    if isinstance(override_reasoning, dict):
        reasoning.update(override_reasoning)
    return reasoning


def resolve_openai_responses_instructions(
    render_input: ProviderRenderInput,
) -> str | None:
    explicit_provider_context = provider_context_messages(render_input)
    request_messages = messages_from_projected_input_items(render_input.input_items)
    system_messages = [
        coerce_text_content(message.content)
        for message in (*explicit_provider_context, *request_messages)
        if message.role == LlmMessageRole.SYSTEM
    ]
    if not system_messages:
        return None
    return "\n\n".join(system_messages)


def apply_provider_continuation_input(
    payload: dict[str, Any],
    render_input: ProviderRenderInput,
) -> None:
    _apply_provider_continuation(payload, render_input.continuation)


def _apply_provider_continuation(
    payload: dict[str, Any],
    continuation: LlmProviderContinuation | None,
) -> None:
    if continuation is None:
        return
    if continuation.mode != "provider_native":
        return
    if continuation.previous_response_id is None:
        return
    payload["previous_response_id"] = continuation.previous_response_id


def uses_provider_native_continuation_input(
    render_input: ProviderRenderInput,
) -> bool:
    return _uses_provider_native_continuation(render_input.continuation)


def _uses_provider_native_continuation(
    continuation: LlmProviderContinuation | None,
) -> bool:
    return (
        continuation is not None
        and continuation.mode == "provider_native"
        and continuation.previous_response_id is not None
    )


def openai_response_request_input_items(
    render_input: ProviderRenderInput,
    *,
    tool_name_aliases: dict[str, str] | None,
) -> list[dict[str, Any]]:
    return openai_response_projected_input_items(
        render_input.input_items,
        tool_name_aliases=tool_name_aliases,
        continuation_delta_only=uses_provider_native_continuation_input(render_input),
    )
