from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from crxzipple.modules.llm.application.runtime_request import (
    RuntimeLlmRequestRenderSnapshot,
    RuntimeLlmRequest,
    RuntimeLlmTranscript,
    RuntimeToolSurface,
    RuntimeToolSurfaceRef,
    build_runtime_llm_request_metadata,
    build_runtime_request_render_snapshot,
    messages_from_runtime_input_items,
    provider_context_messages_from_messages,
    request_time_tool_surface,
    runtime_input_item_mode_metadata,
    runtime_input_items_from_projected_payloads,
    runtime_transcript_policy,
    sanitize_runtime_input_items_for_capabilities,
    tool_schemas_from_projected_refs,
    tool_surface_request_metadata,
)
from crxzipple.modules.llm.domain import (
    LlmInputItem,
    ToolSchema,
)

if TYPE_CHECKING:
    from crxzipple.modules.orchestration.application.ports import (
        RequestRenderSnapshotRecord,
    )
    from crxzipple.modules.orchestration.application.runtime_llm_request_draft import (
        RuntimeLlmRequestDraft,
    )
    from crxzipple.modules.orchestration.application.tool_resolver import ResolvedToolSet
else:
    RequestRenderSnapshotRecord = Any
    RuntimeLlmRequestDraft = Any
    ResolvedToolSet = Any


RuntimeToolSurfaceSnapshotBuilder = Callable[..., object]


@dataclass(frozen=True, slots=True)
class _ResolvedToolSetView:
    tools: tuple[object, ...] = ()
    blocked_access: tuple[object, ...] = ()


@dataclass(slots=True)
class RuntimeLlmRequestBuilder:
    """Build the runtime LLM request envelope from orchestration facts.

    Orchestration owns run lifecycle. Context Workspace owns the Context Tree.
    The LLM module owns canonical request DTOs and provider protocol rendering.
    This builder maps run/context/tool facts into that LLM-owned request shape.
    """

    tool_surface_snapshot_builder: RuntimeToolSurfaceSnapshotBuilder | None = None

    def draft_with_request_render_snapshot(
        self,
        draft: RuntimeLlmRequestDraft,
        request_render_snapshot: RequestRenderSnapshotRecord | None,
    ) -> RuntimeLlmRequestDraft:
        return self._draft_with_request_render_snapshot_report(
            draft,
            request_render_snapshot,
        )

    @staticmethod
    def visible_tool_schema_names(
        request_render_snapshot: RequestRenderSnapshotRecord | None,
    ) -> tuple[str, ...]:
        return tuple(
            schema.name
            for schema in _tool_schemas_from_request_render_snapshot(
                request_render_snapshot,
            )
            if schema.name.strip()
        )

    def resolved_tools_for_draft(
        self,
        resolved_tools: ResolvedToolSet,
        draft: RuntimeLlmRequestDraft,
        request_render_snapshot: RequestRenderSnapshotRecord | None,
    ) -> ResolvedToolSet | _ResolvedToolSetView:
        if draft.surface_policy.surface != "interactive":
            return resolved_tools
        visible_tool_names = set(self.visible_tool_schema_names(request_render_snapshot))
        if not visible_tool_names:
            return _ResolvedToolSetView(
                blocked_access=tuple(getattr(resolved_tools, "blocked_access", ())),
            )
        return _ResolvedToolSetView(
            tools=tuple(
                item
                for item in getattr(resolved_tools, "tools", ())
                if item.schema.name in visible_tool_names
                or item.tool.id in visible_tool_names
            ),
            blocked_access=tuple(getattr(resolved_tools, "blocked_access", ())),
        )

    def request_metadata(
        self,
        *,
        draft: RuntimeLlmRequestDraft,
        request_render_snapshot_id: str | None,
        snapshot_metadata: dict[str, object],
        tool_schemas: tuple[ToolSchema, ...],
    ) -> dict[str, object]:
        return build_llm_request_metadata(
            draft=draft,
            request_render_snapshot_id=request_render_snapshot_id,
            snapshot_metadata=snapshot_metadata,
            tool_schemas=tool_schemas,
        )

    def request_envelope(
        self,
        *,
        draft: RuntimeLlmRequestDraft,
        request_render_snapshot: RequestRenderSnapshotRecord | None,
        resolved_tools: ResolvedToolSet | None,
        snapshot_metadata: dict[str, object],
        run_id: str | None = None,
        agent_id: str | None = None,
        persist_tool_surface_snapshot: bool = True,
        provider_options: dict[str, object] | None = None,
        reasoning_config: dict[str, object] | None = None,
        output_contract: dict[str, object] | None = None,
    ) -> "RuntimeLlmRequest":
        draft_with_snapshot = self.draft_with_request_render_snapshot(
            draft,
            request_render_snapshot,
        )
        visible_tool_schemas = _tool_schemas_from_request_render_snapshot(
            request_render_snapshot,
        )
        tool_surface = _tool_surface_from_resolved_tools(
            resolved_tools_for_envelope := self.resolved_tools_for_draft(
                resolved_tools or _ResolvedToolSetView(),
                draft_with_snapshot,
                request_render_snapshot,
            ),
            tool_schemas=visible_tool_schemas,
            request_render_snapshot=request_render_snapshot,
        )
        if persist_tool_surface_snapshot and self.tool_surface_snapshot_builder is not None:
            tool_surface = request_time_tool_surface(tool_surface)
        metadata = self.request_metadata(
            draft=draft_with_snapshot,
            request_render_snapshot_id=(
                request_render_snapshot.snapshot_id
                if request_render_snapshot is not None
                else None
            ),
            snapshot_metadata=snapshot_metadata,
            tool_schemas=visible_tool_schemas,
        )
        persisted_tool_surface_id = (
            self._persist_tool_surface_snapshot(
                draft=draft_with_snapshot,
                tool_surface=tool_surface,
                resolved_tools=resolved_tools_for_envelope,
                run_id=run_id,
                agent_id=agent_id,
                request_render_snapshot=request_render_snapshot,
            )
            if persist_tool_surface_snapshot
            else None
        )
        if persisted_tool_surface_id is not None:
            metadata["tool_surface_snapshot_persisted"] = True
            metadata["tool_surface_snapshot_id"] = persisted_tool_surface_id
        metadata["tool_surface_id"] = tool_surface.id
        metadata["tool_surface_function_count"] = len(tool_surface.functions)
        metadata.update(tool_surface_request_metadata(tool_surface))
        snapshot_input_items = _runtime_input_items_from_request_render_snapshot(
            request_render_snapshot,
        )
        if (
            not snapshot_input_items
            and request_render_snapshot is not None
            and _mode_requires_transcript_input(draft_with_snapshot.mode)
        ):
            raise _validation_error(
                "Request render snapshot did not project any runtime input items.",
                code="request_render_projected_input_required",
                details={
                    "mode": _mode_value(draft_with_snapshot.mode),
                    "session_key": draft_with_snapshot.session_key,
                    "active_session_id": draft_with_snapshot.active_session_id,
                    "request_render_snapshot_id": (
                        request_render_snapshot.snapshot_id
                        if request_render_snapshot is not None
                        else None
                    ),
                    "request_context_source": _request_render_context_source(
                        request_render_snapshot,
                    ),
                },
            )
        if (
            request_render_snapshot is None
            and _mode_requires_transcript_input(draft_with_snapshot.mode)
        ):
            raise _validation_error(
                "Runtime LLM request construction requires a request render snapshot.",
                code="request_render_snapshot_required",
                details={
                    "mode": _mode_value(draft_with_snapshot.mode),
                    "session_key": draft_with_snapshot.session_key,
                    "active_session_id": draft_with_snapshot.active_session_id,
                },
            )
        runtime_input_items = (
            snapshot_input_items
            if snapshot_input_items
            else ()
        )
        (
            runtime_input_items,
            input_filter_report,
        ) = _filter_runtime_input_items_for_request_render_snapshot(
            runtime_input_items,
            request_render_snapshot,
        )
        input_items = sanitize_runtime_input_items_for_capabilities(
            runtime_input_items,
            llm_capabilities=draft_with_snapshot.llm_capabilities,
        )
        if not input_items and _mode_requires_transcript_input(draft_with_snapshot.mode):
            raise _validation_error(
                "LLM request construction requires a non-empty runtime transcript.",
                code="runtime_transcript_input_required",
                details={
                    "mode": _mode_value(draft_with_snapshot.mode),
                    "session_key": draft_with_snapshot.session_key,
                    "active_session_id": draft_with_snapshot.active_session_id,
                    "request_render_snapshot_id": (
                        request_render_snapshot.snapshot_id
                        if request_render_snapshot is not None
                        else None
                    ),
                },
            )
        metadata.update(
            runtime_input_item_mode_metadata(
                input_items=input_items,
            ),
        )
        if snapshot_input_items:
            metadata["runtime_input_source"] = "request_render_snapshot"
            metadata["request_render_projected_input_item_count"] = len(
                snapshot_input_items,
            )
        metadata["runtime_input_filter"] = input_filter_report
        canonical_messages = messages_from_runtime_input_items(
            input_items,
        )
        provider_context_messages = provider_context_messages_from_messages(
            draft_with_snapshot.messages,
        )
        return RuntimeLlmRequest(
            llm_id=draft_with_snapshot.llm_id,
            session_key=draft_with_snapshot.session_key,
            active_session_id=draft_with_snapshot.active_session_id,
            messages=canonical_messages,
            provider_context_messages=provider_context_messages,
            transcript=RuntimeLlmTranscript(
                items=input_items,
                policy=runtime_transcript_policy(
                    draft_with_snapshot.transcript_policy,
                    require_tool_call=draft_with_snapshot.surface_policy.require_tool_call,
                ),
            ),
            tool_schemas=visible_tool_schemas,
            request_render_snapshot=_request_render_snapshot_from_snapshot(
                request_render_snapshot,
            ),
            tool_surface=tool_surface,
            reasoning_config=dict(reasoning_config or {}),
            output_contract=dict(output_contract or {}),
            provider_options=dict(provider_options or {}),
            metadata=metadata,
            blocked_tool_access=tuple(
                item.to_payload()
                for item in resolved_tools_for_envelope.blocked_access
            ),
        )

    def _persist_tool_surface_snapshot(
        self,
        *,
        draft: RuntimeLlmRequestDraft,
        tool_surface: "RuntimeToolSurface",
        resolved_tools: ResolvedToolSet | _ResolvedToolSetView,
        run_id: str | None,
        agent_id: str | None,
        request_render_snapshot: RequestRenderSnapshotRecord | None,
    ) -> str | None:
        if self.tool_surface_snapshot_builder is None:
            return None
        tool_ids = tuple(item.tool.id for item in resolved_tools.tools)
        result = self.tool_surface_snapshot_builder(
            session_id=draft.active_session_id,
            run_id=run_id,
            agent_id=agent_id,
            surface_id=tool_surface.id,
            tool_ids=tool_ids,
            persist=True,
            runtime_context={
                "agent_id": agent_id,
                "run_id": run_id,
                "session_key": draft.session_key,
                "active_session_id": draft.active_session_id,
                "request_render_snapshot_id": (
                    request_render_snapshot.snapshot_id
                    if request_render_snapshot is not None
                    else None
                ),
                "provider_visible_tool_count": len(tool_ids),
            },
        )
        return _surface_id_from_snapshot_result(result)

    @staticmethod
    def _draft_with_request_render_snapshot_report(
        draft: RuntimeLlmRequestDraft,
        request_render_snapshot: RequestRenderSnapshotRecord | None,
    ) -> RuntimeLlmRequestDraft:
        if request_render_snapshot is None or draft.report is None:
            return draft
        return replace(
            draft,
            report=replace(
                draft.report,
                request_render_snapshot=_request_render_snapshot_report(
                    snapshot_id=request_render_snapshot.snapshot_id,
                    estimate=(
                        dict(request_render_snapshot.estimate)
                        if isinstance(request_render_snapshot.estimate, dict)
                        else {}
                    ),
                    included_node_ids=tuple(
                        request_render_snapshot.included_node_ids,
                    ),
                    mirrored_node_ids=tuple(
                        request_render_snapshot.mirrored_node_ids,
                    ),
                ),
            ),
        )

def build_llm_request_metadata(
    *,
    draft: RuntimeLlmRequestDraft,
    request_render_snapshot_id: str | None,
    snapshot_metadata: dict[str, object],
    tool_schemas: tuple[ToolSchema, ...],
) -> dict[str, object]:
    provider_tool_schema_names = tuple(
        schema.name for schema in tool_schemas if schema.name.strip()
    )
    return build_runtime_llm_request_metadata(
        runtime_request_mode=_mode_value(draft.mode),
        runtime_request_surface=draft.surface_policy.surface,
        request_render_snapshot_id=request_render_snapshot_id,
        snapshot_metadata=snapshot_metadata,
        provider_tool_schema_names=provider_tool_schema_names,
    )


def _surface_id_from_snapshot_result(result: object) -> str | None:
    raw = getattr(result, "surface_id", None)
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    if isinstance(result, Mapping):
        raw = result.get("surface_id")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def _validation_error(
    message: str,
    *,
    code: str,
    details: dict[str, object],
) -> Exception:
    from crxzipple.modules.orchestration.domain import OrchestrationValidationError

    return OrchestrationValidationError(message, code=code, details=details)


def _request_render_snapshot_report(**kwargs: object) -> object:
    from crxzipple.modules.orchestration.application.runtime_request_report import (
        RequestRenderSnapshotReport,
    )

    return RequestRenderSnapshotReport(**kwargs)


def _mode_value(mode: object) -> str:
    return str(getattr(mode, "value", mode) or "").strip()


def _mode_requires_transcript_input(mode: object) -> bool:
    return _mode_value(mode) not in {"heartbeat", "memory_flush", "compaction"}


def _request_render_snapshot_from_snapshot(
    snapshot: RequestRenderSnapshotRecord | None,
) -> RuntimeLlmRequestRenderSnapshot:
    if snapshot is None:
        return build_runtime_request_render_snapshot()
    return build_runtime_request_render_snapshot(
        snapshot_id=snapshot.snapshot_id,
        included_node_ids=tuple(snapshot.included_node_ids),
        mirrored_node_ids=tuple(snapshot.mirrored_node_ids),
        included_refs=tuple(dict(item) for item in snapshot.included_refs),
        collapsed_refs=tuple(dict(item) for item in snapshot.collapsed_refs),
        protocol_required_refs=tuple(
            dict(item) for item in snapshot.protocol_required_refs
        ),
        estimate=snapshot.estimate or {},
        metadata=snapshot.metadata,
    )


def _filter_runtime_input_items_for_request_render_snapshot(
    input_items: tuple["LlmInputItem", ...],
    snapshot: RequestRenderSnapshotRecord | None,
) -> tuple[tuple["LlmInputItem", ...], dict[str, object]]:
    before_count = len(input_items)
    filtered, orphan_report = _drop_unpaired_function_call_items(input_items)
    mode = (
        "request_render_projected_input"
        if snapshot is not None and snapshot.projected_input_items
        else "unfiltered"
    )
    return filtered, {
        "mode": mode,
        "input_before_filter_count": before_count,
        "input_after_filter_count": len(filtered),
        "dropped_input_item_count": before_count - len(filtered),
        **orphan_report,
    }


def _drop_unpaired_function_call_items(
    input_items: tuple["LlmInputItem", ...],
) -> tuple[tuple["LlmInputItem", ...], dict[str, object]]:
    call_ids = {
        call_id
        for item in input_items
        if item.kind == "function_call"
        and (call_id := _input_item_tool_call_id(item)) is not None
    }
    output_call_ids = {
        call_id
        for item in input_items
        if item.kind == "function_call_output"
        and (call_id := _input_item_tool_call_id(item)) is not None
    }
    dropped_calls = tuple(
        item
        for item in input_items
        if item.kind == "function_call"
        and _input_item_tool_call_id(item) not in output_call_ids
    )
    dropped_outputs = tuple(
        item
        for item in input_items
        if item.kind == "function_call_output"
        and _input_item_tool_call_id(item) not in call_ids
    )
    dropped = (*dropped_calls, *dropped_outputs)
    kept = tuple(item for item in input_items if item not in dropped)
    if not dropped:
        return input_items, {"dropped_orphan_function_call_count": 0}
    report = {
        "dropped_orphan_function_call_count": len(dropped_calls),
        "dropped_orphan_function_call_ids": [
            call_id
            for item in dropped_calls
            if (call_id := _input_item_tool_call_id(item)) is not None
        ],
    }
    if dropped_outputs:
        report["dropped_orphan_function_call_output_count"] = len(dropped_outputs)
        report["dropped_orphan_function_call_output_ids"] = [
            call_id
            for item in dropped_outputs
            if (call_id := _input_item_tool_call_id(item)) is not None
        ]
    return kept, report


def _runtime_input_items_from_request_render_snapshot(
    snapshot: RequestRenderSnapshotRecord | None,
) -> tuple["LlmInputItem", ...]:
    if snapshot is None or not snapshot.projected_input_items:
        return ()
    return runtime_input_items_from_projected_payloads(
        tuple(raw for raw in snapshot.projected_input_items if isinstance(raw, Mapping)),
        default_source="context_slice",
    )


def _request_render_context_source(
    snapshot: RequestRenderSnapshotRecord | None,
) -> str | None:
    if snapshot is None or not isinstance(snapshot.metadata, Mapping):
        return None
    value = snapshot.metadata.get("request_context_source")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _input_item_tool_call_id(item: "LlmInputItem") -> str | None:
    metadata = item.metadata if isinstance(item.metadata, Mapping) else {}
    payload = item.payload if isinstance(item.payload, Mapping) else {}
    return _first_text(
        metadata.get("tool_call_id"),
        metadata.get("call_id"),
        payload.get("tool_call_id"),
        payload.get("call_id"),
    )


def _first_text(*values: object) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _tool_schemas_from_request_render_snapshot(
    snapshot: RequestRenderSnapshotRecord | None,
) -> tuple[ToolSchema, ...]:
    if snapshot is None:
        return ()
    return tool_schemas_from_projected_refs(
        tuple(raw for raw in snapshot.tool_schema_refs if isinstance(raw, Mapping)),
    )


def _tool_surface_from_resolved_tools(
    resolved_tools: ResolvedToolSet,
    *,
    tool_schemas: tuple[ToolSchema, ...],
    request_render_snapshot: RequestRenderSnapshotRecord | None,
) -> RuntimeToolSurface:
    snapshot_id = (
        request_render_snapshot.snapshot_id
        if request_render_snapshot is not None
        else "none"
    )
    schema_names = tuple(schema.name for schema in tool_schemas)
    schema_ref_by_name = _tool_schema_ref_by_name(request_render_snapshot)
    functions: list[RuntimeToolSurfaceRef] = []
    for item in resolved_tools.tools:
        schema_ref = schema_ref_by_name.get(item.schema.name, {})
        functions.append(
            RuntimeToolSurfaceRef(
                tool_id=item.tool.id,
                name=item.schema.name,
                schema=item.schema,
                target=_tool_target_label(item.target),
                source_id=_tool_schema_ref_text(schema_ref, "source_id"),
                group_key=_tool_schema_ref_text(schema_ref, "group_key"),
                always_visible=item.schema.name in schema_names,
                enabled=True,
                metadata=_tool_surface_ref_metadata(schema_ref),
            ),
        )
    return RuntimeToolSurface(
        id=f"tool_surface:{snapshot_id}",
        functions=tuple(functions),
        mirrored_schema_names=schema_names,
        blocked_access_count=len(resolved_tools.blocked_access),
        metadata={
            "request_render_snapshot_id": (
                request_render_snapshot.snapshot_id
                if request_render_snapshot is not None
                else None
            ),
            "tool_schema_count": len(schema_names),
            "mirrored_schema_name_count": len(schema_names),
            "function_count": len(functions),
        },
    )


def _tool_schema_ref_by_name(
    snapshot: RequestRenderSnapshotRecord | None,
) -> dict[str, dict[str, object]]:
    if snapshot is None:
        return {}
    refs: dict[str, dict[str, object]] = {}
    for raw_ref in snapshot.tool_schema_refs:
        if not isinstance(raw_ref, Mapping):
            continue
        name = _tool_schema_ref_text(raw_ref, "name", "function_name")
        if name is None or name in refs:
            continue
        refs[name] = dict(raw_ref)
    return refs


def _tool_surface_ref_metadata(ref: Mapping[str, object]) -> dict[str, object]:
    metadata: dict[str, object] = {}
    for key in (
        "source",
        "node_id",
        "tool_ref_id",
    ):
        value = _tool_schema_ref_text(ref, key)
        if value is not None:
            metadata[key] = value
    function_name = _tool_schema_ref_text(ref, "function_name", "name")
    if function_name is not None:
        metadata["function_name"] = function_name
    return metadata


def _tool_schema_ref_text(
    ref: Mapping[str, object],
    *keys: str,
) -> str | None:
    for key in keys:
        value = ref.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _tool_target_label(target: object) -> str:
    mode = getattr(target, "mode", None)
    strategy = getattr(target, "strategy", None)
    environment = getattr(target, "environment", None)
    parts = []
    for value in (mode, strategy, environment):
        if value is None:
            continue
        parts.append(str(getattr(value, "value", value)))
    return ":".join(parts) or "unknown"


__all__ = [
    "RuntimeLlmRequestBuilder",
    "build_llm_request_metadata",
]
