from __future__ import annotations

from typing import Any
from uuid import uuid4

import httpx
import requests

from crxzipple.modules.llm.application.adapters import (
    LlmAdapterRequest,
    LlmAdapterResponse,
)
from crxzipple.modules.llm.domain.entities import LlmProfile
from crxzipple.modules.llm.domain.value_objects import LlmResult, LlmUsage, ToolCallIntent
from crxzipple.modules.llm.infrastructure.adapters.common import (
    default_base_url,
    ensure_async_json_response,
    ensure_image_input_supported,
    ensure_json_response,
    gemini_contents,
    gemini_tool_schema,
    join_url,
    resolve_credential_binding,
)
from crxzipple.shared.infrastructure.http import get_async_http_client


class GeminiGenerateContentAdapter:
    DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

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
            description=f"Gemini profile '{profile.id}'",
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
            description=f"Gemini profile '{profile.id}'",
        )
        return self._response_from_payload(profile, data)

    def _invoke_request(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
    ) -> tuple[str, dict[str, str], dict[str, Any]]:
        ensure_image_input_supported(profile, request.messages)
        token = resolve_credential_binding(
            profile.credential_binding,
            required=True,
            description=f"LLM profile '{profile.id}'",
        )
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": token,
        }

        contents, system_parts = gemini_contents(request.messages)
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
        if isinstance(request.overrides.get("generationConfig"), dict):
            generation_config.update(dict(request.overrides["generationConfig"]))
        if generation_config:
            payload["generationConfig"] = generation_config

        if request.tool_schemas:
            payload["tools"] = [
                {
                    "functionDeclarations": [
                        gemini_tool_schema(tool) for tool in request.tool_schemas
                    ],
                },
            ]
        if isinstance(request.overrides.get("toolConfig"), dict):
            payload["toolConfig"] = dict(request.overrides["toolConfig"])

        for key, value in request.overrides.items():
            if key not in {"contents", "system_instruction", "tools", "toolConfig", "generationConfig"}:
                payload[key] = value

        return (
            join_url(
                default_base_url(profile, self.DEFAULT_BASE_URL),
                f"/models/{profile.model_name}:generateContent",
            ),
            headers,
            payload,
        )

    @staticmethod
    def _response_from_payload(
        profile: LlmProfile,
        data: dict[str, Any],
    ) -> LlmAdapterResponse:
        candidates = data.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise RuntimeError(f"Gemini profile '{profile.id}' returned no candidates.")
        candidate = candidates[0]
        if not isinstance(candidate, dict):
            raise RuntimeError(f"Gemini profile '{profile.id}' returned an invalid candidate.")
        content = candidate.get("content")
        if not isinstance(content, dict):
            raise RuntimeError(f"Gemini profile '{profile.id}' returned no content payload.")
        parts = content.get("parts")
        if not isinstance(parts, list):
            parts = []

        text_fragments: list[str] = []
        tool_calls: list[ToolCallIntent] = []
        for part in parts:
            if not isinstance(part, dict):
                continue
            if part.get("text") is not None:
                text_fragments.append(str(part.get("text")))
            function_call = part.get("functionCall")
            if isinstance(function_call, dict) and function_call.get("name"):
                tool_calls.append(
                    ToolCallIntent(
                        id=str(function_call.get("id") or uuid4().hex),
                        name=str(function_call.get("name")),
                        arguments=(
                            dict(function_call.get("args"))
                            if isinstance(function_call.get("args"), dict)
                            else {}
                        ),
                    ),
                )

        usage_raw = data.get("usageMetadata")
        usage = None
        if isinstance(usage_raw, dict):
            usage = LlmUsage(
                input_tokens=usage_raw.get("promptTokenCount"),
                output_tokens=usage_raw.get("candidatesTokenCount"),
                total_tokens=usage_raw.get("totalTokenCount"),
            )

        return LlmAdapterResponse(
            result=LlmResult(
                text="".join(text_fragments) or None,
                tool_calls=tuple(tool_calls),
                usage=usage,
                finish_reason=(
                    str(candidate.get("finishReason"))
                    if candidate.get("finishReason") is not None
                    else None
                ),
                metadata={
                    "provider": profile.provider.value,
                    "response_id": data.get("responseId"),
                    "model": data.get("modelVersion"),
                },
            ),
            provider_request_id=(
                str(data.get("responseId")) if data.get("responseId") is not None else None
            ),
        )
