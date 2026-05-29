from __future__ import annotations

from html import escape
from uuid import uuid4

from crxzipple.modules.context_workspace.application.models import (
    ContextActionInput,
    ContextActionResult,
    ContextNodeUpsertInput,
    ContextNodeUpsertResult,
    ContextTreeView,
    EnsureContextWorkspaceInput,
    RecordContextRenderSnapshotInput,
    RenderContextPromptInput,
    RenderContextPromptResult,
)
from crxzipple.modules.context_workspace.application.ports import (
    ContextChildrenRequest,
    ContextOwnerRegistry,
)
from crxzipple.modules.context_workspace.domain import (
    ContextAction,
    ContextActionNotAllowedError,
    ContextEstimate,
    ContextNode,
    ContextNodeNotFoundError,
    ContextNodeRepository,
    ContextNodeSeed,
    ContextNodeState,
    ContextOperationRepository,
    ContextRenderSnapshot,
    ContextRenderSnapshotNotFoundError,
    ContextRenderSnapshotRepository,
    ContextTreeOperation,
    ContextWorkspace,
    ContextWorkspaceNotFoundError,
    ContextWorkspaceRepository,
)


class ContextWorkspaceService:
    def __init__(
        self,
        *,
        workspace_repository: ContextWorkspaceRepository,
        node_repository: ContextNodeRepository,
        owner_registry: ContextOwnerRegistry | None = None,
    ) -> None:
        self._workspaces = workspace_repository
        self._nodes = node_repository
        self._owner_registry = owner_registry

    def ensure_workspace(
        self,
        data: EnsureContextWorkspaceInput,
    ) -> ContextWorkspace:
        workspace = self._workspaces.get_by_session(data.session_key)
        if workspace is None:
            workspace = ContextWorkspace.new(
                session_key=data.session_key,
                agent_id=data.agent_id,
                metadata=data.metadata,
            )
            self._workspaces.add(workspace)
        else:
            changed = False
            if workspace.agent_id != data.agent_id:
                workspace.agent_id = data.agent_id
                changed = True
            for key, value in data.metadata.items():
                if workspace.metadata.get(key) != value:
                    workspace.metadata[key] = value
                    changed = True
            if changed:
                workspace.touch_revision()
                self._workspaces.save(workspace)
        self._ensure_default_root_nodes(workspace)
        self._refresh_expanded_children(workspace)
        return workspace

    def get_by_session(self, session_key: str) -> ContextWorkspace:
        workspace = self._workspaces.get_by_session(session_key)
        if workspace is None:
            raise ContextWorkspaceNotFoundError(
                f"Context workspace for session '{session_key}' was not found.",
            )
        return workspace

    def get(self, workspace_id: str) -> ContextWorkspace:
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            raise ContextWorkspaceNotFoundError(
                f"Context workspace '{workspace_id}' was not found.",
            )
        return workspace

    def list_workspaces(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[ContextWorkspace, ...]:
        return self._workspaces.list_recent(
            limit=max(1, min(int(limit), 500)),
            offset=max(0, int(offset)),
        )

    def _ensure_default_root_nodes(self, workspace: ContextWorkspace) -> None:
        nodes = _children_from_seeds(
            workspace=workspace,
            seeds=_default_root_node_seeds(
                session_key=workspace.session_key,
                agent_id=workspace.agent_id,
                metadata=workspace.metadata,
            ),
            node_repository=self._nodes,
        )
        if nodes:
            self._nodes.save_many(nodes)

    def _refresh_expanded_children(self, workspace: ContextWorkspace) -> None:
        for node in self._nodes.list_for_workspace(workspace.id):
            if node.state.collapsed:
                continue
            self._load_owner_children(workspace, node)

    def _load_owner_children(
        self,
        workspace: ContextWorkspace,
        node: ContextNode,
    ) -> None:
        if self._owner_registry is None:
            return
        provider = self._owner_registry.get(node.owner)
        if provider is None:
            return
        seeds = provider.children(ContextChildrenRequest(workspace=workspace, node=node))
        children = _children_from_seeds(
            workspace=workspace,
            seeds=seeds,
            node_repository=self._nodes,
        )
        self._nodes.save_many(children)


class ContextTreeService:
    def __init__(
        self,
        *,
        workspace_repository: ContextWorkspaceRepository,
        node_repository: ContextNodeRepository,
        operation_repository: ContextOperationRepository,
        owner_registry: ContextOwnerRegistry | None = None,
    ) -> None:
        self._workspaces = workspace_repository
        self._nodes = node_repository
        self._operations = operation_repository
        self._owner_registry = owner_registry

    def list_tree(self, session_key: str) -> ContextTreeView:
        workspace = self._require_workspace(session_key)
        nodes = self._nodes.list_for_workspace(workspace.id)
        return ContextTreeView(
            workspace=workspace,
            nodes=nodes,
            estimate=_aggregate_estimate(nodes),
        )

    def apply_action(self, data: ContextActionInput) -> ContextActionResult:
        workspace = self._require_workspace(data.session_key)
        node = self._nodes.get(workspace_id=workspace.id, node_id=data.node_id)
        if node is None:
            raise ContextNodeNotFoundError(
                f"Context node '{data.node_id}' was not found.",
            )
        if not node.supports(data.action):
            raise ContextActionNotAllowedError(
                f"Context node '{data.node_id}' does not support action '{data.action.value}'.",
            )
        node.apply_state(_state_after_action(node.state, data.action))
        if data.action in {ContextAction.EXPAND, ContextAction.READ_SKILL}:
            self._load_owner_children(workspace, node)
        workspace.touch_revision()
        self._nodes.save(node)
        self._workspaces.save(workspace)
        operation = ContextTreeOperation(
            id=f"ctxop_{uuid4().hex}",
            workspace_id=workspace.id,
            session_key=workspace.session_key,
            run_id=data.run_id,
            node_id=node.id,
            action=data.action,
            actor=data.actor,
            status="succeeded",
            payload=data.payload,
            result={"state": node.state.to_payload()},
            tree_revision=workspace.active_revision,
        )
        self._operations.add(operation)
        return ContextActionResult(
            workspace=workspace,
            node=node,
            action=data.action,
            operation_id=operation.id,
        )

    def upsert_nodes(self, data: ContextNodeUpsertInput) -> ContextNodeUpsertResult:
        workspace = self._require_workspace(data.session_key)
        nodes = _children_from_seeds(
            workspace=workspace,
            seeds=data.nodes,
            node_repository=self._nodes,
        )
        self._nodes.save_many(nodes)
        workspace.touch_revision()
        self._workspaces.save(workspace)
        operation = ContextTreeOperation(
            id=f"ctxop_{uuid4().hex}",
            workspace_id=workspace.id,
            session_key=workspace.session_key,
            run_id=data.run_id,
            node_id=data.parent_node_id,
            action=data.action,
            actor=data.actor,
            status="succeeded",
            payload=data.payload,
            result={"node_ids": [node.id for node in nodes]},
            tree_revision=workspace.active_revision,
        )
        self._operations.add(operation)
        return ContextNodeUpsertResult(
            workspace=workspace,
            nodes=nodes,
            action=data.action,
            operation_id=operation.id,
        )

    def _require_workspace(self, session_key: str) -> ContextWorkspace:
        workspace = self._workspaces.get_by_session(session_key)
        if workspace is None:
            raise ContextWorkspaceNotFoundError(
                f"Context workspace for session '{session_key}' was not found.",
            )
        return workspace

    def _load_owner_children(
        self,
        workspace: ContextWorkspace,
        node: ContextNode,
    ) -> None:
        if self._owner_registry is None:
            return
        provider = self._owner_registry.get(node.owner)
        if provider is None:
            return
        seeds = provider.children(ContextChildrenRequest(workspace=workspace, node=node))
        children = _children_from_seeds(
            workspace=workspace,
            seeds=seeds,
            node_repository=self._nodes,
        )
        self._nodes.save_many(children)


class ContextRenderService:
    def __init__(
        self,
        *,
        workspace_repository: ContextWorkspaceRepository,
        node_repository: ContextNodeRepository,
        snapshot_repository: ContextRenderSnapshotRepository,
    ) -> None:
        self._workspaces = workspace_repository
        self._nodes = node_repository
        self._snapshots = snapshot_repository

    def render_prompt_body(
        self,
        data: RenderContextPromptInput,
    ) -> RenderContextPromptResult:
        workspace = self._require_workspace(data.session_key)
        nodes = self._nodes.list_for_workspace(workspace.id)
        visible_nodes = tuple(node for node in nodes if node.state.prompt_visible)
        estimate = _aggregate_estimate(visible_nodes)
        prompt_body = _render_context_tree(workspace, visible_nodes)
        (
            provider_attachments,
            mirrored_node_ids,
            tool_schema_mirror_available,
        ) = _render_provider_attachments(
            visible_nodes,
            base=data.provider_attachments,
        )
        return RenderContextPromptResult(
            workspace=workspace,
            prompt_body=prompt_body,
            estimate=estimate,
            included_node_ids=tuple(node.id for node in visible_nodes),
            provider_attachments=provider_attachments,
            mirrored_node_ids=mirrored_node_ids,
            tool_schema_mirror_available=tool_schema_mirror_available,
        )

    def record_render_snapshot(
        self,
        data: RecordContextRenderSnapshotInput,
    ) -> ContextRenderSnapshot:
        workspace = self._require_workspace(data.session_key)
        snapshot = ContextRenderSnapshot(
            id=data.snapshot_id,
            workspace_id=workspace.id,
            session_key=workspace.session_key,
            run_id=data.run_id,
            tree_revision=workspace.active_revision,
            prompt_body=data.prompt_body,
            provider_attachments=data.provider_attachments,
            estimate=data.estimate,
            included_node_ids=data.included_node_ids,
            mirrored_node_ids=data.mirrored_node_ids,
            metadata=data.metadata,
        )
        self._snapshots.add(snapshot)
        return snapshot

    def get_snapshot_by_run(self, run_id: str) -> ContextRenderSnapshot:
        snapshot = self._snapshots.get_by_run(run_id)
        if snapshot is None:
            raise ContextRenderSnapshotNotFoundError(
                f"Context render snapshot for run '{run_id}' was not found.",
            )
        return snapshot

    def list_recent_snapshots(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[ContextRenderSnapshot, ...]:
        return self._snapshots.list_recent(
            limit=max(1, min(int(limit), 500)),
            offset=max(0, int(offset)),
        )

    def _require_workspace(self, session_key: str) -> ContextWorkspace:
        workspace = self._workspaces.get_by_session(session_key)
        if workspace is None:
            raise ContextWorkspaceNotFoundError(
                f"Context workspace for session '{session_key}' was not found.",
            )
        return workspace


def _default_root_node_seeds(
    *,
    session_key: str,
    agent_id: str,
    metadata: dict[str, object] | None = None,
) -> tuple[ContextNodeSeed, ...]:
    common_actions = (
        ContextAction.EXPAND,
        ContextAction.COLLAPSE,
        ContextAction.PIN,
        ContextAction.UNPIN,
        ContextAction.ESTIMATE,
    )
    return (
        _agent_identity_node_seed(
            agent_id=agent_id,
            metadata=metadata,
            actions=common_actions,
        ),
        _run_flow_node_seed(metadata),
        _run_runtime_node_seed(
            metadata,
            actions=common_actions,
        ),
        ContextNodeSeed(
            node_id="session.current",
            owner="session",
            kind="session",
            title="Current Session",
            summary=f"Active context handles for session '{session_key}'.",
            state=ContextNodeState(collapsed=False, loaded=True),
            actions=common_actions + (ContextAction.FOLD_SESSION_RANGE,),
            owner_ref={"session_key": session_key},
            estimate=ContextEstimate(text_chars=96, text_tokens=24),
            display_order=20,
        ),
        ContextNodeSeed(
            node_id="tools.available",
            owner="tool",
            kind="tool_group",
            title="Available Tools",
            summary="Authorized tool handles can be expanded and selectively mirrored as provider schemas.",
            actions=common_actions,
            owner_ref={"agent_id": agent_id, "session_key": session_key},
            estimate=ContextEstimate(text_chars=120, text_tokens=30),
            display_order=30,
        ),
        ContextNodeSeed(
            node_id="skills.available",
            owner="skills",
            kind="skill_group",
            title="Available Skills",
            summary="Ready skill handles can be expanded when instructions are needed.",
            actions=common_actions + (ContextAction.READ_SKILL,),
            owner_ref={"agent_id": agent_id},
            estimate=ContextEstimate(text_chars=96, text_tokens=24),
            display_order=40,
        ),
        ContextNodeSeed(
            node_id="memory.visible",
            owner="memory",
            kind="memory_scope_group",
            title="Visible Memory",
            summary="Memory scopes visible to the current agent and session.",
            actions=common_actions + (ContextAction.RECALL_MEMORY,),
            owner_ref={"agent_id": agent_id, "session_key": session_key},
            estimate=ContextEstimate(text_chars=96, text_tokens=24),
            display_order=50,
        ),
        ContextNodeSeed(
            node_id="artifacts.session",
            owner="artifacts",
            kind="artifact_group",
            title="Session Artifacts",
            summary="Artifacts referenced by the session can be opened when needed.",
            actions=common_actions + (ContextAction.OPEN_ARTIFACT,),
            owner_ref={"session_key": session_key},
            estimate=ContextEstimate(text_chars=96, text_tokens=24),
            display_order=60,
        ),
        ContextNodeSeed(
            node_id="workspace.bootstrap",
            owner="workspace",
            kind="workspace_group",
            title="Workspace Bootstrap",
            summary="Workspace instruction and bootstrap file handles.",
            actions=common_actions,
            owner_ref={"agent_id": agent_id, "session_key": session_key},
            estimate=ContextEstimate(text_chars=96, text_tokens=24),
            display_order=70,
        ),
    )


def _agent_identity_node_seed(
    *,
    agent_id: str,
    metadata: dict[str, object] | None,
    actions: tuple[ContextAction, ...],
) -> ContextNodeSeed:
    payload = _context_block_payload(
        metadata,
        key="agent_instruction_node",
        default_summary=f"Runtime identity for agent '{agent_id}'.",
    )
    content = payload["content"]
    return ContextNodeSeed(
        node_id="agent.identity",
        owner="agent",
        kind="agent_identity",
        title="Agent Identity",
        summary=payload["summary"],
        content=content,
        state=ContextNodeState(collapsed=False, loaded=True),
        actions=actions,
        owner_ref={"agent_id": agent_id},
        estimate=_text_estimate(payload["summary"] + "\n" + content),
        display_order=10,
        metadata=payload["metadata"],
    )


def _children_from_seeds(
    *,
    workspace: ContextWorkspace,
    seeds: tuple[ContextNodeSeed, ...],
    node_repository: ContextNodeRepository,
) -> tuple[ContextNode, ...]:
    children: list[ContextNode] = []
    for seed in seeds:
        node = ContextNode.from_seed(seed, workspace_id=workspace.id)
        existing = node_repository.get(
            workspace_id=workspace.id,
            node_id=node.id,
        )
        if existing is not None:
            node.created_at = existing.created_at
            node.apply_state(existing.state)
        children.append(node)
    return tuple(children)


def _run_flow_node_seed(metadata: dict[str, object] | None) -> ContextNodeSeed:
    payload = _run_flow_payload(metadata)
    summary = payload["summary"]
    return ContextNodeSeed(
        node_id="run.flow",
        owner="orchestration",
        kind="run_flow",
        title=payload["title"],
        summary=summary,
        state=ContextNodeState(collapsed=False, loaded=True),
        actions=(ContextAction.PIN, ContextAction.UNPIN, ContextAction.ESTIMATE),
        owner_ref={"mode": payload["mode"]},
        estimate=_text_estimate(summary),
        display_order=15,
        metadata=payload["metadata"],
    )


def _run_runtime_node_seed(
    metadata: dict[str, object] | None,
    *,
    actions: tuple[ContextAction, ...],
) -> ContextNodeSeed:
    payload = _context_block_payload(
        metadata,
        key="runtime_context_node",
        default_summary="Current run runtime bindings and provider context.",
    )
    content = payload["content"]
    return ContextNodeSeed(
        node_id="run.runtime",
        owner="orchestration",
        kind="run_runtime",
        title="Run Runtime",
        summary=payload["summary"],
        content=content,
        state=ContextNodeState(collapsed=False, loaded=True),
        actions=actions,
        owner_ref=dict(payload["metadata"]),
        estimate=_text_estimate(payload["summary"] + "\n" + content),
        display_order=16,
        metadata=payload["metadata"],
    )


def _context_block_payload(
    metadata: dict[str, object] | None,
    *,
    key: str,
    default_summary: str,
) -> dict[str, object]:
    raw = (metadata or {}).get(key)
    if not isinstance(raw, dict):
        return {"summary": default_summary, "content": "", "metadata": {}}
    content = _optional_text(raw.get("content")) or ""
    summary = _optional_text(raw.get("summary")) or default_summary
    raw_metadata = raw.get("metadata")
    node_metadata = dict(raw_metadata) if isinstance(raw_metadata, dict) else {}
    if bool(raw.get("truncated")):
        node_metadata["truncated"] = True
    return {
        "summary": _truncate(summary, 1900),
        "content": content,
        "metadata": node_metadata,
    }


def _run_flow_payload(metadata: dict[str, object] | None) -> dict[str, object]:
    raw = (metadata or {}).get("run_flow_node")
    if isinstance(raw, dict):
        mode = _optional_text(raw.get("mode")) or "normal_turn"
        title = _optional_text(raw.get("title")) or _title_for_mode(mode)
        summary = (
            _truncate(_optional_text(raw.get("summary")) or _summary_for_mode(mode), 1900)
        )
        raw_metadata = raw.get("metadata")
        node_metadata = dict(raw_metadata) if isinstance(raw_metadata, dict) else {}
        node_metadata.setdefault("mode", mode)
        return {
            "mode": mode,
            "title": title,
            "summary": summary,
            "metadata": node_metadata,
        }
    mode = _optional_text((metadata or {}).get("prompt_mode")) or "normal_turn"
    return {
        "mode": mode,
        "title": _title_for_mode(mode),
        "summary": _summary_for_mode(mode),
        "metadata": {"mode": mode},
    }


def _title_for_mode(mode: str) -> str:
    return {
        "session_start": "Flow: Session Start",
        "approval_resume": "Flow: Approval Resume",
        "approval_denied": "Flow: Approval Denied",
        "recovery_resume": "Flow: Recovery Resume",
        "heartbeat": "Flow: Heartbeat",
        "memory_flush": "Flow: Memory Flush",
        "compaction": "Flow: Compaction",
    }.get(mode, "Flow: Normal Turn")


def _summary_for_mode(mode: str) -> str:
    if mode == "session_start":
        return "Start a fresh active session using only visible transcript, context tree, and memory nodes."
    if mode == "approval_resume":
        return "Resume the interrupted task after an approval update without restarting from scratch."
    if mode == "approval_denied":
        return "Continue with available tools and access after the requested approval was denied."
    if mode == "recovery_resume":
        return "Resume paused work after background results became available."
    if mode == "heartbeat":
        return "Handle a lightweight heartbeat and avoid broad exploratory work unless there is clear unfinished work."
    if mode == "memory_flush":
        return "Capture durable memory only; do not answer the user conversation in this run."
    if mode == "compaction":
        return "Compact the session into a concise factual continuation summary."
    return "Handle the latest user request using visible context tree nodes, transcript, and callable tool schemas."


def _text_estimate(text: str) -> ContextEstimate:
    normalized = text or ""
    return ContextEstimate(
        text_chars=len(normalized),
        text_tokens=max((len(normalized) + 3) // 4, 1) if normalized else 0,
    )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _truncate(value: str, limit: int) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 0)].rstrip() + "..."


def _aggregate_estimate(nodes: tuple[ContextNode, ...]) -> ContextEstimate:
    total = ContextEstimate()
    for node in nodes:
        total = total.plus(node.estimate)
    return total


def _state_after_action(
    state: ContextNodeState,
    action: ContextAction,
) -> ContextNodeState:
    if action in {ContextAction.EXPAND, ContextAction.READ_SKILL}:
        return state.expand()
    if action is ContextAction.OPEN_ARTIFACT:
        return state.with_updates(loaded=True, opened=True)
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


def _render_context_tree(
    workspace: ContextWorkspace,
    nodes: tuple[ContextNode, ...],
) -> str:
    lines = [
        "<context_instructions>",
        "  You are given a context tree.",
        "  Collapsed nodes are available handles, not full content.",
        (
            "  Use context_tree.list, context_tree.expand, "
            "context_tree.collapse, context_tree.pin, context_tree.unpin, "
            "context_tree.estimate, context_tree.read_skill, "
            "context_tree.recall_memory, context_tree.open_artifact, "
            "context_tree.enable_tool_schema, and context_tree.disable_tool_schema "
            "to inspect or adjust it."
        ),
        "</context_instructions>",
        (
            f'<context_tree session="{escape(workspace.session_key)}" '
            f'revision="{workspace.active_revision}">'
        ),
    ]
    for node in sorted(nodes, key=lambda item: (item.display_order, item.id)):
        state = "collapsed" if node.state.collapsed else "expanded"
        if node.state.opened:
            state = "opened"
        actions = " ".join(action.value for action in node.actions)
        lines.append(
            f'  <node id="{escape(node.id)}" kind="{escape(node.kind)}" '
            f'owner="{escape(node.owner)}" state="{state}" actions="{escape(actions)}">',
        )
        lines.append(f"    <title>{escape(node.title)}</title>")
        if node.summary:
            lines.append(f"    <summary>{escape(node.summary)}</summary>")
        if node.content and not node.state.collapsed:
            lines.append(f"    <content>{escape(node.content)}</content>")
        lines.append("  </node>")
    lines.append("</context_tree>")
    return "\n".join(lines)


def _render_provider_attachments(
    nodes: tuple[ContextNode, ...],
    *,
    base: dict[str, object],
) -> tuple[dict[str, object], tuple[str, ...], bool]:
    attachments = dict(base)
    tool_schemas = list(_provider_tool_schemas(attachments.get("tool_schemas")))
    artifact_candidates = list(
        _provider_artifact_candidates(attachments.get("artifact_content_candidates")),
    )
    mirrored_node_ids: list[str] = []
    tool_schema_mirror_available = False
    existing_tool_names = {
        schema.get("name")
        for schema in tool_schemas
        if isinstance(schema.get("name"), str)
    }
    for node in nodes:
        if node.owner != "tool" or node.kind != "tool_function":
            continue
        if isinstance(node.metadata.get("provider_schema"), dict):
            tool_schema_mirror_available = True
        if not node.state.schema_enabled:
            continue
        schema = node.metadata.get("provider_schema")
        if not isinstance(schema, dict):
            continue
        schema_name = schema.get("name")
        if not isinstance(schema_name, str) or not schema_name.strip():
            continue
        if schema_name in existing_tool_names:
            continue
        tool_schemas.append(dict(schema))
        existing_tool_names.add(schema_name)
        mirrored_node_ids.append(node.id)
    existing_artifact_node_ids = {
        candidate.get("node_id")
        for candidate in artifact_candidates
        if isinstance(candidate.get("node_id"), str)
    }
    for node in nodes:
        if node.owner != "artifacts":
            continue
        if node.kind not in {"artifact_image", "artifact_file"}:
            continue
        if not node.state.opened:
            continue
        artifact_id = node.owner_ref.get("artifact_id")
        if not isinstance(artifact_id, str) or not artifact_id.strip():
            continue
        if node.id in existing_artifact_node_ids:
            continue
        artifact_candidates.append(
            {
                "node_id": node.id,
                "artifact_id": artifact_id.strip(),
                "kind": node.kind,
                "mime_type": node.metadata.get("mime_type"),
                "name": node.metadata.get("name") or node.title,
                "preferred_variant": node.owner_ref.get("preferred_variant"),
            },
        )
        existing_artifact_node_ids.add(node.id)
        mirrored_node_ids.append(node.id)
    if tool_schemas:
        attachments["tool_schemas"] = tool_schemas
    if artifact_candidates:
        attachments["artifact_content_candidates"] = artifact_candidates
    return attachments, tuple(mirrored_node_ids), tool_schema_mirror_available


def _provider_tool_schemas(value: object) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list):
        return ()
    return tuple(dict(item) for item in value if isinstance(item, dict))


def _provider_artifact_candidates(value: object) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list):
        return ()
    return tuple(dict(item) for item in value if isinstance(item, dict))


__all__ = [
    "ContextRenderService",
    "ContextTreeService",
    "ContextWorkspaceService",
]
