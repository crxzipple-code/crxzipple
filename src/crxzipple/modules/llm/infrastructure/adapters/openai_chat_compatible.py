from __future__ import annotations

from typing import Any

import requests

from crxzipple.modules.llm.application.adapters import (
    LlmAdapterRequest,
    LlmAdapterResponse,
)
from crxzipple.modules.llm.domain.entities import LlmProfile
from crxzipple.modules.llm.domain.value_objects import LlmResult, LlmUsage
from crxzipple.modules.llm.infrastructure.adapters.common import (
    build_openai_tool_name_aliases,
    build_tool_call_intents,
    default_base_url,
    ensure_image_input_supported,
    ensure_json_response,
    join_url,
    openai_chat_messages,
    openai_tool_schema,
    resolve_credential_binding,
)


class OpenAIChatCompatibleAdapter:
    DEFAULT_BASE_URL = "https://api.openai.com/v1"

    def invoke(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
    ) -> LlmAdapterResponse:
        ensure_image_input_supported(profile, request.messages)
        tool_name_aliases = build_openai_tool_name_aliases(request.tool_schemas)
        alias_to_original = {
            alias: original
            for original, alias in tool_name_aliases.items()
        }
        token = resolve_credential_binding(
            profile.credential_binding,
            required=profile.provider.value == "openai_compatible",
            description=f"LLM profile '{profile.id}'",
        )
        headers = {"Content-Type": "application/json"}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"

        payload: dict[str, Any] = {
            "model": profile.model_name,
            "messages": openai_chat_messages(
                request.messages,
                tool_name_aliases=tool_name_aliases,
            ),
        }
        if request.tool_schemas:
            payload["tools"] = [
                openai_tool_schema(tool, tool_name_aliases=tool_name_aliases)
                for tool in request.tool_schemas
            ]
        if request.response_format is not None:
            payload["response_format"] = dict(request.response_format)

        defaults = profile.default_params
        if defaults.temperature is not None:
            payload["temperature"] = defaults.temperature
        if defaults.top_p is not None:
            payload["top_p"] = defaults.top_p
        if defaults.max_output_tokens is not None:
            payload["max_tokens"] = defaults.max_output_tokens

        for key, value in request.overrides.items():
            if key not in {"model", "messages", "tools"}:
                payload[key] = value

        response = requests.post(
            join_url(
                default_base_url(profile, self.DEFAULT_BASE_URL),
                "/chat/completions",
            ),
            headers=headers,
            json=payload,
            timeout=profile.timeout_seconds,
        )
        data = ensure_json_response(
            response,
            description=f"OpenAI-compatible profile '{profile.id}'",
        )

        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise RuntimeError(
                f"OpenAI-compatible profile '{profile.id}' returned no choices.",
            )
        choice = choices[0]
        if not isinstance(choice, dict):
            raise RuntimeError(
                f"OpenAI-compatible profile '{profile.id}' returned an invalid choice payload.",
            )
        message = choice.get("message")
        if not isinstance(message, dict):
            raise RuntimeError(
                f"OpenAI-compatible profile '{profile.id}' returned no message payload.",
            )

        raw_tool_calls: list[dict[str, Any]] = []
        tool_calls = message.get("tool_calls")
        if isinstance(tool_calls, list):
            for item in tool_calls:
                if not isinstance(item, dict):
                    continue
                function_payload = item.get("function")
                raw_tool_calls.append(
                    {
                        "id": item.get("id"),
                        "name": (
                            function_payload.get("name")
                            if isinstance(function_payload, dict)
                            else None
                        ),
                        "arguments": (
                            function_payload.get("arguments")
                            if isinstance(function_payload, dict)
                            else None
                        ),
                    },
                )

        usage_raw = data.get("usage")
        usage = None
        if isinstance(usage_raw, dict):
            usage = LlmUsage(
                input_tokens=usage_raw.get("prompt_tokens"),
                output_tokens=usage_raw.get("completion_tokens"),
                total_tokens=usage_raw.get("total_tokens"),
            )

        return LlmAdapterResponse(
            result=LlmResult(
                text=(
                    str(message.get("content"))
                    if message.get("content") is not None
                    else None
                ),
                tool_calls=build_tool_call_intents(
                    raw_tool_calls,
                    tool_name_aliases=alias_to_original,
                ),
                usage=usage,
                finish_reason=(
                    str(choice.get("finish_reason"))
                    if choice.get("finish_reason") is not None
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
