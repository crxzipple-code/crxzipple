from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.modules.llm.application.adapters import LlmAdapterRequest
from crxzipple.modules.llm.domain.entities import LlmProfile
from crxzipple.modules.llm.domain import (
    LlmMessageRole,
)
from crxzipple.modules.llm.infrastructure.adapters.adapter_utils import (
    coerce_text_content,
    default_base_url,
)
from crxzipple.modules.llm.infrastructure.adapters.provider_openai_message_projection import (
    openai_response_projected_input_items,
)
from crxzipple.modules.llm.infrastructure.adapters.provider_request_preview import (
    openai_provider_payload_fingerprint,
    openai_provider_request_preview,
    openai_response_input_fingerprints,
)
from crxzipple.modules.llm.infrastructure.adapters.http_helpers import join_url
from crxzipple.modules.llm.infrastructure.adapters.openai_codex_continuation import (
    requested_provider_transport_input,
    uses_provider_native_continuation_input,
    websocket_continuation_delta_items_input,
    websocket_response_create_payload_input,
)
from crxzipple.modules.llm.infrastructure.adapters.openai_codex_runtime_context import (
    runtime_context_input_item,
)
from crxzipple.modules.llm.infrastructure.adapters.openai_codex_websocket_transport import (
    codex_websocket_endpoint,
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
class OpenAICodexRenderedRequest:
    endpoint: str
    payload: dict[str, Any]
    tool_name_aliases: dict[str, str]
    full_input_items: list[dict[str, Any]]
    transport: str


@dataclass(frozen=True, slots=True)
class OpenAICodexResponsesRenderer:
    default_base_url: str
    default_instructions: str
    renderer_id: str = "openai_codex_responses"

    def render_http(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
    ) -> OpenAICodexRenderedRequest:
        return self.render_http_input(
            ProviderRenderInput.from_request(profile=profile, request=request),
        )

    def render_http_input(
        self,
        render_input: ProviderRenderInput,
    ) -> OpenAICodexRenderedRequest:
        profile = render_input.profile
        tool_name_aliases = build_openai_tool_name_aliases(render_input.tool_schemas)
        full_input_items = self.build_full_input_items_input(
            render_input=render_input,
            tool_name_aliases=tool_name_aliases,
        )
        payload = self.build_payload_input(
            render_input,
            tool_name_aliases=tool_name_aliases,
            full_input_items=full_input_items,
        )
        return OpenAICodexRenderedRequest(
            endpoint=join_url(default_base_url(profile, self.default_base_url), "/responses"),
            payload=payload,
            tool_name_aliases=tool_name_aliases,
            full_input_items=full_input_items,
            transport="http",
        )

    def render_websocket_create(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
        *,
        endpoint: str,
    ) -> OpenAICodexRenderedRequest:
        return self.render_websocket_create_input(
            ProviderRenderInput.from_request(profile=profile, request=request),
            endpoint=endpoint,
        )

    def render_websocket_create_input(
        self,
        render_input: ProviderRenderInput,
        *,
        endpoint: str,
    ) -> OpenAICodexRenderedRequest:
        rendered = self.render_http_input(render_input)
        return OpenAICodexRenderedRequest(
            endpoint=endpoint,
            payload=websocket_response_create_payload_input(
                rendered.payload,
                render_input,
            ),
            tool_name_aliases=rendered.tool_name_aliases,
            full_input_items=rendered.full_input_items,
            transport="websocket",
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
        rendered = self.render_http_input(render_input)
        if requested_provider_transport_input(render_input) == "websocket":
            endpoint = codex_websocket_endpoint(rendered.endpoint)
            websocket_rendered = self.render_websocket_create_input(
                render_input,
                endpoint=endpoint,
            )
            return openai_provider_request_preview(
                profile=profile,
                endpoint=endpoint,
                payload=websocket_rendered.payload,
                renderer_id=self.renderer_id,
                transport="websocket",
                message_type="response.create",
                input_delta_mode=bool(
                    websocket_rendered.payload.get("previous_response_id"),
                ),
                input_baseline_count=len(websocket_rendered.full_input_items),
                input_baseline_fingerprints=openai_response_input_fingerprints(
                    websocket_rendered.full_input_items,
                ),
                request_metadata=request.request_metadata,
                runtime_context=request.runtime_context,
                runtime_route=request.runtime_route,
                runtime_policy=request.runtime_policy,
                canonical_input_items=render_input.input_items,
            )
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
        full_input_items: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return self.build_payload_input(
            render_input
            or ProviderRenderInput.from_request(
                profile=profile,
                request=request,
            ),
            tool_name_aliases=tool_name_aliases,
            full_input_items=full_input_items,
        )

    def build_payload_input(
        self,
        render_input: ProviderRenderInput,
        *,
        tool_name_aliases: dict[str, str] | None = None,
        full_input_items: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        model_input = render_input
        profile = render_input.profile
        full_items = (
            list(full_input_items)
            if full_input_items is not None
            else self.build_full_input_items_input(
                render_input=model_input,
                tool_name_aliases=tool_name_aliases,
            )
        )
        instructions = self.resolve_instructions_input(model_input)
        tool_payloads = [
            openai_tool_schema(tool, tool_name_aliases=tool_name_aliases)
            for tool in model_input.tool_schemas
        ]
        delta_input_items = websocket_continuation_delta_items_input(
            model_input,
            full_items,
            instructions_fingerprint=openai_provider_payload_fingerprint(instructions),
            tool_fingerprints=tuple(
                openai_provider_payload_fingerprint(tool) for tool in tool_payloads
            ),
        )
        input_items = (
            delta_input_items
            if delta_input_items is not None
            else full_items
        )
        runtime_context_item = runtime_context_input_item(model_input.runtime_context)
        if runtime_context_item is not None:
            input_items = [*input_items, runtime_context_item]
        if not input_items and delta_input_items is None:
            raise RuntimeError(
                "OpenAI Codex invocations require at least one non-system message.",
            )
        parallel_tool_calls = model_input.request_policy.get(
            "parallel_tool_calls",
            True,
        )
        if not isinstance(parallel_tool_calls, bool):
            parallel_tool_calls = True
        include = model_input.provider_options.get("include")
        if not isinstance(include, list):
            include = []
        payload: dict[str, Any] = {
            "model": profile.model_name,
            "instructions": instructions,
            "input": input_items,
            "tools": tool_payloads,
            "tool_choice": (
                "required"
                if model_input.request_policy.get("require_tool_call") is True
                else "auto"
            ),
            "parallel_tool_calls": parallel_tool_calls,
            "store": False,
            "stream": True,
            "include": include,
        }
        if delta_input_items is not None:
            payload["_crxzipple_input_delta_mode"] = True
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
                "stream",
                "reasoning",
                "provider_transport",
                "include",
            }:
                payload[key] = value
        return payload

    def resolve_instructions_input(self, render_input: ProviderRenderInput) -> str:
        explicit_provider_context = provider_context_messages(render_input)
        request_messages = messages_from_projected_input_items(render_input.input_items)
        system_messages = [
            coerce_text_content(message.content)
            for message in (*explicit_provider_context, *request_messages)
            if message.role == LlmMessageRole.SYSTEM
        ]
        if system_messages:
            return "\n\n".join(system_messages)
        return self.default_instructions

    def build_input_items_input(
        self,
        *,
        render_input: ProviderRenderInput,
        tool_name_aliases: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        full_items = self.build_full_input_items_input(
            render_input=render_input,
            tool_name_aliases=tool_name_aliases,
        )
        items = websocket_continuation_delta_items_input(
            render_input,
            full_items,
            instructions_fingerprint=openai_provider_payload_fingerprint(
                self.resolve_instructions_input(render_input),
            ),
            tool_fingerprints=tuple(
                openai_provider_payload_fingerprint(
                    openai_tool_schema(
                        tool,
                        tool_name_aliases=tool_name_aliases,
                    ),
                )
                for tool in render_input.tool_schemas
            ),
        )
        if items is None:
            items = full_items
        if not items and not uses_provider_native_continuation_input(render_input):
            raise RuntimeError(
                "OpenAI Codex invocations require at least one non-system message.",
            )
        return items

    def build_full_input_items_input(
        self,
        *,
        render_input: ProviderRenderInput,
        tool_name_aliases: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        return openai_response_projected_input_items(
            render_input.input_items,
            tool_name_aliases=tool_name_aliases,
        )


def merged_reasoning_payload(
    *,
    defaults_reasoning_effort: str | None,
    override_reasoning: object,
) -> dict[str, Any]:
    reasoning: dict[str, Any] = {}
    if defaults_reasoning_effort:
        reasoning["effort"] = defaults_reasoning_effort
    if isinstance(override_reasoning, dict):
        reasoning.update(override_reasoning)
    return reasoning
