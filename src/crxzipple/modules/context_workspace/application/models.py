from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from crxzipple.modules.context_workspace.domain import (
    ContextAction,
    ContextActor,
    ContextActorKind,
    ContextEstimate,
    ContextNode,
    ContextNodeSeed,
    ContextWorkspace,
)
from crxzipple.modules.context_workspace.domain.value_objects import JsonObject


@dataclass(frozen=True, slots=True)
class EnsureContextWorkspaceInput:
    session_key: str
    agent_id: str
    metadata: JsonObject = field(default_factory=dict)
    refresh_expanded_children: bool = True


@dataclass(frozen=True, slots=True)
class ContextTreeView:
    workspace: ContextWorkspace
    nodes: tuple[ContextNode, ...]
    estimate: ContextEstimate


@dataclass(frozen=True, slots=True)
class BuildContextObservationSliceInput:
    session_key: str
    run_id: str
    audience: str = "llm_request"
    provider_profile: str | None = None
    metadata: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BuildContextControlSliceInput:
    session_key: str
    run_id: str
    audience: str = "llm_request"
    provider_profile: str | None = None
    metadata: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ContextControlRef:
    node_id: str
    owner: str
    kind: str
    title: str = ""
    owner_ref: JsonObject = field(default_factory=dict)
    metadata: JsonObject = field(default_factory=dict)

    def to_payload(self) -> JsonObject:
        payload: JsonObject = {
            "node_id": self.node_id,
            "owner": self.owner,
            "kind": self.kind,
            "title": self.title,
            "owner_ref": dict(self.owner_ref),
            "metadata": dict(self.metadata),
        }
        return {
            key: value
            for key, value in payload.items()
            if value not in (None, "", {}, [])
        }


@dataclass(frozen=True, slots=True)
class ContextControlReport:
    selected_node_ids: tuple[str, ...] = ()
    omitted_node_ids: tuple[str, ...] = ()
    collapsed_refs: tuple[JsonObject, ...] = ()
    archived_refs: tuple[JsonObject, ...] = ()
    protocol_required_refs: tuple[JsonObject, ...] = ()
    metadata: JsonObject = field(default_factory=dict)

    def to_payload(self) -> JsonObject:
        payload: JsonObject = {
            "selected_node_ids": list(self.selected_node_ids),
            "omitted_node_ids": list(self.omitted_node_ids),
            "selected_count": len(self.selected_node_ids),
            "omitted_count": len(self.omitted_node_ids),
            "collapsed_refs": [dict(item) for item in self.collapsed_refs],
            "archived_refs": [dict(item) for item in self.archived_refs],
            "protocol_required_refs": [
                dict(item) for item in self.protocol_required_refs
            ],
            "metadata": dict(self.metadata),
        }
        return {
            key: value
            for key, value in payload.items()
            if value not in (None, "", {}, [])
        }


@dataclass(frozen=True, slots=True)
class ContextControlSlice:
    slice_id: str
    session_key: str
    run_id: str
    audience: str
    tree_revision: int
    selected_refs: tuple[ContextControlRef, ...] = ()
    active_tools: tuple[ContextSliceToolRef, ...] = ()
    report: ContextControlReport = field(default_factory=ContextControlReport)
    metadata: JsonObject = field(default_factory=dict)

    def to_payload(self) -> JsonObject:
        payload: JsonObject = {
            "slice_id": self.slice_id,
            "session_key": self.session_key,
            "run_id": self.run_id,
            "audience": self.audience,
            "tree_revision": self.tree_revision,
            "selected_refs": [item.to_payload() for item in self.selected_refs],
            "active_tools": [tool.to_payload() for tool in self.active_tools],
            "report": self.report.to_payload(),
            "metadata": dict(self.metadata),
        }
        return {
            key: value
            for key, value in payload.items()
            if value not in (None, "", {}, [])
        }


@dataclass(frozen=True, slots=True)
class ContextSliceItem:
    item_id: str
    section: str
    owner: str
    kind: str
    title: str
    summary: str = ""
    text: str = ""
    content: object | None = None
    owner_ref: JsonObject = field(default_factory=dict)
    node_id: str | None = None
    estimate: ContextEstimate = field(default_factory=ContextEstimate)
    metadata: JsonObject = field(default_factory=dict)

    def to_payload(self) -> JsonObject:
        payload: JsonObject = {
            "item_id": self.item_id,
            "section": self.section,
            "owner": self.owner,
            "kind": self.kind,
            "title": self.title,
            "summary": self.summary,
            "text": self.text,
            "content": self.content,
            "owner_ref": dict(self.owner_ref),
            "estimate": self.estimate.to_payload(),
            "metadata": dict(self.metadata),
        }
        if self.node_id is not None:
            payload["node_id"] = self.node_id
        return {
            key: value
            for key, value in payload.items()
            if value not in (None, "", {}, [])
        }


@dataclass(frozen=True, slots=True)
class ContextSliceToolRef:
    tool_ref_id: str
    source_id: str
    function_name: str
    schema: JsonObject = field(default_factory=dict)
    owner_ref: JsonObject = field(default_factory=dict)
    node_id: str | None = None
    metadata: JsonObject = field(default_factory=dict)

    def to_payload(self) -> JsonObject:
        payload: JsonObject = {
            "tool_ref_id": self.tool_ref_id,
            "source_id": self.source_id,
            "function_name": self.function_name,
            "schema": dict(self.schema),
            "owner_ref": dict(self.owner_ref),
            "metadata": dict(self.metadata),
        }
        if self.node_id is not None:
            payload["node_id"] = self.node_id
        return {
            key: value
            for key, value in payload.items()
            if value not in (None, "", {}, [])
        }


@dataclass(frozen=True, slots=True)
class ContextSliceReport:
    included_node_ids: tuple[str, ...] = ()
    omitted_node_ids: tuple[str, ...] = ()
    archived_refs: tuple[JsonObject, ...] = ()
    collapsed_refs: tuple[JsonObject, ...] = ()
    redacted_refs: tuple[JsonObject, ...] = ()
    unresolved_refs: tuple[JsonObject, ...] = ()
    budget: JsonObject = field(default_factory=dict)
    loss: JsonObject = field(default_factory=dict)
    metadata: JsonObject = field(default_factory=dict)

    def to_payload(self) -> JsonObject:
        payload: JsonObject = {
            "included_node_ids": list(self.included_node_ids),
            "omitted_node_ids": list(self.omitted_node_ids),
            "included_count": len(self.included_node_ids),
            "omitted_count": len(self.omitted_node_ids),
            "archived_refs": [dict(item) for item in self.archived_refs],
            "collapsed_refs": [dict(item) for item in self.collapsed_refs],
            "redacted_refs": [dict(item) for item in self.redacted_refs],
            "unresolved_refs": [dict(item) for item in self.unresolved_refs],
            "budget": dict(self.budget),
            "loss": dict(self.loss),
            "metadata": dict(self.metadata),
        }
        return {
            key: value
            for key, value in payload.items()
            if value not in (None, "", {}, [])
        }


@dataclass(frozen=True, slots=True)
class ContextSlice:
    slice_id: str
    session_key: str
    run_id: str
    audience: str
    tree_revision: int
    items: tuple[ContextSliceItem, ...] = ()
    active_tools: tuple[ContextSliceToolRef, ...] = ()
    report: ContextSliceReport = field(default_factory=ContextSliceReport)
    provider_attachments: JsonObject = field(default_factory=dict)
    metadata: JsonObject = field(default_factory=dict)

    def to_payload(self) -> JsonObject:
        payload: JsonObject = {
            "slice_id": self.slice_id,
            "session_key": self.session_key,
            "run_id": self.run_id,
            "audience": self.audience,
            "tree_revision": self.tree_revision,
            "items": [item.to_payload() for item in self.items],
            "active_tools": [tool.to_payload() for tool in self.active_tools],
            "report": self.report.to_payload(),
            "provider_attachments": dict(self.provider_attachments),
            "metadata": dict(self.metadata),
        }
        return {
            key: value
            for key, value in payload.items()
            if value not in (None, "", {}, [])
        }


@dataclass(frozen=True, slots=True)
class ContextActionInput:
    session_key: str
    node_id: str
    action: ContextAction
    actor: ContextActor = field(
        default_factory=lambda: ContextActor(kind=ContextActorKind.SYSTEM),
    )
    run_id: str | None = None
    payload: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ContextActionResult:
    workspace: ContextWorkspace
    node: ContextNode
    action: ContextAction
    operation_id: str


@dataclass(frozen=True, slots=True)
class ContextNodeUpsertInput:
    session_key: str
    nodes: tuple[ContextNodeSeed, ...]
    action: ContextAction
    actor: ContextActor = field(
        default_factory=lambda: ContextActor(kind=ContextActorKind.SYSTEM),
    )
    parent_node_id: str | None = None
    run_id: str | None = None
    payload: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ContextNodeUpsertResult:
    workspace: ContextWorkspace
    nodes: tuple[ContextNode, ...]
    action: ContextAction
    operation_id: str


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


@dataclass(frozen=True, slots=True)
class ContextWorkspaceServices:
    workspaces: object
    tree: object
    observation_snapshots: object
    slice_builder: object
    control_slice_builder: object | None = None
    request_render_snapshots: object | None = None


__all__ = [
    "BuildContextControlSliceInput",
    "BuildContextObservationSliceInput",
    "ContextActionInput",
    "ContextActionResult",
    "ContextControlRef",
    "ContextControlReport",
    "ContextControlSlice",
    "ContextDebugDeltaInput",
    "ContextDebugDeltaResult",
    "ContextNodeUpsertInput",
    "ContextNodeUpsertResult",
    "ContextObservationRenderInput",
    "ContextObservationRenderResult",
    "ContextSlice",
    "ContextSliceItem",
    "ContextSliceReport",
    "ContextSliceToolRef",
    "ContextTreeView",
    "ContextWorkspaceServices",
    "EnsureContextWorkspaceInput",
    "RecordContextSnapshotInput",
    "RecordRequestRenderSnapshotInput",
]
