from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from uuid import uuid4

from crxzipple.modules.llm.domain import (
    LlmCapability,
    LlmInputItem,
    LlmInputItemKind,
    LlmMessage,
    LlmMessageRole,
    ToolSchema,
)
from crxzipple.shared.request_render_budget import request_render_budget_metadata


@dataclass(frozen=True, slots=True)
class RuntimeLlmRequestRenderSnapshot:
    snapshot_id: str | None = None
    included_node_ids: tuple[str, ...] = ()
    mirrored_node_ids: tuple[str, ...] = ()
    included_refs: tuple[dict[str, object], ...] = ()
    collapsed_refs: tuple[dict[str, object], ...] = ()
    protocol_required_refs: tuple[dict[str, object], ...] = ()
    estimate: dict[str, object] = field(default_factory=dict)
    diagnostics: dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        estimate_summary = _estimate_summary(self.estimate)
        payload: dict[str, object] = {
            "kind": "request_render",
            "included_node_count": len(self.included_node_ids),
            "mirrored_node_count": len(self.mirrored_node_ids),
            "included_ref_count": len(self.included_refs),
            "collapsed_ref_count": len(self.collapsed_refs),
            "protocol_required_ref_count": len(self.protocol_required_refs),
            "estimate": estimate_summary,
            "diagnostics": dict(self.diagnostics),
        }
        if self.snapshot_id is not None:
            payload["snapshot_id"] = self.snapshot_id
        return {
            key: value
            for key, value in payload.items()
            if value not in (None, "", {}, [])
        }


def build_runtime_request_render_snapshot(
    *,
    snapshot_id: str | None = None,
    included_node_ids: tuple[str, ...] = (),
    mirrored_node_ids: tuple[str, ...] = (),
    included_refs: tuple[dict[str, object], ...] = (),
    collapsed_refs: tuple[dict[str, object], ...] = (),
    protocol_required_refs: tuple[dict[str, object], ...] = (),
    estimate: Mapping[str, object] | None = None,
    metadata: Mapping[str, object] | None = None,
) -> RuntimeLlmRequestRenderSnapshot:
    return RuntimeLlmRequestRenderSnapshot(
        snapshot_id=snapshot_id,
        included_node_ids=tuple(included_node_ids),
        mirrored_node_ids=tuple(mirrored_node_ids),
        included_refs=tuple(dict(item) for item in included_refs),
        collapsed_refs=tuple(dict(item) for item in collapsed_refs),
        protocol_required_refs=tuple(dict(item) for item in protocol_required_refs),
        estimate=dict(estimate or {}),
        diagnostics=_request_render_snapshot_diagnostics(metadata or {}),
    )


def build_runtime_llm_request_metadata(
    *,
    runtime_request_mode: str,
    runtime_request_surface: str,
    request_render_snapshot_id: str | None,
    snapshot_metadata: Mapping[str, object],
    provider_tool_schema_names: tuple[str, ...] = (),
) -> dict[str, object]:
    runtime_contract = snapshot_metadata.get("runtime_contract")
    metadata: dict[str, object] = {
        "runtime_request_mode": runtime_request_mode,
        "runtime_request_surface": runtime_request_surface,
        "tree_schema_version": snapshot_metadata.get("tree_schema_version"),
        "request_render_snapshot_id": request_render_snapshot_id,
        "request_render_snapshot_kind": snapshot_metadata.get(
            "snapshot_kind",
            "request_render",
        ),
        "context_history_delivery": snapshot_metadata.get("history_delivery"),
        "provider_tool_schema_count": len(provider_tool_schema_names),
        "provider_tool_schema_names": list(provider_tool_schema_names),
        "mirrored_tool_schema_count": snapshot_metadata.get(
            "mirrored_tool_schema_count",
        ),
        "tool_schema_mirror_skipped_count": snapshot_metadata.get(
            "tool_schema_mirror_skipped_count",
        ),
        "tool_schema_mirror_default_schema_source": snapshot_metadata.get(
            "tool_schema_mirror_default_schema_source",
        ),
        "tool_schema_mirror_available_count": snapshot_metadata.get(
            "tool_schema_mirror_available_count",
        ),
        "tool_schema_mirror_enabled_candidate_count": snapshot_metadata.get(
            "tool_schema_mirror_enabled_candidate_count",
        ),
        "tool_schema_mirror_default_requested_count": snapshot_metadata.get(
            "tool_schema_mirror_default_requested_count",
        ),
        "tool_schema_mirror_default_candidate_count": snapshot_metadata.get(
            "tool_schema_mirror_default_candidate_count",
        ),
        "tool_schema_mirror_default_mirrored_count": snapshot_metadata.get(
            "tool_schema_mirror_default_mirrored_count",
        ),
        "tool_schema_mirror_duplicate_count": snapshot_metadata.get(
            "tool_schema_mirror_duplicate_count",
        ),
        "tool_schema_mirror_group_count": snapshot_metadata.get(
            "tool_schema_mirror_group_count",
        ),
        "tool_schema_mirror_visible_group_count": snapshot_metadata.get(
            "tool_schema_mirror_visible_group_count",
        ),
        "tool_schema_mirror_collapsed_group_count": snapshot_metadata.get(
            "tool_schema_mirror_collapsed_group_count",
        ),
        "tool_schema_mirror_default_group_count": snapshot_metadata.get(
            "tool_schema_mirror_default_group_count",
        ),
        "tool_schema_mirror_default_group_ref_count": snapshot_metadata.get(
            "tool_schema_mirror_default_group_ref_count",
        ),
        "tool_schema_mirror_default_group_match_count": snapshot_metadata.get(
            "tool_schema_mirror_default_group_match_count",
        ),
        "tool_schema_mirror_skipped_by_reason": snapshot_metadata.get(
            "tool_schema_mirror_skipped_by_reason",
        ),
        "tool_schema_mirror_max_count": snapshot_metadata.get(
            "tool_schema_mirror_max_count",
        ),
        "tool_schema_mirror_max_estimated_tokens": snapshot_metadata.get(
            "tool_schema_mirror_max_estimated_tokens",
        ),
        "artifact_content_block_count": snapshot_metadata.get(
            "artifact_content_block_count",
        ),
        "artifact_content_candidate_count": snapshot_metadata.get(
            "artifact_content_candidate_count",
        ),
        "artifact_content_image_count": snapshot_metadata.get(
            "artifact_content_image_count",
        ),
        "artifact_content_file_count": snapshot_metadata.get(
            "artifact_content_file_count",
        ),
        "artifact_content_omitted_count": snapshot_metadata.get(
            "artifact_content_omitted_count",
        ),
        "duplicate_tool_delivery_risk": snapshot_metadata.get(
            "duplicate_tool_delivery_risk",
        ),
        "session_budget_status": snapshot_metadata.get("session_budget_status"),
        "mirrored_node_count": snapshot_metadata.get("mirrored_node_count"),
        "llm_request_policy": snapshot_metadata.get("llm_request_policy"),
        "runtime_request_flow_context": snapshot_metadata.get("flow_context"),
        "request_context_source": snapshot_metadata.get("request_context_source"),
        "context_slice_id": snapshot_metadata.get("context_slice_id"),
        "context_slice_item_count": snapshot_metadata.get("context_slice_item_count"),
        "context_slice_included_node_count": snapshot_metadata.get(
            "context_slice_included_node_count",
        ),
        "context_slice_omitted_node_count": snapshot_metadata.get(
            "context_slice_omitted_node_count",
        ),
        "context_slice_active_tool_count": snapshot_metadata.get(
            "context_slice_active_tool_count",
        ),
        "context_slice_projected_input_item_count": snapshot_metadata.get(
            "context_slice_projected_input_item_count",
        ),
        "context_slice_archived_ref_count": snapshot_metadata.get(
            "context_slice_archived_ref_count",
        ),
        "context_slice_redacted_ref_count": snapshot_metadata.get(
            "context_slice_redacted_ref_count",
        ),
        "context_slice_unresolved_ref_count": snapshot_metadata.get(
            "context_slice_unresolved_ref_count",
        ),
        "context_slice_loss": snapshot_metadata.get("context_slice_loss"),
        "visible_input_summary": snapshot_metadata.get("visible_input_summary"),
    }
    metadata.update(request_render_budget_metadata(snapshot_metadata))
    if isinstance(runtime_contract, dict):
        metadata["runtime_contract"] = dict(runtime_contract)
    if snapshot_metadata.get("runtime_contract_version") is not None:
        metadata["runtime_contract_version"] = snapshot_metadata.get(
            "runtime_contract_version",
        )
    if snapshot_metadata.get("runtime_contract_hash") is not None:
        metadata["runtime_contract_hash"] = snapshot_metadata.get(
            "runtime_contract_hash",
        )
    return {
        key: value
        for key, value in metadata.items()
        if value not in (None, "", {}, [])
    }


def runtime_request_context_from_metadata(
    metadata: Mapping[str, object] | None,
) -> dict[str, object]:
    """Project request-render control-plane metadata into renderer context."""

    if not isinstance(metadata, Mapping):
        return {}
    context: dict[str, object] = {}
    for key in (
        "request_context_source",
        "context_slice_id",
        "context_slice_item_count",
        "context_slice_included_node_count",
        "context_slice_omitted_node_count",
        "context_slice_active_tool_count",
        "context_slice_projected_input_item_count",
        "context_slice_archived_ref_count",
        "context_slice_redacted_ref_count",
        "context_slice_unresolved_ref_count",
        "context_slice_loss",
        "request_render_snapshot_id",
        "tool_surface_snapshot_id",
        "tool_surface_function_count",
        "tool_surface_mirrored_schema_count",
    ):
        value = metadata.get(key)
        if value not in (None, "", {}, []):
            context[key] = value
    request_render_snapshot = metadata.get("request_render_snapshot")
    if isinstance(request_render_snapshot, Mapping):
        snapshot_id = _metadata_text(request_render_snapshot.get("snapshot_id"))
        if snapshot_id is not None:
            context.setdefault("request_render_snapshot_id", snapshot_id)
        included_node_count = request_render_snapshot.get("included_node_count")
        if isinstance(included_node_count, int):
            context.setdefault(
                "request_render_snapshot_included_node_count",
                included_node_count,
            )
    tool_surface = metadata.get("tool_surface")
    if isinstance(tool_surface, Mapping):
        surface_id = _metadata_text(tool_surface.get("id"))
        if surface_id is not None:
            context.setdefault("tool_surface_id", surface_id)
        functions = tool_surface.get("functions")
        if isinstance(functions, list | tuple):
            context.setdefault("tool_surface_function_count", len(functions))
        mirrored_schema_names = tool_surface.get("mirrored_schema_names")
        if isinstance(mirrored_schema_names, list | tuple):
            context.setdefault(
                "tool_surface_mirrored_schema_count",
                len(mirrored_schema_names),
            )
    return context


@dataclass(frozen=True, slots=True)
class RuntimeRequestRenderContext:
    """Renderer-facing request context derived from the formal runtime request.

    This is the provider-neutral control-plane slice summary consumed by
    provider renderers. It intentionally carries only identifiers, counts, and
    safe loss/summary fields, never raw Context Tree/debug bodies.
    """

    payload: dict[str, object] = field(default_factory=dict)

    @classmethod
    def from_request_metadata(
        cls,
        metadata: Mapping[str, object] | None,
    ) -> "RuntimeRequestRenderContext":
        return cls(payload=runtime_request_context_from_metadata(metadata))

    def to_payload(self) -> dict[str, object]:
        return dict(self.payload)


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
class RuntimeToolSurfaceRef:
    tool_id: str
    name: str
    schema: ToolSchema
    target: str
    source_id: str | None = None
    group_key: str | None = None
    always_visible: bool = True
    enabled: bool = True
    metadata: dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "tool_id": self.tool_id,
            "name": self.name,
            "schema": self.schema.to_payload(),
            "target": self.target,
            "always_visible": self.always_visible,
            "enabled": self.enabled,
        }
        if self.source_id is not None:
            payload["source_id"] = self.source_id
        if self.group_key is not None:
            payload["group_key"] = self.group_key
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


@dataclass(frozen=True, slots=True)
class RuntimeToolSurface:
    id: str
    functions: tuple[RuntimeToolSurfaceRef, ...] = ()
    mirrored_schema_names: tuple[str, ...] = ()
    blocked_access_count: int = 0
    metadata: dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "id": self.id,
            "functions": [item.to_payload() for item in self.functions],
            "mirrored_schema_names": list(self.mirrored_schema_names),
            "blocked_access_count": self.blocked_access_count,
            "metadata": dict(self.metadata),
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


def messages_from_runtime_input_items(
    input_items: tuple[LlmInputItem, ...],
    *,
    fallback_messages: tuple[LlmMessage, ...] = (),
) -> tuple[LlmMessage, ...]:
    if not input_items:
        return fallback_messages
    messages: list[LlmMessage] = []
    for item in input_items:
        payload = dict(item.payload)
        metadata = dict(item.metadata)
        if item.kind is LlmInputItemKind.MESSAGE:
            messages.append(
                LlmMessage(
                    role=_message_role_from_payload(payload.get("role")),
                    content=payload.get("content", ""),
                    name=_metadata_text(payload.get("name")),
                    metadata=metadata,
                ),
            )
            continue
        if item.kind is LlmInputItemKind.FUNCTION_CALL:
            call_id = str(payload.get("call_id") or "").strip()
            messages.append(
                LlmMessage(
                    role=LlmMessageRole.ASSISTANT,
                    content={
                        "type": "function_call",
                        "call_id": call_id,
                        "name": str(payload.get("name") or "").strip(),
                        "arguments": (
                            dict(payload.get("arguments"))
                            if isinstance(payload.get("arguments"), dict)
                            else {}
                        ),
                    },
                    tool_call_id=call_id or None,
                    metadata=metadata,
                ),
            )
            continue
        if item.kind is LlmInputItemKind.FUNCTION_CALL_OUTPUT:
            messages.append(
                LlmMessage(
                    role=LlmMessageRole.TOOL,
                    content=payload.get("output", ""),
                    name=_metadata_text(metadata.get("tool_name")),
                    tool_call_id=_metadata_text(payload.get("call_id")),
                    metadata=metadata,
                ),
            )
            continue
        if item.kind is LlmInputItemKind.REASONING:
            messages.append(
                LlmMessage(
                    role=LlmMessageRole.ASSISTANT,
                    content=payload.get("content", ""),
                    metadata={**metadata, "kind": "reasoning"},
                ),
            )
    return tuple(messages)


def runtime_input_items_from_projected_payloads(
    projected_input_items: tuple[Mapping[str, object], ...],
    *,
    default_source: str = "context_slice",
) -> tuple[LlmInputItem, ...]:
    """Build canonical runtime input items from Context Slice projection payloads."""

    items: list[LlmInputItem] = []
    for raw in projected_input_items:
        kind = _input_item_kind_from_text(raw.get("kind"))
        payload = raw.get("payload")
        if kind is None or not isinstance(payload, Mapping):
            continue
        metadata = raw.get("metadata")
        source = _metadata_text(raw.get("source")) or default_source
        items.append(
            LlmInputItem(
                kind=kind,
                payload=dict(payload),
                source=source,
                metadata=dict(metadata) if isinstance(metadata, Mapping) else {},
            ),
        )
    return tuple(items)


def tool_schemas_from_projected_refs(
    tool_schema_refs: tuple[Mapping[str, object], ...],
) -> tuple[ToolSchema, ...]:
    """Build canonical tool schemas from Context Slice tool schema refs."""

    schemas: list[ToolSchema] = []
    for raw_ref in tool_schema_refs:
        schema_payload = raw_ref.get("schema")
        if not isinstance(schema_payload, Mapping):
            continue
        try:
            schemas.append(ToolSchema.from_payload(schema_payload))
        except Exception:
            continue
    return dedupe_tool_schemas(tuple(schemas))


def provider_context_messages_from_messages(
    messages: tuple[LlmMessage, ...],
) -> tuple[LlmMessage, ...]:
    provider_context_messages: list[LlmMessage] = []
    for message in messages:
        if message.role is not LlmMessageRole.SYSTEM:
            continue
        if _empty_content(message.content):
            continue
        metadata = dict(message.metadata)
        metadata.setdefault("provider_context_kind", "runtime_instruction")
        metadata.setdefault("source", "runtime_request_draft_message")
        provider_context_messages.append(
            LlmMessage(
                role=message.role,
                content=message.content,
                name=message.name,
                tool_call_id=message.tool_call_id,
                metadata=metadata,
            ),
        )
    return tuple(provider_context_messages)


def sanitize_runtime_input_items_for_capabilities(
    input_items: tuple[LlmInputItem, ...],
    *,
    llm_capabilities: tuple[LlmCapability, ...],
) -> tuple[LlmInputItem, ...]:
    if LlmCapability.VISION_INPUT in set(llm_capabilities):
        return input_items
    sanitized: list[LlmInputItem] = []
    for item in input_items:
        payload = dict(item.payload) if isinstance(item.payload, Mapping) else item.payload
        if isinstance(payload, dict):
            if item.kind is LlmInputItemKind.MESSAGE:
                payload["content"] = _remove_vision_blocks(payload.get("content"))
            elif item.kind is LlmInputItemKind.FUNCTION_CALL_OUTPUT:
                payload["output"] = _remove_vision_blocks(payload.get("output"))
        sanitized.append(
            LlmInputItem(
                kind=item.kind,
                payload=payload,
                source=_normalize_input_item_source(item.source),
                metadata=_normalize_input_item_metadata(item.metadata),
            ),
        )
    return tuple(sanitized)


def runtime_input_item_mode_metadata(
    input_items: tuple[LlmInputItem, ...],
) -> dict[str, object]:
    source_counts: dict[str, int] = {}
    kind_counts: dict[str, int] = {}
    for item in input_items:
        source_counts[item.source] = source_counts.get(item.source, 0) + 1
        kind_counts[item.kind.value] = kind_counts.get(item.kind.value, 0) + 1
    return {
        "input_mode": "runtime_transcript" if input_items else "empty",
        "input_item_count": len(input_items),
        "input_item_kind_counts": kind_counts,
        "input_item_source_counts": source_counts,
    }


def runtime_transcript_input_items_from_messages(
    *,
    input_items: tuple[LlmInputItem, ...],
    messages: tuple[LlmMessage, ...],
) -> tuple[LlmInputItem, ...]:
    if input_items:
        return input_items
    return tuple(
        LlmInputItem(
            kind=LlmInputItemKind.MESSAGE,
            payload={
                "role": message.role.value,
                "content": message.content,
                **({"name": message.name} if message.name is not None else {}),
            },
            source="runtime_transcript",
            metadata=dict(message.metadata),
        )
        for message in messages
        if message.role is not LlmMessageRole.SYSTEM
        and not _empty_content(message.content)
    )


def tool_surface_request_metadata(
    tool_surface: RuntimeToolSurface,
) -> dict[str, object]:
    function_refs = _tool_surface_function_refs(tool_surface.functions)
    metadata: dict[str, object] = {
        "tool_surface_mirrored_schema_names": list(
            tool_surface.mirrored_schema_names,
        ),
        "tool_surface_mirrored_schema_count": len(
            tool_surface.mirrored_schema_names,
        ),
        "tool_surface_always_visible_count": sum(
            1 for function in tool_surface.functions if function.always_visible
        ),
        "tool_surface_context_selected_count": sum(
            1 for function in tool_surface.functions if not function.always_visible
        ),
        "tool_surface_function_refs": function_refs,
        "tool_surface_source_refs": _dedupe_surface_refs(
            function_refs,
            key_fields=("source_id",),
        ),
        "tool_surface_group_refs": _dedupe_surface_refs(
            function_refs,
            key_fields=("source_id", "group_key"),
        ),
    }
    return {
        key: value
        for key, value in metadata.items()
        if value not in (None, "", {}, [])
    }


def runtime_transcript_policy(
    transcript_policy: Mapping[str, object],
    *,
    require_tool_call: bool = False,
) -> dict[str, object]:
    policy = dict(transcript_policy)
    if require_tool_call:
        policy["require_tool_call"] = True
    return policy


def request_time_tool_surface(tool_surface: RuntimeToolSurface) -> RuntimeToolSurface:
    return RuntimeToolSurface(
        id=f"{tool_surface.id}:{uuid4().hex}",
        functions=tool_surface.functions,
        mirrored_schema_names=tool_surface.mirrored_schema_names,
        blocked_access_count=tool_surface.blocked_access_count,
        metadata={
            **tool_surface.metadata,
            "base_tool_surface_id": tool_surface.id,
            "request_time_unique": True,
        },
    )


def dedupe_tool_schemas(tool_schemas: tuple[ToolSchema, ...] | None) -> tuple[ToolSchema, ...]:
    if not tool_schemas:
        return ()
    schemas: list[ToolSchema] = []
    seen: set[str] = set()
    for schema in tool_schemas:
        name = schema.name.strip()
        if not name or name in seen:
            continue
        schemas.append(schema)
        seen.add(name)
    return tuple(schemas)


def request_render_snapshot_preview_payload(
    request_render_snapshot: Mapping[str, object],
) -> dict[str, object]:
    allowed_keys = {
        "snapshot_id",
        "included_node_count",
        "mirrored_node_count",
        "included_ref_count",
        "collapsed_ref_count",
        "protocol_required_ref_count",
        "estimate",
        "diagnostics",
        "tree_schema_version",
        "kind",
    }
    payload: dict[str, object] = {}
    for key, value in request_render_snapshot.items():
        if key not in allowed_keys or value in (None, "", {}, []):
            continue
        payload[key] = value
    return {
        key: value
        for key, value in payload.items()
        if value not in (None, "", {}, [])
    }


def _estimate_summary(estimate: Mapping[str, object]) -> dict[str, object]:
    summary: dict[str, object] = {}
    for key in (
        "estimated_tokens",
        "text_tokens",
        "tool_schema_tokens",
        "file_tokens",
        "text_chars",
        "image_count",
        "file_count",
        "provider_attachment_count",
        "truncated",
        "status",
    ):
        value = estimate.get(key)
        if value not in (None, "", {}, []):
            summary[key] = value
    breakdown = estimate.get("breakdown")
    if isinstance(breakdown, Mapping):
        by_kind = breakdown.get("by_kind")
        if isinstance(by_kind, Mapping):
            summary["kind_count"] = len(by_kind)
        by_owner = breakdown.get("by_owner")
        if isinstance(by_owner, Mapping):
            summary["owner_count"] = len(by_owner)
    top_nodes = estimate.get("top_nodes_by_tokens")
    if isinstance(top_nodes, list | tuple):
        summary["top_node_count"] = len(top_nodes)
    return summary


def request_metadata_preview_payload(
    request_metadata: Mapping[str, object],
) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, value in request_metadata.items():
        if not isinstance(key, str) or value in (None, "", {}, []):
            continue
        if key in _OMITTED_METADATA_KEYS:
            continue
        if key == "request_render_snapshot" and isinstance(value, Mapping):
            request_render_snapshot = request_render_snapshot_preview_payload(value)
            if request_render_snapshot:
                payload["request_render_snapshot"] = request_render_snapshot
            continue
        if key == "tool_surface" and isinstance(value, Mapping):
            tool_surface = _tool_surface_preview_payload(value)
            if tool_surface:
                payload[key] = tool_surface
            continue
        preview_value = _metadata_preview_value(value)
        if preview_value not in (None, "", {}, []):
            payload[key] = preview_value
    return payload


_OMITTED_METADATA_KEYS = {
    "artifact_content_blocks",
    "content",
    "context_slice",
    "debug_body",
    "files",
    "input",
    "messages",
    "prompt_body",
    "provider_attachment_mirror",
    "provider_attachments",
    "raw_tree_body",
    "rendered_prompt",
    "text",
    "tool_schemas",
}


def _metadata_preview_value(value: object, *, depth: int = 0) -> object:
    if isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Mapping):
        if depth >= 3:
            return {"field_count": len(value)}
        payload: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                continue
            if key in _OMITTED_METADATA_KEYS:
                continue
            preview_item = _metadata_preview_value(item, depth=depth + 1)
            if preview_item not in (None, "", {}, []):
                payload[key] = preview_item
        return payload
    if isinstance(value, list | tuple):
        if depth >= 3:
            return {"item_count": len(value)}
        preview_items: list[object] = []
        for item in value[:80]:
            preview_item = _metadata_preview_value(item, depth=depth + 1)
            if preview_item not in (None, "", {}, []):
                preview_items.append(preview_item)
        if len(value) > len(preview_items):
            return {
                "item_count": len(value),
                "items": preview_items,
            }
        return preview_items
    return None


def _tool_surface_preview_payload(tool_surface: Mapping[str, object]) -> dict[str, object]:
    payload: dict[str, object] = {}
    surface_id = tool_surface.get("id")
    if isinstance(surface_id, str) and surface_id.strip():
        payload["id"] = surface_id.strip()
    functions = tool_surface.get("functions")
    if isinstance(functions, list | tuple):
        names: list[str] = []
        for function in functions:
            if not isinstance(function, Mapping):
                continue
            name = function.get("name")
            if isinstance(name, str) and name.strip():
                names.append(name.strip())
        payload["function_count"] = len(functions)
        if names:
            payload["function_names"] = names
    mirrored_schema_names = tool_surface.get("mirrored_schema_names")
    if isinstance(mirrored_schema_names, list | tuple):
        names = [
            name.strip()
            for name in mirrored_schema_names
            if isinstance(name, str) and name.strip()
        ]
        payload["mirrored_schema_count"] = len(mirrored_schema_names)
        if names:
            payload["mirrored_schema_names"] = names
    return {
        key: value
        for key, value in payload.items()
        if value not in (None, "", {}, [])
    }


def _request_render_snapshot_diagnostics(
    metadata: Mapping[str, object],
) -> dict[str, object]:
    diagnostics: dict[str, object] = {}
    for key in (
        "tool_schema_mirror_budget_status",
        "tool_schema_mirror_skipped_count",
        "tool_schema_mirror_duplicate_count",
        "tool_schema_mirror_skipped_by_reason",
        "duplicate_tool_delivery_risk",
        "session_budget_status",
        "visible_input_summary",
        "request_render_timings",
        "context_slice_omitted_node_count",
        "context_slice_archived_ref_count",
        "context_slice_redacted_ref_count",
        "context_slice_unresolved_ref_count",
        "context_slice_loss",
    ):
        value = metadata.get(key)
        if value not in (None, "", {}, []):
            diagnostics[key] = value
    return diagnostics


def _tool_surface_function_refs(
    functions: tuple[RuntimeToolSurfaceRef, ...],
) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    for function in functions:
        ref: dict[str, object] = {
            "tool_id": function.tool_id,
            "name": function.name,
            "enabled": function.enabled,
            "always_visible": function.always_visible,
        }
        if function.source_id is not None:
            ref["source_id"] = function.source_id
        if function.group_key is not None:
            ref["group_key"] = function.group_key
        for key in ("source", "node_id", "tool_ref_id", "function_name"):
            value = function.metadata.get(key)
            if value not in (None, "", {}, []):
                ref[key] = value
        refs.append(ref)
    return refs


def _dedupe_surface_refs(
    refs: list[dict[str, object]],
    *,
    key_fields: tuple[str, ...],
) -> list[dict[str, object]]:
    seen: set[tuple[object, ...]] = set()
    result: list[dict[str, object]] = []
    for ref in refs:
        key = tuple(ref.get(field) for field in key_fields)
        if any(value is None for value in key) or key in seen:
            continue
        seen.add(key)
        result.append({field: ref[field] for field in key_fields})
    return result


def _normalize_input_item_source(source: str) -> str:
    if source == "context_slice":
        return "runtime_transcript"
    return source


def _normalize_input_item_metadata(metadata: Mapping[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in metadata.items()
        if not key.startswith("context_slice")
    }


def _remove_vision_blocks(value: object) -> object:
    if isinstance(value, list):
        filtered: list[object] = []
        omitted_names: list[str] = []
        for block in value:
            if not isinstance(block, Mapping):
                filtered.append(block)
                continue
            block_type = str(block.get("type") or "").strip().lower()
            if block_type in {"image", "image_ref"}:
                name = _metadata_text(block.get("name")) or block_type
                omitted_names.append(name)
                continue
            filtered.append(dict(block))
        if filtered:
            if omitted_names:
                filtered.append(
                    {
                        "type": "text",
                        "text": "[image omitted: model does not support vision input]",
                    },
                )
            return filtered
        if omitted_names:
            return [
                {
                    "type": "text",
                    "text": "[image omitted: model does not support vision input]",
                },
            ]
        return filtered
    if isinstance(value, Mapping):
        block_type = str(value.get("type") or "").strip().lower()
        if block_type in {"image", "image_ref"}:
            return {
                "type": "text",
                "text": "[image omitted: model does not support vision input]",
            }
        return {key: _remove_vision_blocks(item) for key, item in value.items()}
    return value


def _message_role_from_payload(value: object) -> LlmMessageRole:
    try:
        return LlmMessageRole(str(value or "user").strip().lower())
    except ValueError:
        return LlmMessageRole.USER


def _input_item_kind_from_text(value: object) -> LlmInputItemKind | None:
    text = _metadata_text(value)
    if text is None:
        return None
    try:
        return LlmInputItemKind(text)
    except ValueError:
        return None


def _metadata_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _empty_content(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, list | tuple | dict):
        return len(value) == 0
    return False


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
