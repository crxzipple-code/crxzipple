from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from crxzipple.modules.llm.application.adapters import LlmAdapterRequest
from crxzipple.modules.llm.domain.entities import LlmProfile
from crxzipple.modules.llm.domain.value_objects import (
    LlmInputItem,
    LlmMessage,
    LlmProviderContinuation,
    ToolSchema,
)


@dataclass(frozen=True, slots=True)
class ProviderRenderInput:
    """Provider-neutral renderer input assembled by the adapter boundary."""

    profile: LlmProfile
    request: LlmAdapterRequest
    input_items: tuple[LlmInputItem, ...] = ()
    provider_context_messages: tuple[LlmMessage, ...] = ()
    tool_schemas: tuple[ToolSchema, ...] = ()
    request_policy: dict[str, Any] = field(default_factory=dict)
    provider_options: dict[str, Any] = field(default_factory=dict)
    response_format: dict[str, Any] | None = None
    provider_transport: str = "auto"
    continuation: LlmProviderContinuation | None = None
    runtime_context: dict[str, Any] = field(default_factory=dict)
    runtime_route: dict[str, Any] = field(default_factory=dict)
    runtime_policy: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_request(
        cls,
        *,
        profile: LlmProfile,
        request: LlmAdapterRequest,
    ) -> "ProviderRenderInput":
        return cls(
            profile=profile,
            request=request,
            input_items=tuple(request.input_items),
            provider_context_messages=tuple(request.provider_context_messages),
            tool_schemas=tuple(request.tool_schemas),
            request_policy=dict(request.request_policy),
            provider_options=dict(request.overrides),
            response_format=(
                dict(request.response_format)
                if request.response_format is not None
                else None
            ),
            provider_transport=request.provider_transport,
            continuation=request.continuation,
            runtime_context=dict(request.runtime_context),
            runtime_route=dict(request.runtime_route),
            runtime_policy=dict(request.runtime_policy),
        )


@dataclass(frozen=True, slots=True)
class ProviderWireRequest:
    renderer_id: str
    endpoint: str
    payload: dict[str, Any]
    transport: str = "http"
    render_strategy: str = "full_wire_payload"
    render_report: dict[str, Any] = field(default_factory=dict)
    tool_name_aliases: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_rendered(
        cls,
        *,
        renderer_id: str,
        rendered: Any,
        preview: dict[str, Any],
    ) -> "ProviderWireRequest":
        payload = getattr(rendered, "payload")
        if not isinstance(payload, dict):
            raise TypeError("Rendered provider request payload must be a dict.")
        endpoint = getattr(rendered, "endpoint")
        if not isinstance(endpoint, str) or not endpoint:
            raise TypeError("Rendered provider request endpoint must be a non-empty string.")
        return cls(
            renderer_id=renderer_id,
            endpoint=endpoint,
            payload=payload,
            transport=str(preview.get("transport") or getattr(rendered, "transport", "http")),
            render_strategy=str(
                preview.get("render_strategy")
                or preview.get("render_report", {}).get("render_strategy")
                or "full_wire_payload",
            ),
            render_report=dict(preview.get("render_report") or {}),
            tool_name_aliases=dict(getattr(rendered, "tool_name_aliases", {}) or {}),
        )


class ProviderRequestPreviewRenderer(Protocol):
    renderer_id: str

    def preview(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
    ) -> dict[str, Any]: ...


__all__ = [
    "ProviderRenderInput",
    "ProviderRequestPreviewRenderer",
    "ProviderWireRequest",
]
