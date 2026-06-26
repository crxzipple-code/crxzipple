from __future__ import annotations

from dataclasses import dataclass, field

from crxzipple.modules.context_workspace.domain import (
    ContextEstimate,
    ContextNode,
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
class ContextWorkspaceServices:
    workspaces: object
    tree: object
    observation_snapshots: object
    slice_builder: object
    control_slice_builder: object | None = None
    request_render_snapshots: object | None = None


__all__ = [
    "ContextTreeView",
    "ContextWorkspaceServices",
    "EnsureContextWorkspaceInput",
]
