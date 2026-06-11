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


@dataclass(frozen=True, slots=True)
class ContextTreeView:
    workspace: ContextWorkspace
    nodes: tuple[ContextNode, ...]
    estimate: ContextEstimate


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
class RenderContextPromptInput:
    session_key: str
    run_id: str | None = None
    provider_attachments: JsonObject = field(default_factory=dict)
    metadata: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RenderContextPromptResult:
    workspace: ContextWorkspace
    prompt_body: str
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
class RecordContextRenderSnapshotInput:
    session_key: str
    run_id: str
    prompt_body: str
    provider_attachments: JsonObject = field(default_factory=dict)
    estimate: ContextEstimate = field(default_factory=ContextEstimate)
    included_node_ids: tuple[str, ...] = ()
    mirrored_node_ids: tuple[str, ...] = ()
    metadata: JsonObject = field(default_factory=dict)
    snapshot_id: str = field(default_factory=lambda: f"ctxsnap_{uuid4().hex}")


@dataclass(frozen=True, slots=True)
class ContextWorkspaceServices:
    workspaces: object
    tree: object
    render: object


__all__ = [
    "ContextActionInput",
    "ContextActionResult",
    "ContextNodeUpsertInput",
    "ContextNodeUpsertResult",
    "ContextTreeView",
    "ContextWorkspaceServices",
    "EnsureContextWorkspaceInput",
    "RecordContextRenderSnapshotInput",
    "RenderContextPromptInput",
    "RenderContextPromptResult",
]
