from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from crxzipple.modules.context_workspace.domain import (
    ContextEstimate,
    ContextWorkspace,
)
from crxzipple.modules.context_workspace.domain.value_objects import JsonObject


@dataclass(frozen=True, slots=True)
class ContextObservationRenderInput:
    session_key: str
    run_id: str | None = None
    provider_attachments: JsonObject = field(default_factory=dict)
    metadata: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ContextObservationRenderResult:
    """Observation-only debug render of the current tree slice.

    This object is for Workbench/Trace/CLI inspection. Provider-facing LLM
    requests must consume `ContextSlice` and `RecordRequestRenderSnapshotInput`
    projections instead of this debug body.
    """

    workspace: ContextWorkspace
    debug_body: str
    estimate: ContextEstimate
    included_node_ids: tuple[str, ...]
    estimate_breakdown: JsonObject = field(default_factory=dict)
    runtime_contract: JsonObject = field(default_factory=dict)
    tree_schema_version: str = ""
    root_node_ids: tuple[str, ...] = ()
    provider_attachments: JsonObject = field(default_factory=dict)
    provider_attachment_report: JsonObject = field(default_factory=dict)
    mirrored_node_ids: tuple[str, ...] = ()
    tool_schema_mirror_available: bool = False


@dataclass(frozen=True, slots=True)
class ContextDebugDeltaInput:
    session_key: str
    baseline_snapshot_id: str
    run_id: str | None = None
    provider_attachments: JsonObject = field(default_factory=dict)
    metadata: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ContextDebugDeltaResult:
    workspace: ContextWorkspace
    baseline_snapshot_id: str
    baseline_revision: int
    current_revision: int
    changed_revision: bool
    added_node_ids: tuple[str, ...] = ()
    removed_node_ids: tuple[str, ...] = ()
    current_included_node_ids: tuple[str, ...] = ()
    baseline_included_node_ids: tuple[str, ...] = ()
    added_tool_schema_names: tuple[str, ...] = ()
    removed_tool_schema_names: tuple[str, ...] = ()
    current_tool_schema_names: tuple[str, ...] = ()
    baseline_tool_schema_names: tuple[str, ...] = ()
    debug_body: str = ""
    provider_attachments: JsonObject = field(default_factory=dict)
    provider_attachment_report: JsonObject = field(default_factory=dict)
    estimate: ContextEstimate = field(default_factory=ContextEstimate)
    metadata: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RecordContextSnapshotInput:
    """Persist an observation/debug snapshot.

    This is not the provider request snapshot. It stores the human/debug render
    body and is opt-in when exposed through HTTP.
    """

    session_key: str
    run_id: str
    debug_body: str
    provider_attachments: JsonObject = field(default_factory=dict)
    estimate: ContextEstimate = field(default_factory=ContextEstimate)
    included_node_ids: tuple[str, ...] = ()
    mirrored_node_ids: tuple[str, ...] = ()
    included_refs: tuple[JsonObject, ...] = ()
    collapsed_refs: tuple[JsonObject, ...] = ()
    protocol_required_refs: tuple[JsonObject, ...] = ()
    metadata: JsonObject = field(default_factory=dict)
    parent_snapshot_id: str | None = None
    parent_tree_revision: int | None = None
    include_metadata_defaults: bool = True
    snapshot_id: str = field(default_factory=lambda: f"ctxsnap_{uuid4().hex}")


@dataclass(frozen=True, slots=True)
class RecordRequestRenderSnapshotInput:
    """Persist the provider request projection produced from a Context Slice."""

    session_key: str
    run_id: str
    tree_revision: int
    workspace_id: str | None = None
    turn_id: str | None = None
    step_id: str | None = None
    llm_invocation_id: str | None = None
    provider: str | None = None
    transport: str | None = None
    model: str | None = None
    renderer_id: str | None = None
    renderer_version: str | None = None
    session_frontier_revision: str | None = None
    input_item_refs: tuple[JsonObject, ...] = ()
    projected_input_items: tuple[JsonObject, ...] = ()
    tool_schema_refs: tuple[JsonObject, ...] = ()
    resource_refs: tuple[JsonObject, ...] = ()
    request_hash: str | None = None
    estimated_tokens: int | None = None
    render_report: JsonObject = field(default_factory=dict)
    timings: JsonObject = field(default_factory=dict)
    metadata: JsonObject = field(default_factory=dict)
    snapshot_id: str = field(default_factory=lambda: f"reqsnap_{uuid4().hex}")


__all__ = [
    "ContextDebugDeltaInput",
    "ContextDebugDeltaResult",
    "ContextObservationRenderInput",
    "ContextObservationRenderResult",
    "RecordContextSnapshotInput",
    "RecordRequestRenderSnapshotInput",
]
