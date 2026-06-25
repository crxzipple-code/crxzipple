from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.modules.llm.application.adapters import LlmAdapterRequest
from crxzipple.modules.llm.domain.entities import LlmProfile
from crxzipple.modules.llm.domain import (
    LlmMessage,
    LlmMessageRole,
)
from crxzipple.modules.llm.infrastructure.adapters.adapter_utils import (
    coerce_text_content,
    default_base_url,
)
from crxzipple.modules.llm.infrastructure.adapters.provider_openai_message_projection import (
    openai_chat_messages,
)
from crxzipple.modules.llm.infrastructure.adapters.http_helpers import join_url
from crxzipple.modules.llm.infrastructure.adapters.provider_request_preview import (
    provider_wire_request_preview,
)
from crxzipple.modules.llm.infrastructure.adapters.provider_protocol import (
    ProviderRenderInput,
)
from crxzipple.modules.llm.infrastructure.adapters.tool_schemas import (
    build_openai_tool_name_aliases,
    openai_chat_tool_schema,
)
from crxzipple.modules.llm.infrastructure.rendering.input_projection import (
    messages_from_projected_input_items,
    provider_context_messages,
)


@dataclass(frozen=True, slots=True)
class OpenAIChatCompatibleRenderedRequest:
    endpoint: str
    payload: dict[str, Any]
    messages: tuple[LlmMessage, ...]
    tool_name_aliases: dict[str, str]

    @property
    def alias_to_original_tool_names(self) -> dict[str, str]:
        return {
            alias: original
            for original, alias in self.tool_name_aliases.items()
        }


@dataclass(frozen=True, slots=True)
class OpenAIChatCompatibleRequestRenderer:
    default_base_url: str = "https://api.openai.com/v1"
    renderer_id: str = "openai_chat_compatible"

    def preview(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
        *,
        stream: bool = False,
    ) -> dict[str, Any]:
        return self.preview_input(
            ProviderRenderInput.from_request(profile=profile, request=request),
            stream=stream,
        )

    def preview_input(
        self,
        render_input: ProviderRenderInput,
        *,
        stream: bool = False,
    ) -> dict[str, Any]:
        profile = render_input.profile
        request = render_input.request
        rendered = self.render_input(render_input, stream=stream)
        return provider_wire_request_preview(
            profile=profile,
            endpoint=rendered.endpoint,
            payload=rendered.payload,
            renderer_id=self.renderer_id,
            transport="sse" if stream else "http",
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
        *,
        stream: bool = False,
    ) -> OpenAIChatCompatibleRenderedRequest:
        return self.render_input(
            ProviderRenderInput.from_request(profile=profile, request=request),
            stream=stream,
        )

    def render_input(
        self,
        render_input: ProviderRenderInput,
        *,
        stream: bool = False,
    ) -> OpenAIChatCompatibleRenderedRequest:
        profile = render_input.profile
        request_messages = messages_from_projected_input_items(render_input.input_items)
        explicit_provider_context = provider_context_messages(render_input)
        normalized_messages = _normalize_message_order(
            (*explicit_provider_context, *request_messages),
        )
        tool_name_aliases = build_openai_tool_name_aliases(render_input.tool_schemas)

        payload: dict[str, Any] = {
            "model": profile.model_name,
            "messages": openai_chat_messages(
                normalized_messages,
                tool_name_aliases=tool_name_aliases,
            ),
        }
        if stream:
            payload["stream"] = True
        if render_input.tool_schemas:
            payload["tools"] = [
                openai_chat_tool_schema(tool, tool_name_aliases=tool_name_aliases)
                for tool in render_input.tool_schemas
            ]
            if render_input.request_policy.get("require_tool_call") is True:
                payload["tool_choice"] = "required"
        if render_input.response_format is not None:
            payload["response_format"] = dict(render_input.response_format)

        defaults = profile.default_params
        if defaults.temperature is not None:
            payload["temperature"] = defaults.temperature
        if defaults.top_p is not None:
            payload["top_p"] = defaults.top_p
        if defaults.max_output_tokens is not None:
            payload["max_tokens"] = defaults.max_output_tokens
        _merge_payload_fields(payload, defaults.extra_body)

        overrides = dict(render_input.provider_options)
        extra_body_overrides = overrides.pop("extra_body", None)
        if isinstance(extra_body_overrides, dict):
            _merge_payload_fields(payload, extra_body_overrides)

        protected_keys = {"model", "messages", "tools"}
        if stream:
            protected_keys.add("stream")
        for key, value in overrides.items():
            if key not in protected_keys:
                payload[key] = value

        return OpenAIChatCompatibleRenderedRequest(
            endpoint=join_url(
                default_base_url(profile, self.default_base_url),
                "/chat/completions",
            ),
            payload=payload,
            messages=normalized_messages,
            tool_name_aliases=tool_name_aliases,
        )


def _merge_payload_fields(
    payload: dict[str, Any],
    fields: dict[str, Any] | None,
) -> None:
    if not fields:
        return
    for key, value in fields.items():
        if key in {"model", "messages", "tools"}:
            continue
        if isinstance(payload.get(key), dict) and isinstance(value, dict):
            merged = dict(payload[key])
            merged.update(value)
            payload[key] = merged
            continue
        payload[key] = value


def _normalize_message_order(
    messages: tuple[LlmMessage, ...],
) -> tuple[LlmMessage, ...]:
    system_messages = tuple(
        message for message in messages if message.role == LlmMessageRole.SYSTEM
    )
    if not system_messages:
        return messages
    non_system_messages = tuple(
        message for message in messages if message.role != LlmMessageRole.SYSTEM
    )
    combined_system = LlmMessage(
        role=LlmMessageRole.SYSTEM,
        content="\n\n".join(
            coerce_text_content(message.content)
            for message in system_messages
        ),
    )
    return (combined_system,) + non_system_messages
