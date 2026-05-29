from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from crxzipple.modules.artifacts.domain.entities import Artifact, ArtifactVariant
from crxzipple.modules.context_workspace.application import (
    ContextActionInput,
    ContextNodeUpsertInput,
    ContextRenderService,
    ContextTreeService,
    RenderContextPromptInput,
)
from crxzipple.modules.context_workspace.domain import (
    ContextAction,
    ContextActor,
    ContextActorKind,
    ContextEstimate,
    ContextNodeSeed,
    ContextNodeState,
    ContextNode,
)
from crxzipple.modules.memory.application import (
    MemoryActorContext,
    MemoryRecallItem,
    MemoryRecallRequest,
    MemoryRuntimeService,
    memory_citation,
)
from crxzipple.modules.tool.domain import ToolExecutionContext, ToolRunResult

CONTEXT_TREE_LIST_TOOL_ID = "context_tree.list"
CONTEXT_TREE_EXPAND_TOOL_ID = "context_tree.expand"
CONTEXT_TREE_COLLAPSE_TOOL_ID = "context_tree.collapse"
CONTEXT_TREE_PIN_TOOL_ID = "context_tree.pin"
CONTEXT_TREE_UNPIN_TOOL_ID = "context_tree.unpin"
CONTEXT_TREE_ESTIMATE_TOOL_ID = "context_tree.estimate"
CONTEXT_TREE_READ_SKILL_TOOL_ID = "context_tree.read_skill"
CONTEXT_TREE_RECALL_MEMORY_TOOL_ID = "context_tree.recall_memory"
CONTEXT_TREE_OPEN_ARTIFACT_TOOL_ID = "context_tree.open_artifact"
CONTEXT_TREE_ENABLE_TOOL_SCHEMA_TOOL_ID = "context_tree.enable_tool_schema"
CONTEXT_TREE_DISABLE_TOOL_SCHEMA_TOOL_ID = "context_tree.disable_tool_schema"

_SESSION_KEY_ATTR = "session_key"
_AGENT_ID_ATTR = "agent_id"
_RUN_ID_ATTR = "run_id"


@dataclass(frozen=True, slots=True)
class ContextTreeToolDeps:
    context_tree_service: ContextTreeService | None = field(
        default=None,
        metadata={"dependency_id": "context_tree_service"},
    )
    context_render_service: ContextRenderService | None = field(
        default=None,
        metadata={"dependency_id": "context_render_service"},
    )
    memory_runtime_service: MemoryRuntimeService | None = field(
        default=None,
        metadata={"dependency_id": "memory_runtime_service"},
    )
    artifact_service: Any | None = field(
        default=None,
        metadata={"dependency_id": "artifact_service"},
    )


def _coerce_deps(value: ContextTreeToolDeps | Any) -> ContextTreeToolDeps | None:
    if isinstance(value, ContextTreeToolDeps):
        return value
    context_tree_service = getattr(value, "context_tree_service", None)
    context_render_service = getattr(value, "context_render_service", None)
    memory_runtime_service = getattr(value, "memory_runtime_service", None)
    artifact_service = getattr(value, "artifact_service", None)
    if context_tree_service is None or context_render_service is None:
        return None
    return ContextTreeToolDeps(
        context_tree_service=context_tree_service,
        context_render_service=context_render_service,
        memory_runtime_service=memory_runtime_service,
        artifact_service=artifact_service,
    )


def context_tree_list(deps: ContextTreeToolDeps | Any):
    resolved = _coerce_deps(deps)
    if resolved is None:
        return None

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        session_key = _resolve_session_key(arguments, execution_context)
        view = resolved.context_tree_service.list_tree(session_key)
        nodes = tuple(_node_payload(node) for node in _sorted_nodes(view.nodes))
        return ToolRunResult.text(
            _render_tree_list(nodes),
            details={
                "session_key": view.workspace.session_key,
                "workspace_id": view.workspace.id,
                "revision": view.workspace.active_revision,
                "estimate": view.estimate.to_payload(),
                "nodes": nodes,
            },
            metadata={
                "tool": CONTEXT_TREE_LIST_TOOL_ID,
                "session_key": view.workspace.session_key,
                "node_count": len(nodes),
            },
        )

    return handler


def context_tree_estimate(deps: ContextTreeToolDeps | Any):
    resolved = _coerce_deps(deps)
    if resolved is None:
        return None

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        session_key = _resolve_session_key(arguments, execution_context)
        rendered = resolved.context_render_service.render_prompt_body(
            RenderContextPromptInput(session_key=session_key),
        )
        estimate = rendered.estimate.to_payload()
        return ToolRunResult.text(
            _render_estimate(estimate),
            details={
                "session_key": rendered.workspace.session_key,
                "workspace_id": rendered.workspace.id,
                "revision": rendered.workspace.active_revision,
                "estimate": estimate,
                "included_node_ids": list(rendered.included_node_ids),
                "mirrored_node_ids": list(rendered.mirrored_node_ids),
                "tool_schema_mirror_available": rendered.tool_schema_mirror_available,
                "provider_attachment_keys": sorted(rendered.provider_attachments),
            },
            metadata={
                "tool": CONTEXT_TREE_ESTIMATE_TOOL_ID,
                "session_key": rendered.workspace.session_key,
                "included_node_count": len(rendered.included_node_ids),
            },
        )

    return handler


def context_tree_expand(deps: ContextTreeToolDeps | Any):
    return _context_tree_action_tool(
        deps,
        tool_id=CONTEXT_TREE_EXPAND_TOOL_ID,
        action=ContextAction.EXPAND,
    )


def context_tree_collapse(deps: ContextTreeToolDeps | Any):
    return _context_tree_action_tool(
        deps,
        tool_id=CONTEXT_TREE_COLLAPSE_TOOL_ID,
        action=ContextAction.COLLAPSE,
    )


def context_tree_pin(deps: ContextTreeToolDeps | Any):
    return _context_tree_action_tool(
        deps,
        tool_id=CONTEXT_TREE_PIN_TOOL_ID,
        action=ContextAction.PIN,
    )


def context_tree_unpin(deps: ContextTreeToolDeps | Any):
    return _context_tree_action_tool(
        deps,
        tool_id=CONTEXT_TREE_UNPIN_TOOL_ID,
        action=ContextAction.UNPIN,
    )


def context_tree_read_skill(deps: ContextTreeToolDeps | Any):
    return _context_tree_action_tool(
        deps,
        tool_id=CONTEXT_TREE_READ_SKILL_TOOL_ID,
        action=ContextAction.READ_SKILL,
    )


def context_tree_recall_memory(deps: ContextTreeToolDeps | Any):
    resolved = _coerce_deps(deps)
    if resolved is None or resolved.memory_runtime_service is None:
        return None

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        session_key = _resolve_session_key(arguments, execution_context)
        target_node_id = str(arguments.get("node_id") or "memory.visible").strip()
        if not target_node_id:
            target_node_id = "memory.visible"
        query = _required_text(arguments.get("query"), "query")
        raw_limit = arguments.get("limit")
        try:
            limit = int(raw_limit) if raw_limit is not None else 5
        except (TypeError, ValueError) as exc:
            raise ValueError("context_tree.recall_memory limit must be an integer.") from exc
        limit = min(max(limit, 1), 10)
        _require_action_target(
            resolved.context_tree_service,
            session_key=session_key,
            node_id=target_node_id,
            action=ContextAction.RECALL_MEMORY,
        )
        recall = resolved.memory_runtime_service.recall(
            MemoryRecallRequest(
                actor=_memory_actor_from_context(execution_context),
                query=query,
                max_items=limit,
                metadata={"tool": CONTEXT_TREE_RECALL_MEMORY_TOOL_ID},
            ),
        )
        seeds = _memory_recall_node_seeds(
            parent_id=target_node_id,
            query=query,
            items=recall.items,
        )
        upsert = resolved.context_tree_service.upsert_nodes(
            ContextNodeUpsertInput(
                session_key=session_key,
                parent_node_id=target_node_id,
                nodes=seeds,
                action=ContextAction.RECALL_MEMORY,
                actor=_actor_from_context(execution_context),
                run_id=_context_str(execution_context, _RUN_ID_ATTR),
                payload={
                    "tool": CONTEXT_TREE_RECALL_MEMORY_TOOL_ID,
                    "query": query,
                    "limit": limit,
                    "searched_layers": [
                        {
                            "scope_ref": layer.scope_ref,
                            "layer_kind": layer.layer.layer_kind,
                            "access": layer.layer.access,
                        }
                        for layer in recall.searched_layers
                    ],
                },
            ),
        )
        rendered = resolved.context_render_service.render_prompt_body(
            RenderContextPromptInput(session_key=session_key),
        )
        return ToolRunResult.text(
            (
                f"Recalled {len(recall.items)} memory item(s) for '{query}' "
                f"under '{target_node_id}'."
            ),
            details={
                "session_key": upsert.workspace.session_key,
                "workspace_id": upsert.workspace.id,
                "revision": upsert.workspace.active_revision,
                "operation_id": upsert.operation_id,
                "query": query,
                "node_ids": [node.id for node in upsert.nodes],
                "included_node_ids": list(rendered.included_node_ids),
                "estimate": rendered.estimate.to_payload(),
            },
            metadata={
                "tool": CONTEXT_TREE_RECALL_MEMORY_TOOL_ID,
                "session_key": upsert.workspace.session_key,
                "query": query,
                "result_count": len(recall.items),
                "operation_id": upsert.operation_id,
            },
        )

    return handler


def context_tree_open_artifact(deps: ContextTreeToolDeps | Any):
    resolved = _coerce_deps(deps)
    if resolved is None or resolved.artifact_service is None:
        return None

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        session_key = _resolve_session_key(arguments, execution_context)
        node_id = _required_text(arguments.get("node_id"), "node_id")
        node = _require_action_target(
            resolved.context_tree_service,
            session_key=session_key,
            node_id=node_id,
            action=ContextAction.OPEN_ARTIFACT,
        )
        artifact_id = _artifact_id_from_node(node)
        variant = _artifact_variant_from_arguments(arguments, node=node)
        binary = resolved.artifact_service.resolve_variant(artifact_id, variant=variant)
        result = resolved.context_tree_service.apply_action(
            ContextActionInput(
                session_key=session_key,
                node_id=node_id,
                action=ContextAction.OPEN_ARTIFACT,
                actor=_actor_from_context(execution_context),
                run_id=_context_str(execution_context, _RUN_ID_ATTR),
                payload={
                    "tool": CONTEXT_TREE_OPEN_ARTIFACT_TOOL_ID,
                    "artifact_id": artifact_id,
                    "variant": variant.value,
                },
            ),
        )
        rendered = resolved.context_render_service.render_prompt_body(
            RenderContextPromptInput(session_key=session_key),
        )
        return ToolRunResult.text(
            (
                f"Opened artifact '{artifact_id}' variant '{variant.value}' "
                f"from context node '{node_id}'."
            ),
            details={
                "session_key": result.workspace.session_key,
                "workspace_id": result.workspace.id,
                "revision": result.workspace.active_revision,
                "operation_id": result.operation_id,
                "node": _node_payload(result.node),
                "artifact": _artifact_payload(
                    binary.artifact,
                    path=str(binary.path),
                    variant=binary.variant,
                ),
                "included_node_ids": list(rendered.included_node_ids),
                "estimate": rendered.estimate.to_payload(),
            },
            metadata={
                "tool": CONTEXT_TREE_OPEN_ARTIFACT_TOOL_ID,
                "session_key": result.workspace.session_key,
                "node_id": result.node.id,
                "artifact_id": artifact_id,
                "variant": variant.value,
                "operation_id": result.operation_id,
            },
        )

    return handler


def context_tree_enable_tool_schema(deps: ContextTreeToolDeps | Any):
    return _context_tree_action_tool(
        deps,
        tool_id=CONTEXT_TREE_ENABLE_TOOL_SCHEMA_TOOL_ID,
        action=ContextAction.ENABLE_TOOL_SCHEMA,
    )


def context_tree_disable_tool_schema(deps: ContextTreeToolDeps | Any):
    return _context_tree_action_tool(
        deps,
        tool_id=CONTEXT_TREE_DISABLE_TOOL_SCHEMA_TOOL_ID,
        action=ContextAction.DISABLE_TOOL_SCHEMA,
    )


def _context_tree_action_tool(
    deps: ContextTreeToolDeps | Any,
    *,
    tool_id: str,
    action: ContextAction,
):
    resolved = _coerce_deps(deps)
    if resolved is None:
        return None

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        session_key = _resolve_session_key(arguments, execution_context)
        node_id = _required_text(arguments.get("node_id"), "node_id")
        result = resolved.context_tree_service.apply_action(
            ContextActionInput(
                session_key=session_key,
                node_id=node_id,
                action=action,
                actor=_actor_from_context(execution_context),
                run_id=_context_str(execution_context, _RUN_ID_ATTR),
                payload={"tool": tool_id},
            ),
        )
        rendered = resolved.context_render_service.render_prompt_body(
            RenderContextPromptInput(session_key=session_key),
        )
        return ToolRunResult.text(
            (
                f"Applied context tree action '{action.value}' to '{node_id}'. "
                f"Tree revision is now {result.workspace.active_revision}."
            ),
            details={
                "session_key": result.workspace.session_key,
                "workspace_id": result.workspace.id,
                "revision": result.workspace.active_revision,
                "operation_id": result.operation_id,
                "node": _node_payload(result.node),
                "included_node_ids": list(rendered.included_node_ids),
                "mirrored_node_ids": list(rendered.mirrored_node_ids),
                "tool_schema_mirror_available": rendered.tool_schema_mirror_available,
                "estimate": rendered.estimate.to_payload(),
            },
            metadata={
                "tool": tool_id,
                "session_key": result.workspace.session_key,
                "node_id": result.node.id,
                "action": action.value,
                "operation_id": result.operation_id,
            },
        )

    return handler


def _require_action_target(
    tree_service: ContextTreeService,
    *,
    session_key: str,
    node_id: str,
    action: ContextAction,
) -> ContextNode:
    view = tree_service.list_tree(session_key)
    for node in view.nodes:
        if node.id == node_id:
            if not node.supports(action):
                raise ValueError(
                    f"Context node '{node_id}' does not support action '{action.value}'.",
                )
            return node
    raise ValueError(f"Context node '{node_id}' was not found.")


def _artifact_id_from_node(node: ContextNode) -> str:
    artifact_id = node.owner_ref.get("artifact_id")
    if not isinstance(artifact_id, str) or not artifact_id.strip():
        raise ValueError(
            f"Context node '{node.id}' does not reference an artifact.",
        )
    return artifact_id.strip()


def _artifact_variant_from_arguments(
    arguments: dict[str, Any],
    *,
    node: ContextNode,
) -> ArtifactVariant:
    raw = arguments.get("variant")
    if raw is None:
        raw = node.owner_ref.get("preferred_variant")
    if raw is None:
        raw = "llm" if node.kind == "artifact_image" else "original"
    try:
        return ArtifactVariant(str(raw).strip())
    except ValueError as exc:
        allowed = ", ".join(variant.value for variant in ArtifactVariant)
        raise ValueError(
            f"context_tree.open_artifact variant must be one of: {allowed}.",
        ) from exc


def _memory_actor_from_context(
    execution_context: ToolExecutionContext | None,
) -> MemoryActorContext:
    if execution_context is None:
        raise ValueError("context_tree.recall_memory requires execution context.")
    actor = MemoryActorContext.from_attrs(execution_context.attrs)
    if actor.agent_id is None:
        raise ValueError("context_tree.recall_memory requires agent_id.")
    return actor


def _resolve_session_key(
    arguments: dict[str, Any],
    execution_context: ToolExecutionContext | None,
) -> str:
    raw = arguments.get("session_key")
    if raw is not None and str(raw).strip():
        return str(raw).strip()
    session_key = _context_str(execution_context, _SESSION_KEY_ATTR)
    if session_key is None:
        raise ValueError("context_tree tool requires a session_key.")
    return session_key


def _actor_from_context(
    execution_context: ToolExecutionContext | None,
) -> ContextActor:
    actor_id = _context_str(execution_context, _AGENT_ID_ATTR)
    if actor_id is not None:
        return ContextActor(kind=ContextActorKind.AGENT, actor_id=actor_id)
    return ContextActor(kind=ContextActorKind.SYSTEM)


def _context_str(
    execution_context: ToolExecutionContext | None,
    key: str,
) -> str | None:
    if execution_context is None:
        return None
    return execution_context.get_str(key)


def _required_text(value: object, field_name: str) -> str:
    if value is None:
        raise ValueError(f"context_tree tool requires {field_name}.")
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"context_tree tool requires {field_name}.")
    return normalized


def _sorted_nodes(nodes: tuple[ContextNode, ...]) -> tuple[ContextNode, ...]:
    return tuple(sorted(nodes, key=lambda item: (item.display_order, item.id)))


def _node_payload(node: ContextNode) -> dict[str, object]:
    return {
        "id": node.id,
        "parent_id": node.parent_id,
        "owner": node.owner,
        "kind": node.kind,
        "title": node.title,
        "summary": node.summary,
        "state": node.state.to_payload(),
        "actions": [action.value for action in node.actions],
        "estimate": node.estimate.to_payload(),
        "display_order": node.display_order,
        "owner_ref": dict(node.owner_ref),
        "metadata": {
            key: value
            for key, value in node.metadata.items()
            if key != "provider_schema"
        },
    }


def _artifact_payload(
    artifact: Artifact,
    *,
    path: str,
    variant: ArtifactVariant,
) -> dict[str, object]:
    return {
        "id": artifact.id,
        "kind": artifact.kind.value,
        "mime_type": artifact.mime_type,
        "name": artifact.name,
        "size_bytes": artifact.size_bytes,
        "width": artifact.width,
        "height": artifact.height,
        "variant": variant.value,
        "path": path,
        "preview_url": f"/artifacts/{artifact.id}/preview",
        "original_url": f"/artifacts/{artifact.id}/original",
        "download_url": f"/artifacts/{artifact.id}/download",
    }


def _memory_recall_node_seeds(
    *,
    parent_id: str,
    query: str,
    items: tuple[MemoryRecallItem, ...],
) -> tuple[ContextNodeSeed, ...]:
    recall_id = f"{parent_id}.recall.{uuid4().hex}"
    summary = f"Memory recall for query '{query}' returned {len(items)} item(s)."
    seeds: list[ContextNodeSeed] = [
        ContextNodeSeed(
            node_id=recall_id,
            parent_id=parent_id,
            owner="memory",
            kind="memory_recall",
            title=f"Recall: {query}",
            summary=summary,
            state=ContextNodeState(collapsed=False, loaded=True),
            actions=(
                ContextAction.COLLAPSE,
                ContextAction.PIN,
                ContextAction.UNPIN,
                ContextAction.ESTIMATE,
            ),
            owner_ref={"query": query},
            estimate=_text_estimate(summary),
            display_order=1000,
            metadata={"query": query, "result_count": len(items)},
        ),
    ]
    for index, item in enumerate(items, start=1):
        text = _truncate(item.text, 1600)
        citation = (
            item.citation
            or memory_citation(item.path, item.start_line, item.end_line)
        )
        seeds.append(
            ContextNodeSeed(
                node_id=f"{recall_id}.item.{index}",
                parent_id=recall_id,
                owner="memory",
                kind="memory_recall_item",
                title=citation,
                summary=text,
                state=ContextNodeState(collapsed=False, loaded=True),
                actions=(ContextAction.PIN, ContextAction.UNPIN, ContextAction.ESTIMATE),
                owner_ref={
                    "path": item.path,
                    "citation": citation,
                    "source_scope_ref": item.source_scope_ref,
                    "source_layer_kind": item.source_layer_kind,
                },
                estimate=_text_estimate(text),
                display_order=index * 10,
                metadata={
                    "path": item.path,
                    "kind": item.kind,
                    "citation": citation,
                    "start_line": item.start_line,
                    "end_line": item.end_line,
                    "score": item.score,
                    "source_scope_ref": item.source_scope_ref,
                    "source_layer_kind": item.source_layer_kind,
                    "source_owner_kind": (
                        item.source_owner_kind.value
                        if item.source_owner_kind is not None
                        else None
                    ),
                },
            ),
        )
    return tuple(seeds)


def _text_estimate(text: str) -> ContextEstimate:
    normalized = text or ""
    return ContextEstimate(
        text_chars=len(normalized),
        text_tokens=max((len(normalized) + 3) // 4, 1) if normalized else 0,
    )


def _node_token(value: str) -> str:
    return quote(value.strip(), safe="")


def _truncate(value: str, limit: int) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 0)].rstrip() + "..."


def _render_tree_list(nodes: tuple[dict[str, object], ...]) -> str:
    if not nodes:
        return "Context tree is empty."
    lines = ["Context tree nodes:"]
    for node in nodes:
        state = node.get("state")
        state_payload = state if isinstance(state, dict) else {}
        collapsed = "collapsed" if state_payload.get("collapsed") else "expanded"
        loaded = "loaded" if state_payload.get("loaded") else "unloaded"
        parent_id = node.get("parent_id") or "root"
        lines.append(
            f"- {node['id']} ({node['kind']}, {collapsed}, {loaded}, parent: {parent_id})",
        )
    return "\n".join(lines)


def _render_estimate(estimate: dict[str, object]) -> str:
    return (
        "Context tree estimate: "
        f"{estimate.get('text_tokens', 0)} text tokens, "
        f"{estimate.get('tool_schema_tokens', 0)} tool schema tokens, "
        f"{estimate.get('provider_attachment_count', 0)} provider attachments."
    )
