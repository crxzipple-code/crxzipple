from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any
from uuid import uuid4

from crxzipple.modules.llm.domain import LlmMessage, LlmMessageRole
from crxzipple.modules.orchestration.application.ports import (
    ContextRenderSnapshotRecord,
)
from crxzipple.modules.orchestration.application.prompt_input import (
    RunPromptInput,
)
from crxzipple.modules.orchestration.application.prompting import (
    ContextRenderReport,
)
from crxzipple.modules.orchestration.application.tool_resolver import ResolvedToolSet
from crxzipple.shared.content_blocks import text_content_block
from crxzipple.shared.context_render_budget import context_render_budget_metadata


ToolSurfaceSnapshotBuilder = Callable[..., object]


@dataclass(slots=True)
class ProviderPromptRequestBuilder:
    """Build provider-facing prompt request pieces from a Context render snapshot.

    Orchestration owns run lifecycle. Context Workspace owns the prompt tree.
    This builder is the narrow translation layer between those facts and the
    provider message/tool-schema shape required by the LLM module.
    """

    tool_surface_snapshot_builder: ToolSurfaceSnapshotBuilder | None = None

    def prompt_with_context_snapshot(
        self,
        prompt: RunPromptInput,
        context_render_snapshot: ContextRenderSnapshotRecord | None,
        *,
        include_context_messages: bool = True,
    ) -> RunPromptInput:
        prompt = self._prompt_with_context_render_report(
            prompt,
            context_render_snapshot,
        )
        prompt = self._prompt_with_context_provider_mirror(
            prompt,
            context_render_snapshot,
        )
        if not include_context_messages:
            return self._prompt_with_context_delta(
                prompt,
                context_render_snapshot,
            )
        prompt = self._prompt_with_context_workspace_body(
            prompt,
            context_render_snapshot,
        )
        return self._prompt_with_context_artifact_mirror(
            prompt,
            context_render_snapshot,
        )

    def resolved_tools_for_prompt(
        self,
        resolved_tools: ResolvedToolSet,
        prompt: RunPromptInput,
        context_render_snapshot: ContextRenderSnapshotRecord | None,
    ) -> ResolvedToolSet:
        if prompt.surface_policy.surface != "interactive":
            return resolved_tools
        if context_render_snapshot is None or context_render_snapshot.tool_schemas is None:
            return ResolvedToolSet(
                tools=(),
                blocked_access=resolved_tools.blocked_access,
            )
        visible_tool_names = {
            schema.name for schema in prompt.tool_schemas if schema.name.strip()
        }
        return ResolvedToolSet(
            tools=tuple(
                item
                for item in resolved_tools.tools
                if item.schema.name in visible_tool_names
                or item.tool.id in visible_tool_names
            ),
            blocked_access=resolved_tools.blocked_access,
        )

    def request_metadata(
        self,
        *,
        prompt: RunPromptInput,
        context_render_snapshot_id: str | None,
        snapshot_metadata: dict[str, object],
    ) -> dict[str, object]:
        return build_llm_request_metadata(
            prompt=prompt,
            context_render_snapshot_id=context_render_snapshot_id,
            snapshot_metadata=snapshot_metadata,
        )

    def request_envelope(
        self,
        *,
        prompt: RunPromptInput,
        context_render_snapshot: ContextRenderSnapshotRecord | None,
        resolved_tools: ResolvedToolSet | None,
        snapshot_metadata: dict[str, object],
        run_id: str | None = None,
        agent_id: str | None = None,
        persist_tool_surface_snapshot: bool = True,
        provider_options: dict[str, object] | None = None,
        reasoning_config: dict[str, object] | None = None,
        output_contract: dict[str, object] | None = None,
        include_context_messages: bool = True,
    ) -> "LlmRequestEnvelope":
        prompt_with_snapshot = self.prompt_with_context_snapshot(
            prompt,
            context_render_snapshot,
            include_context_messages=include_context_messages,
        )
        tool_surface = ToolSurface.from_resolved_tools(
            resolved_tools_for_envelope := self.resolved_tools_for_prompt(
                resolved_tools or ResolvedToolSet(tools=()),
                prompt_with_snapshot,
                context_render_snapshot,
            ),
            tool_schemas=prompt_with_snapshot.tool_schemas,
            context_render_snapshot=context_render_snapshot,
        )
        if persist_tool_surface_snapshot and self.tool_surface_snapshot_builder is not None:
            tool_surface = _request_time_tool_surface(tool_surface)
        metadata = self.request_metadata(
            prompt=prompt_with_snapshot,
            context_render_snapshot_id=(
                context_render_snapshot.snapshot_id
                if context_render_snapshot is not None
                else None
            ),
            snapshot_metadata=snapshot_metadata,
        )
        persisted_tool_surface_id = (
            self._persist_tool_surface_snapshot(
                prompt=prompt_with_snapshot,
                tool_surface=tool_surface,
                resolved_tools=resolved_tools_for_envelope,
                run_id=run_id,
                agent_id=agent_id,
                context_render_snapshot=context_render_snapshot,
            )
            if persist_tool_surface_snapshot
            else None
        )
        if persisted_tool_surface_id is not None:
            metadata["tool_surface_snapshot_persisted"] = True
            metadata["tool_surface_snapshot_id"] = persisted_tool_surface_id
        metadata["tool_surface_id"] = tool_surface.id
        metadata["tool_surface_function_count"] = len(tool_surface.functions)
        metadata.update(_tool_surface_metadata(tool_surface))
        return LlmRequestEnvelope(
            llm_id=prompt_with_snapshot.llm_id,
            session_key=prompt_with_snapshot.session_key,
            active_session_id=prompt_with_snapshot.active_session_id,
            messages=prompt_with_snapshot.messages,
            tool_schemas=prompt_with_snapshot.tool_schemas,
            context_surface=ContextSurface.from_snapshot(context_render_snapshot),
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
        prompt: RunPromptInput,
        tool_surface: "ToolSurface",
        resolved_tools: ResolvedToolSet,
        run_id: str | None,
        agent_id: str | None,
        context_render_snapshot: ContextRenderSnapshotRecord | None,
    ) -> str | None:
        if self.tool_surface_snapshot_builder is None:
            return None
        tool_ids = tuple(item.tool.id for item in resolved_tools.tools)
        result = self.tool_surface_snapshot_builder(
            session_id=prompt.active_session_id,
            run_id=run_id,
            agent_id=agent_id,
            surface_id=tool_surface.id,
            tool_ids=tool_ids,
            persist=True,
            runtime_context={
                "agent_id": agent_id,
                "run_id": run_id,
                "session_key": prompt.session_key,
                "active_session_id": prompt.active_session_id,
                "context_render_snapshot_id": (
                    context_render_snapshot.snapshot_id
                    if context_render_snapshot is not None
                    else None
                ),
                "provider_visible_tool_count": len(tool_ids),
            },
        )
        return _surface_id_from_snapshot_result(result)

    @staticmethod
    def _prompt_with_context_render_report(
        prompt: RunPromptInput,
        context_render_snapshot: ContextRenderSnapshotRecord | None,
    ) -> RunPromptInput:
        if context_render_snapshot is None or prompt.report is None:
            return prompt
        return replace(
            prompt,
            report=replace(
                prompt.report,
                context_render=ContextRenderReport(
                    snapshot_id=context_render_snapshot.snapshot_id,
                    estimate=(
                        dict(context_render_snapshot.estimate)
                        if isinstance(context_render_snapshot.estimate, dict)
                        else {}
                    ),
                    included_node_ids=tuple(
                        context_render_snapshot.included_node_ids,
                    ),
                    mirrored_node_ids=tuple(
                        context_render_snapshot.mirrored_node_ids,
                    ),
                ),
            ),
        )

    @staticmethod
    def _prompt_with_context_provider_mirror(
        prompt: RunPromptInput,
        context_render_snapshot: ContextRenderSnapshotRecord | None,
    ) -> RunPromptInput:
        if prompt.surface_policy.surface != "interactive":
            return prompt
        if context_render_snapshot is None or context_render_snapshot.tool_schemas is None:
            return replace(prompt, tool_schemas=())
        return replace(
            prompt,
            tool_schemas=context_render_snapshot.tool_schemas,
        )

    @staticmethod
    def _prompt_with_context_workspace_body(
        prompt: RunPromptInput,
        context_render_snapshot: ContextRenderSnapshotRecord | None,
    ) -> RunPromptInput:
        if context_render_snapshot is None:
            return prompt
        prompt_body = (context_render_snapshot.prompt_body or "").strip()
        if not prompt_body:
            return prompt
        context_message = LlmMessage(
            role=LlmMessageRole.SYSTEM,
            content=prompt_body,
            metadata={
                "prompt_block_kind": "context_workspace",
                "context_render_snapshot_id": context_render_snapshot.snapshot_id,
            },
        )
        return replace(
            prompt,
            messages=_insert_after_system_prefix(prompt.messages, context_message),
        )

    @staticmethod
    def _prompt_with_context_delta(
        prompt: RunPromptInput,
        context_render_snapshot: ContextRenderSnapshotRecord | None,
    ) -> RunPromptInput:
        delta = _context_delta_payload(context_render_snapshot)
        if delta is None:
            return prompt
        context_message = LlmMessage(
            role=LlmMessageRole.SYSTEM,
            content=str(delta["prompt_body"]),
            metadata={
                "prompt_block_kind": "context_workspace_delta",
                "context_render_snapshot_id": (
                    context_render_snapshot.snapshot_id
                    if context_render_snapshot is not None
                    else None
                ),
                "baseline_snapshot_id": delta.get("baseline_snapshot_id"),
                "baseline_revision": delta.get("baseline_revision"),
                "current_revision": delta.get("current_revision"),
                "added_node_count": len(_list_value(delta.get("added_node_ids"))),
                "removed_node_count": len(_list_value(delta.get("removed_node_ids"))),
                "added_tool_schema_count": len(
                    _list_value(delta.get("added_tool_schema_names")),
                ),
                "removed_tool_schema_count": len(
                    _list_value(delta.get("removed_tool_schema_names")),
                ),
            },
        )
        return replace(
            prompt,
            messages=_insert_after_system_prefix(prompt.messages, context_message),
        )

    @staticmethod
    def _prompt_with_context_artifact_mirror(
        prompt: RunPromptInput,
        context_render_snapshot: ContextRenderSnapshotRecord | None,
    ) -> RunPromptInput:
        if context_render_snapshot is None:
            return prompt
        artifact_blocks = tuple(context_render_snapshot.artifact_content_blocks)
        if not artifact_blocks:
            return prompt
        artifact_message = LlmMessage(
            role=LlmMessageRole.USER,
            content=[
                text_content_block(
                    "Opened context artifact attachments for this turn:",
                ),
                *artifact_blocks,
            ],
            metadata={
                "prompt_block_kind": "context_artifacts",
                "context_render_snapshot_id": context_render_snapshot.snapshot_id,
            },
        )
        return replace(
            prompt,
            messages=prompt.messages + (artifact_message,),
        )


def build_llm_request_metadata(
    *,
    prompt: RunPromptInput,
    context_render_snapshot_id: str | None,
    snapshot_metadata: dict[str, object],
) -> dict[str, object]:
    runtime_contract = snapshot_metadata.get("runtime_contract")
    metadata: dict[str, object] = {
        "prompt_mode": prompt.mode.value,
        "prompt_input": prompt.surface_policy.surface,
        "tree_schema_version": snapshot_metadata.get("tree_schema_version"),
        "context_render_snapshot_id": context_render_snapshot_id,
        "context_history_delivery": snapshot_metadata.get("history_delivery"),
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
        "tool_schema_mirror_groups": snapshot_metadata.get(
            "tool_schema_mirror_groups",
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
        "tool_schema_mirror_default_group_refs": snapshot_metadata.get(
            "tool_schema_mirror_default_group_refs",
        ),
        "tool_schema_mirror_default_group_ref_count": snapshot_metadata.get(
            "tool_schema_mirror_default_group_ref_count",
        ),
        "tool_schema_mirror_default_group_matches": snapshot_metadata.get(
            "tool_schema_mirror_default_group_matches",
        ),
        "tool_schema_mirror_default_group_match_count": snapshot_metadata.get(
            "tool_schema_mirror_default_group_match_count",
        ),
        "tool_schema_mirror_default_schema_reasons": snapshot_metadata.get(
            "tool_schema_mirror_default_schema_reasons",
        ),
        "tool_schema_mirror_default_mirrored": snapshot_metadata.get(
            "tool_schema_mirror_default_mirrored",
        ),
        "tool_schema_mirror_skipped": snapshot_metadata.get(
            "tool_schema_mirror_skipped",
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
        "browser_investigation_affordance_status": snapshot_metadata.get(
            "browser_investigation_affordance_status",
        ),
        "browser_investigation_route_bias": snapshot_metadata.get(
            "browser_investigation_route_bias",
        ),
        "browser_investigation_present_paths": snapshot_metadata.get(
            "browser_investigation_present_paths",
        ),
        "browser_investigation_missing_paths": snapshot_metadata.get(
            "browser_investigation_missing_paths",
        ),
        "browser_investigation_schema_names": snapshot_metadata.get(
            "browser_investigation_schema_names",
        ),
        "browser_investigation_runtime_code_schema_names": snapshot_metadata.get(
            "browser_investigation_runtime_code_schema_names",
        ),
        "browser_investigation_network_schema_names": snapshot_metadata.get(
            "browser_investigation_network_schema_names",
        ),
        "browser_investigation_stateful_schema_names": snapshot_metadata.get(
            "browser_investigation_stateful_schema_names",
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
        "work_plan_status": snapshot_metadata.get("work_plan_status"),
        "work_plan_phase": snapshot_metadata.get("work_plan_phase"),
        "work_plan_update_reason": snapshot_metadata.get("work_plan_update_reason"),
        "work_plan_phase_changed": snapshot_metadata.get("work_plan_phase_changed"),
        "work_plan_update_count": snapshot_metadata.get("work_plan_update_count"),
        "final_response_requires_evidence_path": snapshot_metadata.get(
            "final_response_requires_evidence_path",
        ),
        "verified_evidence_path_count": snapshot_metadata.get(
            "verified_evidence_path_count",
        ),
        "verified_evidence_paths": snapshot_metadata.get("verified_evidence_paths"),
        "browser_verified_evidence_path_count": snapshot_metadata.get(
            "browser_verified_evidence_path_count",
        ),
        "browser_verified_evidence_paths": snapshot_metadata.get(
            "browser_verified_evidence_paths",
        ),
        "unverified_evidence_paths": snapshot_metadata.get(
            "unverified_evidence_paths",
        ),
        "mirrored_node_count": snapshot_metadata.get("mirrored_node_count"),
        "llm_request_policy": snapshot_metadata.get("llm_request_policy"),
    }
    metadata.update(context_render_budget_metadata(snapshot_metadata))
    session_item_refs = _direct_session_item_refs(prompt.messages)
    tool_protocol_refs = _direct_tool_protocol_refs(prompt.messages)
    current_inbound_ref = _current_inbound_ref(
        session_item_refs=session_item_refs,
        snapshot_metadata=snapshot_metadata,
    )
    if session_item_refs:
        metadata["direct_session_item_refs"] = session_item_refs
        metadata["direct_session_item_count"] = len(session_item_refs)
        item_frontier = _direct_session_item_frontier(session_item_refs)
        if item_frontier:
            metadata["direct_session_item_frontier"] = item_frontier
    if tool_protocol_refs:
        metadata["direct_tool_protocol_refs"] = tool_protocol_refs
        metadata["direct_tool_protocol_call_ids"] = _tool_protocol_call_ids(
            tool_protocol_refs,
        )
    transcript_budget = _prompt_report_transcript_budget(prompt)
    if transcript_budget:
        metadata["direct_transcript_budget"] = transcript_budget
    if current_inbound_ref:
        metadata["current_inbound_ref"] = current_inbound_ref
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


def _surface_id_from_snapshot_result(result: object) -> str | None:
    raw = getattr(result, "surface_id", None)
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    if isinstance(result, Mapping):
        raw = result.get("surface_id")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def _request_time_tool_surface(tool_surface: "ToolSurface") -> "ToolSurface":
    return replace(
        tool_surface,
        id=f"{tool_surface.id}:{uuid4().hex}",
        metadata={
            **tool_surface.metadata,
            "base_tool_surface_id": tool_surface.id,
            "request_time_unique": True,
        },
    )


def _context_delta_payload(
    context_render_snapshot: ContextRenderSnapshotRecord | None,
) -> dict[str, object] | None:
    if context_render_snapshot is None:
        return None
    raw_delta = context_render_snapshot.metadata.get("context_delta")
    if not isinstance(raw_delta, dict):
        return None
    prompt_body = raw_delta.get("prompt_body")
    if not isinstance(prompt_body, str) or not prompt_body.strip():
        return None
    return {**raw_delta, "prompt_body": prompt_body.strip()}


def _list_value(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


@dataclass(frozen=True, slots=True)
class ContextSurface:
    snapshot_id: str | None = None
    rendered_context: str | None = None
    included_node_ids: tuple[str, ...] = ()
    mirrored_node_ids: tuple[str, ...] = ()
    included_refs: tuple[dict[str, object], ...] = ()
    collapsed_refs: tuple[dict[str, object], ...] = ()
    protocol_required_refs: tuple[dict[str, object], ...] = ()
    estimate: dict[str, object] = field(default_factory=dict)
    provider_attachment_mirror: dict[str, object] = field(default_factory=dict)
    diagnostics: dict[str, object] = field(default_factory=dict)

    @classmethod
    def from_snapshot(
        cls,
        snapshot: ContextRenderSnapshotRecord | None,
    ) -> "ContextSurface":
        if snapshot is None:
            return cls()
        return cls(
            snapshot_id=snapshot.snapshot_id,
            rendered_context=snapshot.prompt_body,
            included_node_ids=tuple(snapshot.included_node_ids),
            mirrored_node_ids=tuple(snapshot.mirrored_node_ids),
            included_refs=tuple(dict(item) for item in snapshot.included_refs),
            collapsed_refs=tuple(dict(item) for item in snapshot.collapsed_refs),
            protocol_required_refs=tuple(
                dict(item) for item in snapshot.protocol_required_refs
            ),
            estimate=dict(snapshot.estimate or {}),
            provider_attachment_mirror=dict(snapshot.provider_attachments),
            diagnostics=_context_surface_diagnostics(snapshot),
        )

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "included_node_ids": list(self.included_node_ids),
            "mirrored_node_ids": list(self.mirrored_node_ids),
            "included_refs": [dict(item) for item in self.included_refs],
            "collapsed_refs": [dict(item) for item in self.collapsed_refs],
            "protocol_required_refs": [
                dict(item) for item in self.protocol_required_refs
            ],
            "estimate": dict(self.estimate),
            "provider_attachment_mirror": dict(self.provider_attachment_mirror),
            "diagnostics": dict(self.diagnostics),
        }
        if self.snapshot_id is not None:
            payload["snapshot_id"] = self.snapshot_id
        if self.rendered_context is not None:
            payload["rendered_context"] = self.rendered_context
        return {
            key: value
            for key, value in payload.items()
            if value not in (None, "", {}, [])
        }


@dataclass(frozen=True, slots=True)
class ToolSurfaceFunction:
    tool_id: str
    name: str
    schema: ToolSchema
    target: str
    source_id: str | None = None
    group_key: str | None = None
    always_visible: bool = True
    enabled: bool = True

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
        return payload


@dataclass(frozen=True, slots=True)
class ToolSurface:
    id: str
    functions: tuple[ToolSurfaceFunction, ...] = ()
    mirrored_schema_names: tuple[str, ...] = ()
    blocked_access_count: int = 0
    metadata: dict[str, object] = field(default_factory=dict)

    @classmethod
    def from_resolved_tools(
        cls,
        resolved_tools: ResolvedToolSet,
        *,
        tool_schemas: tuple[ToolSchema, ...],
        context_render_snapshot: ContextRenderSnapshotRecord | None,
    ) -> "ToolSurface":
        snapshot_id = (
            context_render_snapshot.snapshot_id
            if context_render_snapshot is not None
            else "none"
        )
        schema_names = tuple(schema.name for schema in tool_schemas)
        functions: list[ToolSurfaceFunction] = []
        for item in resolved_tools.tools:
            source_id, group_key = _tool_surface_source_ref(
                item.schema.name,
                context_render_snapshot,
            )
            functions.append(
                ToolSurfaceFunction(
                    tool_id=item.tool.id,
                    name=item.schema.name,
                    schema=item.schema,
                    target=_tool_target_label(item.target),
                    source_id=source_id,
                    group_key=group_key,
                    always_visible=item.schema.name in schema_names,
                    enabled=True,
                ),
            )
        return cls(
            id=f"tool_surface:{snapshot_id}",
            functions=tuple(functions),
            mirrored_schema_names=schema_names,
            blocked_access_count=len(resolved_tools.blocked_access),
            metadata={
                "context_render_snapshot_id": (
                    context_render_snapshot.snapshot_id
                    if context_render_snapshot is not None
                    else None
                ),
                "tool_schema_count": len(schema_names),
                "mirrored_schema_name_count": len(schema_names),
                "function_count": len(functions),
                "source_refs": _tool_surface_function_source_refs(functions),
            },
        )

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
class LlmRequestEnvelope:
    llm_id: str
    session_key: str
    active_session_id: str
    messages: tuple[LlmMessage, ...]
    tool_schemas: tuple[ToolSchema, ...]
    context_surface: ContextSurface
    tool_surface: ToolSurface
    reasoning_config: dict[str, object] = field(default_factory=dict)
    output_contract: dict[str, object] = field(default_factory=dict)
    provider_options: dict[str, object] = field(default_factory=dict)
    metadata: dict[str, object] = field(default_factory=dict)
    blocked_tool_access: tuple[dict[str, object], ...] = ()

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "llm_id": self.llm_id,
            "session_key": self.session_key,
            "active_session_id": self.active_session_id,
            "messages": [message.to_payload() for message in self.messages],
            "tool_schemas": [schema.to_payload() for schema in self.tool_schemas],
            "context_surface": self.context_surface.to_payload(),
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


def _context_surface_diagnostics(
    snapshot: ContextRenderSnapshotRecord,
) -> dict[str, object]:
    metadata = snapshot.metadata
    diagnostics: dict[str, object] = {}
    for key in (
        "tool_schema_mirror_budget_status",
        "tool_schema_mirror_skipped_count",
        "tool_schema_mirror_duplicate_count",
        "tool_schema_mirror_skipped_by_reason",
        "browser_investigation_affordance_status",
        "duplicate_tool_delivery_risk",
        "session_budget_status",
    ):
        value = metadata.get(key)
        if value not in (None, "", {}, []):
            diagnostics[key] = value
    return diagnostics


def _tool_surface_source_ref(
    schema_name: str,
    snapshot: ContextRenderSnapshotRecord | None,
) -> tuple[str | None, str | None]:
    if snapshot is None:
        return None, None
    metadata = snapshot.metadata
    matches = metadata.get("tool_schema_mirror_default_group_matches")
    if not isinstance(matches, list):
        return None, None
    for item in matches:
        if not isinstance(item, dict):
            continue
        names = item.get("matched_schema_names")
        if isinstance(names, list) and schema_name not in names:
            continue
        if item.get("name") not in (None, schema_name) and not isinstance(names, list):
            continue
        source_id = item.get("source_id")
        group_key = item.get("group_key")
        return (
            str(source_id) if source_id is not None else None,
            str(group_key) if group_key is not None else None,
        )
    return None, None


def _tool_surface_function_source_refs(
    functions: list[ToolSurfaceFunction],
) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    for function in functions:
        payload: dict[str, object] = {
            "tool_id": function.tool_id,
            "name": function.name,
            "enabled": function.enabled,
            "always_visible": function.always_visible,
        }
        if function.source_id is not None:
            payload["source_id"] = function.source_id
        if function.group_key is not None:
            payload["group_key"] = function.group_key
        refs.append(payload)
    return refs


def _tool_surface_metadata(tool_surface: ToolSurface) -> dict[str, object]:
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


def _tool_surface_function_refs(
    functions: tuple[ToolSurfaceFunction, ...],
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


def _direct_session_item_refs(
    messages: tuple[LlmMessage, ...],
) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    for message in messages:
        ref = _session_item_ref(message)
        if ref is not None:
            refs.append(ref)
    return refs


def _direct_tool_protocol_refs(
    messages: tuple[LlmMessage, ...],
) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    for message in messages:
        ref = _session_item_ref(message)
        if ref is None:
            continue
        if message.tool_call_id:
            refs.append(ref)
            continue
        if message.role is LlmMessageRole.ASSISTANT and _is_function_call_content(
            message.content,
        ):
            refs.append(ref)
    return refs


def _session_item_ref(message: LlmMessage) -> dict[str, object] | None:
    metadata = message.metadata
    item_id = _metadata_text(metadata.get("session_item_id"))
    session_id = _metadata_text(metadata.get("session_id"))
    sequence_no = _metadata_int_or_none(metadata.get("sequence_no"))
    if item_id is None or session_id is None or sequence_no is None:
        return None
    ref: dict[str, object] = {
        "item_id": item_id,
        "session_id": session_id,
        "sequence_no": sequence_no,
        "role": message.role.value,
    }
    for source_key in (
        "kind",
        "phase",
        "source_module",
        "source_kind",
        "source_id",
        "provider_item_id",
        "provider_item_type",
    ):
        value = _metadata_text(metadata.get(source_key))
        if value is not None:
            ref[source_key] = value
    tool_call_id = _metadata_text(
        metadata.get("tool_call_id") or message.tool_call_id,
    )
    if tool_call_id is not None:
        ref["tool_call_id"] = tool_call_id
    tool_name = _metadata_text(metadata.get("tool_name") or message.name)
    if tool_name is not None:
        ref["tool_name"] = tool_name
    tool_status = _metadata_text(metadata.get("tool_status"))
    if tool_status is not None:
        ref["tool_status"] = tool_status
    if metadata.get("tool_error") is not None:
        ref["tool_error_present"] = True
    return ref


def _is_function_call_content(content: object) -> bool:
    return isinstance(content, dict) and content.get("type") == "function_call"


def _direct_session_item_frontier(
    refs: list[dict[str, object]],
) -> dict[str, object]:
    sequence_numbers = [
        ref.get("sequence_no") for ref in refs if isinstance(ref.get("sequence_no"), int)
    ]
    if not sequence_numbers:
        return {}
    payload: dict[str, object] = {
        "from_sequence_no": min(sequence_numbers),
        "to_sequence_no": max(sequence_numbers),
        "item_count": len(sequence_numbers),
    }
    first_id = refs[0].get("item_id")
    last_id = refs[-1].get("item_id")
    if isinstance(first_id, str):
        payload["from_item_id"] = first_id
    if isinstance(last_id, str):
        payload["to_item_id"] = last_id
    return payload


def _prompt_report_transcript_budget(
    prompt: RunPromptInput,
) -> dict[str, object]:
    if prompt.report is None:
        return {}
    report_payload = prompt.report.to_payload()
    transcript = report_payload.get("transcript")
    if not isinstance(transcript, dict):
        return {}
    budget = transcript.get("budget")
    if not isinstance(budget, dict):
        return {}
    return dict(budget)


def _tool_protocol_call_ids(
    refs: list[dict[str, object]],
) -> list[str]:
    call_ids: list[str] = []
    for ref in refs:
        call_id = ref.get("tool_call_id")
        if not isinstance(call_id, str) or not call_id.strip():
            continue
        normalized = call_id.strip()
        if normalized not in call_ids:
            call_ids.append(normalized)
    return call_ids


def _current_inbound_ref(
    *,
    session_item_refs: list[dict[str, object]],
    snapshot_metadata: dict[str, object],
) -> dict[str, object] | None:
    current_item_id = _metadata_text(
        snapshot_metadata.get("current_inbound_session_item_id"),
    )
    if current_item_id is not None:
        for ref in session_item_refs:
            if ref.get("item_id") == current_item_id:
                return dict(ref)
        return {"item_id": current_item_id}
    return None

def _metadata_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _metadata_int_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _insert_after_system_prefix(
    messages: tuple[LlmMessage, ...],
    message: LlmMessage,
) -> tuple[LlmMessage, ...]:
    insert_at = 0
    for existing in messages:
        if existing.role is not LlmMessageRole.SYSTEM:
            break
        insert_at += 1
    return messages[:insert_at] + (message,) + messages[insert_at:]


__all__ = [
    "ProviderPromptRequestBuilder",
    "build_llm_request_metadata",
]
