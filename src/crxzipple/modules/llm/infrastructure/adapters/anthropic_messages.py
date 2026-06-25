from __future__ import annotations

from typing import Any

import httpx
import requests

from crxzipple.modules.llm.application.adapters import (
    LlmAdapterRequest,
    LlmAdapterResponse,
)
from crxzipple.modules.llm.domain.entities import LlmProfile
from crxzipple.modules.llm.domain import (
    LlmMessagePhase,
    LlmMessageRole,
    LlmResponseItem,
    LlmResponseItemKind,
    LlmResult,
    LlmUsage,
    utcnow,
)
from crxzipple.modules.llm.infrastructure.adapters.adapter_utils import (
    ensure_image_input_supported,
    parse_json_arguments,
)
from crxzipple.modules.llm.infrastructure.adapters.http_helpers import (
    ensure_async_json_response,
    ensure_json_response,
    resolve_credential_binding,
)
from crxzipple.modules.llm.infrastructure.adapters.anthropic_messages_renderer import (
    AnthropicMessagesRenderer,
)
from crxzipple.modules.llm.infrastructure.adapters.provider_protocol import (
    ProviderRenderInput,
    ProviderWireRequest,
)
from crxzipple.modules.llm.infrastructure.rendering.input_projection import (
    messages_from_projected_input_items,
)
from crxzipple.shared.infrastructure.http import get_async_http_client


class AnthropicMessagesAdapter:
    DEFAULT_BASE_URL = "https://api.anthropic.com/v1"
    DEFAULT_VERSION = "2023-06-01"

    def __init__(self) -> None:
        self._renderer = AnthropicMessagesRenderer(
            default_base_url=self.DEFAULT_BASE_URL,
        )

    def invoke(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
    ) -> LlmAdapterResponse:
        render_input = ProviderRenderInput.from_request(profile=profile, request=request)
        wire_request = self._wire_request(profile, request, render_input=render_input)
        response = self._send_wire_request(
            profile,
            request,
            wire_request,
            render_input=render_input,
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

    def preview_request(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
    ) -> dict[str, Any]:
        return self._renderer.preview_input(
            ProviderRenderInput.from_request(profile=profile, request=request),
        )

    async def invoke_async(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
    ) -> LlmAdapterResponse:
        render_input = ProviderRenderInput.from_request(profile=profile, request=request)
        wire_request = self._wire_request(profile, request, render_input=render_input)
        response = await self._send_wire_request_async(
            profile,
            request,
            wire_request,
            render_input=render_input,
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

    def _request_headers(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
        *,
        render_input: ProviderRenderInput | None = None,
    ) -> dict[str, str]:
        model_input = render_input or ProviderRenderInput.from_request(
            profile=profile,
            request=request,
        )
        request_messages = messages_from_projected_input_items(
            model_input.input_items,
        )
        ensure_image_input_supported(profile, request_messages)
        token = resolve_credential_binding(
            profile.credential_binding_id,
            required=True,
            description=f"LLM profile '{profile.id}'",
            resolved_credential=request.resolved_credential,
        )
        return {
            "Content-Type": "application/json",
            "x-api-key": token,
            "anthropic-version": self.DEFAULT_VERSION,
        }

    def _send_wire_request(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
        wire_request: ProviderWireRequest,
        *,
        render_input: ProviderRenderInput | None = None,
    ) -> requests.Response:
        return requests.post(
            wire_request.endpoint,
            headers=self._request_headers(
                profile,
                request,
                render_input=render_input,
            ),
            json=wire_request.payload,
            timeout=profile.timeout_seconds,
        )

    async def _send_wire_request_async(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
        wire_request: ProviderWireRequest,
        *,
        render_input: ProviderRenderInput | None = None,
    ) -> httpx.Response:
        client = get_async_http_client(
            wire_request.endpoint,
            timeout=profile.timeout_seconds,
            client_factory=httpx.AsyncClient,
        )
        return await client.post(
            wire_request.endpoint,
            headers=self._request_headers(
                profile,
                request,
                render_input=render_input,
            ),
            json=wire_request.payload,
        )

    def _wire_request(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
        *,
        render_input: ProviderRenderInput | None = None,
    ) -> ProviderWireRequest:
        model_input = render_input or ProviderRenderInput.from_request(
            profile=profile,
            request=request,
        )
        rendered = self._renderer.render_input(model_input)
        return ProviderWireRequest.from_rendered(
            renderer_id=self._renderer.renderer_id,
            rendered=rendered,
            preview=self._renderer.preview_input(model_input),
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
                provider_replay_candidate=True,
                user_timeline_candidate=True,
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
                provider_replay_candidate=True,
                user_timeline_candidate=False,
                created_at=now,
                completed_at=now,
            ),
        )
    return tuple(items)
