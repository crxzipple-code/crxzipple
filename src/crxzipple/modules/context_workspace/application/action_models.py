from __future__ import annotations

from dataclasses import dataclass, field

from crxzipple.modules.context_workspace.domain import (
    ContextAction,
    ContextActor,
    ContextActorKind,
    ContextNode,
    ContextNodeSeed,
    ContextWorkspace,
)
from crxzipple.modules.context_workspace.domain.value_objects import JsonObject


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


__all__ = [
    "ContextActionInput",
    "ContextActionResult",
    "ContextNodeUpsertInput",
    "ContextNodeUpsertResult",
]
