from __future__ import annotations

from dataclasses import dataclass, field

from crxzipple.modules.llm.domain import (
    LlmInputItem,
    LlmMessage,
    ToolSchema,
)
from crxzipple.modules.llm.application.runtime_input_items import (
    messages_from_runtime_input_items,
    metadata_text as _metadata_text,
    provider_context_messages_from_messages,
    runtime_input_item_mode_metadata,
    runtime_input_items_from_projected_payloads,
    runtime_transcript_input_items_from_messages,
    runtime_transcript_policy,
    sanitize_runtime_input_items_for_capabilities,
)
from crxzipple.modules.llm.application.runtime_request_preview import (
    request_metadata_preview_payload,
    request_render_snapshot_preview_payload,
)
from crxzipple.modules.llm.application.runtime_request_snapshot import (
    RuntimeLlmRequestRenderSnapshot,
    RuntimeRequestRenderContext,
    build_runtime_llm_request_metadata,
    build_runtime_request_render_snapshot,
    runtime_request_context_from_metadata,
)
from crxzipple.modules.llm.application.runtime_tool_surface import (
    RuntimeToolSurface,
    RuntimeToolSurfaceRef,
    dedupe_tool_schemas,
    request_time_tool_surface,
    tool_schemas_from_projected_refs,
    tool_surface_request_metadata,
)


@dataclass(frozen=True, slots=True)
class RuntimeRequestRoute:
    """Renderer-facing route data for the current LLM request."""

    llm_id: str
    session_key: str
    active_session_id: str
    provider_transport: str = "auto"

    @classmethod
    def from_runtime_request(
        cls,
        request: "RuntimeLlmRequest",
    ) -> "RuntimeRequestRoute":
        return cls(
            llm_id=request.llm_id,
            session_key=request.session_key,
            active_session_id=request.active_session_id,
            provider_transport=_metadata_text(
                request.provider_options.get("provider_transport"),
            )
            or "auto",
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "llm_id": self.llm_id,
            "session_key": self.session_key,
            "active_session_id": self.active_session_id,
            "provider_transport": self.provider_transport,
        }


@dataclass(frozen=True, slots=True)
class RuntimeRequestRenderPolicy:
    """Renderer-facing policy data selected by the runtime control plane."""

    transcript_policy: dict[str, object] = field(default_factory=dict)
    reasoning: dict[str, object] = field(default_factory=dict)
    response_format: dict[str, object] = field(default_factory=dict)
    provider_option_keys: tuple[str, ...] = ()

    @classmethod
    def from_runtime_request(
        cls,
        request: "RuntimeLlmRequest",
    ) -> "RuntimeRequestRenderPolicy":
        response_format = request.response_format()
        return cls(
            transcript_policy=dict(request.transcript.policy),
            reasoning=dict(request.reasoning_config),
            response_format=dict(response_format or {}),
            provider_option_keys=tuple(sorted(str(key) for key in request.provider_options)),
        )

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "transcript_policy": dict(self.transcript_policy),
            "reasoning": dict(self.reasoning),
            "response_format": dict(self.response_format),
            "provider_option_keys": list(self.provider_option_keys),
        }
        return {
            key: value
            for key, value in payload.items()
            if value not in (None, "", {}, [])
        }


@dataclass(frozen=True, slots=True)
class RuntimeLlmTranscript:
    items: tuple[LlmInputItem, ...] = ()
    policy: dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "items": [item.to_payload() for item in self.items],
        }
        if self.policy:
            payload["policy"] = dict(self.policy)
        return payload


@dataclass(frozen=True, slots=True)
class RuntimeLlmRequest:
    llm_id: str
    session_key: str
    active_session_id: str
    messages: tuple[LlmMessage, ...]
    tool_schemas: tuple[ToolSchema, ...]
    request_render_snapshot: RuntimeLlmRequestRenderSnapshot
    tool_surface: RuntimeToolSurface
    provider_context_messages: tuple[LlmMessage, ...] = ()
    transcript: RuntimeLlmTranscript = field(default_factory=RuntimeLlmTranscript)
    reasoning_config: dict[str, object] = field(default_factory=dict)
    output_contract: dict[str, object] = field(default_factory=dict)
    provider_options: dict[str, object] = field(default_factory=dict)
    metadata: dict[str, object] = field(default_factory=dict)
    blocked_tool_access: tuple[dict[str, object], ...] = ()

    def request_metadata(self) -> dict[str, object]:
        metadata = dict(self.metadata)
        if self.request_render_snapshot.snapshot_id:
            metadata["request_render_snapshot"] = (
                self.request_render_snapshot.to_payload()
            )
        if self.tool_surface.id:
            metadata["tool_surface"] = self.tool_surface.to_payload()
        if self.reasoning_config:
            metadata["reasoning_config"] = dict(self.reasoning_config)
        if self.output_contract:
            metadata["output_contract"] = dict(self.output_contract)
        if self.blocked_tool_access:
            metadata["blocked_tool_access"] = [
                dict(item) for item in self.blocked_tool_access
            ]
        if self.provider_context_messages:
            metadata["provider_context_message_count"] = len(
                self.provider_context_messages,
            )
            metadata["provider_context_message_kinds"] = [
                str(message.metadata.get("provider_context_kind", "")).strip()
                for message in self.provider_context_messages
                if str(message.metadata.get("provider_context_kind", "")).strip()
            ]
        return metadata

    def renderer_context(self) -> RuntimeRequestRenderContext:
        return RuntimeRequestRenderContext.from_request_metadata(
            self.request_metadata(),
        )

    def renderer_route(self) -> RuntimeRequestRoute:
        return RuntimeRequestRoute.from_runtime_request(self)

    def renderer_policy(self) -> RuntimeRequestRenderPolicy:
        return RuntimeRequestRenderPolicy.from_runtime_request(self)

    def response_format(self) -> dict[str, object] | None:
        response_format = self.output_contract.get("response_format")
        return dict(response_format) if isinstance(response_format, dict) else None

    def provider_overrides(self) -> dict[str, object]:
        overrides = dict(self.provider_options)
        if self.reasoning_config:
            existing = overrides.get("reasoning")
            reasoning = dict(existing) if isinstance(existing, dict) else {}
            reasoning.update(self.reasoning_config)
            overrides["reasoning"] = reasoning
        return overrides

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "llm_id": self.llm_id,
            "session_key": self.session_key,
            "active_session_id": self.active_session_id,
            "messages": [message.to_payload() for message in self.messages],
            "provider_context_messages": [
                message.to_payload() for message in self.provider_context_messages
            ],
            "transcript": self.transcript.to_payload(),
            "tool_schemas": [schema.to_payload() for schema in self.tool_schemas],
            "request_render_snapshot": self.request_render_snapshot.to_payload(),
            "tool_surface": self.tool_surface.to_payload(),
            "reasoning_config": dict(self.reasoning_config),
            "output_contract": dict(self.output_contract),
            "provider_options": dict(self.provider_options),
            "metadata": dict(self.metadata),
            "blocked_tool_access": [
                dict(item) for item in self.blocked_tool_access
            ],
        }
        return {
            key: value
            for key, value in payload.items()
            if value not in (None, "", {}, [])
        }


__all__ = [
    "RuntimeLlmRequestRenderSnapshot",
    "RuntimeLlmRequest",
    "RuntimeLlmTranscript",
    "RuntimeToolSurface",
    "RuntimeToolSurfaceRef",
    "build_runtime_llm_request_metadata",
    "build_runtime_request_render_snapshot",
    "dedupe_tool_schemas",
    "messages_from_runtime_input_items",
    "provider_context_messages_from_messages",
    "request_time_tool_surface",
    "runtime_request_context_from_metadata",
    "runtime_input_items_from_projected_payloads",
    "runtime_input_item_mode_metadata",
    "runtime_transcript_input_items_from_messages",
    "runtime_transcript_policy",
    "sanitize_runtime_input_items_for_capabilities",
    "tool_schemas_from_projected_refs",
    "tool_surface_request_metadata",
    "request_render_snapshot_preview_payload",
    "request_metadata_preview_payload",
]
