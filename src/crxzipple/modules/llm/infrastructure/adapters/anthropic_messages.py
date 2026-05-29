from __future__ import annotations

from typing import Any

import httpx
import requests

from crxzipple.modules.llm.application.adapters import (
    LlmAdapterRequest,
    LlmAdapterResponse,
)
from crxzipple.modules.llm.domain.entities import LlmProfile
from crxzipple.modules.llm.domain.value_objects import (
    LlmResult,
    LlmUsage,
    ToolCallIntent,
)
from crxzipple.modules.llm.infrastructure.adapters.common import (
    anthropic_messages,
    anthropic_tool_schema,
    coerce_text_content,
    default_base_url,
    ensure_async_json_response,
    ensure_image_input_supported,
    ensure_json_response,
    join_url,
    parse_json_arguments,
    resolve_credential_binding,
)
from crxzipple.shared.infrastructure.http import get_async_http_client


class AnthropicMessagesAdapter:
    DEFAULT_BASE_URL = "https://api.anthropic.com/v1"
    DEFAULT_VERSION = "2023-06-01"

    def invoke(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
    ) -> LlmAdapterResponse:
        url, headers, payload = self._invoke_request(profile, request)
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=profile.timeout_seconds,
        )
        data = ensure_json_response(
            response,
            description=f"Anthropic profile '{profile.id}'",
        )
        return self._response_from_payload(profile, data)

    async def invoke_async(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
    ) -> LlmAdapterResponse:
        url, headers, payload = self._invoke_request(profile, request)
        client = get_async_http_client(
            url,
            timeout=profile.timeout_seconds,
            client_factory=httpx.AsyncClient,
        )
        response = await client.post(
            url,
            headers=headers,
            json=payload,
        )
        data = await ensure_async_json_response(
            response,
            description=f"Anthropic profile '{profile.id}'",
        )
        return self._response_from_payload(profile, data)

    def _invoke_request(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
    ) -> tuple[str, dict[str, str], dict[str, Any]]:
        ensure_image_input_supported(profile, request.messages)
        token = resolve_credential_binding(
            profile.credential_binding_id,
            required=True,
            description=f"LLM profile '{profile.id}'",
            resolved_credential=request.resolved_credential,
        )
        headers = {
            "Content-Type": "application/json",
            "x-api-key": token,
            "anthropic-version": self.DEFAULT_VERSION,
        }

        system_messages = [
            coerce_text_content(message.content)
            for message in request.messages
            if message.role.value == "system"
        ]
        payload: dict[str, Any] = {
            "model": profile.model_name,
            "messages": anthropic_messages(
                tuple(
                    message
                    for message in request.messages
                    if message.role.value != "system"
                ),
            ),
            "max_tokens": request.overrides.get("max_tokens")
            or profile.default_params.max_output_tokens
            or 1024,
        }
        if system_messages:
            payload["system"] = "\n\n".join(system_messages)
        if request.tool_schemas:
            payload["tools"] = [
                anthropic_tool_schema(tool) for tool in request.tool_schemas
            ]
        if profile.default_params.temperature is not None:
            payload["temperature"] = profile.default_params.temperature
        if profile.default_params.top_p is not None:
            payload["top_p"] = profile.default_params.top_p

        for key, value in request.overrides.items():
            if key not in {"model", "messages", "system", "tools"}:
                payload[key] = value

        return (
            join_url(default_base_url(profile, self.DEFAULT_BASE_URL), "/messages"),
            headers,
            payload,
        )

    @staticmethod
    def _response_from_payload(
        profile: LlmProfile,
        data: dict[str, Any],
    ) -> LlmAdapterResponse:
        content = data.get("content")
        if not isinstance(content, list):
            raise RuntimeError(f"Anthropic profile '{profile.id}' returned no content.")

        text_fragments: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and block.get("text") is not None:
                text_fragments.append(str(block.get("text")))
            if block.get("type") == "tool_use":
                tool_calls.append(
                    {
                        "id": block.get("id"),
                        "name": block.get("name"),
                        "input": block.get("input"),
                    },
                )

        usage_raw = data.get("usage")
        usage = None
        if isinstance(usage_raw, dict):
            usage = LlmUsage(
                input_tokens=usage_raw.get("input_tokens"),
                output_tokens=usage_raw.get("output_tokens"),
            )

        return LlmAdapterResponse(
            result=LlmResult(
                text="".join(text_fragments) or None,
                tool_calls=tuple(
                    ToolCallIntent(
                        id=str(item.get("id") or item.get("name") or "tool_call"),
                        name=str(item.get("name") or ""),
                        arguments=parse_json_arguments(item.get("input")),
                    )
                    for item in tool_calls
                    if item.get("name")
                ),
                usage=usage,
                finish_reason=(
                    str(data.get("stop_reason"))
                    if data.get("stop_reason") is not None
                    else None
                ),
                metadata={
                    "provider": profile.provider.value,
                    "response_id": data.get("id"),
                    "model": data.get("model"),
                },
            ),
            provider_request_id=str(data.get("id")) if data.get("id") is not None else None,
        )
