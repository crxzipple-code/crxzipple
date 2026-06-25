from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from crxzipple.modules.llm.application.runtime_request import (
    RuntimeLlmRequest,
    RuntimeLlmTranscript,
)
from crxzipple.modules.llm.application.runtime_request_factory_helpers import (
    build_llm_request_metadata,
    mode_requires_transcript_input,
    mode_value,
    request_render_snapshot_from_snapshot,
    request_render_snapshot_report,
    runtime_context_metadata,
    surface_id_from_snapshot_result,
    validation_error,
)
from crxzipple.modules.llm.application.runtime_input_items import (
    messages_from_runtime_input_items,
    provider_context_messages_from_messages,
    runtime_input_item_mode_metadata,
    runtime_transcript_policy,
    sanitize_runtime_input_items_for_capabilities,
)
from crxzipple.modules.llm.application.runtime_request_input_filter import (
    filter_runtime_input_items_for_request_render_snapshot,
    request_render_context_source,
    runtime_input_items_from_request_render_snapshot,
)
from crxzipple.modules.llm.application.runtime_tool_surface import (
    RuntimeToolSurface,
    request_time_tool_surface,
    tool_surface_request_metadata,
)
from crxzipple.modules.llm.application.runtime_request_tool_surface_builder import (
    tool_schemas_from_request_render_snapshot,
    tool_surface_from_resolved_tools,
)
from crxzipple.modules.llm.domain import ToolSchema

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
        return self._draft_withrequest_render_snapshot_report(
            draft,
            request_render_snapshot,
        )

    @staticmethod
    def visible_tool_schema_names(
        request_render_snapshot: RequestRenderSnapshotRecord | None,
    ) -> tuple[str, ...]:
        return tuple(
            schema.name
            for schema in tool_schemas_from_request_render_snapshot(
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
        run_id: str | None = None,
        agent_id: str | None = None,
    ) -> dict[str, object]:
        return build_llm_request_metadata(
            draft=draft,
            request_render_snapshot_id=request_render_snapshot_id,
            snapshot_metadata=snapshot_metadata,
            tool_schemas=tool_schemas,
            run_id=run_id,
            agent_id=agent_id,
            session_key=draft.session_key,
            active_session_id=draft.active_session_id,
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
        visible_tool_schemas = tool_schemas_from_request_render_snapshot(
            request_render_snapshot,
        )
        tool_surface = tool_surface_from_resolved_tools(
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
            run_id=run_id,
            agent_id=agent_id,
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
        runtime_context = runtime_context_metadata(draft_with_snapshot.runtime_context)
        for key, value in {
            "run_id": run_id,
            "agent_id": agent_id,
            "session_key": draft_with_snapshot.session_key,
            "active_session_id": draft_with_snapshot.active_session_id,
        }.items():
            text = str(value or "").strip()
            if text:
                runtime_context.setdefault(key, text)
        if runtime_context:
            metadata["runtime_context"] = runtime_context
        metadata["tool_surface_id"] = tool_surface.id
        metadata["tool_surface_function_count"] = len(tool_surface.functions)
        metadata.update(tool_surface_request_metadata(tool_surface))
        snapshot_input_items = runtime_input_items_from_request_render_snapshot(
            request_render_snapshot,
        )
        if (
            not snapshot_input_items
            and request_render_snapshot is not None
            and mode_requires_transcript_input(draft_with_snapshot.mode)
        ):
            raise validation_error(
                "Request render snapshot did not project any runtime input items.",
                code="request_render_projected_input_required",
                details={
                    "mode": mode_value(draft_with_snapshot.mode),
                    "session_key": draft_with_snapshot.session_key,
                    "active_session_id": draft_with_snapshot.active_session_id,
                    "request_render_snapshot_id": (
                        request_render_snapshot.snapshot_id
                        if request_render_snapshot is not None
                        else None
                    ),
                    "request_context_source": request_render_context_source(
                        request_render_snapshot,
                    ),
                },
            )
        if (
            request_render_snapshot is None
            and mode_requires_transcript_input(draft_with_snapshot.mode)
        ):
            raise validation_error(
                "Runtime LLM request construction requires a request render snapshot.",
                code="request_render_snapshot_required",
                details={
                    "mode": mode_value(draft_with_snapshot.mode),
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
        ) = filter_runtime_input_items_for_request_render_snapshot(
            runtime_input_items,
            request_render_snapshot,
        )
        input_items = sanitize_runtime_input_items_for_capabilities(
            runtime_input_items,
            llm_capabilities=draft_with_snapshot.llm_capabilities,
        )
        if not input_items and mode_requires_transcript_input(draft_with_snapshot.mode):
            raise validation_error(
                "LLM request construction requires a non-empty runtime transcript.",
                code="runtime_transcript_input_required",
                details={
                    "mode": mode_value(draft_with_snapshot.mode),
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
            request_render_snapshot=request_render_snapshot_from_snapshot(
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
        return surface_id_from_snapshot_result(result)

    @staticmethod
    def _draft_withrequest_render_snapshot_report(
        draft: RuntimeLlmRequestDraft,
        request_render_snapshot: RequestRenderSnapshotRecord | None,
    ) -> RuntimeLlmRequestDraft:
        if request_render_snapshot is None or draft.report is None:
            return draft
        return replace(
            draft,
            report=replace(
                draft.report,
                request_render_snapshot=request_render_snapshot_report(
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

__all__ = [
    "RuntimeLlmRequestBuilder",
    "build_llm_request_metadata",
]
