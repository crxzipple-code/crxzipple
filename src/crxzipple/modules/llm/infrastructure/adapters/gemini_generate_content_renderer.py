from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.modules.llm.application.adapters import LlmAdapterRequest
from crxzipple.modules.llm.domain.entities import LlmProfile
from crxzipple.modules.llm.infrastructure.adapters.adapter_utils import (
    default_base_url,
)
from crxzipple.modules.llm.infrastructure.adapters.provider_gemini_message_projection import (
    gemini_contents,
)
from crxzipple.modules.llm.infrastructure.adapters.http_helpers import join_url
from crxzipple.modules.llm.infrastructure.adapters.provider_request_preview import (
    provider_wire_request_preview,
)
from crxzipple.modules.llm.infrastructure.adapters.provider_protocol import (
    ProviderRenderInput,
)
from crxzipple.modules.llm.infrastructure.adapters.tool_schemas import (
    gemini_tool_schema,
)
from crxzipple.modules.llm.infrastructure.rendering.input_projection import (
    messages_from_projected_input_items,
    provider_context_messages,
)


@dataclass(frozen=True, slots=True)
class GeminiGenerateContentRenderedRequest:
    endpoint: str
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class GeminiGenerateContentRenderer:
    default_base_url: str
    renderer_id: str = "gemini_generate_content"

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
    ) -> GeminiGenerateContentRenderedRequest:
        return self.render_input(
            ProviderRenderInput.from_request(profile=profile, request=request),
        )

    def render_input(
        self,
        render_input: ProviderRenderInput,
    ) -> GeminiGenerateContentRenderedRequest:
        profile = render_input.profile
        request_messages = messages_from_projected_input_items(render_input.input_items)
        explicit_provider_context = provider_context_messages(render_input)
        contents, system_parts = gemini_contents(
            (*explicit_provider_context, *request_messages),
        )
        payload: dict[str, Any] = {"contents": list(contents)}
        if system_parts:
            payload["system_instruction"] = {
                "parts": [{"text": "\n\n".join(system_parts)}],
            }

        generation_config: dict[str, Any] = {}
        if profile.default_params.temperature is not None:
            generation_config["temperature"] = profile.default_params.temperature
        if profile.default_params.top_p is not None:
            generation_config["topP"] = profile.default_params.top_p
        if profile.default_params.max_output_tokens is not None:
            generation_config["maxOutputTokens"] = profile.default_params.max_output_tokens
        if isinstance(render_input.provider_options.get("generationConfig"), dict):
            generation_config.update(dict(render_input.provider_options["generationConfig"]))
        if generation_config:
            payload["generationConfig"] = generation_config

        if render_input.tool_schemas:
            payload["tools"] = [
                {
                    "functionDeclarations": [
                        gemini_tool_schema(tool) for tool in render_input.tool_schemas
                    ],
                },
            ]
            if render_input.request_policy.get("require_tool_call") is True:
                payload["toolConfig"] = {
                    "functionCallingConfig": {
                        "mode": "ANY",
                    },
                }
        if isinstance(render_input.provider_options.get("toolConfig"), dict):
            payload["toolConfig"] = dict(render_input.provider_options["toolConfig"])

        for key, value in render_input.provider_options.items():
            if key not in {
                "contents",
                "system_instruction",
                "tools",
                "toolConfig",
                "generationConfig",
            }:
                payload[key] = value

        return GeminiGenerateContentRenderedRequest(
            endpoint=join_url(
                default_base_url(profile, self.default_base_url),
                f"/models/{profile.model_name}:generateContent",
            ),
            payload=payload,
        )
