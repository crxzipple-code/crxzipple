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
    LlmMessagePhase,
    LlmMessageRole,
    LlmResponseItem,
    LlmResponseItemKind,
    LlmResult,
    LlmUsage,
    utcnow,
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
        return self._response_from_payload(
            profile,
            data,
            invocation_id=request.invocation_id,
        )

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
        return self._response_from_payload(
            profile,
            data,
            invocation_id=request.invocation_id,
        )

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
        *,
        invocation_id: str,
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

        response_items = _anthropic_response_items(
            invocation_id=invocation_id,
            text="".join(text_fragments) or None,
            tool_calls=tool_calls,
            provider_response_id=str(data.get("id")) if data.get("id") is not None else None,
            model_name=str(data.get("model")) if data.get("model") is not None else None,
        )
        return LlmAdapterResponse(
            result=LlmResult.from_response_items(
                response_items,
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
                text_fallback="".join(text_fragments) or None,
            ),
            response_items=response_items,
            provider_request_id=str(data.get("id")) if data.get("id") is not None else None,
        )


def _anthropic_response_items(
    *,
    invocation_id: str,
    text: str | None,
    tool_calls: list[dict[str, Any]],
    provider_response_id: str | None,
    model_name: str | None,
) -> tuple[LlmResponseItem, ...]:
    items: list[LlmResponseItem] = []
    now = utcnow()
    if text is not None:
        sequence_no = len(items) + 1
        items.append(
            LlmResponseItem(
                id=f"{invocation_id}:item:{sequence_no}",
                invocation_id=invocation_id,
                sequence_no=sequence_no,
                kind=LlmResponseItemKind.ASSISTANT_MESSAGE,
                role=LlmMessageRole.ASSISTANT,
                phase=LlmMessagePhase.FINAL_ANSWER,
                content_payload={"text": text},
                provider_payload={
                    "type": "message.text",
                    "response_id": provider_response_id,
                    "model": model_name,
                },
                provider_item_id=(
                    f"{provider_response_id}:text"
                    if provider_response_id is not None
                    else f"{invocation_id}:text"
                ),
                provider_item_type="message.text",
                model_visible=True,
                user_visible=True,
                created_at=now,
                completed_at=now,
            ),
        )
    for tool_call in tool_calls:
        tool_name = tool_call.get("name")
        if not tool_name:
            continue
        sequence_no = len(items) + 1
        call_id = str(tool_call.get("id") or tool_name or f"tool_call_{sequence_no}")
        items.append(
            LlmResponseItem(
                id=f"{invocation_id}:item:{sequence_no}",
                invocation_id=invocation_id,
                sequence_no=sequence_no,
                kind=LlmResponseItemKind.TOOL_CALL,
                role=LlmMessageRole.ASSISTANT,
                phase=LlmMessagePhase.UNKNOWN,
                content_payload={
                    "call_id": call_id,
                    "tool_name": str(tool_name),
                    "arguments": parse_json_arguments(tool_call.get("input")),
                },
                provider_payload={
                    "type": "tool_use",
                    "response_id": provider_response_id,
                    "model": model_name,
                },
                provider_item_id=call_id,
                provider_item_type="tool_use",
                call_id=call_id,
                tool_name=str(tool_name),
                model_visible=True,
                user_visible=False,
                created_at=now,
                completed_at=now,
            ),
        )
    return tuple(items)
