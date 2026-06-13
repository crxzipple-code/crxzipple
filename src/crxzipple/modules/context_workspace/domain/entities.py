from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

from crxzipple.modules.context_workspace.domain.exceptions import (
    ContextWorkspaceValidationError,
)
from crxzipple.modules.context_workspace.domain.value_objects import (
    ContextAction,
    ContextActor,
    ContextEstimate,
    ContextNodeSeed,
    ContextNodeState,
    JsonObject,
    normalize_timestamp,
    utcnow,
)
from crxzipple.shared.domain import AggregateRoot, Entity


@dataclass(kw_only=True)
class ContextWorkspace(AggregateRoot[str]):
    session_key: str
    agent_id: str
    status: str = "active"
    active_revision: int = 1
    metadata: JsonObject = field(default_factory=dict)
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        _require_text(self.id, "workspace id")
        self.session_key = _require_text(self.session_key, "session_key")
        self.agent_id = _require_text(self.agent_id, "agent_id")
        self.status = _require_text(self.status, "status")
        self.active_revision = max(int(self.active_revision), 1)
        self.metadata = dict(self.metadata)
        self.created_at = normalize_timestamp(self.created_at)
        self.updated_at = normalize_timestamp(self.updated_at)

    @classmethod
    def new(
        cls,
        *,
        session_key: str,
        agent_id: str,
        metadata: JsonObject | None = None,
    ) -> "ContextWorkspace":
        return cls(
            id=f"ctx_{uuid4().hex}",
            session_key=session_key,
            agent_id=agent_id,
            metadata=dict(metadata or {}),
        )

    def touch_revision(self, *, happened_at: datetime | None = None) -> int:
        self.active_revision += 1
        self.updated_at = normalize_timestamp(happened_at)
        return self.active_revision


@dataclass(kw_only=True)
class ContextNode(Entity[str]):
    workspace_id: str
    owner: str
    kind: str
    title: str
    summary: str = ""
    content: str = ""
    parent_id: str | None = None
    state: ContextNodeState = field(default_factory=ContextNodeState)
    actions: tuple[ContextAction, ...] = ()
    owner_ref: JsonObject = field(default_factory=dict)
    estimate: ContextEstimate = field(default_factory=ContextEstimate)
    revision: str | None = None
    freshness: str = "live"
    display_order: int = 0
    metadata: JsonObject = field(default_factory=dict)
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        _require_text(self.id, "node id")
        self.workspace_id = _require_text(self.workspace_id, "workspace_id")
        self.owner = _require_text(self.owner, "owner")
        self.kind = _require_text(self.kind, "kind")
        self.title = _require_text(self.title, "title")
        if self.parent_id is not None:
            self.parent_id = _require_text(self.parent_id, "parent_id")
        self.summary = str(self.summary or "")
        self.content = str(self.content or "")
        self.actions = tuple(ContextAction(action) for action in self.actions)
        self.owner_ref = dict(self.owner_ref)
        self.metadata = dict(self.metadata)
        self.created_at = normalize_timestamp(self.created_at)
        self.updated_at = normalize_timestamp(self.updated_at)

    @classmethod
    def from_seed(
        cls,
        seed: ContextNodeSeed,
        *,
        workspace_id: str,
        created_at: datetime | None = None,
    ) -> "ContextNode":
        now = normalize_timestamp(created_at)
        return cls(
            id=seed.node_id,
            workspace_id=workspace_id,
            parent_id=seed.parent_id,
            owner=seed.owner,
            kind=seed.kind,
            title=seed.title,
            summary=seed.summary,
            content=seed.content,
            state=seed.state,
            actions=seed.actions,
            owner_ref=dict(seed.owner_ref),
            estimate=seed.estimate,
            revision=seed.revision,
            freshness=seed.freshness,
            display_order=seed.display_order,
            metadata=dict(seed.metadata),
            created_at=now,
            updated_at=now,
        )

    def supports(self, action: ContextAction) -> bool:
        return action in self.actions

    def apply_state(
        self,
        state: ContextNodeState,
        *,
        happened_at: datetime | None = None,
    ) -> None:
        self.state = state
        self.updated_at = normalize_timestamp(happened_at)


@dataclass(kw_only=True)
class ContextTreeOperation(Entity[str]):
    workspace_id: str
    session_key: str
    action: ContextAction
    actor: ContextActor
    status: str
    node_id: str | None = None
    run_id: str | None = None
    reason: str | None = None
    payload: JsonObject = field(default_factory=dict)
    result: JsonObject | None = None
    tree_revision: int | None = None
    created_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        _require_text(self.id, "operation id")
        self.workspace_id = _require_text(self.workspace_id, "workspace_id")
        self.session_key = _require_text(self.session_key, "session_key")
        self.action = ContextAction(self.action)
        self.status = _require_text(self.status, "status")
        if self.node_id is not None:
            self.node_id = _require_text(self.node_id, "node_id")
        if self.run_id is not None:
            self.run_id = _require_text(self.run_id, "run_id")
        self.payload = dict(self.payload)
        self.result = dict(self.result) if self.result is not None else None
        self.created_at = normalize_timestamp(self.created_at)


@dataclass(kw_only=True)
class ContextRenderSnapshot(AggregateRoot[str]):
    workspace_id: str
    session_key: str
    run_id: str
    tree_revision: int
    prompt_body: str
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
    created_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        _require_text(self.id, "snapshot id")
        self.workspace_id = _require_text(self.workspace_id, "workspace_id")
        self.session_key = _require_text(self.session_key, "session_key")
        self.run_id = _require_text(self.run_id, "run_id")
        if int(self.tree_revision) <= 0:
            raise ContextWorkspaceValidationError("tree_revision must be positive.")
        self.tree_revision = int(self.tree_revision)
        self.provider_attachments = dict(self.provider_attachments)
        self.included_node_ids = tuple(self.included_node_ids)
        self.mirrored_node_ids = tuple(self.mirrored_node_ids)
        self.included_refs = _normalize_ref_tuple(self.included_refs)
        self.collapsed_refs = _normalize_ref_tuple(self.collapsed_refs)
        self.protocol_required_refs = _normalize_ref_tuple(
            self.protocol_required_refs,
        )
        self.metadata = dict(self.metadata)
        if self.parent_snapshot_id is not None:
            self.parent_snapshot_id = _require_text(
                self.parent_snapshot_id,
                "parent_snapshot_id",
            )
        if self.parent_tree_revision is not None:
            if int(self.parent_tree_revision) <= 0:
                raise ContextWorkspaceValidationError(
                    "parent_tree_revision must be positive.",
                )
            self.parent_tree_revision = int(self.parent_tree_revision)
        self.created_at = normalize_timestamp(self.created_at)


def _require_text(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ContextWorkspaceValidationError(f"{label} cannot be blank.")
    return normalized


def _normalize_ref_tuple(refs: tuple[JsonObject, ...]) -> tuple[JsonObject, ...]:
    return tuple(dict(ref) for ref in refs if isinstance(ref, dict))


__all__ = [
    "ContextNode",
    "ContextRenderSnapshot",
    "ContextTreeOperation",
    "ContextWorkspace",
]
