from __future__ import annotations

from crxzipple.modules.context_workspace.application import root_nodes
from crxzipple.modules.context_workspace.application.models import ContextActionInput
from crxzipple.modules.context_workspace.application.ports import (
    ContextChildrenRequest,
    ContextOwnerRegistry,
)
from crxzipple.modules.context_workspace.domain import (
    ContextAction,
    ContextNode,
    ContextNodeRepository,
    ContextNodeSeed,
    ContextNodeState,
    ContextWorkspace,
)


_SCHEMA_ENABLED_SOURCE_KEY = "schema_enabled_source"
_SCHEMA_ENABLED_SOURCE_ACTION = "context_tree_action"
_OWNER_CHILD_LOADING_ACTIONS = {
    ContextAction.EXPAND,
}


def ensure_default_root_nodes(
    *,
    workspace: ContextWorkspace,
    node_repository: ContextNodeRepository,
) -> None:
    nodes = children_from_seeds(
        workspace=workspace,
        seeds=root_nodes.default_root_node_seeds(
            session_key=workspace.session_key,
            agent_id=workspace.agent_id,
            metadata=workspace.metadata,
        ),
        node_repository=node_repository,
        preserve_existing_dynamic_roots=True,
    )
    if nodes:
        node_repository.save_many(nodes)


def refresh_owner_children(
    *,
    workspace: ContextWorkspace,
    node_repository: ContextNodeRepository,
    owner_registry: ContextOwnerRegistry | None,
    preload_only: bool = False,
) -> None:
    nodes = node_repository.list_for_workspace(workspace.id)
    for node in nodes:
        if node.state.collapsed and not _preloads_children(node):
            continue
        if not _can_load_owner_children(node):
            continue
        load_owner_children(
            workspace=workspace,
            node=node,
            node_repository=node_repository,
            owner_registry=owner_registry,
            workspace_nodes=nodes,
            recursive=True,
            preload_only=preload_only,
        )
    prune_orphan_nodes(
        workspace=workspace,
        node_repository=node_repository,
    )


def load_owner_children(
    *,
    workspace: ContextWorkspace,
    node: ContextNode,
    node_repository: ContextNodeRepository,
    owner_registry: ContextOwnerRegistry | None,
    workspace_nodes: tuple[ContextNode, ...] | None = None,
    recursive: bool = False,
    preload_only: bool = False,
) -> None:
    latest_node = node_repository.get(workspace_id=workspace.id, node_id=node.id)
    if latest_node is None:
        return
    node = latest_node
    if not _can_load_owner_children(node):
        return
    if owner_registry is None:
        return
    provider = owner_registry.get(node.owner)
    if provider is None:
        return
    seeds = provider.children(ContextChildrenRequest(workspace=workspace, node=node))
    keep_node_ids = tuple(seed.node_id for seed in seeds)
    nodes_for_stale_check = (
        workspace_nodes
        if workspace_nodes is not None
        else node_repository.list_for_workspace(workspace.id)
    )
    stale_child_ids = tuple(
        child.id
        for child in nodes_for_stale_check
        if child.parent_id == node.id and child.id not in keep_node_ids
    )
    if stale_child_ids:
        node_repository.delete_subtrees(
            workspace_id=workspace.id,
            root_node_ids=stale_child_ids,
        )
    children = children_from_seeds(
        workspace=workspace,
        seeds=seeds,
        node_repository=node_repository,
    )
    node_repository.save_many(children)
    if not recursive:
        return
    for child in children:
        if child.state.collapsed and not _preloads_children(child):
            continue
        if preload_only and not _preloads_children(child):
            continue
        load_owner_children(
            workspace=workspace,
            node=child,
            node_repository=node_repository,
            owner_registry=owner_registry,
            recursive=True,
            preload_only=preload_only,
        )


def prune_orphan_nodes(
    *,
    workspace: ContextWorkspace,
    node_repository: ContextNodeRepository,
) -> None:
    nodes = node_repository.list_for_workspace(workspace.id)
    node_ids = {node.id for node in nodes}
    orphan_ids = tuple(
        node.id
        for node in nodes
        if node.parent_id is not None and node.parent_id not in node_ids
    )
    if orphan_ids:
        node_repository.delete_subtrees(
            workspace_id=workspace.id,
            root_node_ids=orphan_ids,
        )


def children_from_seeds(
    *,
    workspace: ContextWorkspace,
    seeds: tuple[ContextNodeSeed, ...],
    node_repository: ContextNodeRepository,
    preserve_existing_state: bool = True,
    preserve_existing_dynamic_roots: bool = False,
) -> tuple[ContextNode, ...]:
    children: list[ContextNode] = []
    for seed in seeds:
        node = ContextNode.from_seed(
            _seed_with_default_parent(seed),
            workspace_id=workspace.id,
        )
        existing = node_repository.get(
            workspace_id=workspace.id,
            node_id=node.id,
        )
        if existing is not None:
            node.created_at = existing.created_at
            if preserve_existing_state:
                node.apply_state(_state_for_existing_seed(node, existing))
                _preserve_existing_control_metadata(node, existing)
            if preserve_existing_dynamic_roots:
                _preserve_existing_dynamic_root_node(node, existing)
        children.append(node)
    return tuple(children)


def state_after_action(
    state: ContextNodeState,
    action: ContextAction,
) -> ContextNodeState:
    if action is ContextAction.EXPAND:
        return state.expand()
    if action is ContextAction.COLLAPSE:
        return state.collapse()
    if action is ContextAction.PIN:
        return state.with_updates(pinned=True)
    if action is ContextAction.UNPIN:
        return state.with_updates(pinned=False)
    if action is ContextAction.ENABLE_TOOL_SCHEMA:
        return state.with_updates(schema_enabled=True)
    if action is ContextAction.DISABLE_TOOL_SCHEMA:
        return state.with_updates(schema_enabled=False)
    return state.with_updates(loaded=True)


def record_schema_enabled_action(
    node: ContextNode,
    data: ContextActionInput,
) -> None:
    if data.action not in {
        ContextAction.ENABLE_TOOL_SCHEMA,
        ContextAction.DISABLE_TOOL_SCHEMA,
    }:
        return
    node.metadata[_SCHEMA_ENABLED_SOURCE_KEY] = _SCHEMA_ENABLED_SOURCE_ACTION
    node.metadata["schema_enabled_action"] = data.action.value
    if data.run_id is not None:
        node.metadata["schema_enabled_run_id"] = data.run_id


def _preloads_children(node: ContextNode) -> bool:
    if node.owner == "tool" and node.id == "tools.available":
        return True
    if node.owner == "workspace" and node.id == "workspace.resources":
        return True
    if node.owner == "session" and node.id in {
        "session.current",
        "session.instance.active",
        "session.segments.active",
        "session.segment.active",
    }:
        return True
    return False


def _can_load_owner_children(node: ContextNode) -> bool:
    return _preloads_children(node) or any(
        action in _OWNER_CHILD_LOADING_ACTIONS for action in node.actions
    )


def _seed_with_default_parent(seed: ContextNodeSeed) -> ContextNodeSeed:
    parent_id = seed.parent_id
    if parent_id is None:
        parent_id = root_nodes.default_parent_id_for_node_id(seed.node_id)
    if parent_id == seed.parent_id:
        return seed
    return ContextNodeSeed(
        node_id=seed.node_id,
        parent_id=parent_id,
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
    )


def _state_for_existing_seed(
    node: ContextNode,
    existing: ContextNode,
) -> ContextNodeState:
    if node.id in {"context.priority", "context.tree_usage", "session.items.current"}:
        if node.revision != existing.revision:
            return node.state.with_updates(pinned=existing.state.pinned)
        return existing.state
    if node.owner == "session" and node.kind == "tool_interaction":
        if node.revision != existing.revision:
            return node.state.with_updates(
                pinned=existing.state.pinned,
                opened=existing.state.opened,
            )
        if _tool_interaction_owner_state_changed(node, existing):
            return node.state.with_updates(pinned=existing.state.pinned)
        return existing.state
    if node.owner == "tool" and node.kind in {
        "tool_bundle",
        "tool_bundle_group",
        "tool_function",
        "tool_cli_source",
    }:
        if node.kind == "tool_function" and _is_internal_context_tool_function(node):
            return node.state.with_updates(pinned=existing.state.pinned)
        if node.kind == "tool_function":
            if _schema_enabled_was_set_by_action(existing):
                if node.revision != existing.revision:
                    return node.state.with_updates(
                        pinned=existing.state.pinned,
                        schema_enabled=existing.state.schema_enabled,
                    )
                return existing.state
            if existing.state.schema_enabled != node.state.schema_enabled:
                return node.state.with_updates(pinned=existing.state.pinned)
        if node.revision != existing.revision:
            return node.state.with_updates(pinned=existing.state.pinned)
        return existing.state
    if node.id == "tools.available" or node.id.endswith(".context_tree"):
        return node.state.with_updates(pinned=existing.state.pinned)
    return existing.state


def _is_internal_context_tool_function(node: ContextNode) -> bool:
    tool_id = _metadata_text(node.owner_ref.get("tool_id")) or _metadata_text(
        node.metadata.get("tool_id"),
    )
    if tool_id == "capability.search":
        return False
    if tool_id is not None and tool_id.startswith("context_tree."):
        return True
    source_id = _metadata_text(node.owner_ref.get("source_id")) or _metadata_text(
        node.metadata.get("source_id"),
    )
    return bool(source_id and source_id.endswith(".context_tree"))


def _preserve_existing_control_metadata(
    node: ContextNode,
    existing: ContextNode,
) -> None:
    for key in (
        _SCHEMA_ENABLED_SOURCE_KEY,
        "schema_enabled_action",
        "schema_enabled_run_id",
    ):
        if key in existing.metadata:
            node.metadata[key] = existing.metadata[key]


def _schema_enabled_was_set_by_action(node: ContextNode) -> bool:
    return node.metadata.get(_SCHEMA_ENABLED_SOURCE_KEY) == _SCHEMA_ENABLED_SOURCE_ACTION


def _preserve_existing_dynamic_root_node(
    node: ContextNode,
    existing: ContextNode,
) -> None:
    if node.id != "work.plan":
        return
    node.summary = existing.summary
    node.content = existing.content
    node.owner_ref = dict(existing.owner_ref)
    node.estimate = existing.estimate
    node.revision = existing.revision
    node.freshness = existing.freshness
    node.metadata = dict(existing.metadata)


def _tool_interaction_owner_state_changed(
    node: ContextNode,
    existing: ContextNode,
) -> bool:
    for key in (
        "frontier",
        "consumed",
        "collapsed_by_default",
        "opened_by_default",
    ):
        if _metadata_bool(node.metadata.get(key)) != _metadata_bool(
            existing.metadata.get(key),
        ):
            return True
    for key in ("lifecycle_status", "content_digest"):
        if str(node.metadata.get(key) or "") != str(existing.metadata.get(key) or ""):
            return True
    return False


def _metadata_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _metadata_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


__all__ = [
    "children_from_seeds",
    "ensure_default_root_nodes",
    "load_owner_children",
    "prune_orphan_nodes",
    "record_schema_enabled_action",
    "refresh_owner_children",
    "state_after_action",
]
