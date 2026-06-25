from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from crxzipple.modules.llm.application.runtime_input_items import (
    metadata_text as _metadata_text,
)
from crxzipple.modules.llm.application.runtime_request_preview import (
    estimate_summary as _estimate_summary,
    request_render_snapshot_diagnostics as _request_render_snapshot_diagnostics,
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
        "run_id",
        "agent_id",
        "session_key",
        "active_session_id",
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
    runtime_context = metadata.get("runtime_context")
    if isinstance(runtime_context, Mapping):
        for key in (
            "agent_id",
            "run_id",
            "llm_id",
            "session_key",
            "active_session_id",
            "agent_home_dir",
            "workspace_dir",
            "available_tool_ids",
            "current_step",
            "max_steps",
            "remaining_steps",
            "step_budget_status",
        ):
            value = runtime_context.get(key)
            if value not in (None, "", {}, []):
                context.setdefault(key, value)
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


__all__ = [
    "RuntimeLlmRequestRenderSnapshot",
    "RuntimeRequestRenderContext",
    "build_runtime_llm_request_metadata",
    "build_runtime_request_render_snapshot",
    "runtime_request_context_from_metadata",
]
