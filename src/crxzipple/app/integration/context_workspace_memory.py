"""Memory context tree adapter."""

from __future__ import annotations

from typing import Protocol
from urllib.parse import quote

from crxzipple.modules.context_workspace.application import ContextChildrenRequest
from crxzipple.modules.context_workspace.domain import (
    ContextAction,
    ContextEstimate,
    ContextNodeSeed,
    ContextNodeState,
)
from crxzipple.modules.memory.application import (
    MemoryActorContext,
    MemoryAccessPlan,
)


class MemoryContextService(Protocol):
    def resolve_access_plan(self, actor: MemoryActorContext) -> MemoryAccessPlan:
        ...


class MemoryContextNodeProvider:
    owner = "memory"

    def __init__(self, memory_runtime_service: MemoryContextService) -> None:
        self._memory_runtime_service = memory_runtime_service

    def children(
        self,
        request: ContextChildrenRequest,
    ) -> tuple[ContextNodeSeed, ...]:
        if request.node.id != "memory.visible":
            return ()
        try:
            plan = self._memory_runtime_service.resolve_access_plan(
                MemoryActorContext(
                    agent_id=request.workspace.agent_id,
                    session_key=request.workspace.session_key,
                    workspace_dir=_optional_text(
                        request.workspace.metadata.get("workspace_dir"),
                    ),
                ),
            )
        except Exception:
            return ()
        return tuple(
            _memory_scope_node_seed(
                layer,
                parent_id=request.node.id,
                display_order=index * 10,
            )
            for index, layer in enumerate(plan.readable_layers, start=1)
        )


_MEMORY_SCOPE_ACTIONS = (
    ContextAction.EXPAND,
    ContextAction.COLLAPSE,
    ContextAction.PIN,
    ContextAction.UNPIN,
    ContextAction.RECALL_MEMORY,
    ContextAction.ESTIMATE,
)


def _memory_scope_node_seed(
    layer,
    *,
    parent_id: str,
    display_order: int,
) -> ContextNodeSeed:
    layer_kind = str(layer.layer.layer_kind)
    access = str(layer.layer.access)
    owner_kind = str(getattr(layer.layer.owner_kind, "value", layer.layer.owner_kind))
    writable = access == "read_write"
    title = f"{layer.scope_ref} {layer_kind}"
    summary = (
        f"Memory layer '{layer_kind}' for scope '{layer.scope_ref}' "
        f"({owner_kind}, {access})."
    )
    governance = {
        "governance_scope": layer_kind,
        "scope_ref": layer.scope_ref,
        "layer_kind": layer_kind,
        "owner_kind": owner_kind,
        "access": access,
        "readable": True,
        "writable": writable,
        "default_write": layer.layer.default_write,
        "space_id": layer.context.space_id,
        "engine_id": layer.engine_id,
    }
    return ContextNodeSeed(
        node_id=(
            f"memory.scope.{_node_token(layer.scope_ref)}."
            f"{_node_token(layer_kind)}"
        ),
        parent_id=parent_id,
        owner="memory",
        kind="memory_scope",
        title=title,
        summary=summary,
        state=ContextNodeState(loaded=True),
        actions=_MEMORY_SCOPE_ACTIONS,
        owner_ref=governance,
        estimate=ContextEstimate(
            text_chars=len(summary),
            text_tokens=max((len(summary) + 3) // 4, 1),
        ),
        display_order=display_order,
        metadata=governance,
    )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _node_token(value: str) -> str:
    return quote(value.strip(), safe="")


__all__ = ["MemoryContextNodeProvider"]
